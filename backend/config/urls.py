"""Configuration des URLs du backend ETSL."""

from django.contrib import admin
from django.urls import include, path

from .views import health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
    path("api/users/", include("users.urls")),
    path("api/documents/", include("documents.urls")),
]
