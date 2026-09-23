"""API module M12 — Juridique & GED (RF-ERP-B0...B4)."""

from datetime import date as _date

from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import (
    Assurance,
    Caution,
    Contentieux,
    Convention,
    Courrier,
    DossierGlobalRental,
    Reunion,
)
from .serializers import (
    AssuranceSerializer,
    CautionSerializer,
    ContentieuxSerializer,
    ConventionSerializer,
    CourrierSerializer,
    DossierGlobalRentalSerializer,
    ReunionSerializer,
)
from .services import (
    CanManageJuridique,
    CanValidateJuridique,
    compute_alertes,
    compute_stats,
)


class DjangoValidationMixin:
    """Convertit les `ValidationError` Django en réponses HTTP 400."""

    def handle_exception(self, exc):
        if isinstance(exc, DjangoValidationError):
            exc = DRFValidationError(getattr(exc, "messages", [str(exc)]))
        return super().handle_exception(exc)


class CourrierViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    """Bureau d'ordre (RF-ERP-B1, proc. 3.3)."""

    queryset = Courrier.objects.select_related("tiers", "document").all()
    serializer_class = CourrierSerializer
    permission_classes = [CanManageJuridique]

    def get_queryset(self):
        qs = super().get_queryset()
        sens = self.request.query_params.get("sens")
        statut = self.request.query_params.get("statut")
        if sens:
            qs = qs.filter(sens=sens)
        if statut:
            qs = qs.filter(statut=statut)
        return qs

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)

    @action(detail=True, methods=["post"])
    def enregistrer(self, request, pk=None):
        courrier = self.get_object()
        courrier.enregistrer()
        return Response(self.get_serializer(courrier).data)

    @action(detail=True, methods=["post"])
    def classer(self, request, pk=None):
        courrier = self.get_object()
        courrier.classer()
        return Response(self.get_serializer(courrier).data)

    @action(detail=True, methods=["post"])
    def archiver(self, request, pk=None):
        courrier = self.get_object()
        try:
            courrier.archiver()
        except ValueError as exc:
            raise DRFValidationError(str(exc))
        return Response(self.get_serializer(courrier).data)


class ConventionViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    """Contrats & conventions (RF-ERP-B2, proc. 3.6 / 8.3)."""

    queryset = Convention.objects.select_related("partenaire", "affaire", "document").all()
    serializer_class = ConventionSerializer

    def get_permissions(self):
        if self.action in ("signer", "resilier", "cloturer"):
            return [CanValidateJuridique()]
        return [CanManageJuridique()]

    def get_queryset(self):
        qs = super().get_queryset()
        statut = self.request.query_params.get("statut")
        type = self.request.query_params.get("type")
        if statut:
            qs = qs.filter(statut=statut)
        if type:
            qs = qs.filter(type=type)
        return qs

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)

    @action(detail=True, methods=["post"])
    def signer(self, request, pk=None):
        convention = self.get_object()
        try:
            convention.signer()
        except ValueError as exc:
            raise DRFValidationError(str(exc))
        return Response(self.get_serializer(convention).data)

    @action(detail=True, methods=["post"])
    def cloturer(self, request, pk=None):
        convention = self.get_object()
        try:
            convention.cloturer()
        except ValueError as exc:
            raise DRFValidationError(str(exc))
        return Response(self.get_serializer(convention).data)

    @action(detail=True, methods=["post"])
    def resilier(self, request, pk=None):
        convention = self.get_object()
        try:
            convention.resilier()
        except ValueError as exc:
            raise DRFValidationError(str(exc))
        return Response(self.get_serializer(convention).data)


class ContentieuxViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    """Contentieux (RF-ERP-B3, proc. 8.5)."""

    queryset = Contentieux.objects.select_related("document").all()
    serializer_class = ContentieuxSerializer

    def get_permissions(self):
        if self.action in ("instruire", "cloturer"):
            return [CanValidateJuridique()]
        return [CanManageJuridique()]

    def get_queryset(self):
        qs = super().get_queryset()
        statut = self.request.query_params.get("statut")
        nature = self.request.query_params.get("nature")
        if statut:
            qs = qs.filter(statut=statut)
        if nature:
            qs = qs.filter(nature=nature)
        return qs

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)

    @action(detail=True, methods=["post"])
    def instruire(self, request, pk=None):
        contentieux = self.get_object()
        try:
            contentieux.instruire()
        except ValueError as exc:
            raise DRFValidationError(str(exc))
        return Response(self.get_serializer(contentieux).data)

    @action(detail=True, methods=["post"])
    def cloturer(self, request, pk=None):
        contentieux = self.get_object()
        issue = request.data.get("issue")
        decision = request.data.get("decision", "")
        try:
            contentieux.cloturer(issue, decision)
        except ValueError as exc:
            raise DRFValidationError(str(exc))
        return Response(self.get_serializer(contentieux).data)


class CautionViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    """Cautions & garanties (RF-ERP-B4, proc. 8.6)."""

    queryset = Caution.objects.select_related("emetteur", "convention", "document").all()
    serializer_class = CautionSerializer

    def get_permissions(self):
        if self.action in ("lever", "appeler"):
            return [CanValidateJuridique()]
        return [CanManageJuridique()]

    def get_queryset(self):
        qs = super().get_queryset()
        statut = self.request.query_params.get("statut")
        if statut:
            qs = qs.filter(statut=statut)
        return qs

    @action(detail=True, methods=["post"])
    def lever(self, request, pk=None):
        caution = self.get_object()
        try:
            caution.lever()
        except ValueError as exc:
            raise DRFValidationError(str(exc))
        return Response(self.get_serializer(caution).data)

    @action(detail=True, methods=["post"])
    def appeler(self, request, pk=None):
        caution = self.get_object()
        try:
            caution.appeler()
        except ValueError as exc:
            raise DRFValidationError(str(exc))
        return Response(self.get_serializer(caution).data)


class AssuranceViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    """Assurances & sinistres (RF-ERP-B4, proc. 8.6)."""

    queryset = Assurance.objects.select_related("assureur", "document").all()
    serializer_class = AssuranceSerializer

    def get_permissions(self):
        if self.action in ("renouveler", "resilier", "declarer-sinistre"):
            return [CanValidateJuridique()]
        return [CanManageJuridique()]

    def get_queryset(self):
        qs = super().get_queryset()
        statut = self.request.query_params.get("statut")
        if statut:
            qs = qs.filter(statut=statut)
        return qs

    @action(detail=True, methods=["post"])
    def renouveler(self, request, pk=None):
        assurance = self.get_object()
        nouvelle_echeance = request.data.get("date_echeance")
        if nouvelle_echeance:
            nouvelle_echeance = _date.fromisoformat(nouvelle_echeance)
        assurance.renouveler(nouvelle_echeance)
        return Response(self.get_serializer(assurance).data)

    @action(detail=True, methods=["post"])
    def resilier(self, request, pk=None):
        assurance = self.get_object()
        try:
            assurance.resilier()
        except ValueError as exc:
            raise DRFValidationError(str(exc))
        return Response(self.get_serializer(assurance).data)

    @action(detail=True, methods=["post"], url_path="declarer-sinistre")
    def declarer_sinistre(self, request, pk=None):
        assurance = self.get_object()
        detail = request.data.get("detail", "")
        assurance.declarer_sinistre(detail)
        return Response(self.get_serializer(assurance).data)


class ReunionViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    """Réunions & comptes rendus (RF-ERP-B1, proc. 3.7)."""

    queryset = Reunion.objects.prefetch_related("participants").select_related(
        "animateur", "compte_rendu"
    ).all()
    serializer_class = ReunionSerializer
    permission_classes = [CanManageJuridique]

    def get_queryset(self):
        qs = super().get_queryset()
        statut = self.request.query_params.get("statut")
        if statut:
            qs = qs.filter(statut=statut)
        return qs

    def perform_create(self, serializer):
        reunion = serializer.save()
        if self.request.data.get("animateur"):
            reunion.animateur_id = self.request.data["animateur"]
            reunion.save(update_fields=["animateur"])
        participants = self.request.data.get("participants")
        if isinstance(participants, list):
            reunion.participants.set(participants)

    def perform_update(self, serializer):
        reunion = serializer.save()
        participants = self.request.data.get("participants")
        if isinstance(participants, list):
            reunion.participants.set(participants)

    @action(detail=True, methods=["post"])
    def tenir(self, request, pk=None):
        reunion = self.get_object()
        compte_rendu = request.data.get("compte_rendu")
        try:
            reunion.tenir(compte_rendu)
        except ValueError as exc:
            raise DRFValidationError(str(exc))
        return Response(self.get_serializer(reunion).data)

    @action(detail=True, methods=["post"])
    def cloturer(self, request, pk=None):
        reunion = self.get_object()
        try:
            reunion.cloturer()
        except ValueError as exc:
            raise DRFValidationError(str(exc))
        return Response(self.get_serializer(reunion).data)

    @action(detail=False, methods=["get"])
    def stats(self, request):
        return Response(compute_stats())


class DossierGlobalRentalViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    """Dossier intra-groupe GLOBAL RENTAL (RF-ERP-B4, fil rouge compte 618)."""

    queryset = DossierGlobalRental.objects.select_related("partenaire_gr", "affaire").all()
    serializer_class = DossierGlobalRentalSerializer
    permission_classes = [CanManageJuridique]

    def get_queryset(self):
        qs = super().get_queryset()
        statut = self.request.query_params.get("statut")
        if statut:
            qs = qs.filter(statut=statut)
        return qs

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)

    @action(detail=True, methods=["post"])
    def ouvrir(self, request, pk=None):
        dossier = self.get_object()
        try:
            dossier.ouvrir()
        except ValueError as exc:
            raise DRFValidationError(str(exc))
        return Response(self.get_serializer(dossier).data)

    @action(detail=True, methods=["post"])
    def cloturer(self, request, pk=None):
        dossier = self.get_object()
        try:
            dossier.cloturer()
        except ValueError as exc:
            raise DRFValidationError(str(exc))
        return Response(self.get_serializer(dossier).data)


@extend_schema(
    responses={200: OpenApiTypes.OBJECT},
    description="Alertes J-90 / J-60 / J-30 / expirées (RF-ERP-B0).",
)
class AlertesViewSet(viewsets.ViewSet):
    """Alertes J-90 / J-60 / J-30 / expirées (RF-ERP-B0)."""

    permission_classes = [IsAuthenticated]

    def list(self, request):
        return Response(compute_alertes())