"""API module M1 — Commercial / CRM / CLM (RF-ERP-01…05)."""

from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import (
    Affaire,
    ClientProfile,
    Contract,
    ContractService,
    Estimate,
    EstimateLine,
    EstimateOption,
    Milestone,
    Opportunity,
    SoumissionEvent,
    TenderReview,
)
from .serializers import (
    AffaireSerializer,
    ClientProfileSerializer,
    ContractSerializer,
    ContractServiceSerializer,
    EstimateLineSerializer,
    EstimateOptionSerializer,
    EstimateSerializer,
    MilestoneSerializer,
    OpportunitySerializer,
    SoumissionEventSerializer,
    TenderReviewSerializer,
)
from .services import CanManageCommercial, can_see_amount, pipeline_stats


class _CommonViewSet(viewsets.ModelViewSet):
    """Lecture authentifiée ; écriture réservée aux rôles commerciaux."""

    http_method_names = ["get", "post", "patch", "delete"]

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [IsAuthenticated()]
        return [CanManageCommercial()]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["can_view_amount"] = can_see_amount(self.request.user)
        return context


class ClientProfileViewSet(_CommonViewSet):
    serializer_class = ClientProfileSerializer

    def get_queryset(self):
        qs = ClientProfile.objects.select_related("partner").all()
        segment = self.request.query_params.get("segment")
        if segment:
            qs = qs.filter(segment=segment)
        if self.request.query_params.get("active") is not None:
            active = self.request.query_params["active"].lower() in ("1", "true", "yes")
            qs = qs.filter(is_active=active)
        return qs


class OpportunityViewSet(_CommonViewSet):
    serializer_class = OpportunitySerializer

    def get_queryset(self):
        qs = Opportunity.objects.select_related("client__partner", "owner").all()
        stage = self.request.query_params.get("stage")
        client = self.request.query_params.get("client")
        if stage:
            qs = qs.filter(stage=stage)
        if client:
            qs = qs.filter(client_id=client)
        if self.request.query_params.get("active") is not None:
            active = self.request.query_params["active"].lower() in ("1", "true", "yes")
            qs = qs.filter(is_active=active)
        return qs

    @action(detail=False, methods=["get"], url_path="pipeline")
    def pipeline(self, request):
        """Pilotage M1.4 — pipeline par étape, taux de conversion, marge par segment."""
        return Response(pipeline_stats())


class EstimateViewSet(_CommonViewSet):
    serializer_class = EstimateSerializer

    def get_queryset(self):
        qs = Estimate.objects.select_related("opportunity", "client__partner", "currency")
        status_ = self.request.query_params.get("status")
        if status_:
            qs = qs.filter(status=status_)
        if self.request.query_params.get("global_rental") is not None:
            gr = self.request.query_params["global_rental"].lower() in ("1", "true", "yes")
            qs = qs.filter(is_global_rental=gr)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class EstimateOptionViewSet(_CommonViewSet):
    serializer_class = EstimateOptionSerializer

    def get_queryset(self):
        qs = EstimateOption.objects.all()
        estimate = self.request.query_params.get("estimate")
        if estimate:
            qs = qs.filter(estimate_id=estimate)
        return qs


class EstimateLineViewSet(_CommonViewSet):
    serializer_class = EstimateLineSerializer

    def get_queryset(self):
        qs = EstimateLine.objects.select_related("article", "unit").all()
        estimate = self.request.query_params.get("estimate")
        if estimate:
            qs = qs.filter(estimate_id=estimate)
        return qs


class TenderReviewViewSet(_CommonViewSet):
    serializer_class = TenderReviewSerializer

    def get_queryset(self):
        qs = TenderReview.objects.select_related("client", "estimate").all()
        for param, field in (("estimate", "estimate_id"), ("client", "client_id")):
            value = self.request.query_params.get(param)
            if value:
                qs = qs.filter(**{field: value})
        return qs

    def perform_create(self, serializer):
        serializer.save(reviewed_by=self.request.user, reviewed_at=timezone.now())


class AffaireViewSet(_CommonViewSet):
    serializer_class = AffaireSerializer

    def get_queryset(self):
        qs = Affaire.objects.select_related("opportunity", "client__partner", "currency")
        status_ = self.request.query_params.get("status")
        if status_:
            qs = qs.filter(status=status_)
        if self.request.query_params.get("global_rental") is not None:
            gr = self.request.query_params["global_rental"].lower() in ("1", "true", "yes")
            qs = qs.filter(is_global_rental=gr)
        return qs


class MilestoneViewSet(_CommonViewSet):
    serializer_class = MilestoneSerializer

    def get_queryset(self):
        qs = Milestone.objects.select_related("affaire").all()
        affaire = self.request.query_params.get("affaire")
        if affaire:
            qs = qs.filter(affaire_id=affaire)
        return qs


class ContractViewSet(_CommonViewSet):
    serializer_class = ContractSerializer

    def get_queryset(self):
        qs = Contract.objects.select_related("client__partner", "currency", "affaire").all()
        profile = self.request.query_params.get("profile")
        if profile:
            qs = qs.filter(profile=profile)
        expiring = self.request.query_params.get("expiring")
        if expiring:
            days = int(expiring)
            qs = qs.filter(end_date__isnull=False)
            qs = qs.filter(
                end_date__lte=timezone.localdate() + timezone.timedelta(days=days),
                end_date__gte=timezone.localdate(),
            ).exclude(status=Contract.Status.CLOTURE)
            return qs
        if self.request.query_params.get("active") is not None:
            active = self.request.query_params["active"].lower() in ("1", "true", "yes")
            qs = qs.filter(status=Contract.Status.ACTIF if active else Contract.Status.BROUILLON)
        return qs


class ContractServiceViewSet(_CommonViewSet):
    serializer_class = ContractServiceSerializer

    def get_queryset(self):
        qs = ContractService.objects.select_related("contract").all()
        contract = self.request.query_params.get("contract")
        if contract:
            qs = qs.filter(contract_id=contract)
        return qs


class SoumissionEventViewSet(_CommonViewSet):
    serializer_class = SoumissionEventSerializer

    def get_queryset(self):
        qs = SoumissionEvent.objects.select_related("client__partner", "opportunity")
        for param, field in (("client", "client_id"), ("opportunity", "opportunity_id"), ("estimate", "estimate_id")):
            value = self.request.query_params.get(param)
            if value:
                qs = qs.filter(**{field: value})
        return qs

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)