from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AccountViewSet,
    AnalyticAccountViewSet,
    AnalyticAxisViewSet,
    AnnexeViewSet,
    ArticleViewSet,
    CurrencyViewSet,
    PartnerViewSet,
    UnitOfMeasureViewSet,
)

router = DefaultRouter()
router.register("annexes", AnnexeViewSet, basename="annexes")
router.register("currencies", CurrencyViewSet, basename="currency")
router.register("units", UnitOfMeasureViewSet, basename="unit")
router.register("accounts", AccountViewSet, basename="account")
router.register("partners", PartnerViewSet, basename="partner")
router.register("articles", ArticleViewSet, basename="article")
router.register("analytic-axes", AnalyticAxisViewSet, basename="analyticaxis")
router.register("analytic-accounts", AnalyticAccountViewSet, basename="analyticaccount")

urlpatterns = [
    path("", include(router.urls)),
]
