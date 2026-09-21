from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import RegistreEntryViewSet, RegistreViewSet

router = DefaultRouter()
router.register("registres", RegistreViewSet, basename="registre")
router.register("entries", RegistreEntryViewSet, basename="registreentry")

urlpatterns = [path("", include(router.urls))]
