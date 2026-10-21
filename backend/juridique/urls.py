from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ActionContentieuxViewSet,
    JalonContentieuxViewSet,
    ParametreJuridiqueViewSet,
    PieceDossierViewSet,
    RisquesViewSet,
    AlertesViewSet,
    AssuranceViewSet,
    CautionViewSet,
    ContentieuxViewSet,
    ConventionViewSet,
    CourrierViewSet,
    DossierGlobalRentalViewSet,
    LienDocumentViewSet,
    RechercheJuridiqueView,
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
router.register("liens", LienDocumentViewSet, basename="juridique-liens")
router.register("recherche", RechercheJuridiqueView, basename="juridique-recherche")
router.register("alertes", AlertesViewSet, basename="juridique-alertes")
router.register("parametres", ParametreJuridiqueViewSet, basename="juridique-parametres")
router.register("jalons", JalonContentieuxViewSet, basename="juridique-jalons")
router.register("actions-contentieux", ActionContentieuxViewSet, basename="juridique-actions-contentieux")
router.register("pieces", PieceDossierViewSet, basename="juridique-pieces")
router.register("risques", RisquesViewSet, basename="juridique-risques")

urlpatterns = [
    path("", include(router.urls)),
]