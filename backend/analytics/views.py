"""Vues Couche D — BI / décisionnel (RF-ERP-C0...C3).

Lecture seule pour tout utilisateur authentifié ; montants masqués selon le
pattern RF-59 (services). Aucune écriture exposée ici (les datamarts dbt /
Superset vivent sur le réplica lecteur).
"""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import (
    alertes_agregees,
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
        return Response(alertes_agregees())