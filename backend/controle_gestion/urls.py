from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views_m11 as m11
from . import views_suivi as suivi
from .views import (
    AnalyseEcartViewSet,
    BudgetLigneViewSet,
    BudgetRevisionViewSet,
    BudgetViewSet,
    ClotureGestionViewSet,
    ConsommationsStockView,
    CoutsHseView,
    AtterrissageView,
    DoctrineView,
    NiveauxMargeView,
    MargesView,
    GrAffairesView,
    MaintenanceCoutsView,
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
router.register("maintenance-couts", MaintenanceCoutsView, basename="cg-maintenance-couts")
router.register("couts-hse", CoutsHseView, basename="cg-couts-hse")
router.register("sous-activite", SousActiviteView, basename="cg-sous-activite")
router.register("niveaux-marge", NiveauxMargeView, basename="cg-niveaux-marge")
router.register("atterrissage", AtterrissageView, basename="cg-atterrissage")
router.register("doctrine", DoctrineView, basename="cg-doctrine")
router.register("parametres", ParametreGestionViewSet, basename="cg-parametres")
router.register("analyses-ecart", AnalyseEcartViewSet, basename="cg-analyses-ecart")
# Écarts M11 (2026-10-21)
router.register("revision-lignes", m11.BudgetRevisionLigneViewSet, basename="cg-revision-lignes")
router.register("axes", m11.AxeGestionViewSet, basename="cg-axes")
router.register("valeurs-axes", m11.ValeurAxeViewSet, basename="cg-valeurs-axes")
router.register("imputation-structure", m11.ImputationStructureView, basename="cg-imputation-structure")
router.register("pipe-budget", m11.PipeBudgetView, basename="cg-pipe-budget")
router.register("kpis", m11.KpiView, basename="cg-kpis")
router.register("tableau-bord", m11.TableauBordView, basename="cg-tableau-bord")
router.register("cout-mo-affaires", m11.CoutMoAffairesView, basename="cg-cout-mo-affaires")
router.register("marges-affaires", m11.MargeAffaireViewSet, basename="cg-marges-affaires")
router.register("plans-sous-activite", m11.PlanActionViewSet, basename="cg-plans-sous-activite")
router.register("reportings", m11.ReportingViewSet, basename="cg-reportings")
router.register("revues-performance", m11.RevuePerformanceViewSet, basename="cg-revues-performance")
router.register("provisions-fnp", m11.ProvisionFnpViewSet, basename="cg-provisions-fnp")
# Suivi inter-modules (M3 → M11, M10 → M11)
router.register("marges-terminaison", suivi.MargesTerminaisonView, basename="cg-marges-terminaison")
router.register("balance-agee", suivi.BalanceAgeeGestionView, basename="cg-balance-agee")

urlpatterns = [
    path("", include(router.urls)),
]