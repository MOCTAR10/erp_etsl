"""Routes Couche D — BI / décisionnel (RF-ERP-C0...C3)."""

from django.urls import path

from .views import (
    AlertesAgregeesView,
    DashboardDirectionView,
    ReportingPetrolierView,
)

urlpatterns = [
    path("dashboard/", DashboardDirectionView.as_view(), name="analytics-dashboard"),
    path("petrolier/", ReportingPetrolierView.as_view(), name="analytics-petrolier"),
    path("alertes/", AlertesAgregeesView.as_view(), name="analytics-alertes"),
]