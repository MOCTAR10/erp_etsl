from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AttachementViewSet,
    BesoinMatiereViewSet,
    BonTransfertViewSet,
    EscaladeSurchargeViewSet,
    FicheControleChantierViewSet,
    FichePreparationViewSet,
    ParametreOperationsViewSet,
    RapportExecutionViewSet,
    RepartitionAffaireOFViewSet,
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
router.register("parametres", ParametreOperationsViewSet, basename="parametreoperations")
router.register("fiches-preparation", FichePreparationViewSet, basename="fichepreparation")
router.register("besoins-matiere", BesoinMatiereViewSet, basename="besoinmatiere")
router.register("rapports", RapportExecutionViewSet, basename="rapportexecution")
router.register("fiches-controle", FicheControleChantierViewSet, basename="fichecontrolechantier")
router.register("transferts", BonTransfertViewSet, basename="bontransfert")
router.register("attachements", AttachementViewSet, basename="attachement")
router.register("repartitions", RepartitionAffaireOFViewSet, basename="repartitionaffaireof")
router.register("escalades", EscaladeSurchargeViewSet, basename="escaladesurcharge")

urlpatterns = [
    path("", include(router.urls)),
]