"""Vues API M5 — Stocks & Traçabilité matière (RF-ERP-40…43)."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .models import (
    ArticleStock,
    CertificatMatiere,
    Depot,
    Inventaire,
    InventaireLigne,
    LotMatiere,
    MouvementStock,
    ParametreStock,
    PlanInventaireTournant,
    StockQuant,
    ValorisationMensuelle,
)
from .serializers import (
    ArticleStockSerializer,
    CertificatMatiereSerializer,
    DepotSerializer,
    InventaireLigneSerializer,
    InventaireSerializer,
    LotMatiereSerializer,
    MouvementStockSerializer,
    ParametreStockSerializer,
    PlanInventaireTournantSerializer,
    StockQuantSerializer,
    TraceabiliteEntrySerializer,
    ValorisationEntrySerializer,
    ValorisationMensuelleSerializer,
)
from .cloture import figer_valorisation_mensuelle, generer_inventaire_tournant
from .services import (
    PARAMETRES_STOCK_DEFAUT,
    TYPE_GED_CERTIFICAT,
    TYPE_GED_PIECE_STOCK,
    CanManageStocks,
    CanQualiteStock,
    alertes_stock,
    apply_move,
    archiver_piece_ged,
    audit_valorisation,
    can_see_amount,
    controler_depot,
    bon_de_sortie_pdf,
    get_param_stock,
    cloturer_inventaire,
    traceabilite,
    valuation,
)


class DepotViewSet(viewsets.ModelViewSet):
    queryset = Depot.objects.select_related("responsable").all()
    serializer_class = DepotSerializer
    search_fields = ("code", "label", "site",)
    permission_classes = [CanManageStocks]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("active") == "1":
            qs = qs.filter(is_active=True)
        return qs


MAX_PIECE = 15 * 1024 * 1024


def _as_bool(raw, field):
    """Booléen tolérant (JSON ou multipart « True » / « false ») ; 400 sur une valeur inconnue."""
    if isinstance(raw, bool):
        return raw
    valeur = str(raw).strip().lower()
    if valeur in ("1", "true", "vrai", "oui", "yes", "on"):
        return True
    if valeur in ("0", "false", "faux", "non", "no", "off"):
        return False
    raise ValidationError({field: "Booléen attendu."})


def _fichier(request):
    fichier = request.FILES.get("fichier")
    if fichier is None:
        raise ValidationError({"fichier": "Fichier requis (PDF ou image)."})
    if fichier.size > MAX_PIECE:
        raise ValidationError({"fichier": "Fichier trop volumineux (15 Mo maximum)."})
    return fichier


class LotMatiereViewSet(viewsets.ModelViewSet):
    queryset = LotMatiere.objects.select_related("article", "nc_blocage", "bloque_par").all()
    serializer_class = LotMatiereSerializer
    search_fields = ("code", "numero_lot", "numero_coulee", "article__code", "article__label",)
    permission_classes = [CanManageStocks]

    def get_permissions(self):
        if self.action in ("bloquer", "lever_quarantaine"):
            return [CanQualiteStock()]
        return super().get_permissions()

    def perform_destroy(self, instance):
        # Conservation (CDC M5 §7.5) : un lot entré en stock ou certifié reste au registre.
        if instance.mouvements.exists() or instance.certificats.exists():
            raise ValidationError({"detail": "Lot mouvementé ou certifié : conservé au registre, suppression interdite."})
        instance.delete()

    @action(detail=True, methods=["post"], url_path="bloquer")
    @transaction.atomic
    def bloquer(self, request, pk=None):
        """Mise en quarantaine (QA/QC) : plus aucune sortie possible jusqu'à la levée."""
        lot = LotMatiere.objects.select_for_update().get(pk=self.get_object().pk)
        motif = str(request.data.get("motif") or "").strip()
        if not motif:
            raise ValidationError({"motif": "Motif de quarantaine requis."})
        if lot.statut == LotMatiere.Statut.BLOQUE:
            raise ValidationError({"detail": "Lot déjà en quarantaine."})
        lot.mettre_en_quarantaine(motif, user=request.user)
        return Response(self.get_serializer(lot).data)

    @action(detail=True, methods=["post"], url_path="lever-quarantaine")
    @transaction.atomic
    def lever_quarantaine(self, request, pk=None):
        lot = LotMatiere.objects.select_for_update().get(pk=self.get_object().pk)
        if lot.statut != LotMatiere.Statut.BLOQUE:
            raise ValidationError({"detail": "Le lot n'est pas en quarantaine."})
        if lot.nc_blocage_id and lot.nc_blocage.statut != "cloturee":
            raise ValidationError({"detail": f"NC {lot.nc_blocage.code} ouverte : clôturer la NC (CAPA) avant de lever la quarantaine."})
        lot.lever_quarantaine()
        return Response(self.get_serializer(lot).data)

    def get_queryset(self):
        qs = super().get_queryset()
        if article := self.request.query_params.get("article"):
            qs = qs.filter(article_id=article)
        if statut := self.request.query_params.get("statut"):
            qs = qs.filter(statut=statut)
        return qs


