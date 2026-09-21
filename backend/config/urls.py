"""Configuration des URLs du backend ETSL."""

from django.contrib import admin
from django.urls import include, path

from .views import health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
    path("api/users/", include("users.urls")),
    path("api/documents/", include("documents.urls")),
    path("api/workflow/", include("workflow.urls")),
    path("api/reports/", include("reports.urls")),
    path("api/referentiels/", include("referentiels.urls")),
    path("api/registres/", include("registres.urls")),
    path("api/accounting/", include("accounting_kernel.urls")),
    path("api/integrations/", include("integrations.urls")),
    path("api/outbox/", include("outbox.urls")),
    path("api/commercial/", include("commercial.urls")),
]
