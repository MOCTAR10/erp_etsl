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
from .views import ImportBatchViewSet, ImportFileView

router = DefaultRouter()
router.register("batches", ImportBatchViewSet, basename="importbatch")
router.register("api-clients", ApiClientViewSet, basename="api-client")
router.register("webhooks", WebhookEndpointViewSet, basename="webhook-endpoint")
router.register("webhook-deliveries", WebhookDeliveryViewSet, basename="webhook-delivery")

urlpatterns = [
    path("import/", ImportFileView.as_view(), name="import-file"),
    path("gr/equipements/", GrEquipementsView.as_view(), name="gr-equipements"),
    path("gr/locations/", GrLocationsView.as_view(), name="gr-locations"),
    path("gr/compteurs/", GrCompteursView.as_view(), name="gr-compteurs"),
    path("gr/documents/", GrDocumentsView.as_view(), name="gr-documents"),
    path("", include(router.urls)),
]