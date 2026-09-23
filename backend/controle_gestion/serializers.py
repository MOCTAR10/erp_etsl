"""Sérialiseurs M11 — Contrôle de gestion (RF-ERP-A0…A4)."""

from rest_framework import serializers

from accounting_kernel.models import FiscalYear

from .models import Budget, BudgetLigne, BudgetRevision, ClotureGestion


class BudgetLigneSerializer(serializers.ModelSerializer):
    period_number = serializers.IntegerField(source="period.number", read_only=True)
    period_label = serializers.CharField(source="period.__str__", read_only=True)

    class Meta:
        model = BudgetLigne
        fields = [
            "id",
            "budget",
            "period",
            "period_number",
            "period_label",
            "montant",
        ]

    def validate(self, attrs):
        budget = attrs.get("budget") or (
            self.instance.budget if self.instance else None
        )
        period = attrs.get("period") or (self.instance.period if self.instance else None)
        if budget and period:
            if period.fiscal_year_id != budget.fiscal_year_id:
                raise serializers.ValidationError(
                    "La période comptable doit appartenir à l'exercice du budget."
                )
            qs = BudgetLigne.objects.filter(budget=budget, period=period)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    "Une ligne de budget existe déjà pour cette période."
                )
        return attrs


class BudgetRevisionSerializer(serializers.ModelSerializer):
    budget_code = serializers.CharField(source="budget.code", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    created_by_name = serializers.CharField(
        source="created_by.get_full_name", read_only=True, default=None
    )
    has_amount_access = serializers.SerializerMethodField()

    class Meta:
        model = BudgetRevision
        fields = [
            "id",
            "code",
            "budget",
            "budget_code",
            "numero",
            "date_revision",
            "ancien_montant",
            "nouveau_montant",
            "commentaire",
            "statut",
            "statut_label",
            "created_by",
            "created_by_name",
            "has_amount_access",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["code", "numero", "ancien_montant", "statut", "created_by"]

    def get_has_amount_access(self, obj):
        from .services import can_see_amount

        return can_see_amount(self.context.get("request").user)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        from .services import can_see_amount

        request = self.context.get("request")
        if not can_see_amount(getattr(request, "user", None)):
            data["ancien_montant"] = None
            data["nouveau_montant"] = None
            data["has_amount_access"] = False
        return data


class BudgetSerializer(serializers.ModelSerializer):
    fiscal_year = serializers.PrimaryKeyRelatedField(
        queryset=FiscalYear.objects.all()
    )
    axis_code = serializers.CharField(source="axis.code", read_only=True, default=None)
    analytic_code = serializers.CharField(source="analytic.code", read_only=True, default=None)
    analytic_label = serializers.CharField(source="analytic.label", read_only=True, default=None)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    type_label = serializers.CharField(source="get_type_budget_display", read_only=True)
    lignes = BudgetLigneSerializer(many=True, read_only=True)
    montant_lignes = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    nb_revisions = serializers.IntegerField(read_only=True)
    has_amount_access = serializers.SerializerMethodField()

    class Meta:
        model = Budget
        fields = [
            "id",
            "code",
            "label",
            "type_budget",
            "type_label",
            "fiscal_year",
            "axis",
            "axis_code",
            "analytic",
            "analytic_code",
            "analytic_label",
            "montant",
            "montant_lignes",
            "statut",
            "statut_label",
            "lignes",
            "nb_revisions",
            "created_by",
            "has_amount_access",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["code", "statut", "created_by"]

    def get_has_amount_access(self, obj):
        from .services import can_see_amount

        return can_see_amount(self.context.get("request").user)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        from .services import can_see_amount

        request = self.context.get("request")
        if not can_see_amount(getattr(request, "user", None)):
            data["montant"] = None
            data["montant_lignes"] = None
            data["has_amount_access"] = False
        return data


class ClotureGestionSerializer(serializers.ModelSerializer):
    period_label = serializers.CharField(source="period.__str__", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    jours_ecoulement = serializers.IntegerField(read_only=True)
    conforme_j4 = serializers.BooleanField(read_only=True)

    class Meta:
        model = ClotureGestion
        fields = [
            "id",
            "code",
            "period",
            "period_label",
            "date_cloture",
            "statut",
            "statut_label",
            "jours_ecoulement",
            "conforme_j4",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["code", "statut"]