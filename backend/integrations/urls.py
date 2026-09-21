from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ImportBatchViewSet, ImportFileView

router = DefaultRouter()
router.register("batches", ImportBatchViewSet, basename="importbatch")

urlpatterns = [
    path("import/", ImportFileView.as_view(), name="import-file"),
    path("", include(router.urls)),
]