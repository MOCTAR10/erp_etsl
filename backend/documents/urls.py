from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AuditLogViewSet, DocumentTypeViewSet, DocumentViewSet, DossierViewSet

router = DefaultRouter()
router.register("documents", DocumentViewSet, basename="documents")
router.register("dossiers", DossierViewSet, basename="dossiers")
router.register("types", DocumentTypeViewSet, basename="types")
router.register("audit", AuditLogViewSet, basename="audit")

urlpatterns = [
    path("", include(router.urls)),
]
