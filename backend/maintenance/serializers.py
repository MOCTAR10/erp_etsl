"""Sérialiseurs M8 — Maintenance & GMAO (parc machines & équipements)."""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Actif, Inspection, OrdreTravail
from .services import can_see_amount


def _validate_instance(serializer, instance, exclude=()):
    try:
        instance.full_clean(exclude=list(exclude))
    except DjangoValidationError as exc:
        if hasattr(exc, "error_dict"):
            raise serializers.ValidationError(exc.message_dict)
        raise serializers.ValidationError({"detail": exc.messages})


def _apply_and_validate(serializer, attrs, exclude=("code",)):
    instance = serializer.instance or serializer.Meta.model(**attrs)
    if serializer.instance:
        for key, value in attrs.items():
            setattr(instance, key, value)
    _validate_instance(serializer, instance, exclude=exclude)
    return attrs


class ActifSerializer(serializers.ModelSerializer):
    categorie_label = serializers.CharField(source="get_categorie_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    compteur_type_label = serializers.CharField(source="get_compteur_type_display", read_only=True)
    compteur_lecture = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    equipe_gr_code = serializers.CharField(
        source="equipement_gr.code", read_only=True, default=None
    )
    en_arret = serializers.BooleanField(read_only=True)

    class Meta:
        model = Actif
        fields = [
            "id", "code", "designation", "categorie", "categorie_label", "fabricant",
            "modele", "numero_serie", "site", "statut", "statut_label", "en_arret",
            "date_mise_en_service", "garanti_jusqu", "compteur_type",
            "compteur_type_label", "compteur_value", "compteur_lecture",
            "is_global_rental", "equipement_gr", "equipe_gr_code", "signe_618",
            "notes", "created_at", "updated_at",
        ]
        read_only_fields = ["code", "compteur_lecture"]

    def validate(self, attrs):
        return _apply_and_validate(self, attrs)


class OrdreTravailSerializer(serializers.ModelSerializer):
    actif_code = serializers.CharField(source="actif.code", read_only=True)
    actif_designation = serializers.CharField(source="actif.designation", read_only=True)
    type_label = serializers.CharField(source="get_type_ot_display", read_only=True)
    priorite_label = serializers.CharField(source="get_priorite_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    decision_label = serializers.CharField(source="get_decision_display", read_only=True)
    demandeur_name = serializers.CharField(
        source="demandeur.get_full_name", read_only=True, default=None
    )
    technicien_name = serializers.CharField(
        source="technicien.get_full_name", read_only=True, default=None
    )
    cout_main_oeuvre = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    cout_total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    has_amount_access = serializers.SerializerMethodField()

    class Meta:
        model = OrdreTravail
        fields = [
            "id", "code", "actif", "actif_code", "actif_designation", "type_ot",
            "type_label", "priorite", "priorite_label", "description", "cause",
            "demandeur", "demandeur_name", "technicien", "technicien_name",
            "date_demande", "date_planifiee", "date_debut", "date_fin", "heures_mo",
            "tarif_horaire", "cout_pieces", "cout_main_oeuvre", "cout_total",
            "has_amount_access", "decision", "decision_label", "rapport", "statut",
            "statut_label", "created_by", "created_at", "updated_at",
        ]
        read_only_fields = [
            "code", "cout_main_oeuvre", "cout_total", "date_debut", "date_fin",
            "decision", "rapport",
        ]

    def get_has_amount_access(self, obj):
        return can_see_amount(self.context.get("request").user)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if not can_see_amount(getattr(request, "user", None)):
            for key in ("heures_mo", "tarif_horaire", "cout_pieces", "cout_main_oeuvre", "cout_total"):
                data[key] = None
            data["has_amount_access"] = False
        return data

    def validate(self, attrs):
        return _apply_and_validate(self, attrs)


class InspectionSerializer(serializers.ModelSerializer):
    actif_code = serializers.CharField(source="actif.code", read_only=True)
    actif_designation = serializers.CharField(source="actif.designation", read_only=True)
    type_label = serializers.CharField(source="get_type_inspection_display", read_only=True)
    resultat_label = serializers.CharField(source="get_resultat_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    intervenant_name = serializers.CharField(
        source="intervenant.get_full_name", read_only=True, default=None
    )
    ot_genere_code = serializers.CharField(source="ot_genere.code", read_only=True, default=None)

    class Meta:
        model = Inspection
        fields = [
            "id", "code", "actif", "actif_code", "actif_designation", "type_inspection",
            "type_label", "date_inspection", "prochaine_inspection", "organisme",
            "organisme_libelle", "resultat", "resultat_label", "constat", "intervenant",
            "intervenant_name", "statut", "statut_label", "ot_genere", "ot_genere_code",
            "created_at", "updated_at",
        ]
        read_only_fields = ["code", "ot_genere"]

    def validate(self, attrs):
        return _apply_and_validate(self, attrs)