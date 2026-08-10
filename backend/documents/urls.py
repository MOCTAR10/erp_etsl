from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import DocumentTypeViewSet, DocumentViewSet, DossierViewSet

router = DefaultRouter()
router.register("documents", DocumentViewSet, basename="documents")
router.register("dossiers", DossierViewSet, basename="dossiers")
router.register("types", DocumentTypeViewSet, basename="types")

urlpatterns = [
    path("", include(router.urls)),
]
