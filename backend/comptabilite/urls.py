from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CompteBancaireViewSet,
    ControleInterneViewSet,
    DeclarationTvaViewSet,
    EngagementViewSet,
    PaiementViewSet,
    RapprochementBancaireViewSet,
    ReleveBancaireViewSet,
    TauxTvaViewSet,
)

router = DefaultRouter()
router.register("taux-tva", TauxTvaViewSet, basename="compta-taux-tva")
router.register("comptes-bancaires", CompteBancaireViewSet, basename="compta-comptes-bancaires")
router.register("releves", ReleveBancaireViewSet, basename="compta-releves")
router.register("rapprochements", RapprochementBancaireViewSet, basename="compta-rapprochements")
router.register("engagements", EngagementViewSet, basename="compta-engagements")
router.register("paiements", PaiementViewSet, basename="compta-paiements")
router.register("declarations-tva", DeclarationTvaViewSet, basename="compta-declarations-tva")
router.register("controles", ControleInterneViewSet, basename="compta-controles")

urlpatterns = [
    path("", include(router.urls)),
]