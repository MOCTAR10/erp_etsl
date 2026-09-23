"""Sérialiseurs M12 — Juridique & GED (RF-ERP-B0...B4)."""

from rest_framework import serializers

from .models import (
    Assurance,
    Caution,
    Contentieux,
    Convention,
    Courrier,
    DossierGlobalRental,
    Reunion,
)
from .services import can_see_amount


class AmountMaskMixin:
    """Masque les montants hors rôles autorisés (pattern RF-59 / RF-ERP-B0)."""

    amount_fields = ()

    def get_has_amount_access(self, obj):
        request = self.context.get("request")
        return can_see_amount(getattr(request, "user", None))

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if not can_see_amount(getattr(request, "user", None)):
            for field in self.amount_fields:
                if field in data:
                    data[field] = None
            data["has_amount_access"] = False
        return data


class CourrierSerializer(serializers.ModelSerializer):
    sens_label = serializers.CharField(source="get_sens_display", read_only=True)
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    tiers_name = serializers.CharField(source="tiers.name", read_only=True, default=None)
    document_title = serializers.CharField(
        source="document.title", read_only=True, default=None
    )

    class Meta:
        model = Courrier
        fields = [
            "id",
            "code",
            "sens",
            "sens_label",
            "type",
            "type_label",
            "objet",
            "reference",
            "tiers",
            "tiers_name",
            "expediteur",
            "destinataire",
            "date_courrier",
            "date_reception",
            "statut",
            "statut_label",
            "document",
            "document_title",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["code", "statut"]


class ConventionSerializer(AmountMaskMixin, serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    partenaire_name = serializers.CharField(source="partenaire.name", read_only=True, default=None)
    affaire_code = serializers.CharField(source="affaire.code", read_only=True, default=None)
    document_title = serializers.CharField(
        source="document.title", read_only=True, default=None
    )
    days_left = serializers.IntegerField(read_only=True)
    expiry_status = serializers.CharField(read_only=True)
    a_renouveler = serializers.BooleanField(read_only=True)
    has_amount_access = serializers.SerializerMethodField()
    amount_fields = ("montant",)

    class Meta:
        model = Convention
        fields = [
            "id",
            "code",
            "type",
            "type_label",
            "titre",
            "partenaire",
            "partenaire_name",
            "montant",
            "date_debut",
            "date_fin",
            "renouvelable",
            "affaire",
            "affaire_code",
            "statut",
            "statut_label",
            "document",
            "document_title",
            "days_left",
            "expiry_status",
            "a_renouveler",
            "has_amount_access",
            "commentaire",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "code",
            "statut",
            "days_left",
            "expiry_status",
            "a_renouveler",
        ]


class ContentieuxSerializer(AmountMaskMixin, serializers.ModelSerializer):
    nature_label = serializers.CharField(source="get_nature_display", read_only=True)
    phase_label = serializers.CharField(source="get_phase_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    document_title = serializers.CharField(
        source="document.title", read_only=True, default=None
    )
    has_amount_access = serializers.SerializerMethodField()
    amount_fields = ("montant_en_jeu",)

    class Meta:
        model = Contentieux
        fields = [
            "id",
            "code",
            "nature",
            "nature_label",
            "objet",
            "partie_adverse",
            "conseil_ext",
            "montant_en_jeu",
            "reference",
            "date_ouverture",
            "phase",
            "phase_label",
            "statut",
            "statut_label",
            "decision",
            "document",
            "document_title",
            "has_amount_access",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["code", "statut", "phase"]


class CautionSerializer(AmountMaskMixin, serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    emetteur_name = serializers.CharField(source="emetteur.name", read_only=True, default=None)
    convention_code = serializers.CharField(
        source="convention.code", read_only=True, default=None
    )
    document_title = serializers.CharField(
        source="document.title", read_only=True, default=None
    )
    days_left = serializers.IntegerField(read_only=True)
    expiry_status = serializers.CharField(read_only=True)
    has_amount_access = serializers.SerializerMethodField()
    amount_fields = ("montant",)

    class Meta:
        model = Caution
        fields = [
            "id",
            "code",
            "type",
            "type_label",
            "emetteur",
            "emetteur_name",
            "beneficiaire",
            "objet",
            "montant",
            "numero_instrument",
            "date_emission",
            "date_echeance",
            "statut",
            "statut_label",
            "convention",
            "convention_code",
            "document",
            "document_title",
            "days_left",
            "expiry_status",
            "has_amount_access",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["code", "statut", "days_left", "expiry_status"]


class AssuranceSerializer(AmountMaskMixin, serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    assureur_name = serializers.CharField(source="assureur.name", read_only=True, default=None)
    document_title = serializers.CharField(
        source="document.title", read_only=True, default=None
    )
    days_left = serializers.IntegerField(read_only=True)
    expiry_status = serializers.CharField(read_only=True)
    has_amount_access = serializers.SerializerMethodField()
    amount_fields = ("prime_annuelle",)

    class Meta:
        model = Assurance
        fields = [
            "id",
            "code",
            "type",
            "type_label",
            "assureur",
            "assureur_name",
            "numero_police",
            "prime_annuelle",
            "date_debut",
            "date_echeance",
            "objets_couverts",
            "statut",
            "statut_label",
            "nb_sinistres",
            "sinistres",
            "document",
            "document_title",
            "days_left",
            "expiry_status",
            "has_amount_access",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["code", "statut", "days_left", "expiry_status", "sinistres"]


class ReunionSerializer(serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    animateur_name = serializers.CharField(
        source="animateur.get_full_name", read_only=True, default=None
    )
    compte_rendu_title = serializers.CharField(
        source="compte_rendu.title", read_only=True, default=None
    )
    participants = serializers.PrimaryKeyRelatedField(
        many=True, read_only=True
    )
    participants_names = serializers.SerializerMethodField()
    nb_decisions = serializers.IntegerField(read_only=True)
    nb_decisions_ouvertes = serializers.IntegerField(read_only=True)

    class Meta:
        model = Reunion
        fields = [
            "id",
            "code",
            "type",
            "type_label",
            "objet",
            "date_reunion",
            "lieu",
            "animateur",
            "animateur_name",
            "participants",
            "participants_names",
            "compte_rendu",
            "compte_rendu_title",
            "statut",
            "statut_label",
            "decisions",
            "nb_decisions",
            "nb_decisions_ouvertes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["code", "statut"]

    def get_participants_names(self, obj):
        return [p.get_full_name() for p in obj.participants.all()]


class DossierGlobalRentalSerializer(AmountMaskMixin, serializers.ModelSerializer):
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    partenaire_gr_name = serializers.CharField(
        source="partenaire_gr.name", read_only=True
    )
    affaire_code = serializers.CharField(source="affaire.code", read_only=True, default=None)
    has_amount_access = serializers.SerializerMethodField()
    amount_fields = ("montant_estime",)

    class Meta:
        model = DossierGlobalRental
        fields = [
            "id",
            "code",
            "partenaire_gr",
            "partenaire_gr_name",
            "affaire",
            "affaire_code",
            "reference_contrat",
            "objet",
            "montant_estime",
            "signe_618",
            "date_debut",
            "date_fin",
            "statut",
            "statut_label",
            "references_documents",
            "commentaire",
            "has_amount_access",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["code", "statut"]

    def validate(self, attrs):
        partenaire = attrs.get("partenaire_gr")
        if partenaire is not None and not partenaire.is_global_rental:
            raise serializers.ValidationError(
                {"partenaire_gr": "Le partenaire doit être flaggé GLOBAL RENTAL (RF-ERP-B4)."}
            )
        return attrs