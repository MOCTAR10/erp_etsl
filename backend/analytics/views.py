"""Vues Couche D — BI / décisionnel (RF-ERP-C0...C3).

Lecture seule pour tout utilisateur authentifié ; montants masqués selon le
pattern RF-59 (services). Aucune écriture exposée ici (les datamarts dbt /
Superset vivent sur le réplica lecteur).
"""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import (
    alertes_agregees,
    dashboard_direction,
    reporting_petrolier,
)


class DashboardDirectionView(APIView):
    """Tableau de bord Direction — KPIs consolidés des 12 modules (C1)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(dashboard_direction(request.user))


class ReportingPetrolierView(APIView):
    """Reporting client pétrolier — ASMR / HSE / Qualité (C2)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(reporting_petrolier(request.user))


class AlertesAgregeesView(APIView):
    """Alertes J-90 / J-60 / J-30 / expirées transverses (C3)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(alertes_agregees())