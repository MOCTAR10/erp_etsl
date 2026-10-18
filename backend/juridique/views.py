"""API module M12 — Juridique & GED (RF-ERP-B0...B4)."""

from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import OpenApiParameter
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from .models import (
    Assurance,
    Caution,
    Contentieux,
    Convention,
    Courrier,
    DossierGlobalRental,
    LienDocument,
    Reunion,
)
from .serializers import (
    LienDocumentSerializer,
    AssuranceSerializer,
    CautionSerializer,
    ContentieuxSerializer,
    ConventionSerializer,
    CourrierSerializer,
    DossierGlobalRentalSerializer,
    ReunionSerializer,
)
from config.inputs import date_input
from users.permissions import can_read_module
from .services import (
    CanValidateDg,
    CanManageJuridique,
    RECHERCHE_MIN,
    rechercher_documents,
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
    search_fields = ("code", "objet", "reference",)
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
        try:
            courrier.enregistrer()
        except ValueError as exc:
            raise DRFValidationError(str(exc))
        return Response(self.get_serializer(courrier).data)

    @action(detail=True, methods=["post"])
    def classer(self, request, pk=None):
        courrier = self.get_object()
        try:
            courrier.classer()
        except ValueError as exc:
            raise DRFValidationError(str(exc))
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
    search_fields = ("code", "titre",)

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
    search_fields = ("code", "objet", "partie_adverse",)

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
    search_fields = ("code", "beneficiaire", "objet",)

    def get_permissions(self):
        if self.action in ("lever", "appeler", "valider_dg"):
            return [CanValidateDg()]
        return [CanManageJuridique()]

    @action(detail=True, methods=["post"], url_path="valider-dg")
    def valider_dg(self, request, pk=None):
        obj = self.get_object()
        if obj.valide_dg_par_id:
            raise DRFValidationError("Déjà validée par la Direction Générale.")
        obj.valide_dg_par = request.user
        obj.valide_dg_le = timezone.now()
        obj.save(update_fields=["valide_dg_par", "valide_dg_le", "updated_at"])
        return Response(self.get_serializer(obj).data)

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
    search_fields = ("code", "numero_police",)

    def get_permissions(self):
        # NB : self.action = nom de la MÉTHODE (declarer_sinistre), pas l'url_path (bug corrigé : la permission
        # de déclaration de sinistre ne s'appliquait jamais).
        if self.action in ("renouveler", "resilier", "valider_dg"):
            return [CanValidateDg()]
        if self.action == "declarer_sinistre":
            return [CanValidateJuridique()]
        return [CanManageJuridique()]

    @action(detail=True, methods=["post"], url_path="valider-dg")
    def valider_dg(self, request, pk=None):
        obj = self.get_object()
        if obj.valide_dg_par_id:
            raise DRFValidationError("Déjà validée par la Direction Générale.")
        obj.valide_dg_par = request.user
        obj.valide_dg_le = timezone.now()
        obj.save(update_fields=["valide_dg_par", "valide_dg_le", "updated_at"])
        return Response(self.get_serializer(obj).data)

    def get_queryset(self):
        qs = super().get_queryset()
        statut = self.request.query_params.get("statut")
        if statut:
            qs = qs.filter(statut=statut)
        return qs

    @action(detail=True, methods=["post"])
    def renouveler(self, request, pk=None):
        assurance = self.get_object()
        nouvelle_echeance = date_input(request.data.get("date_echeance"), "date_echeance")
        try:
            assurance.renouveler(nouvelle_echeance)
        except ValueError as exc:
            raise DRFValidationError(str(exc))
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
    search_fields = ("code", "objet",)
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
    search_fields = ("code", "reference_contrat", "objet",)
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

    permission_classes = [can_read_module("juridique")]

    def list(self, request):
        return Response(compute_alertes())


class LienDocumentViewSet(viewsets.ModelViewSet):
    """Liens document GED ↔ objet métier M1-M11 (recherche juridique interconnectée, clôture M12)."""

    serializer_class = LienDocumentSerializer
    permission_classes = [CanManageJuridique]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        from documents.services import visible_documents

        qs = LienDocument.objects.select_related("document").filter(
            document__in=visible_documents(self.request.user)
        )
        params = self.request.query_params
        if document := params.get("document"):
            qs = qs.filter(document_id=document)
        if objet_type := params.get("objet_type"):
            qs = qs.filter(objet_type=objet_type)
        if objet_id := params.get("objet_id"):
            qs = qs.filter(objet_id=objet_id)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class RechercheJuridiqueView(viewsets.ViewSet):
    """Recherche transverse : documents GED (ACL respectées) retrouvés par leur texte ou par un objet métier lié."""

    permission_classes = [can_read_module("juridique")]

    @extend_schema(
        parameters=[
            OpenApiParameter("q", type=str, required=True),
            OpenApiParameter("module", type=str, required=False),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def list(self, request):
        q = (request.query_params.get("q") or "").strip()
        if len(q) < RECHERCHE_MIN:
            raise DRFValidationError(f"Saisissez au moins {RECHERCHE_MIN} caractères.")
        module = request.query_params.get("module") or None
        docs = rechercher_documents(request.user, q, module)
        return Response({
            "q": q,
            "documents": [
                {
                    "id": str(d.pk), "title": d.title, "status": d.status, "reference": d.reference,
                    "counterparty": d.counterparty,
                    "liens": [
                        {"objet_type": l.objet_type, "objet_id": l.objet_id, "objet_label": l.objet_label, "module": l.module}
                        for l in d.liens_metier.all()
                    ],
                }
                for d in docs
            ],
        })
