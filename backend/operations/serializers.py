from rest_framework import serializers

from .models import (
    GammeOperatoire,
    GammeOperation,
    OrdreFabrication,
    PointageChantier,
    SituationTravaux,
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


class GammeOperatoireSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    operations_count = serializers.IntegerField(source="operations.count", read_only=True)
    total_planned_hours = serializers.DecimalField(
        max_digits=18, decimal_places=2, read_only=True
    )

    class Meta:
        model = GammeOperatoire
        fields = [
            "id",
            "code",
            "label",
            "status",
            "status_label",
            "is_global_rental",
            "operations_count",
            "total_planned_hours",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "code", "created_at", "updated_at"]


class GammeOperationSerializer(serializers.ModelSerializer):
    poste_label = serializers.CharField(source="get_poste_display", read_only=True)
    gamme_code = serializers.CharField(source="gamme.code", read_only=True, default=None)

    class Meta:
        model = GammeOperation
        fields = [
            "id",
            "gamme",
            "gamme_code",
            "sequence",
            "label",
            "poste",
            "poste_label",
            "planned_hours",
        ]
        read_only_fields = ["id"]


class OrdreFabricationSerializer(AmountMaskMixin, serializers.ModelSerializer):
    amount_fields = []
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    scope_label = serializers.CharField(source="get_scope_display", read_only=True)
    affaire_code = serializers.CharField(source="affaire.code", read_only=True, default=None)
    gamme_code = serializers.CharField(source="gamme.code", read_only=True, default=None)
    article_code = serializers.CharField(source="article.code", read_only=True, default=None)
    responsible_name = serializers.SerializerMethodField()
    pointage_hours = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    pointages_count = serializers.IntegerField(source="pointages.count", read_only=True)

    class Meta:
        model = OrdreFabrication
        fields = [
            "id",
            "code",
            "label",
            "affaire",
            "affaire_code",
            "gamme",
            "gamme_code",
            "scope",
            "scope_label",
            "article",
            "article_code",
            "quantity",
            "status",
            "status_label",
            "planned_start",
            "planned_end",
            "calculated_hours",
            "responsible",
            "responsible_name",
            "created_by",
            "pointage_hours",
            "pointages_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "code",
            "created_by",
            "pointage_hours",
            "pointages_count",
            "created_at",
            "updated_at",
        ]

    def get_responsible_name(self, obj):
        if not obj.responsible:
            return None
        return (obj.responsible.first_name + " " + obj.responsible.last_name).strip() or obj.responsible.email


class PointageChantierSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    hours_type_label = serializers.CharField(source="get_hours_type_display", read_only=True)
    ordre_code = serializers.CharField(source="ordre.code", read_only=True, default=None)
    worker_name_filled = serializers.SerializerMethodField()

    class Meta:
        model = PointageChantier
        fields = [
            "id",
            "code",
            "ordre",
            "ordre_code",
            "worker",
            "worker_name",
            "worker_name_filled",
            "date",
            "hours",
            "hours_type",
            "hours_type_label",
            "status",
            "status_label",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "code", "created_by", "created_at", "updated_at"]

    def get_worker_name_filled(self, obj):
        if obj.worker_name:
            return obj.worker_name
        if obj.worker:
            return (obj.worker.first_name + " " + obj.worker.last_name).strip() or obj.worker.email
        return None


class SituationTravauxSerializer(AmountMaskMixin, serializers.ModelSerializer):
    amount_fields = ["amount"]
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    affaire_code = serializers.CharField(source="affaire.code", read_only=True, default=None)
    created_by_name = serializers.SerializerMethodField()
    validated_by_name = serializers.SerializerMethodField()
    ordered_hours = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    ordres_count = serializers.IntegerField(source="ordres.count", read_only=True)

    class Meta:
        model = SituationTravaux
        fields = [
            "id",
            "code",
            "affaire",
            "affaire_code",
            "label",
            "period_start",
            "period_end",
            "amount",
            "progress",
            "status",
            "status_label",
            "ordres",
            "ordres_count",
            "ordered_hours",
            "created_by",
            "created_by_name",
            "validated_by",
            "validated_by_name",
            "validated_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "code",
            "created_by",
            "created_by_name",
            "validated_by",
            "validated_by_name",
            "validated_at",
            "ordered_hours",
            "ordres_count",
            "created_at",
            "updated_at",
        ]

    def get_created_by_name(self, obj):
        if not obj.created_by:
            return None
        return (obj.created_by.first_name + " " + obj.created_by.last_name).strip() or obj.created_by.email

    def get_validated_by_name(self, obj):
        if not obj.validated_by:
            return None
        return (obj.validated_by.first_name + " " + obj.validated_by.last_name).strip() or obj.validated_by.email