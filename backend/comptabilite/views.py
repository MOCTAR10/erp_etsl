"""API module M10 — Comptabilité & Trésorerie (RF-ERP-90…94)."""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import (
    CompteBancaire,
    ControleInterne,
    DeclarationTva,
    Engagement,
    LigneRapprochement,
    LigneReleve,
    Paiement,
    RapprochementBancaire,
    ReleveBancaire,
    TauxTva,
)
from .permissions import IsComptaAdmin
from .serializers import (
    CompteBancaireSerializer,
    ControleInterneSerializer,
    DeclarationTvaSerializer,
    EngagementSerializer,
    LigneReleveSerializer,
    PaiementSerializer,
    RapprochementBancaireSerializer,
    ReleveBancaireSerializer,
    TauxTvaSerializer,
)
from .services import (
    CanManageCompta,
    CanValidateCompta,
    build_paiement_move,
    compute_declaration_tva,
)


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
            return [IsAuthenticated()]
        return [IsComptaAdmin()]


class CompteBancaireViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    queryset = CompteBancaire.objects.select_related("compte_comptable", "devise").all()
    serializer_class = CompteBancaireSerializer
    permission_classes = [CanManageCompta]


class ReleveBancaireViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    queryset = ReleveBancaire.objects.prefetch_related("lignes").all()
    serializer_class = ReleveBancaireSerializer
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

    @action(detail=True, methods=["post"], url_path="lignes")
    def add_lignes(self, request, pk=None):
        """Ajoute des lignes de relevé (import CFONB / MT940 fortement simplifié)."""
        releve = self.get_object()
        if releve.statut == ReleveBancaire.Statut.VALIDE:
            raise DRFValidationError("Relevé déjà validé — lignes verrouillées.")
        lignes = request.data.get("lignes")
        if not isinstance(lignes, list) or not lignes:
            raise DRFValidationError("Fournissez une liste `lignes` non vide.")
        created = []
        for item in lignes:
            item.setdefault("releve", releve.pk)
            serializer = LigneReleveSerializer(data=item)
            serializer.is_valid(raise_exception=True)
            instance = serializer.save()
            created.append(instance)
        return Response(
            LigneReleveSerializer(created, many=True).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["post"])
    def valider(self, request, pk=None):
        releve = self.get_object()
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
        if not rapprochement.lignes.exists():
            raise DRFValidationError("Rapprochez au moins une ligne avant de valider.")
        rapprochement.statut = RapprochementBancaire.Statut.VALIDE
        rapprochement.save(update_fields=["statut"])
        return Response(self.get_serializer(rapprochement).data)


class EngagementViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    """Engagements de dépense — circuit RF-ERP-W1 (visa → engagement)."""

    queryset = Engagement.objects.select_related("compte_depense", "fournisseur", "demande_par").all()
    serializer_class = EngagementSerializer
    permission_classes = [CanManageCompta]

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
        engagement.statut = Engagement.Statut.APPROUVE
        engagement.date_engagement = request.data.get("date_engagement")
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


class PaiementViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    """Paiements / encaissements — comptabilisation via le noyau (RF-ERP-90)."""

    queryset = Paiement.objects.select_related("compte_bancaire", "engagement", "tiers", "facture", "move").all()
    serializer_class = PaiementSerializer

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


class DeclarationTvaViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    queryset = DeclarationTva.objects.select_related("taux_tva").all()
    serializer_class = DeclarationTvaSerializer
    permission_classes = [CanManageCompta]

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
        controle.statut = ControleInterne.Statut.REALISE
        controle.date_realise = request.data.get("date_realise")
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