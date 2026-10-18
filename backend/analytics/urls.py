"""Routes Couche D — BI / décisionnel (RF-ERP-C0...C3) + cubes OLAP à 6 axes."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AlertesAgregeesView,
    CubeAlimenterView,
    CubeArchiveViewSet,
    CubeView,
    DashboardDirectionView,
    ParametreCubeViewSet,
    ReportingPetrolierView,
    TendancesView,
)

router = DefaultRouter()
router.register("cubes/archives", CubeArchiveViewSet, basename="cube-archive")
router.register("cubes/parametres", ParametreCubeViewSet, basename="cube-parametre")

urlpatterns = [
    path("dashboard/", DashboardDirectionView.as_view(), name="analytics-dashboard"),
    path("petrolier/", ReportingPetrolierView.as_view(), name="analytics-petrolier"),
    path("alertes/", AlertesAgregeesView.as_view(), name="analytics-alertes"),
    path("tendances/", TendancesView.as_view(), name="analytics-tendances"),
    path("cubes/", CubeView.as_view(), name="analytics-cube"),
    path("cubes/alimenter/", CubeAlimenterView.as_view(), name="analytics-cube-alimenter"),
    path("", include(router.urls)),
]
