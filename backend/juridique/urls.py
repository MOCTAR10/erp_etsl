from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AlertesViewSet,
    AssuranceViewSet,
    CautionViewSet,
    ContentieuxViewSet,
    ConventionViewSet,
    CourrierViewSet,
    DossierGlobalRentalViewSet,
    ReunionViewSet,
)

router = DefaultRouter()
router.register("courriers", CourrierViewSet, basename="juridique-courriers")
router.register("conventions", ConventionViewSet, basename="juridique-conventions")
router.register("contentieux", ContentieuxViewSet, basename="juridique-contentieux")
router.register("cautions", CautionViewSet, basename="juridique-cautions")
router.register("assurances", AssuranceViewSet, basename="juridique-assurances")
router.register("reunions", ReunionViewSet, basename="juridique-reunions")
router.register("dossiers-gr", DossierGlobalRentalViewSet, basename="juridique-dossiers-gr")
router.register("alertes", AlertesViewSet, basename="juridique-alertes")

urlpatterns = [
    path("", include(router.urls)),
]