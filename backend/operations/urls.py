from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    GammeOperationViewSet,
    GammeViewSet,
    OrdreFabricationViewSet,
    PointageChantierViewSet,
    SituationTravauxViewSet,
)

router = DefaultRouter()
router.register("gammes", GammeViewSet, basename="gamme")
router.register("gamme-operations", GammeOperationViewSet, basename="gammeoperation")
router.register("ordres", OrdreFabricationViewSet, basename="ordrefabrication")
router.register("pointages", PointageChantierViewSet, basename="pointagechantier")
router.register("situations", SituationTravauxViewSet, basename="situationtravaux")

urlpatterns = [
    path("", include(router.urls)),
]