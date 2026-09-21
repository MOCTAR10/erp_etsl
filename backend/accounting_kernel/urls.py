from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AccountMoveLineViewSet,
    AccountMoveViewSet,
    FiscalYearViewSet,
    JournalViewSet,
    PeriodViewSet,
    SequenceViewSet,
)

router = DefaultRouter()
router.register("fiscal-years", FiscalYearViewSet, basename="fiscalyear")
router.register("periods", PeriodViewSet, basename="period")
router.register("journals", JournalViewSet, basename="journal")
router.register("sequences", SequenceViewSet, basename="sequence")
router.register("moves", AccountMoveViewSet, basename="accountmove")
router.register("lines", AccountMoveLineViewSet, basename="accountmoveline")

urlpatterns = [
    path("", include(router.urls)),
]
