from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ActionHseViewSet,
    BordereauDechetViewSet,
    EpiViewSet,
    EquipementAtexViewSet,
    EvaluationRisqueViewSet,
    FormationSecuriteViewSet,
    IncidentViewSet,
    PermisTravailViewSet,
)

router = DefaultRouter()
router.register("permis", PermisTravailViewSet, basename="permis")
router.register("incidents", IncidentViewSet, basename="incidents")
router.register("evaluations-risques", EvaluationRisqueViewSet, basename="evaluations-risques")
router.register("equipements-atex", EquipementAtexViewSet, basename="equipements-atex")
router.register("actions", ActionHseViewSet, basename="actions")
router.register("formations", FormationSecuriteViewSet, basename="formations")
router.register("epis", EpiViewSet, basename="epis")
router.register("bordereaux-dechets", BordereauDechetViewSet, basename="bordereaux-dechets")

urlpatterns = [
    path("", include(router.urls)),
]