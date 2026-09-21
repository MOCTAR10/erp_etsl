from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AffaireViewSet,
    ClientProfileViewSet,
    ContractServiceViewSet,
    ContractViewSet,
    EstimateLineViewSet,
    EstimateOptionViewSet,
    EstimateViewSet,
    MilestoneViewSet,
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
router.register("milestones", MilestoneViewSet, basename="milestone")
router.register("contracts", ContractViewSet, basename="contract")
router.register("contract-services", ContractServiceViewSet, basename="contractservice")
router.register("soumissions", SoumissionEventViewSet, basename="soumission")

urlpatterns = [
    path("", include(router.urls)),
]