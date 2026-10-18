"""Vues Couche D — BI / décisionnel (RF-ERP-C0...C3).

Lecture seule pour tout utilisateur authentifié ; montants masqués selon le
pattern RF-59 (services). Aucune écriture exposée ici (les datamarts dbt /
Superset vivent sur le réplica lecteur).
"""

from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from controle_gestion.services import can_manage_gestion, can_see_amount

from . import cubes
from .models import CubeArchive, ParametreCube
from .serializers import CubeArchiveSerializer, ParametreCubeSerializer

from .services import (
    alertes_agregees,
    tendances,
    dashboard_direction,
    reporting_petrolier,
)


@extend_schema(
    responses={200: OpenApiTypes.OBJECT},
    description="Tableau de bord Direction — KPIs consolidés des 12 modules (C1).",
)
class DashboardDirectionView(APIView):
    """Tableau de bord Direction — KPIs consolidés des 12 modules (C1)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(dashboard_direction(request.user))


@extend_schema(
    responses={200: OpenApiTypes.OBJECT},
    description="Reporting client pétrolier — ASMR / HSE / Qualité (C2).",
)
class ReportingPetrolierView(APIView):
    """Reporting client pétrolier — ASMR / HSE / Qualité (C2)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(reporting_petrolier(request.user))


@extend_schema(
    responses={200: OpenApiTypes.OBJECT},
    description="Alertes J-90 / J-60 / J-30 / expirées transverses (C3).",
)
class AlertesAgregeesView(APIView):
    """Alertes J-90 / J-60 / J-30 / expirées transverses (C3)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(alertes_agregees(request.user))


@extend_schema(
    responses={200: OpenApiTypes.OBJECT},
    description="Tendances mensuelles (6 mois) non financières du cockpit Direction, filtrées par droits.",
)
class TendancesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(tendances(request.user))


class CanReadCube(BasePermission):
    """Les cubes portent des montants : lecture = cercle des montants M11 ; alimentation / archivage = gestion."""

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated):
            return False
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return can_see_amount(user)
        return can_manage_gestion(user)


def _erreur(exc):
    return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    parameters=[
        OpenApiParameter("periode", str, description="AAAA-MM (plusieurs, séparées par une virgule)."),
        OpenApiParameter("axes", str, description="Axes de lecture : affaire, chantier, site, activite, centre, periode."),
    ],
    responses={200: OpenApiTypes.OBJECT},
    description="Cube OLAP à 6 axes (affaire, chantier, site, activité, centre, période) : coupe agrégée (Couche D).",
)
class CubeView(APIView):
    permission_classes = [CanReadCube]

    def get(self, request):
        p = request.query_params
        periodes = [x for x in p.get("periode", "").split(",") if x] or None
        axes = tuple(x for x in p.get("axes", "periode").split(",") if x) or ("periode",)
        filtres = {a: p.get(a) for a in cubes.AXES if a != "periode" and p.get(a)}
        try:
            for per in periodes or ():
                cubes._bornes(per)
            return Response(cubes.lire_cube(periodes, axes, filtres))
        except ValueError as exc:
            return _erreur(exc)


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT})
class CubeAlimenterView(APIView):
    """Alimente (ou ré-alimente) les faits d'un mois depuis le grand livre — idempotent."""

    permission_classes = [CanReadCube]

    def post(self, request):
        periode = request.data.get("periode", "")
        try:
            return Response({"periode": periode, "faits": cubes.alimenter_cube(periode)})
        except ValueError as exc:
            return _erreur(exc)


class CubeArchiveViewSet(viewsets.ReadOnlyModelViewSet):
    """Archives de cubes figées, scellées et conservées 10 ans (lecture seule)."""

    queryset = CubeArchive.objects.all()
    serializer_class = CubeArchiveSerializer
    permission_classes = [CanReadCube]
    lookup_field = "periode"

    @extend_schema(request=OpenApiTypes.OBJECT, responses={201: CubeArchiveSerializer})
    @action(detail=False, methods=["post"], url_path="archiver")
    def archiver(self, request):
        try:
            archive = cubes.archiver_cube(request.data.get("periode", ""), request.user)
        except ValueError as exc:
            return _erreur(exc)
        return Response(self.get_serializer(archive).data, status=status.HTTP_201_CREATED)


class ParametreCubeViewSet(viewsets.ModelViewSet):
    """Paramètres du cube modifiables par ETSL ; création/suppression interdites (définis par le code)."""

    queryset = ParametreCube.objects.all()
    serializer_class = ParametreCubeSerializer
    permission_classes = [CanReadCube]
    http_method_names = ["get", "patch", "post", "head", "options"]

    def get_queryset(self):
        for code in cubes.PARAMETRES_DEFAUT:
            cubes.get_param_cube(code)
        return super().get_queryset()

    def create(self, request, *args, **kwargs):
        return Response({"detail": "Les paramètres sont prédéfinis : modifiez leur valeur."}, status=405)

    @action(detail=True, methods=["post"], url_path="confirmer")
    def confirmer(self, request, pk=None):
        p = self.get_object()
        p.statut_valeur = ParametreCube.StatutValeur.CONFIRME
        p.confirme_par = request.user
        p.confirme_le = timezone.now()
        p.save(update_fields=["statut_valeur", "confirme_par", "confirme_le"])
        return Response(self.get_serializer(p).data)
