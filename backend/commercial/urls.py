from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AvenantViewSet,
    RevueCommandeViewSet,
    AffaireViewSet,
    ClientProfileViewSet,
    ContractServiceViewSet,
    ContractViewSet,
    EstimateLineViewSet,
    EstimateOptionViewSet,
    EstimateViewSet,
    HabilitationRequiseViewSet,
    MilestoneViewSet,
    ParametreCommercialViewSet,
    PilotageM1ViewSet,
    OpportunityViewSet,
    SoumissionEventViewSet,
    TenderReviewViewSet,
)

router = DefaultRouter()
router.register("profiles", ClientProfileViewSet, basename="clientprofile")
router.register("opportunities", OpportunityViewSet, basename="opportunity")
router.register("estimates", EstimateViewSet, basename="estimate")
router.register("estimate-options", EstimateOptionViewSet, basename="estimateoption")
router.register("estimate-lines", EstimateLineViewSet, basename="estimateline")
router.register("tender-reviews", TenderReviewViewSet, basename="tenderreview")
router.register("affaires", AffaireViewSet, basename="affaire")
router.register("revues-commande", RevueCommandeViewSet, basename="revuecommande")
router.register("milestones", MilestoneViewSet, basename="milestone")
router.register("contracts", ContractViewSet, basename="contract")
router.register("contract-services", ContractServiceViewSet, basename="contractservice")
router.register("avenants", AvenantViewSet, basename="avenant")
router.register("soumissions", SoumissionEventViewSet, basename="soumission")
router.register("parametres", ParametreCommercialViewSet, basename="parametrecommercial")
router.register("habilitations-requises", HabilitationRequiseViewSet, basename="habilitationrequise")
router.register("pilotage", PilotageM1ViewSet, basename="pilotagem1")

urlpatterns = [
    path("", include(router.urls)),
]