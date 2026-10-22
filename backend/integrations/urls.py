from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .gr_views import (
    ApiClientViewSet,
    GrCompteursView,
    GrDocumentsView,
    GrEquipementsView,
    GrLocationsView,
    WebhookDeliveryViewSet,
    WebhookEndpointViewSet,
)
from .views_export import ExportSageViewSet
from .views import GabaritImportViewSet, ImportBatchViewSet, ImportFileView, OpeningBalanceView

router = DefaultRouter()
router.register("batches", ImportBatchViewSet, basename="importbatch")
router.register("gabarits", GabaritImportViewSet, basename="gabarit-import")
router.register("exports-sage", ExportSageViewSet, basename="export-sage")
router.register("api-clients", ApiClientViewSet, basename="api-client")
router.register("webhooks", WebhookEndpointViewSet, basename="webhook-endpoint")
router.register("webhook-deliveries", WebhookDeliveryViewSet, basename="webhook-delivery")

urlpatterns = [
    path("import/", ImportFileView.as_view(), name="import-file"),
    path("opening-balances/", OpeningBalanceView.as_view(), name="opening-balances"),
    path("gr/equipements/", GrEquipementsView.as_view(), name="gr-equipements"),
    path("gr/locations/", GrLocationsView.as_view(), name="gr-locations"),
    path("gr/compteurs/", GrCompteursView.as_view(), name="gr-compteurs"),
    path("gr/documents/", GrDocumentsView.as_view(), name="gr-documents"),
    path("", include(router.urls)),
]

# Reprise de données (CDC §10) : gabarits CSV / XML / ZIP GED, à blanc, rapprochements C1-C10.
urlpatterns += [path("migration/", include("integrations.urls_migration"))]
