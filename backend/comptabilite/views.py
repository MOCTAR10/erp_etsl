"""API module M10 — Comptabilité & Trésorerie (RF-ERP-90…94)."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from .models import (
    CompteBancaire,
    ControleInterne,
    DeclarationTva,
    Engagement,
    ClotureMensuelle,
    FactureClient,
    Lettrage,
    LigneRapprochement,
    ModeleFacture,
    LigneReleve,
    ParametreCompta,
    Paiement,
    RapprochementBancaire,
    ReleveBancaire,
    TauxTva,
    PrevisionTresorerie,
    AutoFacture,
    GabaritEtat,
)
from config.inputs import date_input

from . import cloture, facturation
from .permissions import CanConfirmerParametreCompta, IsComptaAdmin
from .serializers import (
    CompteBancaireSerializer,
    ControleInterneSerializer,
    DeclarationTvaSerializer,
    EngagementSerializer,
    ClotureMensuelleSerializer,
    FactureClientSerializer,
    ModeleFactureSerializer,
    LettrageSerializer,
    ParametreComptaSerializer,
    LigneReleveSerializer,
    PaiementSerializer,
    RapprochementBancaireSerializer,
    ReleveBancaireSerializer,
    TauxTvaSerializer,
    PrevisionTresorerieSerializer,
    AutoFactureSerializer,
    GabaritEtatSerializer,
)
from users.permissions import can_read_module
from config.filtres_vues import FiltresMulticriteresMixin
from .services import (
    CanManageCompta,
    CanValidateCompta,
    PARAMETRES_DEFAUT,
    anomalies_lettrage,
    build_paiement_move,
    can_see_amount,
    compute_declaration_tva,
    delettrer,
    get_param,
    importer_releve,
    rapprocher_auto,
    lettrer_auto,
    lettrer_lignes,
    parametres_provisoires,
)


def _est_uuid(valeur):
    import uuid

    try:
        uuid.UUID(str(valeur))
        return True
    except (ValueError, AttributeError):
        return False


class DjangoValidationMixin:
    """Convertit les `ValidationError` Django en réponses HTTP 400."""

    def handle_exception(self, exc):
        if isinstance(exc, DjangoValidationError):
            exc = DRFValidationError(getattr(exc, "messages", [str(exc)]))
        return super().handle_exception(exc)


class TauxTvaViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    queryset = TauxTva.objects.all()
    serializer_class = TauxTvaSerializer
    permission_classes = [CanManageCompta]

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [can_read_module("comptabilite")()]
        return [IsComptaAdmin()]


class CompteBancaireViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    queryset = CompteBancaire.objects.select_related("compte_comptable", "devise").all()
    serializer_class = CompteBancaireSerializer
    search_fields = ("code", "label", "banque",)
    permission_classes = [CanManageCompta]


class ReleveBancaireViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    queryset = ReleveBancaire.objects.prefetch_related("lignes").all()
    serializer_class = ReleveBancaireSerializer
    search_fields = ("code", "compte_bancaire__code", "compte_bancaire__label")
    permission_classes = [CanManageCompta]

    def get_queryset(self):
        qs = super().get_queryset()
        compte = self.request.query_params.get("compte")
        statut = self.request.query_params.get("statut")
        if compte:
            qs = qs.filter(compte_bancaire_id=compte)
        if statut:
            qs = qs.filter(statut=statut)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=False, methods=["post"], url_path="importer")
    def importer(self, request):
        """Importe un relevé MT940 ou CFONB 120 (champ `contenu` ou fichier `fichier`) — gabarits standard."""
        compte = CompteBancaire.objects.filter(pk=request.data.get("compte_bancaire")).first() \
            if _est_uuid(request.data.get("compte_bancaire")) else None
        if compte is None:
            raise DRFValidationError("Compte bancaire inconnu : fournissez `compte_bancaire`.")
        fichier = request.FILES.get("fichier")
        if fichier is not None:
            brut = fichier.read(5_000_001)
            if len(brut) > 5_000_000:
                raise DRFValidationError("Fichier trop volumineux (5 Mo maximum).")
            try:
                texte = brut.decode("utf-8")
            except UnicodeDecodeError:
                texte = brut.decode("latin-1")
        else:
            texte = request.data.get("contenu")
        if not isinstance(texte, str) or not texte.strip():
            raise DRFValidationError("Fournissez le fichier (`fichier`) ou son texte (`contenu`).")
        releve = importer_releve(compte, texte, request.data.get("format") or "auto", request.user)
        return Response(self.get_serializer(releve).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="lignes")
    def add_lignes(self, request, pk=None):
        """Ajoute des lignes de relevé saisies à la main."""
        releve = self.get_object()
        if releve.statut == ReleveBancaire.Statut.VALIDE:
            raise DRFValidationError("Relevé déjà validé — lignes verrouillées.")
        lignes = request.data.get("lignes")
        if not isinstance(lignes, list) or not lignes:
            raise DRFValidationError("Fournissez une liste `lignes` non vide.")
        if not all(isinstance(item, dict) for item in lignes):
            raise DRFValidationError("Chaque ligne doit être un objet {date, libelle, debit|credit}.")
        created = []
        for item in lignes:
            # Le relevé est celui de l'URL : jamais celui fourni par le client (sinon on écrirait dans un relevé validé).
            serializer = LigneReleveSerializer(data={**item, "releve": releve.pk})
            serializer.is_valid(raise_exception=True)
            instance = serializer.save()
            created.append(instance)
        return Response(
            LigneReleveSerializer(created, many=True).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["post"])
    def valider(self, request, pk=None):
        releve = self.get_object()
        if releve.statut == ReleveBancaire.Statut.VALIDE:
            raise DRFValidationError("Relevé déjà validé.")
        if not releve.lignes.exists():
            raise DRFValidationError("Ajoutez au moins une ligne avant de valider.")
        releve.statut = ReleveBancaire.Statut.VALIDE
        releve.save(update_fields=["statut"])
        return Response(self.get_serializer(releve).data)


class RapprochementBancaireViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    queryset = RapprochementBancaire.objects.prefetch_related("lignes").all()
    serializer_class = RapprochementBancaireSerializer
    permission_classes = [CanManageCompta]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=False, methods=["post"], url_path="rapprocher-auto")
    def rapprocher_auto_action(self, request):
        """Rapproche automatiquement relevés et paiements validés d'un compte bancaire (RF-ERP-91)."""
        compte = CompteBancaire.objects.filter(pk=request.data.get("compte_bancaire")).first() \
            if _est_uuid(request.data.get("compte_bancaire")) else None
        if compte is None:
            raise DRFValidationError("Compte bancaire inconnu : fournissez `compte_bancaire`.")
        res = rapprocher_auto(compte, request.user)
        rap = res.pop("rapprochement")
        res["rapprochement"] = str(rap.id) if rap else None
        res["parametres_provisoires"] = parametres_provisoires(["RAPPRO_TOLERANCE_JOURS", "RAPPRO_TOLERANCE_MONTANT"])
        if not can_see_amount(request.user):
            for item in res["ambigues"] + res["lignes_sans_paiement"]:
                item["debit"] = item["credit"] = None
            for item in res["paiements_sans_ligne"]:
                item["montant"] = None
        return Response(res)

    @action(detail=True, methods=["post"], url_path="lignes")
    def add_lignes(self, request, pk=None):
        """Rapproche des lignes de relevé au sein du rapprochement (RF-ERP-91)."""
        rapprochement = self.get_object()
        if rapprochement.statut == RapprochementBancaire.Statut.VALIDE:
            raise DRFValidationError("Rapprochement déjà validé.")
        ligne_ids = request.data.get("lignes")
        if not isinstance(ligne_ids, list) or not ligne_ids:
            raise DRFValidationError("Fournissez une liste `lignes` d'ids.")
        for ligne_pk in ligne_ids:
            ligne = LigneReleve.objects.filter(pk=ligne_pk).first()
            if ligne is None:
                raise DRFValidationError(f"Ligne de relevé introuvable : {ligne_pk}")
            if ligne.releve.compte_bancaire_id != rapprochement.compte_bancaire_id:
                raise DRFValidationError(
                    f"Ligne {ligne_pk} rattachée à un autre compte bancaire."
                )
            LigneRapprochement.objects.get_or_create(
                rapprochement=rapprochement, ligne_releve=ligne
            )
            ligne.rapprochee = True
            ligne.save(update_fields=["rapprochee"])
        return Response(self.get_serializer(rapprochement).data)

    @action(detail=True, methods=["post"])
    def valider(self, request, pk=None):
        rapprochement = self.get_object()
        if rapprochement.statut == RapprochementBancaire.Statut.VALIDE:
            raise DRFValidationError("Rapprochement déjà validé.")
        if not rapprochement.lignes.exists():
            raise DRFValidationError("Rapprochez au moins une ligne avant de valider.")
        rapprochement.statut = RapprochementBancaire.Statut.VALIDE
        rapprochement.save(update_fields=["statut"])
        return Response(self.get_serializer(rapprochement).data)


