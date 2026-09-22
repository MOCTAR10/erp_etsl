from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AffectationParcViewSet,
    DemandeMobilisationViewSet,
    EquipementParcViewSet,
    LectureCompteurViewSet,
    LocationGRViewSet,
)

router = DefaultRouter()
router.register("equipements", EquipementParcViewSet, basename="equipementparc")
router.register("demandes", DemandeMobilisationViewSet, basename="demandemobilisation")
router.register("affectations", AffectationParcViewSet, basename="affectationparc")
router.register("locations", LocationGRViewSet, basename="locationgr")
router.register("lectures", LectureCompteurViewSet, basename="lecturecompteur")

urlpatterns = [
    path("", include(router.urls)),
]