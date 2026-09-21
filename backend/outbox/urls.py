from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import OutboxEventViewSet

router = DefaultRouter()
router.register("events", OutboxEventViewSet, basename="outboxevent")

urlpatterns = [
    path("", include(router.urls)),
]