from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AnalyseEcartViewSet,
    BudgetLigneViewSet,
    BudgetRevisionViewSet,
    BudgetViewSet,
    ClotureGestionViewSet,
    ConsommationsStockView,
    AtterrissageView,
    DoctrineView,
    NiveauxMargeView,
    MargesView,
    GrAffairesView,
    ParametreGestionViewSet,
    SousActiviteView,
)

router = DefaultRouter()
router.register("budgets", BudgetViewSet, basename="cg-budgets")
router.register("budget-lignes", BudgetLigneViewSet, basename="cg-budget-lignes")
router.register("revisions", BudgetRevisionViewSet, basename="cg-revisions")
router.register("clotures", ClotureGestionViewSet, basename="cg-clotures")
router.register("marges", MargesView, basename="cg-marges")
router.register("consommations-stock", ConsommationsStockView, basename="cg-consommations-stock")
router.register("gr-affaires", GrAffairesView, basename="cg-gr-affaires")
router.register("sous-activite", SousActiviteView, basename="cg-sous-activite")
router.register("niveaux-marge", NiveauxMargeView, basename="cg-niveaux-marge")
router.register("atterrissage", AtterrissageView, basename="cg-atterrissage")
router.register("doctrine", DoctrineView, basename="cg-doctrine")
router.register("parametres", ParametreGestionViewSet, basename="cg-parametres")
router.register("analyses-ecart", AnalyseEcartViewSet, basename="cg-analyses-ecart")

urlpatterns = [
    path("", include(router.urls)),
]