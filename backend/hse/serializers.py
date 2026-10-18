"""Sérialiseurs M7 — HSE : Hygiène, Sécurité & Environnement."""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import (
    ActionHse,
    AuditHse,
    BordereauDechet,
    ConstatAudit,
    Duer,
    Epi,
    EquipementAtex,
    EvaluationRisque,
    ExerciceUrgence,
    ExigenceHabilitation,
    FormationSecurite,
    Incident,
    PermisTravail,
    PlanUrgence,
)


def _validate_instance(instance, exclude=()):
    """Valide le modèle (clean) et remonte les erreurs Django vers DRF."""
    try:
        instance.full_clean(exclude=list(exclude))
    except DjangoValidationError as exc:
        if hasattr(exc, "error_dict"):
            raise serializers.ValidationError(exc.message_dict)
        raise serializers.ValidationError({"detail": exc.messages})


def _apply_and_validate(serializer, attrs, exclude=("code",)):
    """Applique les attrs sur l'instance et valide le modèle ; retourne attrs."""
    instance = serializer.instance or serializer.Meta.model(**attrs)
    if serializer.instance:
        for key, value in attrs.items():
            setattr(instance, key, value)
    _validate_instance(instance, exclude=exclude)
    return attrs


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
    gaz_obligatoire = serializers.BooleanField(read_only=True)
    test_gaz_valide = serializers.BooleanField(read_only=True)

    prochain_niveau = serializers.CharField(read_only=True, allow_null=True)

    class Meta:
        model = PermisTravail
        fields = [
            "id", "code", "type_permis", "type_label", "affaire", "affaire_code",
            "ordre", "ordre_code", "emplacement", "description", "mesures",
            "demandeur", "demandeur_name", "validateur", "validateur_name",
            "visa_superviseur_par", "visa_superviseur_le", "visa_hse_par", "visa_hse_le", "visa_dg_par", "visa_dg_le", "prochain_niveau",
            "date_debut", "date_fin", "statut", "statut_label",
            "date_validation", "date_cloture", "notes", "created_at", "updated_at",
            "gaz_obligatoire", "test_gaz_resultat", "test_gaz_valeur", "test_gaz_date",
            "test_gaz_par", "test_gaz_valide", "intervenants",
        ]
        read_only_fields = [
            "visa_superviseur_par", "visa_superviseur_le", "visa_hse_par", "visa_hse_le", "visa_dg_par", "visa_dg_le", "prochain_niveau","validateur", "demandeur", 
            "code", "date_validation", "date_cloture", "statut", "gaz_obligatoire",
            "test_gaz_resultat", "test_gaz_valeur", "test_gaz_date", "test_gaz_par", "test_gaz_valide",
        ]

    def validate(self, attrs):
        # M2M exclu du constructeur du modèle (cf. _apply_and_validate), puis remis pour create()/update().
        intervenants = attrs.pop("intervenants", None)
        _apply_and_validate(self, attrs)
        if intervenants is not None:
            attrs["intervenants"] = intervenants
        return attrs


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
            "responsable_name", "affaire", "affaire_code", "duer", "statut", "statut_label",
            "created_at", "updated_at",
        ]
        read_only_fields = ["code", "score", "criticite"]

    def validate(self, attrs):
        # Un DUER approuvé est scellé : ni ajout, ni modification, ni retrait de risque.
        cibles = [attrs.get("duer"), self.instance.duer if self.instance else None]
        if any(d and d.statut == Duer.Statut.APPROUVE for d in cibles):
            raise serializers.ValidationError({"detail": "DUER approuvé : scellé, créer une nouvelle version."})
        return _apply_and_validate(self, attrs)


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
    consequence_humaine_label = serializers.CharField(source="get_consequence_humaine_display", read_only=True)

    class Meta:
        model = Incident
        fields = [
            "id", "code", "type_incident", "type_label", "gravite", "gravite_label",
            "date_evenement", "lieu", "description", "personnes_impliquees",
            "cause_immediate", "cause_profonde", "consequences", "consequence_humaine",
            "consequence_humaine_label", "jours_arret", "rapport",
            "statut", "statut_label", "archive", "declared_by", "declared_by_name",
            "enqueteur", "enqueteur_name", "date_ouverture_enquete", "date_rapport",
            "actions_count", "created_at", "updated_at",
        ]
        read_only_fields = ["declared_by", "code", "actions_count", "date_ouverture_enquete", "statut"]

    def get_actions_count(self, obj):
        return obj.actions.count()

    def validate(self, attrs):
        return _apply_and_validate(self, attrs)


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
        read_only_fields = ["code", "closed_at", "statut"]


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


