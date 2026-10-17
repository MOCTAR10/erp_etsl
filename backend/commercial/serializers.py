from rest_framework import serializers

from config.serializers import ModelCleanMixin

from .models import (
    Avenant,
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
    RevueCommande,
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
    montant_offre = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = Estimate
        fields = [
            "id",
            "code",
            "version",
            "version_precedente",
            "soumise_le",
            "decision_le",
            "motif_perte",
            "montant_offre",
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
        read_only_fields = ["id", "code", "created_by", "created_at", "updated_at", "status", "version",
                            "version_precedente", "soumise_le", "decision_le", "motif_perte"]

    def validate(self, attrs):
        if self.instance and self.instance.status != Estimate.Status.BROUILLON:
            raise serializers.ValidationError(
                {"detail": "Offre émise : version scellée. Utilisez « réviser » pour créer une nouvelle version."}
            )
        return attrs


def _offre_modifiable(estimate):
    if estimate and estimate.status != Estimate.Status.BROUILLON:
        raise serializers.ValidationError(
            {"estimate": "Offre émise : version scellée (options et lignes non modifiables). Révisez l'offre."}
        )


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

    def validate(self, attrs):
        _offre_modifiable(attrs.get("estimate") or getattr(self.instance, "estimate", None))
        return attrs


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

    def validate(self, attrs):
        _offre_modifiable(attrs.get("estimate") or getattr(self.instance, "estimate", None))
        return attrs


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
            "criteres",
            "score",
            "decision_rao",
            "reviewed_by",
            "reviewed_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["reviewed_by", "id", "review_status", "score", "decision_rao", "created_at", "updated_at"]

    def validate_criteres(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Liste de critères attendue : [{libelle, poids, note}].")
        for i, critere in enumerate(value, start=1):
            if not isinstance(critere, dict) or not str(critere.get("libelle", "")).strip():
                raise serializers.ValidationError(f"Critère {i} : libellé requis.")
            try:
                poids, note = float(critere.get("poids")), float(critere.get("note"))
            except (TypeError, ValueError):
                raise serializers.ValidationError(f"Critère {i} : poids et note numériques requis.")
            if poids <= 0:
                raise serializers.ValidationError(f"Critère {i} : poids strictement positif requis.")
            if not 0 <= note <= 100:
                raise serializers.ValidationError(f"Critère {i} : note entre 0 et 100 requise.")
        return value


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
            "montant",
            "facture_le",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "code", "status", "facture_le", "created_at", "updated_at"]


class AffaireSerializer(AmountMaskMixin, ModelCleanMixin, serializers.ModelSerializer):
    amount_fields = ["contract_amount", "margin"]

    opportunity_code = serializers.CharField(
        source="opportunity.code", read_only=True, default=None
    )
    client_name = serializers.CharField(source="client.partner.name", read_only=True, default=None)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    type_label = serializers.CharField(source="get_affaire_type_display", read_only=True)
    milestones_total = serializers.IntegerField(source="milestones.count", read_only=True)
    responsable_email = serializers.EmailField(source="responsable.email", read_only=True, default=None)
    analytic_code = serializers.CharField(source="analytic.code", read_only=True, default=None)

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
            "responsable",
            "responsable_email",
            "analytic",
            "analytic_code",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "code", "status", "analytic", "created_at", "updated_at"]


class ContractSerializer(AmountMaskMixin, ModelCleanMixin, serializers.ModelSerializer):
    amount_fields = ["amount_initial", "penalty", "montant_actuel"]
    montant_actuel = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    avenants_total = serializers.IntegerField(source="avenants.count", read_only=True)

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
            "montant_actuel",
            "avenants_total",
            "document",
            "signe_le",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "code",
            "days_to_expiry",
            "expiry_status",
            "status",
            "document",
            "signe_le",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        if self.instance and self.instance.status != Contract.Status.BROUILLON:
            figes = [f for f in Contract.CHAMPS_CONTRACTUELS if f in attrs and attrs[f] != getattr(self.instance, f)]
            if figes:
                raise serializers.ValidationError(
                    {f: "Contrat signé : modification uniquement par avenant." for f in figes}
                )
        return super().validate(attrs)


class AvenantSerializer(AmountMaskMixin, ModelCleanMixin, serializers.ModelSerializer):
    amount_fields = ["delta_montant"]
    contract_code = serializers.CharField(source="contract.code", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)

    class Meta:
        model = Avenant
        fields = [
            "id", "contract", "contract_code", "numero", "objet", "delta_montant", "nouvelle_date_fin",
            "statut", "statut_label", "document", "signe_le", "created_by", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "numero", "statut", "document", "signe_le", "created_by", "created_at", "updated_at"]

    def validate(self, attrs):
        if self.instance and self.instance.statut == Avenant.Statut.SIGNE:
            raise serializers.ValidationError({"detail": "Avenant signé : pièce scellée."})
        return super().validate(attrs)


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


class RevueCommandeSerializer(serializers.ModelSerializer):
    affaire_code = serializers.CharField(source="affaire.code", read_only=True)
    delta_prix_pct = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)
    delta_delai_jours = serializers.IntegerField(read_only=True)
    type_label = serializers.CharField(source="get_type_revue_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)

    class Meta:
        model = RevueCommande
        fields = [
            "id", "affaire", "affaire_code", "montant_offre", "montant_commande", "delai_offre_jours",
            "delai_commande_jours", "delta_prix_pct", "delta_delai_jours", "type_revue", "type_label", "statut",
            "statut_label", "commentaire", "valide_par", "valide_le", "created_at", "updated_at",
        ]
        read_only_fields = ["type_revue", "statut", "valide_par", "valide_le", "created_at", "updated_at"]

    def validate_montant_offre(self, value):
        if value <= 0:
            raise serializers.ValidationError("Montant de l'offre strictement positif requis.")
        return value
