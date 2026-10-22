from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .parametres import ParametreGedViewSet
from .purge import DemandePurgeViewSet
from .signature_views import SignatureRequestViewSet
from .views import AuditLogViewSet, DocumentTypeViewSet, DocumentViewSet, DossierViewSet

router = DefaultRouter()
router.register("documents", DocumentViewSet, basename="documents")
router.register("dossiers", DossierViewSet, basename="dossiers")
router.register("types", DocumentTypeViewSet, basename="types")
router.register("audit", AuditLogViewSet, basename="audit")
router.register("signatures", SignatureRequestViewSet, basename="signatures")
router.register("purges", DemandePurgeViewSet, basename="purges")
router.register("parametres", ParametreGedViewSet, basename="parametres-ged")

urlpatterns = [
    path("", include(router.urls)),
]
