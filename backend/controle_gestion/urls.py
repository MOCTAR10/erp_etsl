from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    BudgetLigneViewSet,
    BudgetRevisionViewSet,
    BudgetViewSet,
    ClotureGestionViewSet,
    MargesView,
)

router = DefaultRouter()
router.register("budgets", BudgetViewSet, basename="cg-budgets")
router.register("budget-lignes", BudgetLigneViewSet, basename="cg-budget-lignes")
router.register("revisions", BudgetRevisionViewSet, basename="cg-revisions")
router.register("clotures", ClotureGestionViewSet, basename="cg-clotures")
router.register("marges", MargesView, basename="cg-marges")

urlpatterns = [
    path("", include(router.urls)),
]