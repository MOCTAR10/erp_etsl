from django.urls import path

from . import views

urlpatterns = [
    path("export/", views.ExportView.as_view(), name="report-export"),
    path("sage/", views.SageExportView.as_view(), name="sage-export"),
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path("retention/", views.RetentionReportView.as_view(), name="retention-report"),
]