class LockedAfterMixin:
    """Interdit modification/suppression d'une pièce figée (écriture comptable liée, dépôt…).

    `locked_statuses` : statuts à partir desquels la pièce est immuable ; seules les
    actions dédiées (approuver, comptabiliser, annuler…) font évoluer son statut.
    """

    locked_statuses: tuple = ()
    locked_message = "Pièce figée : modification et suppression impossibles."

    def _assert_unlocked(self):
        if self.get_object().statut in self.locked_statuses:
            raise DRFValidationError(self.locked_message)

    def update(self, request, *args, **kwargs):
        self._assert_unlocked()
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._assert_unlocked()
        return super().destroy(request, *args, **kwargs)


class EngagementViewSet(LockedAfterMixin, DjangoValidationMixin, viewsets.ModelViewSet):
    """Engagements de dépense — circuit RF-ERP-W1 (visa → engagement)."""

    queryset = Engagement.objects.select_related("compte_depense", "fournisseur", "demande_par").all()
    serializer_class = EngagementSerializer
    search_fields = ("code", "objet",)
    locked_statuses = (Engagement.Statut.SOUMIS, Engagement.Statut.APPROUVE, Engagement.Statut.ANNULE)
    locked_message = "Engagement soumis, approuvé ou annulé : non modifiable (proc. 4.3)."

    def get_permissions(self):
        # Le visa d'un engagement engage la société : cercle de validation (RF-33),
        # pas tous les rôles qui peuvent saisir.
        if self.action == "approuver":
            return [CanValidateCompta()]
        return [CanManageCompta()]

    def get_queryset(self):
        qs = super().get_queryset()
        statut = self.request.query_params.get("statut")
        if statut:
            qs = qs.filter(statut=statut)
        return qs

    def perform_create(self, serializer):
        serializer.save(demande_par=self.request.user)

    @action(detail=True, methods=["post"])
    def soumettre(self, request, pk=None):
        engagement = self.get_object()
        if engagement.statut != Engagement.Statut.BROUILLON:
            raise DRFValidationError("Seul un brouillon peut être soumis.")
        engagement.statut = Engagement.Statut.SOUMIS
        engagement.save(update_fields=["statut", "updated_at"])
        return Response(self.get_serializer(engagement).data)

    @action(detail=True, methods=["post"])
    def approuver(self, request, pk=None):
        engagement = self.get_object()
        if engagement.statut != Engagement.Statut.SOUMIS:
            raise DRFValidationError("Seul un engagement soumis peut être approuvé (RF-ERP-W1).")
        raw_date = request.data.get("date_engagement")
        try:
            engagement.date_engagement = (
                serializers.DateField().run_validation(raw_date) if raw_date else timezone.localdate()
            )
        except serializers.ValidationError as exc:
            raise DRFValidationError({"date_engagement": exc.detail})
        engagement.statut = Engagement.Statut.APPROUVE
        engagement.save(update_fields=["statut", "date_engagement", "updated_at"])
        return Response(self.get_serializer(engagement).data)

    @action(detail=True, methods=["post"])
    def annuler(self, request, pk=None):
        engagement = self.get_object()
        if engagement.statut in (Engagement.Statut.ANNULE, Engagement.Statut.APPROUVE):
            raise DRFValidationError("Engagement approuvé ou déjà annulé.")
        engagement.statut = Engagement.Statut.ANNULE
        engagement.save(update_fields=["statut", "updated_at"])
        return Response(self.get_serializer(engagement).data)