class ExigenceHabilitationSerializer(serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_permis_display", read_only=True)

    class Meta:
        model = ExigenceHabilitation
        fields = ["id", "type_permis", "type_label", "mot_cle", "actif"]

    def validate(self, attrs):
        return _apply_and_validate(self, attrs, exclude=("code",))


class ConstatAuditSerializer(serializers.ModelSerializer):
    gravite_label = serializers.CharField(source="get_gravite_display", read_only=True)
    action_code = serializers.CharField(source="action.code", read_only=True, default=None)
    action_statut = serializers.CharField(source="action.statut", read_only=True, default=None)

    class Meta:
        model = ConstatAudit
        fields = [
            "id", "audit", "description", "gravite", "gravite_label", "action", "action_code",
            "action_statut", "created_at",
        ]

    def validate(self, attrs):
        audit = attrs.get("audit") or (self.instance.audit if self.instance else None)
        if audit and audit.statut == AuditHse.Statut.CLOTURE:
            raise serializers.ValidationError({"detail": "Audit clôturé : ses constats sont scellés."})
        return attrs


class AuditHseSerializer(serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_audit_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    nb_constats = serializers.SerializerMethodField()
    nb_ecarts_ouverts = serializers.SerializerMethodField()

    class Meta:
        model = AuditHse
        fields = [
            "id", "code", "type_audit", "type_label", "zone", "referentiel", "date_prevue",
            "date_realisation", "score", "statut", "statut_label", "realise_par", "cloture_par",
            "cloture_le", "nb_constats", "nb_ecarts_ouverts", "created_at", "updated_at",
        ]
        read_only_fields = [
            "code", "date_realisation", "score", "statut", "realise_par", "cloture_par", "cloture_le",
        ]

    def get_nb_constats(self, obj):
        return obj.constats.count()

    def get_nb_ecarts_ouverts(self, obj):
        return len(obj.ecarts_ouverts)

    def validate(self, attrs):
        if self.instance and self.instance.statut == AuditHse.Statut.CLOTURE:
            raise serializers.ValidationError({"detail": "Audit clôturé : modification impossible."})
        return attrs


class DuerSerializer(serializers.ModelSerializer):
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    nb_risques = serializers.SerializerMethodField()
    a_revoir = serializers.BooleanField(read_only=True)

    class Meta:
        model = Duer
        fields = [
            "id", "code", "annee", "perimetre", "version", "statut", "statut_label", "approuve_par",
            "approuve_le", "nb_risques", "a_revoir", "created_at", "updated_at",
        ]
        read_only_fields = ["code", "version", "statut", "approuve_par", "approuve_le"]
        validators = []  # la version est attribuée par save() : le validateur d'unicité DRF la exigerait

    def get_nb_risques(self, obj):
        return obj.risques.count()

    def validate(self, attrs):
        if self.instance and self.instance.statut == Duer.Statut.APPROUVE:
            raise serializers.ValidationError({"detail": "DUER approuvé : scellé, créer une nouvelle version."})
        return attrs


class ExerciceUrgenceSerializer(serializers.ModelSerializer):
    resultat_label = serializers.CharField(source="get_resultat_display", read_only=True)

    class Meta:
        model = ExerciceUrgence
        fields = [
            "id", "plan", "date_exercice", "participants", "resultat", "resultat_label",
            "observations", "created_at",
        ]

    def validate(self, attrs):
        return _apply_and_validate(self, attrs, exclude=("code",))


class PlanUrgenceSerializer(serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_plan_display", read_only=True)
    dernier_exercice = serializers.DateField(read_only=True)
    prochain_exercice = serializers.DateField(read_only=True)
    en_retard = serializers.BooleanField(read_only=True)

    class Meta:
        model = PlanUrgence
        fields = [
            "id", "code", "type_plan", "type_label", "intitule", "perimetre", "periodicite_mois", "actif",
            "dernier_exercice", "prochain_exercice", "en_retard", "created_at", "updated_at",
        ]
        read_only_fields = ["code"]
