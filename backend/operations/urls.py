from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AffectationEquipeViewSet,
    EquipeViewSet,
    PresenceChantierViewSet,
    CapaciteAtelierViewSet,
    DossierOperationnelViewSet,
    GammeOperationViewSet,
    GammeViewSet,
    OrdreFabricationViewSet,
    PointageChantierViewSet,
    SituationTravauxViewSet,
)

router = DefaultRouter()
router.register("gammes", GammeViewSet, basename="gamme")
router.register("gamme-operations", GammeOperationViewSet, basename="gammeoperation")
router.register("ordres", OrdreFabricationViewSet, basename="ordrefabrication")
router.register("pointages", PointageChantierViewSet, basename="pointagechantier")
router.register("capacites", CapaciteAtelierViewSet, basename="capaciteatelier")
router.register("dossiers", DossierOperationnelViewSet, basename="dossieroperationnel")
router.register("equipes", EquipeViewSet, basename="equipe")
router.register("affectations", AffectationEquipeViewSet, basename="affectationequipe")
router.register("presences", PresenceChantierViewSet, basename="presencechantier")
router.register("situations", SituationTravauxViewSet, basename="situationtravaux")

urlpatterns = [
    path("", include(router.urls)),
]