class PaiementViewSet(FiltresMulticriteresMixin, LockedAfterMixin, DjangoValidationMixin, viewsets.ModelViewSet):
    """Paiements / encaissements — comptabilisation via le noyau (RF-ERP-90)."""

    queryset = Paiement.objects.select_related("compte_bancaire", "engagement", "tiers", "facture", "move").all()
    serializer_class = PaiementSerializer
    search_fields = ("code", "reference",)
    # EX-G-09 (lot a7) : critères combinables ; jamais de montant (masqué RF-59).
    champs_filtrables = ("sens", "mode", "statut", "date", "imputation_618", "retenue_source")
    locked_statuses = (Paiement.Statut.VALIDE, Paiement.Statut.ANNULE)
    locked_message = "Paiement validé ou annulé : non modifiable (écriture comptable liée)."

    def get_permissions(self):
        if self.action in ("comptabiliser", "annuler"):
            return [CanValidateCompta()]
        return [CanManageCompta()]

    def get_queryset(self):
        qs = super().get_queryset()
        sens = self.request.query_params.get("sens")
        statut = self.request.query_params.get("statut")
        mois = self.request.query_params.get("mois")
        if sens:
            qs = qs.filter(sens=sens)
        if statut:
            qs = qs.filter(statut=statut)
        if mois:
            qs = qs.filter(date__year=mois[:4], date__month=int(mois[5:7]))
        return qs

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)

    @action(detail=True, methods=["post"])
    def comptabiliser(self, request, pk=None):
        paiement = self.get_object()
        # CDC M2 §5.8 : rapprochement 3-way (BR / BC / facture) obligatoire avant comptabilisation.
        if paiement.facture_id and paiement.facture.status == paiement.facture.Status.RAPPROCHEE:
            raise DRFValidationError(
                f"Facture {paiement.facture.code} rapprochée mais non comptabilisée : comptabilisez-la (Achats) avant le paiement."
            )
        if paiement.facture_id and paiement.facture.status != paiement.facture.Status.COMPTABILISEE:
            raise DRFValidationError(
                f"Facture {paiement.facture.code} non rapprochée (3-way BR / BC / facture) : comptabilisation impossible."
            )
        try:
            move = build_paiement_move(paiement, user=request.user)
        except DjangoValidationError as exc:
            raise DRFValidationError(exc.messages)
        return Response(self.get_serializer(paiement).data)

    @action(detail=True, methods=["post"])
    def annuler(self, request, pk=None):
        paiement = self.get_object()
        if paiement.statut == Paiement.Statut.VALIDE:
            raise DRFValidationError("Paiement déjà validé — extourne via le noyau (RF-ERP-90).")
        paiement.statut = Paiement.Statut.ANNULE
        paiement.save(update_fields=["statut", "updated_at"])
        return Response(self.get_serializer(paiement).data)


