from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ActionCorrectiveViewSet,
    ControleQualiteViewSet,
    NonConformiteViewSet,
    PvControleViewSet,
    QualificationSoudeurViewSet,
    SoudeurViewSet,
    WpsWpqrViewSet,
)

router = DefaultRouter()
router.register("soudeurs", SoudeurViewSet, basename="soudeurs")
router.register("qualifications", QualificationSoudeurViewSet, basename="qualifications")
router.register("wps", WpsWpqrViewSet, basename="wps")
router.register("controles", ControleQualiteViewSet, basename="controles")
router.register("pvs", PvControleViewSet, basename="pvs")
router.register("non-conformites", NonConformiteViewSet, basename="non-conformites")
router.register("actions-correctives", ActionCorrectiveViewSet, basename="actions-correctives")

urlpatterns = [
    path("", include(router.urls)),
]