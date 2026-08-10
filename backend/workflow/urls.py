from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CircuitViewSet, TaskViewSet

router = DefaultRouter()
router.register("circuits", CircuitViewSet, basename="circuits")
router.register("tasks", TaskViewSet, basename="tasks")

urlpatterns = [
    path("", include(router.urls)),
]
