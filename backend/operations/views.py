"""API module M3 — Opérations (Atelier + Chantier) (RF-ERP-20…23)."""

from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import (
    GammeOperatoire,
    GammeOperation,
    OrdreFabrication,
    PointageChantier,
    SituationTravaux,
)
from .serializers import (
    GammeOperatoireSerializer,
    GammeOperationSerializer,
    OrdreFabricationSerializer,
    PointageChantierSerializer,
    SituationTravauxSerializer,
)
from .services import CanManageOperations, can_see_amount, charge_stats


class _CommonViewSet(viewsets.ModelViewSet):
    """Lecture authentifiée ; écriture réservée aux rôles Opérations."""

    http_method_names = ["get", "post", "patch", "delete"]

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [IsAuthenticated()]
        return [CanManageOperations()]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["can_view_amount"] = can_see_amount(self.request.user)
        return context


class GammeViewSet(_CommonViewSet):
    serializer_class = GammeOperatoireSerializer

    def get_queryset(self):
        qs = GammeOperatoire.objects.all()
        status_ = self.request.query_params.get("status")
        if status_:
            qs = qs.filter(status=status_)
        return qs


class GammeOperationViewSet(_CommonViewSet):
    serializer_class = GammeOperationSerializer

    def get_queryset(self):
        qs = GammeOperation.objects.select_related("gamme").all()
        gamme = self.request.query_params.get("gamme")
        if gamme:
            qs = qs.filter(gamme_id=gamme)
        return qs


class OrdreFabricationViewSet(_CommonViewSet):
    serializer_class = OrdreFabricationSerializer

    def get_queryset(self):
        qs = OrdreFabrication.objects.select_related(
            "affaire", "gamme", "article", "responsible"
        )
        status_ = self.request.query_params.get("status")
        if status_:
            qs = qs.filter(status=status_)
        scope = self.request.query_params.get("scope")
        if scope:
            qs = qs.filter(scope=scope)
        affaire = self.request.query_params.get("affaire")
        if affaire:
            qs = qs.filter(affaire_id=affaire)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=False, methods=["get"], url_path="charge")
    def charge(self, request):
        """Plan de charge & capacité atelier (RF-ERP-23)."""
        return Response(charge_stats())


class PointageChantierViewSet(_CommonViewSet):
    serializer_class = PointageChantierSerializer

    def get_queryset(self):
        qs = PointageChantier.objects.select_related("ordre", "worker").all()
        ordre = self.request.query_params.get("ordre")
        if ordre:
            qs = qs.filter(ordre_id=ordre)
        status_ = self.request.query_params.get("status")
        if status_:
            qs = qs.filter(status=status_)
        if self.request.query_params.get("from"):
            qs = qs.filter(date__gte=self.request.query_params["from"])
        if self.request.query_params.get("to"):
            qs = qs.filter(date__lte=self.request.query_params["to"])
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class SituationTravauxViewSet(_CommonViewSet):
    serializer_class = SituationTravauxSerializer

    def get_queryset(self):
        qs = SituationTravaux.objects.select_related("affaire", "created_by", "validated_by").all()
        status_ = self.request.query_params.get("status")
        if status_:
            qs = qs.filter(status=status_)
        affaire = self.request.query_params.get("affaire")
        if affaire:
            qs = qs.filter(affaire_id=affaire)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"], url_path="validate")
    def validate(self, request, pk=None):
        """Validation d'une situation de travaux (RF-ERP-22)."""
        situation = self.get_object()
        situation.status = SituationTravaux.Status.VALIDEE
        situation.validated_by = request.user
        situation.validated_at = timezone.now()
        situation.save(update_fields=["status", "validated_by", "validated_at", "updated_at"])
        return Response(self.get_serializer(situation).data)