class DeclarationTvaViewSet(LockedAfterMixin, DjangoValidationMixin, viewsets.ModelViewSet):
    queryset = DeclarationTva.objects.select_related("taux_tva").all()
    serializer_class = DeclarationTvaSerializer
    search_fields = ("code",)
    permission_classes = [CanManageCompta]
    locked_statuses = (DeclarationTva.Statut.DEPOSEE,)
    locked_message = "Déclaration déposée : non modifiable ni supprimable."

    @action(detail=True, methods=["post"])
    def calculer(self, request, pk=None):
        declaration = self.get_object()
        if declaration.statut == DeclarationTva.Statut.DEPOSEE:
            raise DRFValidationError("Déclaration déjà déposée — recalcul impossible.")
        compute_declaration_tva(declaration)
        return Response(self.get_serializer(declaration).data)

    @action(detail=True, methods=["post"])
    def deposer(self, request, pk=None):
        declaration = self.get_object()
        if declaration.statut == DeclarationTva.Statut.DEPOSEE:
            raise DRFValidationError("Déjà déposée.")
        if not declaration.net_a_payer and not declaration.base_imposable:
            raise DRFValidationError("Calculez d'abord la déclaration.")
        declaration.statut = DeclarationTva.Statut.DEPOSEE
        declaration.save(update_fields=["statut"])
        from . import fiscal

        fiscal.archiver_declaration(declaration, request.user)  # pièce fiscale scellée en GED (10 ans)
        return Response(self.get_serializer(declaration).data)


class ControleInterneViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    queryset = ControleInterne.objects.all()
    serializer_class = ControleInterneSerializer
    permission_classes = [CanManageCompta]

    @action(detail=True, methods=["post"])
    def realiser(self, request, pk=None):
        controle = self.get_object()
        if controle.statut == ControleInterne.Statut.REALISE:
            raise DRFValidationError("Contrôle déjà réalisé.")
        date_realise = date_input(request.data.get("date_realise"), "date_realise", default=timezone.localdate())
        controle.statut = ControleInterne.Statut.REALISE
        controle.date_realise = date_realise
        controle.constat = request.data.get("constat", controle.constat)
        controle.save(update_fields=["statut", "date_realise", "constat", "updated_at"])
        return Response(self.get_serializer(controle).data)

    @action(detail=True, methods=["post"])
    def cloturer(self, request, pk=None):
        controle = self.get_object()
        if controle.statut not in (ControleInterne.Statut.REALISE, ControleInterne.Statut.PLANIFIE):
            raise DRFValidationError("Contrôle déjà clôturé.")
        controle.statut = ControleInterne.Statut.CLOTURE
        controle.save(update_fields=["statut", "updated_at"])
        return Response(self.get_serializer(controle).data)


class ParametreComptaViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    """Paramètres modifiables par ETSL ; création/suppression interdites (définis par le code)."""

    queryset = ParametreCompta.objects.all()
    serializer_class = ParametreComptaSerializer
    http_method_names = ["get", "patch", "post", "head", "options"]

    def get_queryset(self):
        for code in PARAMETRES_DEFAUT:
            get_param(code)
        return super().get_queryset()

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [can_read_module("comptabilite")()]
        if self.action == "confirmer":
            return [CanConfirmerParametreCompta()]
        return [IsComptaAdmin()]

    def create(self, request, *args, **kwargs):
        raise DRFValidationError("Les paramètres sont prédéfinis : modifiez leur valeur.")

    @action(detail=True, methods=["post"], url_path="confirmer")
    def confirmer(self, request, pk=None):
        p = self.get_object()
        p.statut_valeur = ParametreCompta.StatutValeur.CONFIRME
        p.confirme_par = request.user
        p.confirme_le = timezone.now()
        p.save(update_fields=["statut_valeur", "confirme_par", "confirme_le"])
        return Response(self.get_serializer(p).data)


