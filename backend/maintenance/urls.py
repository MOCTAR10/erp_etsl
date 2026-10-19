from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ActifViewSet,
    ExigenceHabilitationMaintenanceViewSet,
    InspectionViewSet,
    OrdreTravailViewSet,
    ParametreMaintenanceViewSet,
    PiecesViewSet,
    PlanPreventifViewSet,
)

router = DefaultRouter()
router.register("actifs", ActifViewSet, basename="actifs")
router.register("ordres", OrdreTravailViewSet, basename="ordres")
router.register("inspections", InspectionViewSet, basename="inspections")
router.register("plans", PlanPreventifViewSet, basename="plans")
router.register("exigences-habilitation", ExigenceHabilitationMaintenanceViewSet, basename="exigences-habilitation")
router.register("parametres", ParametreMaintenanceViewSet, basename="parametremaintenance")
router.register("pieces", PiecesViewSet, basename="pieces")

urlpatterns = [
    path("", include(router.urls)),
]