class CertificatMatiereViewSet(viewsets.ModelViewSet):
    queryset = CertificatMatiere.objects.select_related("lot", "lot__article", "fournisseur", "valide_par", "document").all()
    serializer_class = CertificatMatiereSerializer
    permission_classes = [CanManageStocks]

    def get_permissions(self):
        if self.action == "valider":
            return [CanQualiteStock()]
        return super().get_permissions()

    def perform_update(self, serializer):
        if serializer.instance.date_validation:
            raise ValidationError({"detail": "Certificat validé : pièce scellée, non modifiable."})
        serializer.save()

    def perform_destroy(self, instance):
        if instance.date_validation or instance.document_id:
            raise ValidationError({"detail": "Certificat validé ou numérisé : conservé (traçabilité 10 ans)."})
        instance.delete()

    @action(detail=True, methods=["post"], url_path="valider")
    @transaction.atomic
    def valider(self, request, pk=None):
        """Validation QA/QC du MTC / CoC, attestée (qui, quand) ; un certificat non conforme bloque toute sortie."""
        cert = CertificatMatiere.objects.select_for_update().get(pk=self.get_object().pk)
        if cert.date_validation:
            raise ValidationError({"detail": "Certificat déjà validé."})
        conforme = _as_bool(request.data.get("conforme", True), "conforme")
        cert.conforme = conforme
        cert.date_validation = timezone.localdate()
        cert.valide_par = request.user
        if request.data.get("notes"):
            cert.notes = str(request.data.get("notes"))
        cert.save(update_fields=["conforme", "date_validation", "valide_par", "notes", "updated_at"])
        return Response(self.get_serializer(cert).data)

    @action(detail=True, methods=["post"], url_path="joindre")
    @transaction.atomic
    def joindre(self, request, pk=None):
        """Certificat numérisé scellé en GED (type « certificats matière », conservation paramétrée, 10 ans par défaut)."""
        cert = CertificatMatiere.objects.select_for_update().get(pk=self.get_object().pk)
        if cert.document_id:
            raise ValidationError({"detail": "Un document est déjà joint à ce certificat."})
        fichier = _fichier(request)
        cert.document = archiver_piece_ged(
            fichier.read(), fichier.name, f"{cert.get_type_display()} {cert.numero_certificat} — lot {cert.lot.numero_lot}",
            TYPE_GED_CERTIFICAT, "Certificats matière (MTC / CoC)", int(get_param_stock("CERTIFICAT_RETENTION_ANS")),
            cert.code, request.user, mots=("certificat", cert.type, cert.lot.code),
        )
        cert.save(update_fields=["document", "updated_at"])
        return Response(self.get_serializer(cert).data)

    def get_queryset(self):
        qs = super().get_queryset()
        if lot := self.request.query_params.get("lot"):
            qs = qs.filter(lot_id=lot)
        return qs