class LettrageViewSet(DjangoValidationMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Lettrage.objects.select_related("compte").prefetch_related("lignes__ligne__move").all()
    serializer_class = LettrageSerializer
    permission_classes = [CanManageCompta]

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if p.get("compte"):
            qs = qs.filter(compte_id=p["compte"])
        if p.get("statut"):
            qs = qs.filter(statut=p["statut"])
        return qs

    def create(self, request):
        from accounting_kernel.models import AccountMoveLine

        ids = request.data.get("lignes")
        if not isinstance(ids, list) or not ids:
            raise DRFValidationError("Fournissez une liste `lignes` non vide.")
        try:
            lignes = list(AccountMoveLine.objects.filter(id__in=ids))
        except (DjangoValidationError, ValueError):
            raise DRFValidationError("Identifiant de ligne invalide.")
        if len(lignes) != len(set(map(str, ids))):
            raise DRFValidationError("Ligne d'écriture introuvable.")
        lettrage = lettrer_lignes(lignes, request.user)
        return Response(self.get_serializer(lettrage).data, status=status.HTTP_201_CREATED)

    def _compte(self, request):
        from referentiels.models import Account

        try:
            return Account.objects.get(pk=request.query_params.get("compte") or request.data.get("compte"))
        except (Account.DoesNotExist, DjangoValidationError, ValueError, TypeError):
            raise DRFValidationError("Compte inconnu : fournissez `compte`.")

    @action(detail=False, methods=["post"], url_path="lettrer-auto")
    def lettrer_auto_action(self, request):
        crees, restantes = lettrer_auto(self._compte(request), request.user)
        return Response({"lettrages": crees, "non_lettrees": restantes})

    @action(detail=False, methods=["get"], url_path="anomalies")
    def anomalies_action(self, request):
        delai, rows = anomalies_lettrage(self._compte(request))
        if not can_see_amount(request.user):
            for r in rows:
                r["debit"] = r["credit"] = None
        return Response({
            "delai_jours": delai,
            "parametres_provisoires": parametres_provisoires(["LETTRAGE_TOLERANCE", "LETTRAGE_DELAI_ANOMALIE_JOURS"]),
            "anomalies": rows,
        })

    @action(detail=True, methods=["post"], url_path="delettrer")
    def delettrer_action(self, request, pk=None):
        lettrage = delettrer(self.get_object(), request.user, request.data.get("motif", ""))
        return Response(self.get_serializer(lettrage).data)


class ModeleFactureViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    """Modèle de facture client : un seul enregistrement, modifiable par ETSL, provisoire jusqu'à confirmation."""

    queryset = ModeleFacture.objects.order_by("pk")
    serializer_class = ModeleFactureSerializer
    http_method_names = ["get", "patch", "post", "head", "options"]

    def get_queryset(self):
        facturation.get_modele()
        return super().get_queryset()

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [can_read_module("comptabilite")()]
        if self.action == "confirmer":
            return [CanConfirmerParametreCompta()]
        return [IsComptaAdmin()]

    def create(self, request, *args, **kwargs):
        raise DRFValidationError("Le modèle est unique : modifiez-le.")

    @action(detail=True, methods=["post"], url_path="confirmer")
    def confirmer(self, request, pk=None):
        modele = self.get_object()
        modele.statut_valeur = ModeleFacture.StatutValeur.CONFIRME
        modele.confirme_par, modele.confirme_le = request.user, timezone.now()
        modele.save(update_fields=["statut_valeur", "confirme_par", "confirme_le"])
        return Response(self.get_serializer(modele).data)


class FactureClientViewSet(FiltresMulticriteresMixin, DjangoValidationMixin, viewsets.ModelViewSet):
    """Factures et avoirs clients (M10) : brouillon modifiable, puis émission = écriture comptable + scellé."""

    queryset = FactureClient.objects.select_related("client", "move", "taux_tva").prefetch_related("lignes").all()
    serializer_class = FactureClientSerializer
    search_fields = ("code", "objet",)
    champs_filtrables = ("nature", "statut", "date", "echeance")

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [can_read_module("comptabilite")()]
        if self.action == "emettre":
            return [CanValidateCompta()]
        return [CanManageCompta()]

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        for cle in ("nature", "statut", "client"):
            if p.get(cle):
                qs = qs.filter(**{cle: p[cle]})
        return qs

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)

    def _brouillon(self):
        facture = self.get_object()
        if facture.statut != FactureClient.Statut.BROUILLON:
            raise DRFValidationError("Facture émise : non modifiable, corrigez-la par un avoir.")
        return facture

    def update(self, request, *args, **kwargs):
        self._brouillon()
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._brouillon()
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def emettre(self, request, pk=None):
        facture = facturation.emettre_facture(self.get_object(), request.user)
        return Response(self.get_serializer(facture).data)

    @action(detail=True, methods=["post"])
    def avoir(self, request, pk=None):
        avoir = facturation.creer_avoir(
            self.get_object(), request.user, request.data.get("montant_ht"), str(request.data.get("motif", ""))
        )
        return Response(self.get_serializer(avoir).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        from django.http import HttpResponse

        facture = self.get_object()
        if not can_see_amount(request.user):
            raise DRFValidationError("Rôle non autorisé à consulter les montants.")
        reponse = HttpResponse(facturation.facture_pdf(facture), content_type="application/pdf")
        reponse["Content-Disposition"] = f'inline; filename="{facture.code}.pdf"'
        return reponse

    def _source(self, request, cle, modele, creer):
        from config.inputs import fk_input

        objet = fk_input(request.data.get(cle), modele.objects.all(), cle)
        if objet is None:
            raise DRFValidationError({cle: "Ce champ est obligatoire."})
        facture = creer(objet, request.user)
        return Response(self.get_serializer(facture).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="depuis-jalon")
    def depuis_jalon(self, request):
        from commercial.models import Milestone

        return self._source(request, "jalon", Milestone, facturation.facture_depuis_jalon)

    @action(detail=False, methods=["post"], url_path="depuis-situation")
    def depuis_situation(self, request):
        from operations.models import SituationTravaux

        return self._source(request, "situation", SituationTravaux, facturation.facture_depuis_situation)

    @action(detail=False, methods=["get"], url_path="a-facturer")
    def a_facturer(self, request):
        """Jalons réalisés et situations validées pas encore facturés (entrées de la facturation)."""
        from commercial.models import Milestone
        from operations.models import SituationTravaux

        jalons = Milestone.objects.filter(actual_date__isnull=False, montant__gt=0, facture_le__isnull=True) \
            .exclude(factures_clients__nature="facture").select_related("affaire")
        situations = SituationTravaux.objects.filter(status=SituationTravaux.Status.VALIDEE, amount__gt=0) \
            .exclude(factures_clients__nature="facture").select_related("affaire")
        voit = can_see_amount(request.user)
        return Response({
            "jalons": [{"id": str(j.id), "affaire": j.affaire.code, "label": j.label, "montant": j.montant if voit else None} for j in jalons],
            "situations": [{"id": str(s.id), "code": s.code, "affaire": s.affaire.code if s.affaire_id else "", "label": s.label, "montant": s.amount if voit else None} for s in situations],
        })


class ClotureMensuelleViewSet(DjangoValidationMixin, viewsets.ReadOnlyModelViewSet):
    """Clôture mensuelle : contrôles, chrono < 2 h, synthèse figée, envoi Direction à J+4."""

    queryset = ClotureMensuelle.objects.select_related("period__fiscal_year").all()
    serializer_class = ClotureMensuelleSerializer

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [can_read_module("comptabilite")()]
        return [CanValidateCompta()]

    def _periode(self, request):
        from accounting_kernel.models import Period

        try:
            return Period.objects.get(pk=request.data.get("period"))
        except (Period.DoesNotExist, DjangoValidationError, ValueError, TypeError):
            raise DRFValidationError({"period": "Période inconnue."})

    @action(detail=False, methods=["get"], url_path="controles")
    def controles(self, request):
        """Contrôles de pré-clôture d'une période (sans rien modifier)."""
        from accounting_kernel.models import Period

        try:
            periode = Period.objects.get(pk=request.query_params.get("period"))
        except (Period.DoesNotExist, DjangoValidationError, ValueError, TypeError):
            raise DRFValidationError({"period": "Période inconnue."})
        liste = cloture.controles_cloture(periode)
        return Response({
            "periode": str(periode),
            "bloquants": sum(1 for c in liste if c["bloquant"] and c["nb"]),
            "controles": liste,
        })

    @action(detail=False, methods=["post"])
    def demarrer(self, request):
        c = cloture.demarrer(self._periode(request), request.user)
        return Response(self.get_serializer(c).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cloturer(self, request, pk=None):
        c = cloture.cloturer(self.get_object(), request.user)
        return Response(self.get_serializer(c).data)

    @action(detail=True, methods=["post"], url_path="envoyer-direction")
    def envoyer_direction(self, request, pk=None):
        c = cloture.envoyer_direction(self.get_object(), request.user)
        return Response(self.get_serializer(c).data)

    @action(detail=True, methods=["post"])
    def rouvrir(self, request, pk=None):
        c = cloture.rouvrir(self.get_object(), request.user, request.data.get("motif", ""))
        return Response(self.get_serializer(c).data)


# --------------------------------------------------------------------------------------------------
# Écarts M10 : états, trésorerie 13 semaines, autofacturation, gabarits fiscaux, écriture 618 des locations GR
# --------------------------------------------------------------------------------------------------
def _reponse_etat(request, etat, nom):
    """JSON (décimaux en chaînes) ou export `?export=xlsx|pdf` (journalisé par le middleware d'exports)."""
    from django.http import HttpResponse

    from . import etats

    fmt = request.query_params.get("export")
    if fmt == "xlsx":
        rep = HttpResponse(
            etats.to_xlsx(etat), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        rep["Content-Disposition"] = f'attachment; filename="{nom}.xlsx"'
        return rep
    if fmt == "pdf":
        rep = HttpResponse(etats.to_pdf(etat), content_type="application/pdf")
        rep["Content-Disposition"] = f'attachment; filename="{nom}.pdf"'
        return rep
    if fmt:
        raise DRFValidationError({"export": "Formats acceptés : xlsx, pdf."})
    return Response(etats.jsonable(etat))


class EtatsViewSet(DjangoValidationMixin, viewsets.ViewSet):
    """États comptables et fiscaux (SYSCOHADA) calculés sur les écritures comptabilisées, exportables."""

    permission_classes = [CanManageCompta]

    def _montants(self, request):
        from rest_framework.exceptions import PermissionDenied

        if not can_see_amount(request.user):
            raise PermissionDenied("Rôle non autorisé à consulter les montants (RF-59).")

    def _dates(self, request):
        p = request.query_params
        return date_input(p.get("date_from"), "date_from"), date_input(p.get("date_to"), "date_to")

    def _exercice(self, request):
        brut = request.query_params.get("exercice") or (request.data.get("exercice") if request.method == "POST" else None)
        brut = str(brut or timezone.localdate().year)
        if not brut.isdigit() or not 2000 <= int(brut) <= 2100:
            raise DRFValidationError({"exercice": "Année attendue (AAAA)."})
        return int(brut)

    @action(detail=False, methods=["get"], url_path="grand-livre")
    def grand_livre(self, request):
        from . import etats

        self._montants(request)
        debut, fin = self._dates(request)
        compte = (request.query_params.get("compte") or "").strip()
        if compte and not compte.isdigit():
            raise DRFValidationError({"compte": "Numéro (ou début de numéro) de compte attendu."})
        return _reponse_etat(request, etats.grand_livre(debut, fin, compte or None), "grand-livre")

    @action(detail=False, methods=["get"])
    def balance(self, request):
        from . import etats

        self._montants(request)
        debut, fin = self._dates(request)
        return _reponse_etat(request, etats.balance(debut, fin), "balance-generale")

    @action(detail=False, methods=["get"])
    def bilan(self, request):
        from . import etats

        self._montants(request)
        return _reponse_etat(request, etats.bilan(self._dates(request)[1]), "bilan")

    @action(detail=False, methods=["get"], url_path="compte-resultat")
    def compte_resultat(self, request):
        from . import etats

        self._montants(request)
        debut, fin = self._dates(request)
        return _reponse_etat(request, etats.compte_resultat(debut, fin), "compte-de-resultat")

    @action(detail=False, methods=["get"], url_path="balance-agee")
    def balance_agee(self, request):
        from . import etats

        self._montants(request)
        nature = request.query_params.get("nature") or "clients"
        if nature not in ("clients", "fournisseurs"):
            raise DRFValidationError({"nature": "clients ou fournisseurs."})
        return _reponse_etat(request, etats.balance_agee(nature, self._dates(request)[1]), f"balance-agee-{nature}")

    @action(detail=False, methods=["get"], url_path="plan-comptable")
    def plan_comptable(self, request):
        from . import etats

        return _reponse_etat(request, etats.plan_comptable(), "plan-comptable")

    @action(detail=False, methods=["get"])
    def conservation(self, request):
        from . import etats

        return _reponse_etat(request, etats.conservation(), "conservation")

    @action(detail=False, methods=["get"])
    def liasse(self, request):
        from . import fiscal

        self._montants(request)
        exercice = self._exercice(request)
        return _reponse_etat(request, fiscal.liasse(exercice), f"liasse-{exercice}")

    @action(detail=False, methods=["get"], url_path="etat-2460")
    def etat_2460(self, request):
        from . import fiscal

        self._montants(request)
        exercice = self._exercice(request)
        return _reponse_etat(request, fiscal.etat_2460(exercice), f"etat-2460-{exercice}")

    @action(detail=False, methods=["post"], url_path="archiver-liasse")
    def archiver_liasse(self, request):
        from . import fiscal

        self._montants(request)
        exercice = self._exercice(request)
        doc = fiscal.archiver_liasse(exercice, request.user)
        return Response({"document": str(doc.pk), "titre": doc.title}, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def tresorerie(self, request):
        from . import etats, tresorerie

        self._montants(request)
        debut = date_input(request.query_params.get("debut"), "debut")
        semaines = request.query_params.get("semaines")
        if semaines and not str(semaines).isdigit():
            raise DRFValidationError({"semaines": "Nombre de semaines attendu."})
        plan = tresorerie.plan_tresorerie(debut, int(semaines) if semaines else None)
        if request.query_params.get("export"):
            from .etats import _col

            etat = {
                "titre": "Plan de trésorerie glissant", "sous_titre": f"{plan['semaines']} semaines à partir du {plan['debut']}",
                "provisoire": plan["provisoire"], "avertissement": "Hypothèses et seuil d'alerte provisoires — à confirmer par ETSL.",
                "tableaux": [{"titre": "Trésorerie", "colonnes": [
                    _col("semaine", "Semaine du"), _col("prevu_encaissements", "Encaissements prévus", True),
                    _col("prevu_decaissements", "Décaissements prévus", True), _col("realise_encaissements", "Encaissements réalisés", True),
                    _col("realise_decaissements", "Décaissements réalisés", True), _col("solde_fin_prevu", "Solde prévu", True),
                    _col("solde_fin_reel", "Solde réel", True),
                ], "lignes": plan["rows"]}],
            }
            return _reponse_etat(request, etat, "tresorerie-13-semaines")
        return Response(etats.jsonable(plan))


class PrevisionTresorerieViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    serializer_class = PrevisionTresorerieSerializer
    permission_classes = [CanManageCompta]
    search_fields = ("code", "libelle")

    def get_queryset(self):
        return PrevisionTresorerie.objects.select_related("compte_bancaire").all()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class AutoFactureViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    """Autofactures (TVA autoliquidée) : brouillon modifiable, émission = écriture 6xx / 445 / 401 / 443 scellée."""

    serializer_class = AutoFactureSerializer
    search_fields = ("code", "objet")

    def get_queryset(self):
        return AutoFacture.objects.select_related("fournisseur", "taux_tva", "compte_charge", "move").all()

    def get_permissions(self):
        if self.action == "emettre":
            return [CanValidateCompta()]
        return [CanManageCompta()]

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)

    def _brouillon(self):
        af = self.get_object()
        if af.statut != AutoFacture.Statut.BROUILLON:
            raise DRFValidationError("Autofacture émise : non modifiable ni supprimable.")

    def update(self, request, *args, **kwargs):
        self._brouillon()
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._brouillon()
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def emettre(self, request, pk=None):
        from . import fiscal

        af = fiscal.emettre_autofacture(self.get_object(), request.user)
        return Response(self.get_serializer(af).data)


class GabaritEtatViewSet(DjangoValidationMixin, viewsets.ReadOnlyModelViewSet):
    """Gabarits d'états (bilan, résultat, liasse, état 2460) : provisoires, modifiables par ETSL."""

    serializer_class = GabaritEtatSerializer

    def get_queryset(self):
        from . import fiscal

        return fiscal.tous_gabarits()

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [can_read_module("comptabilite")()]
        if self.action == "confirmer":
            return [CanConfirmerParametreCompta()]
        return [IsComptaAdmin()]

    @action(detail=True, methods=["post"])
    def modifier(self, request, pk=None):
        """Remplace les paramètres (objet JSON, ou texte JSON) ; le gabarit redevient provisoire."""
        import json

        g = self.get_object()
        brut = request.data.get("parametres")
        if isinstance(brut, str):
            try:
                brut = json.loads(brut)
            except ValueError:
                raise DRFValidationError({"parametres": "JSON invalide."})
        if not isinstance(brut, dict):
            raise DRFValidationError({"parametres": "Objet JSON attendu."})
        g.parametres = brut
        g.statut_valeur = GabaritEtat.StatutValeur.PROVISOIRE
        g.confirme_par = g.confirme_le = None
        g.save()
        return Response(self.get_serializer(g).data)

    @action(detail=True, methods=["post"])
    def confirmer(self, request, pk=None):
        g = self.get_object()
        g.statut_valeur = GabaritEtat.StatutValeur.CONFIRME
        g.confirme_par, g.confirme_le = request.user, timezone.now()
        g.save(update_fields=["statut_valeur", "confirme_par", "confirme_le", "modifie_le"])
        return Response(self.get_serializer(g).data)


class LocationGrComptaViewSet(DjangoValidationMixin, viewsets.ViewSet):
    """Locations GLOBAL RENTAL terminées à comptabiliser au 618 (M4 → M10) et écritures passées."""

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [can_read_module("comptabilite")()]
        return [CanValidateCompta()]

    def list(self, request):
        from accounting_kernel.models import AccountMove

        from . import gr

        voit = can_see_amount(request.user)
        a_faire = [
            {
                "id": str(loc.pk), "code": loc.code, "equipement": loc.equipement.label,
                "affaire": loc.affaire.code if loc.affaire_id else None,
                "date_retour": loc.date_retour.isoformat() if loc.date_retour else None,
                "montant": str(gr.montant_location(loc)) if voit else None,
            }
            for loc in gr.locations_a_comptabiliser()
        ]
        passees = [
            {"numero": m.number, "date": m.date.isoformat(), "location": m.source_ref, "libelle": m.label,
             "montant": str(m.total_debit) if voit else None}
            for m in AccountMove.objects.filter(source=gr.SOURCE_GR).exclude(status="draft").prefetch_related("lines")[:50]
        ]
        return Response({"a_comptabiliser": a_faire, "ecritures": passees, "has_amount_access": voit})

    @action(detail=True, methods=["post"])
    def comptabiliser(self, request, pk=None):
        from logistique.models import LocationGR

        from . import gr

        if not _est_uuid(pk):
            raise DRFValidationError("Location inconnue.")
        location = LocationGR.objects.filter(pk=pk).first()
        if location is None:
            from rest_framework.exceptions import NotFound

            raise NotFound("Location inconnue.")
        move = gr.comptabiliser_location_gr(location, request.user)
        return Response({"numero": move.number, "montant": str(move.total_debit)}, status=status.HTTP_201_CREATED)


class RetenueGarantieViewSet(DjangoValidationMixin, viewsets.ViewSet):
    """Retenues de garantie clients par affaire (M1 → M10) : cumul, libéré, solde, échéance ; libération."""

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [can_read_module("comptabilite")()]
        return [CanValidateCompta()]

    def list(self, request):
        from . import retenues
        from .services import parametres_provisoires

        voit = can_see_amount(request.user)
        rows = []
        for r in retenues.situation_affaires():
            rows.append({
                **r, "date_liberation": r["date_liberation"].isoformat() if r["date_liberation"] else None,
                **{k: (str(r[k]) if voit else None) for k in ("retenue", "liberee", "solde")},
            })
        return Response({
            "rows": rows, "has_amount_access": voit, "compte": retenues.compte_retenue().code if voit else None,
            "provisoire": parametres_provisoires(["RETENUE_GARANTIE_ACTIVE", "RETENUE_GARANTIE_COMPTE"]),
        })

    @action(detail=True, methods=["post"])
    def liberer(self, request, pk=None):
        from commercial.models import Affaire

        from . import retenues

        if not _est_uuid(pk):
            raise DRFValidationError("Affaire inconnue.")
        affaire = Affaire.objects.filter(pk=pk).first()
        if affaire is None:
            from rest_framework.exceptions import NotFound

            raise NotFound("Affaire inconnue.")
        lib = retenues.liberer(affaire, request.user, str(request.data.get("motif", "") or ""))
        return Response({"montant": str(lib.montant), "numero": lib.move.number if lib.move else None},
                        status=status.HTTP_201_CREATED)
