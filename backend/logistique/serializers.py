from rest_framework import serializers

from .models import (
    AffectationParc,
    DemandeMobilisation,
    EquipementParc,
    LectureCompteur,
    LocationGR,
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


class EquipementParcSerializer(serializers.ModelSerializer):
    categorie_label = serializers.CharField(source="get_categorie_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    compteur_type_label = serializers.CharField(source="get_compteur_type_display", read_only=True)
    proprietaire_code = serializers.CharField(source="proprietaire.code", read_only=True, default=None)
    proprietaire_gr = serializers.SerializerMethodField()

    class Meta:
        model = EquipementParc
        fields = [
            "id",
            "code",
            "label",
            "registration",
            "categorie",
            "categorie_label",
            "statut",
            "statut_label",
            "compteur_type",
            "compteur_type_label",
            "compteur_value",
            "site",
            "is_global_rental",
            "proprietaire",
            "proprietaire_code",
            "proprietaire_gr",
            "signe_618",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "code", "created_at", "updated_at"]

    def get_proprietaire_gr(self, obj):
        if not obj.proprietaire:
            return None
        return obj.proprietaire.is_global_rental


class DemandeMobilisationSerializer(serializers.ModelSerializer):
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    affaire_code = serializers.CharField(source="affaire.code", read_only=True, default=None)
    ordre_code = serializers.CharField(source="ordre.code", read_only=True, default=None)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = DemandeMobilisation
        fields = [
            "id",
            "code",
            "label",
            "affaire",
            "affaire_code",
            "ordre",
            "ordre_code",
            "departement",
            "date_debut",
            "date_fin",
            "notes",
            "statut",
            "statut_label",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "code", "created_by", "created_by_name", "created_at", "updated_at"]

    def get_created_by_name(self, obj):
        if not obj.created_by:
            return None
        return (obj.created_by.first_name + " " + obj.created_by.last_name).strip() or obj.created_by.email


class AffectationParcSerializer(serializers.ModelSerializer):
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    equipement_code = serializers.CharField(source="equipement.code", read_only=True, default=None)
    equipement_label = serializers.CharField(source="equipement.label", read_only=True, default=None)
    demande_code = serializers.CharField(source="demande.code", read_only=True, default=None)
    affaire_code = serializers.CharField(source="affaire.code", read_only=True, default=None)
    ordre_code = serializers.CharField(source="ordre.code", read_only=True, default=None)
    responsable_name = serializers.SerializerMethodField()

    class Meta:
        model = AffectationParc
        fields = [
            "id",
            "code",
            "equipement",
            "equipement_code",
            "equipement_label",
            "demande",
            "demande_code",
            "affaire",
            "affaire_code",
            "ordre",
            "ordre_code",
            "responsable",
            "responsable_name",
            "date_debut",
            "date_fin",
            "statut",
            "statut_label",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "code", "created_by", "created_at", "updated_at"]

    def get_responsable_name(self, obj):
        if not obj.responsable:
            return None
        return (obj.responsable.first_name + " " + obj.responsable.last_name).strip() or obj.responsable.email


class LocationGRSerializer(AmountMaskMixin, serializers.ModelSerializer):
    amount_fields = ["montant_estime"]
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    periodicite_label = serializers.CharField(source="get_periodicite_display", read_only=True)
    partenaire_code = serializers.CharField(source="partenaire.code", read_only=True, default=None)
    partenaire_name = serializers.CharField(source="partenaire.name", read_only=True, default=None)
    equipement_code = serializers.CharField(source="equipement.code", read_only=True, default=None)
    equipement_label = serializers.CharField(source="equipement.label", read_only=True, default=None)
    affaire_code = serializers.CharField(source="affaire.code", read_only=True, default=None)
    devise_code = serializers.CharField(source="devise.code", read_only=True, default=None, required=False, allow_null=True)
    consommation = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    created_by_name = serializers.SerializerMethodField()
    lectures_count = serializers.IntegerField(source="lectures.count", read_only=True)

    class Meta:
        model = LocationGR
        fields = [
            "id",
            "code",
            "partenaire",
            "partenaire_code",
            "partenaire_name",
            "equipement",
            "equipement_code",
            "equipement_label",
            "affaire",
            "affaire_code",
            "reference_bc",
            "reference_gr",
            "reference_bl",
            "reference_retour",
            "date_debut",
            "date_fin",
            "periodicite",
            "periodicite_label",
            "tarif",
            "devise",
            "devise_code",
            "montant_estime",
            "lecture_initiale",
            "lecture_finale",
            "consommation",
            "imputation_618",
            "statut",
            "statut_label",
            "lectures_count",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "code",
            "created_by",
            "created_by_name",
            "lectures_count",
            "consommation",
            "created_at",
            "updated_at",
        ]

    def get_created_by_name(self, obj):
        if not obj.created_by:
            return None
        return (obj.created_by.first_name + " " + obj.created_by.last_name).strip() or obj.created_by.email


class LectureCompteurSerializer(serializers.ModelSerializer):
    type_lecture_label = serializers.CharField(source="get_type_lecture_display", read_only=True)
    source_label = serializers.CharField(source="get_source_display", read_only=True)
    location_code = serializers.CharField(source="location.code", read_only=True, default=None)
    equipement_code = serializers.CharField(source="location.equipement.code", read_only=True, default=None)
    equipement_label = serializers.CharField(source="location.equipement.label", read_only=True, default=None)
    releve_par_name = serializers.SerializerMethodField()

    class Meta:
        model = LectureCompteur
        fields = [
            "id",
            "code",
            "location",
            "location_code",
            "equipement_code",
            "equipement_label",
            "date",
            "valeur",
            "type_lecture",
            "type_lecture_label",
            "source",
            "source_label",
            "releve_par",
            "releve_par_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "code", "releve_par", "releve_par_name", "created_at", "updated_at"]

    def get_releve_par_name(self, obj):
        if not obj.releve_par:
            return None
        return (obj.releve_par.first_name + " " + obj.releve_par.last_name).strip() or obj.releve_par.email