class MouvementStockViewSet(viewsets.ModelViewSet):
    queryset = MouvementStock.objects.select_related(
        "article", "source", "destination", "lot", "ordre", "devise", "created_by"
    ).all()
    serializer_class = MouvementStockSerializer
    search_fields = ("code", "document_reference", "article__code", "article__label",)
    permission_classes = [CanManageStocks]
    # Journal de stock : création seule (le mouvement est exécuté immédiatement).
    # Une erreur se corrige par un mouvement inverse / un ajustement, jamais par PATCH/DELETE.
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if article := params.get("article"):
            qs = qs.filter(article_id=article)
        if lot := params.get("lot"):
            qs = qs.filter(lot_id=lot)
        if depot := params.get("depot"):
            qs = qs.filter(source_id=depot) | qs.filter(destination_id=depot)
        if type_mouvement := params.get("type"):
            qs = qs.filter(type_mouvement=type_mouvement)
        return qs.distinct()

    @transaction.atomic
    def perform_create(self, serializer):
        mouvement = serializer.save(created_by=self.request.user)
        try:
            controler_depot(mouvement, self.request.user)
            apply_move(mouvement)
        except ValueError as exc:
            from django.db import transaction as t

            t.set_rollback(True)
            from rest_framework.exceptions import ValidationError

            raise ValidationError({"detail": str(exc)})

    @action(detail=True, methods=["get"], url_path="bon-de-sortie")
    def bon_de_sortie(self, request, pk=None):
        """Bon de sortie magasin (PDF) d'une consommation ou d'un transfert."""
        mouvement = self.get_object()
        if mouvement.type_mouvement not in (MouvementStock.Type.CONSOMMATION, MouvementStock.Type.TRANSFERT):
            raise ValidationError({"detail": "Bon de sortie : consommation ou transfert seulement."})
        reponse = HttpResponse(bon_de_sortie_pdf(mouvement), content_type="application/pdf")
        reponse["Content-Disposition"] = f'inline; filename="BS-{mouvement.code}.pdf"'
        return reponse

    @action(detail=True, methods=["post"], url_path="joindre")
    @transaction.atomic
    def joindre(self, request, pk=None):
        """Pièce du mouvement (BL fournisseur, bon de sortie signé) scellée en GED, conservation 10 ans."""
        mouvement = MouvementStock.objects.select_for_update().get(pk=self.get_object().pk)
        if mouvement.document_id:
            raise ValidationError({"detail": "Une pièce est déjà jointe à ce mouvement."})
        fichier = _fichier(request)
        mouvement.document = archiver_piece_ged(
            fichier.read(), fichier.name, f"{mouvement.get_type_mouvement_display()} {mouvement.code} — {mouvement.article.code}",
            TYPE_GED_PIECE_STOCK, "Pièces de stock (BL, bons de sortie)", 10, mouvement.code, request.user,
            mots=("stock", mouvement.type_mouvement, mouvement.code),
        )
        mouvement.save(update_fields=["document", "updated_at"])
        return Response(self.get_serializer(mouvement).data)

    @action(detail=False, methods=["get"], url_path="alertes")
    def alertes(self, request):
        """Alertes stock : seuil minimal, péremption (délai paramétrable), fournisseur non agréé."""
        return Response(alertes_stock())

    @action(detail=False, methods=["get"], url_path="tracabilite")
    def traceabilite(self, request):
        article = request.query_params.get("article")
        lot = request.query_params.get("lot")
        if not (article or lot):
            return Response(
                {"detail": "Paramètre `article` ou `lot` requis."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        rows = traceabilite(article_id=article, lot_id=lot)
        if not can_see_amount(request.user):
            for row in rows:
                row["prix_unitaire"] = None
        return Response(TraceabiliteEntrySerializer(rows, many=True).data)


class StockQuantViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = StockQuant.objects.select_related("depot", "article", "lot").all()
    serializer_class = StockQuantSerializer
    permission_classes = [CanManageStocks]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if depot := params.get("depot"):
            qs = qs.filter(depot_id=depot)
        if article := params.get("article"):
            qs = qs.filter(article_id=article)
        if lot := params.get("lot"):
            qs = qs.filter(lot_id=lot)
        if params.get("positive") == "1":
            qs = qs.filter(quantity__gt=0)
        return qs

    @action(detail=False, methods=["get"], url_path="audit-valorisation")
    def audit_valorisation(self, request):
        """Audit rétrospectif de la valorisation d'un article dans un dépôt (`?depot=&article=[&lot=]`)."""
        from referentiels.models import Article

        try:
            depot = Depot.objects.get(pk=request.query_params.get("depot"))
            article = Article.objects.get(pk=request.query_params.get("article"))
            lot = LotMatiere.objects.get(pk=request.query_params["lot"]) if request.query_params.get("lot") else None
        except (Depot.DoesNotExist, Article.DoesNotExist, LotMatiere.DoesNotExist, ValueError, DjangoValidationError):
            raise ValidationError({"detail": "Paramètres `depot` et `article` (identifiants) requis."})
        resultat = audit_valorisation(depot, article, lot)
        if not can_see_amount(request.user):
            for ligne in resultat["lignes"]:
                ligne["cout_enregistre"] = ligne["cout_recalcule"] = ligne["ecart"] = None
        return Response(resultat)

    @action(detail=False, methods=["get"], url_path="valorisation")
    def valorisation(self, request):
        rows = valuation(depot_id=request.query_params.get("depot"))
        return Response(ValorisationEntrySerializer(rows, many=True).data)


class InventaireViewSet(viewsets.ModelViewSet):
    queryset = Inventaire.objects.select_related(
        "depot", "responsable", "created_by"
    ).prefetch_related("lignes__article", "lignes__lot").all()
    serializer_class = InventaireSerializer
    search_fields = ("code", "depot__code",)
    permission_classes = [CanManageStocks]

    def get_queryset(self):
        qs = super().get_queryset()
        if depot := self.request.query_params.get("depot"):
            qs = qs.filter(depot_id=depot)
        if statut := self.request.query_params.get("statut"):
            qs = qs.filter(statut=statut)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"], url_path="cloturer")
    def cloturer(self, request, pk=None):
        inventaire = self.get_object()
        try:
            inventaire = cloturer_inventaire(inventaire, request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(inventaire).data)


class InventaireLigneViewSet(viewsets.ModelViewSet):
    queryset = InventaireLigne.objects.select_related("inventaire", "article", "lot").all()
    serializer_class = InventaireLigneSerializer
    permission_classes = [CanManageStocks]

    def get_queryset(self):
        qs = super().get_queryset()
        if inventaire := self.request.query_params.get("inventaire"):
            qs = qs.filter(inventaire_id=inventaire)
        return qs


class ArticleStockViewSet(viewsets.ModelViewSet):
    queryset = ArticleStock.objects.select_related("article").all()
    serializer_class = ArticleStockSerializer
    search_fields = ("article__code", "article__label",)
    permission_classes = [CanManageStocks]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("active") == "1":
            qs = qs.filter(is_active=True)
        return qs


class PlanInventaireTournantViewSet(viewsets.ModelViewSet):
    """Plans d'inventaire tournant (clôture M5) : `generer` prépare le passage sans attendre l'échéance."""

    queryset = PlanInventaireTournant.objects.select_related("depot", "responsable").all()
    serializer_class = PlanInventaireTournantSerializer
    permission_classes = [CanManageStocks]

    @action(detail=True, methods=["post"], url_path="generer")
    def generer(self, request, pk=None):
        inventaire = generer_inventaire_tournant(self.get_object())
        if inventaire is None:
            return Response({"detail": "Aucun article en stock dans ce dépôt."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(InventaireSerializer(inventaire, context={"request": request}).data, status=status.HTTP_201_CREATED)


class ValorisationMensuelleViewSet(viewsets.ReadOnlyModelViewSet):
    """Valorisations mensuelles figées, publiées à M11 (non modifiables)."""

    queryset = ValorisationMensuelle.objects.select_related("depot").all()
    serializer_class = ValorisationMensuelleSerializer
    permission_classes = [CanManageStocks]

    def get_queryset(self):
        qs = super().get_queryset()
        if periode := self.request.query_params.get("periode"):
            qs = qs.filter(periode=periode)
        return qs

    @action(detail=False, methods=["post"], url_path="figer")
    def figer(self, request):
        try:
            lignes = figer_valorisation_mensuelle(request.data.get("periode", ""), request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(lignes, many=True).data, status=status.HTTP_201_CREATED)


class ParametreStockViewSet(viewsets.ModelViewSet):
    """Paramètres M5 (délais d'alerte, conservation) : valeurs provisoires modifiables par les rôles stock,
    confirmées par la direction des opérations et au-dessus."""

    queryset = ParametreStock.objects.all()
    serializer_class = ParametreStockSerializer
    permission_classes = [CanManageStocks]
    http_method_names = ["get", "patch", "post", "head", "options"]

    def get_queryset(self):
        for code in PARAMETRES_STOCK_DEFAUT:
            get_param_stock(code)
        return super().get_queryset()

    def create(self, request, *args, **kwargs):
        return Response({"detail": "Paramètres prédéfinis : modification seulement."}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    @action(detail=True, methods=["post"], url_path="confirmer")
    def confirmer(self, request, pk=None):
        from maintenance.services import MAINTENANCE_CONFIRM_ROLES

        u = request.user
        if not (u.is_staff or u.role in MAINTENANCE_CONFIRM_ROLES):
            return Response({"detail": "Confirmation réservée à la direction des opérations et au-dessus."},
                            status=status.HTTP_403_FORBIDDEN)
        p = self.get_object()
        p.statut_valeur = ParametreStock.StatutValeur.CONFIRME
        p.confirme_par = u
        p.confirme_le = timezone.now()
        p.save(update_fields=["statut_valeur", "confirme_par", "confirme_le"])
        return Response(self.get_serializer(p).data)
