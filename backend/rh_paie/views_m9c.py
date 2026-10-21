"""Écarts M9-C : catalogue et plan de formation, matrice habilitation ↔ poste."""

from rest_framework import viewsets

from .models import CatalogueFormation, HabilitationPoste, PlanFormation
from .serializers import CatalogueFormationSerializer, HabilitationPosteSerializer, PlanFormationSerializer
from .services import CanManageRh


class CatalogueFormationViewSet(viewsets.ModelViewSet):
    queryset = CatalogueFormation.objects.all()
    serializer_class = CatalogueFormationSerializer
    permission_classes = [CanManageRh]
    http_method_names = ["get", "post", "patch", "head", "options"]


class PlanFormationViewSet(viewsets.ModelViewSet):
    """Plan annuel : budget voté, coût engagé / réalisé, taux de réalisation, ROI (synthèse calculée)."""

    queryset = PlanFormation.objects.all()
    serializer_class = PlanFormationSerializer
    permission_classes = [CanManageRh]
    http_method_names = ["get", "post", "patch", "head", "options"]


class HabilitationPosteViewSet(viewsets.ModelViewSet):
    queryset = HabilitationPoste.objects.all()
    serializer_class = HabilitationPosteSerializer
    permission_classes = [CanManageRh]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
