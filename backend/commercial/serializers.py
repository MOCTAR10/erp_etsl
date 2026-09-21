from rest_framework import serializers

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


class AmountMaskMixin:
    """Masque les montants si l'utilisateur n'a pas droit à la valeur (RF-59)."""

    amount_fields = []

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not self.context.get("can_view_amount", True):
            for field in self.amount_fields:
                if field in data:
                    data[field] = None
        return data


class ClientProfileSerializer(serializers.ModelSerializer):
    partner_name = serializers.CharField(source="partner.name", read_only=True)
    partner_code = serializers.CharField(source="partner.code", read_only=True)
    segment_label = serializers.CharField(source="get_segment_display", read_only=True)

    class Meta:
        model = ClientProfile
        fields = [
            "id",
            "partner",
            "partner_code",
            "partner_name",
            "segment",
            "segment_label",
            "scoring",
            "origin",
            "contacts",
            "history",
            "last_contact",
            "next_contact",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class OpportunitySerializer(AmountMaskMixin, serializers.ModelSerializer):
    amount_fields = ["amount"]

    client_name = serializers.CharField(source="client.partner.name", read_only=True, default=None)
    stage_label = serializers.CharField(source="get_stage_display", read_only=True)
    owner_name = serializers.SerializerMethodField()

    class Meta:
        model = Opportunity
        fields = [
            "id",
            "code",
            "client",
            "client_name",
            "subject",
            "stage",
            "stage_label",
            "amount",
            "probability",
            "expected_close",
            "origin",
            "owner",
            "owner_name",
            "description",
            "won_date",
            "lost_reason",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "code", "won_date", "created_at", "updated_at"]

    def get_owner_name(self, obj):
        if not obj.owner:
            return None
        return (obj.owner.first_name + " " + obj.owner.last_name).strip() or obj.owner.email


class EstimateSerializer(AmountMaskMixin, serializers.ModelSerializer):
    amount_fields = ["total", "margin"]

    opportunity_code = serializers.CharField(
        source="opportunity.code", read_only=True, default=None
    )
    client_name = serializers.CharField(source="client.partner.name", read_only=True, default=None)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    options_total = serializers.IntegerField(source="options.count", read_only=True)
    lines_total = serializers.IntegerField(source="lines.count", read_only=True)

    class Meta:
        model = Estimate
        fields = [
            "id",
            "code",
            "opportunity",
            "opportunity_code",
            "client",
            "client_name",
            "title",
            "status",
            "status_label",
            "currency",
            "total",
            "margin",
            "valid_until",
            "is_global_rental",
            "created_by",
            "options_total",
            "lines_total",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "code", "created_by", "created_at", "updated_at"]


class EstimateOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = EstimateOption
        fields = [
            "id",
            "estimate",
            "label",
            "amount",
            "duration_months",
            "notes",
            "is_selected",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class EstimateLineSerializer(serializers.ModelSerializer):
    article_code = serializers.CharField(source="article.code", read_only=True, default=None)
    unit_label = serializers.CharField(source="unit.label", read_only=True, default=None)

    class Meta:
        model = EstimateLine
        fields = [
            "id",
            "estimate",
            "article",
            "article_code",
            "label",
            "quantity",
            "unit",
            "unit_label",
            "unit_price",
            "price_total",
        ]
        read_only_fields = ["id", "price_total"]


class TenderReviewSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source="client.name", read_only=True, default=None)
    review_status_label = serializers.CharField(
        source="get_review_status_display", read_only=True
    )

    class Meta:
        model = TenderReview
        fields = [
            "id",
            "estimate",
            "client",
            "client_name",
            "tender_ref",
            "bid_deadline",
            "review_status",
            "review_status_label",
            "requirements",
            "decision",
            "reviewed_by",
            "reviewed_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class MilestoneSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Milestone
        fields = [
            "id",
            "affaire",
            "code",
            "label",
            "planned_date",
            "actual_date",
            "progress",
            "status",
            "status_label",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "code", "status", "created_at", "updated_at"]


class AffaireSerializer(AmountMaskMixin, serializers.ModelSerializer):
    amount_fields = ["contract_amount", "margin"]

    opportunity_code = serializers.CharField(
        source="opportunity.code", read_only=True, default=None
    )
    client_name = serializers.CharField(source="client.partner.name", read_only=True, default=None)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    type_label = serializers.CharField(source="get_affaire_type_display", read_only=True)
    milestones_total = serializers.IntegerField(source="milestones.count", read_only=True)

    class Meta:
        model = Affaire
        fields = [
            "id",
            "code",
            "opportunity",
            "opportunity_code",
            "client",
            "client_name",
            "title",
            "description",
            "affaire_type",
            "type_label",
            "currency",
            "contract_amount",
            "margin",
            "status",
            "status_label",
            "start_date",
            "end_date",
            "is_global_rental",
            "milestones_total",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "code", "created_at", "updated_at"]


class ContractSerializer(AmountMaskMixin, serializers.ModelSerializer):
    amount_fields = ["amount_initial", "penalty"]

    client_name = serializers.CharField(source="client.partner.name", read_only=True, default=None)
    profile_label = serializers.CharField(source="get_profile_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    days_to_expiry = serializers.IntegerField(read_only=True)
    expiry_status = serializers.CharField(read_only=True)
    services_total = serializers.IntegerField(source="services.count", read_only=True)

    class Meta:
        model = Contract
        fields = [
            "id",
            "code",
            "affaire",
            "client",
            "client_name",
            "profile",
            "profile_label",
            "start_date",
            "end_date",
            "months",
            "amount_initial",
            "currency",
            "sla",
            "retenue_rate",
            "indexation",
            "penalty",
            "status",
            "status_label",
            "is_global_rental",
            "notes",
            "days_to_expiry",
            "expiry_status",
            "services_total",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "code",
            "days_to_expiry",
            "expiry_status",
            "created_at",
            "updated_at",
        ]


class ContractServiceSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    frequency_label = serializers.CharField(source="get_frequency_display", read_only=True)

    class Meta:
        model = ContractService
        fields = [
            "id",
            "contract",
            "label",
            "kind",
            "kind_label",
            "sla_hours",
            "price",
            "frequency",
            "frequency_label",
            "is_global_rental",
        ]
        read_only_fields = ["id"]


class SoumissionEventSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source="client.partner.name", read_only=True, default=None)
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = SoumissionEvent
        fields = [
            "id",
            "client",
            "client_name",
            "opportunity",
            "estimate",
            "kind",
            "kind_label",
            "happened_at",
            "content",
            "document",
            "author",
            "author_name",
            "created_at",
        ]
        read_only_fields = ["id", "author", "created_at"]

    def get_author_name(self, obj):
        if not obj.author:
            return None
        return (obj.author.first_name + " " + obj.author.last_name).strip() or obj.author.email