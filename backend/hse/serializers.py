"""Sérialiseurs M7 — HSE : Hygiène, Sécurité & Environnement."""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import (
    ActionHse,
    BordereauDechet,
    Epi,
    EquipementAtex,
    EvaluationRisque,
    FormationSecurite,
    Incident,
    PermisTravail,
)


def _validate_instance(serializer, instance, exclude=()):
    """Valide le modèle (clean) et remonte les erreurs Django vers DRF."""
    try:
        instance.full_clean(exclude=list(exclude))
    except DjangoValidationError as exc:
        if hasattr(exc, "error_dict"):
            raise serializers.ValidationError(exc.message_dict)
        raise serializers.ValidationError({"detail": exc.messages})
    return serializer


class PermisTravailSerializer(serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_permis_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    affaire_code = serializers.CharField(source="affaire.code", read_only=True, default=None)
    ordre_code = serializers.CharField(source="ordre.code", read_only=True, default=None)
    demandeur_name = serializers.CharField(
        source="demandeur.get_full_name", read_only=True, default=None
    )
    validateur_name = serializers.CharField(
        source="validateur.get_full_name", read_only=True, default=None
    )

    class Meta:
        model = PermisTravail
        fields = [
            "id", "code", "type_permis", "type_label", "affaire", "affaire_code",
            "ordre", "ordre_code", "emplacement", "description", "mesures",
            "demandeur", "demandeur_name", "validateur", "validateur_name",
            "date_debut", "date_fin", "statut", "statut_label",
            "date_validation", "date_cloture", "notes", "created_at", "updated_at",
        ]
        read_only_fields = ["code", "date_validation", "date_cloture"]

    def validate(self, attrs):
        instance = self.instance or self.Meta.model(**attrs)
        if self.instance:
            for key, value in attrs.items():
                setattr(instance, key, value)
        return _validate_instance(self, instance, exclude=["code"])


class EvaluationRisqueSerializer(serializers.ModelSerializer):
    criticite = serializers.CharField(read_only=True)
    score = serializers.IntegerField(read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    responsable_name = serializers.CharField(
        source="responsable.get_full_name", read_only=True, default=None
    )
    affaire_code = serializers.CharField(source="affaire.code", read_only=True, default=None)

    class Meta:
        model = EvaluationRisque
        fields = [
            "id", "code", "lieux", "activite", "description", "probabilite",
            "gravite", "score", "criticite", "mesure", "responsable",
            "responsable_name", "affaire", "affaire_code", "statut", "statut_label",
            "created_at", "updated_at",
        ]
        read_only_fields = ["code", "score", "criticite"]

    def validate(self, attrs):
        instance = self.instance or self.Meta.model(**attrs)
        if self.instance:
            for key, value in attrs.items():
                setattr(instance, key, value)
        return _validate_instance(self, instance, exclude=["code"])


class EquipementAtexSerializer(serializers.ModelSerializer):
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    certificat_expire = serializers.BooleanField(read_only=True)

    class Meta:
        model = EquipementAtex
        fields = [
            "id", "code", "designation", "zone_atex", "marquage", "fabricant",
            "numero_serie", "certificat", "date_expiration_certificat",
            "certificat_expire", "date_derniere_inspection", "prochaine_inspection",
            "statut", "statut_label", "notes", "created_at", "updated_at",
        ]
        read_only_fields = ["code", "certificat_expire"]


class IncidentSerializer(serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_incident_display", read_only=True)
    gravite_label = serializers.CharField(source="get_gravite_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    declared_by_name = serializers.CharField(
        source="declared_by.get_full_name", read_only=True, default=None
    )
    enqueteur_name = serializers.CharField(
        source="enqueteur.get_full_name", read_only=True, default=None
    )
    actions_count = serializers.SerializerMethodField()

    class Meta:
        model = Incident
        fields = [
            "id", "code", "type_incident", "type_label", "gravite", "gravite_label",
            "date_evenement", "lieu", "description", "personnes_impliquees",
            "cause_immediate", "cause_profonde", "consequences", "rapport",
            "statut", "statut_label", "archive", "declared_by", "declared_by_name",
            "enqueteur", "enqueteur_name", "date_ouverture_enquete", "date_rapport",
            "actions_count", "created_at", "updated_at",
        ]
        read_only_fields = ["code", "actions_count", "date_ouverture_enquete"]

    def get_actions_count(self, obj):
        return obj.actions.count()

    def validate(self, attrs):
        instance = self.instance or self.Meta.model(**attrs)
        if self.instance:
            for key, value in attrs.items():
                setattr(instance, key, value)
        return _validate_instance(self, instance, exclude=["code"])


class ActionHseSerializer(serializers.ModelSerializer):
    incident_code = serializers.CharField(source="incident.code", read_only=True, default=None)
    risque_code = serializers.CharField(source="risque.code", read_only=True, default=None)
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    responsable_name = serializers.CharField(
        source="responsable.get_full_name", read_only=True, default=None
    )

    class Meta:
        model = ActionHse
        fields = [
            "id", "code", "incident", "incident_code", "risque", "risque_code",
            "type", "type_label", "description", "responsable", "responsable_name",
            "echeance", "statut", "statut_label", "efficace", "closed_at",
            "created_at", "updated_at",
        ]
        read_only_fields = ["code", "closed_at"]


class FormationSecuriteSerializer(serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_session_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)

    class Meta:
        model = FormationSecurite
        fields = [
            "id", "code", "type_session", "type_label", "theme", "formateur",
            "organisme", "date_session", "duree_heures", "nb_participants",
            "evalue", "statut", "statut_label", "notes", "created_at", "updated_at",
        ]
        read_only_fields = ["code"]


class EpiSerializer(serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_epi_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    beneficiaire_name = serializers.CharField(
        source="beneficiaire.get_full_name", read_only=True, default=None
    )
    a_renouveler = serializers.BooleanField(read_only=True)

    class Meta:
        model = Epi
        fields = [
            "id", "code", "type_epi", "type_label", "designation", "taille",
            "beneficiaire", "beneficiaire_name", "date_dotation",
            "date_renouvellement", "a_renouveler", "statut", "statut_label",
            "notes", "created_at", "updated_at",
        ]
        read_only_fields = ["code", "a_renouveler"]


class BordereauDechetSerializer(serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_dechet_display", read_only=True)
    unite_label = serializers.CharField(source="get_unite_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    transporteur_name = serializers.CharField(
        source="transporteur.name", read_only=True, default=None
    )

    class Meta:
        model = BordereauDechet
        fields = [
            "id", "code", "type_dechet", "type_label", "quantite", "unite",
            "unite_label", "transporteur", "transporteur_name", "numero_bsd",
            "date_enlevement", "destination", "statut", "statut_label", "notes",
            "created_at", "updated_at",
        ]
        read_only_fields = ["code"]