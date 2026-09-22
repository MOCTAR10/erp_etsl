from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ActifViewSet, InspectionViewSet, OrdreTravailViewSet

router = DefaultRouter()
router.register("actifs", ActifViewSet, basename="actifs")
router.register("ordres", OrdreTravailViewSet, basename="ordres")
router.register("inspections", InspectionViewSet, basename="inspections")

urlpatterns = [
    path("", include(router.urls)),
]