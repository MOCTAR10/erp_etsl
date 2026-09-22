"""Sérialiseurs M6 — Qualité & Contrôle Qualité / Inspection."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers

from .models import (
    ActionCorrective,
    ControleQualite,
    NonConformite,
    PvControle,
    QualificationSoudeur,
    Soudeur,
    WpsWpqr,
)


class SoudeurSerializer(serializers.ModelSerializer):
    class Meta:
        model = Soudeur
        fields = [
            "id", "code", "nom", "prenoms", "matricule", "qualification",
            "is_active", "display_name", "created_at", "updated_at",
        ]
        read_only_fields = ["code", "display_name"]


class QualificationSoudeurSerializer(serializers.ModelSerializer):
    soudeur_name = serializers.CharField(source="soudeur.display_name", read_only=True)
    soudeur_code = serializers.CharField(source="soudeur.code", read_only=True)
    norme_label = serializers.CharField(source="get_norme_display", read_only=True)
    procede_label = serializers.CharField(source="get_procede_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    est_valide = serializers.BooleanField(read_only=True)

    class Meta:
        model = QualificationSoudeur
        fields = [
            "id", "code", "soudeur", "soudeur_code", "soudeur_name", "norme",
            "norme_label", "procede", "procede_label", "position",
            "groupe_materiaux", "epaisseur_min", "epaisseur_max", "gamme_diametre",
            "date_qualification", "date_validite", "statut", "statut_label",
            "est_valide", "certificat", "notes", "created_at", "updated_at",
        ]
        read_only_fields = ["code", "statut", "est_valide"]

    def validate(self, attrs):
        instance = self.instance or self.Meta.model(**attrs)
        if self.instance:
            for key, value in attrs.items():
                setattr(instance, key, value)
        try:
            instance.clean()
        except DjangoValidationError as exc:
            if hasattr(exc, "error_dict"):
                raise serializers.ValidationError(exc.message_dict)
            raise serializers.ValidationError({"detail": exc.messages})
        return attrs


class WpsWpqrSerializer(serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    norme_label = serializers.CharField(source="get_norme_display", read_only=True)
    procede_label = serializers.CharField(source="get_procede_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    validated_by_name = serializers.CharField(
        source="validated_by.get_full_name", read_only=True, default=None
    )

    class Meta:
        model = WpsWpqr
        fields = [
            "id", "code", "type", "type_label", "reference", "norme", "norme_label",
            "procede", "procede_label", "materiau", "position", "epaisseur",
            "gaz_protection", "parametres", "revue", "statut", "statut_label",
            "validated_by", "validated_by_name", "date_validation",
            "created_at", "updated_at",
        ]
        read_only_fields = ["code"]


class ControleQualiteSerializer(serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_controle_display", read_only=True)
    organisme_label = serializers.CharField(source="get_organisme_display", read_only=True)
    resultat_label = serializers.CharField(source="get_resultat_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    affaire_code = serializers.CharField(source="affaire.code", read_only=True, default=None)
    ordre_code = serializers.CharField(source="ordre.code", read_only=True, default=None)
    wps_code = serializers.CharField(source="wps.code", read_only=True, default=None)
    lot_code = serializers.CharField(source="lot.code", read_only=True, default=None)
    created_by_name = serializers.CharField(
        source="created_by.get_full_name", read_only=True, default=None
    )

    class Meta:
        model = ControleQualite
        fields = [
            "id", "code", "type_controle", "type_label", "organisme", "organisme_label",
            "organisme_libelle", "affaire", "affaire_code", "ordre", "ordre_code",
            "wps", "wps_code", "lot", "lot_code", "point_controle", "exigence",
            "date_controle", "resultat", "resultat_label", "statut", "statut_label",
            "notes", "created_by", "created_by_name", "created_at", "updated_at",
        ]
        read_only_fields = ["code", "created_by"]

    def validate(self, attrs):
        instance = self.instance or self.Meta.model(**attrs)
        if self.instance:
            for key, value in attrs.items():
                setattr(instance, key, value)
        try:
            instance.full_clean(exclude=["type_controle", "code"])
        except DjangoValidationError as exc:
            if hasattr(exc, "error_dict"):
                raise serializers.ValidationError(exc.message_dict)
            raise serializers.ValidationError({"detail": exc.messages})
        return attrs


class NonConformiteSerializer(serializers.ModelSerializer):
    controle_code = serializers.CharField(source="controle.code", read_only=True, default=None)
    source_label = serializers.CharField(source="get_source_display", read_only=True)
    gravite_label = serializers.CharField(source="get_gravite_display", read_only=True)
    traitement_label = serializers.CharField(source="get_traitement_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    decided_by_name = serializers.CharField(
        source="decided_by.get_full_name", read_only=True, default=None
    )
    actions_count = serializers.SerializerMethodField()

    class Meta:
        model = NonConformite
        fields = [
            "id", "code", "controle", "controle_code", "source", "source_label",
            "gravite", "gravite_label", "description", "traitement", "traitement_label",
            "statut", "statut_label", "decided_by", "decided_by_name",
            "date_decision", "archive", "actions_count", "created_at", "updated_at",
        ]
        read_only_fields = ["code", "actions_count"]

    def get_actions_count(self, obj):
        return obj.actions_correctives.count()

    def validate(self, attrs):
        instance = self.instance or self.Meta.model(**attrs)
        if self.instance:
            for key, value in attrs.items():
                setattr(instance, key, value)
        try:
            instance.clean()
        except DjangoValidationError as exc:
            if hasattr(exc, "error_dict"):
                raise serializers.ValidationError(exc.message_dict)
            raise serializers.ValidationError({"detail": exc.messages})
        return attrs


class ActionCorrectiveSerializer(serializers.ModelSerializer):
    non_conformite_code = serializers.CharField(
        source="non_conformite.code", read_only=True
    )
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    responsable_name = serializers.CharField(
        source="responsable.get_full_name", read_only=True, default=None
    )

    class Meta:
        model = ActionCorrective
        fields = [
            "id", "code", "non_conformite", "non_conformite_code", "type", "type_label",
            "description", "responsable", "responsable_name", "echeance", "statut",
            "statut_label", "efficace", "closed_at", "created_at", "updated_at",
        ]
        read_only_fields = ["code", "closed_at"]


class PvControleSerializer(serializers.ModelSerializer):
    affaire_code = serializers.CharField(source="affaire.code", read_only=True, default=None)
    ordre_code = serializers.CharField(source="ordre.code", read_only=True, default=None)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    resultat_label = serializers.CharField(source="get_resultat_display", read_only=True)
    validated_by_name = serializers.CharField(
        source="validated_by.get_full_name", read_only=True, default=None
    )
    controles = ControleQualiteSerializer(many=True, read_only=True)

    class Meta:
        model = PvControle
        fields = [
            "id", "code", "affaire", "affaire_code", "ordre", "ordre_code", "intitule",
            "controles", "date_pv", "statut", "statut_label", "resultat", "resultat_label",
            "reserve_motif", "levee_reserve", "retention_years", "date_archivage",
            "validated_by", "validated_by_name", "notes", "created_at", "updated_at",
        ]
        read_only_fields = ["code"]