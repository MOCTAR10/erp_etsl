"""Routes de la reprise de données (préfixe `migration/`, CDC §10)."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views_migration import (
    CatalogueView,
    HistoriquePaieViewSet,
    ImportRepriseView,
    LotRepriseViewSet,
    ModeleView,
    ParametreRepriseViewSet,
    RapprochementView,
)

router = DefaultRouter()
router.register("lots", LotRepriseViewSet, basename="lot-reprise")
router.register("parametres", ParametreRepriseViewSet, basename="parametre-reprise")
router.register("historique-paie", HistoriquePaieViewSet, basename="historique-paie-reprise")

urlpatterns = [
    path("catalogue/", CatalogueView.as_view(), name="reprise-catalogue"),
    path("modele/", ModeleView.as_view(), name="reprise-modele"),
    path("import/", ImportRepriseView.as_view(), name="reprise-import"),
    path("rapprochements/", RapprochementView.as_view(), name="reprise-rapprochements"),
    path("", include(router.urls)),
]
