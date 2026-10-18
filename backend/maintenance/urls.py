from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ActifViewSet,
    InspectionViewSet,
    OrdreTravailViewSet,
    ParametreMaintenanceViewSet,
    PlanPreventifViewSet,
)

router = DefaultRouter()
router.register("actifs", ActifViewSet, basename="actifs")
router.register("ordres", OrdreTravailViewSet, basename="ordres")
router.register("inspections", InspectionViewSet, basename="inspections")
router.register("plans", PlanPreventifViewSet, basename="plans")
router.register("parametres", ParametreMaintenanceViewSet, basename="parametremaintenance")

urlpatterns = [
    path("", include(router.urls)),
]