"""Sérialiseurs M7 — HSE : Hygiène, Sécurité & Environnement."""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from rh_paie.models import Employe

from .models import (
    ConsommationEnvironnement,
    PlanReductionImpact,
    RevueDirectionHse,
    AptitudeMedicale,
    ParametreHse,
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
    plan_prevention_code = serializers.CharField(source="plan_prevention.code", read_only=True, default=None)

    prochain_niveau = serializers.CharField(read_only=True, allow_null=True)
    intervenants_noms = serializers.SerializerMethodField()

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
            "test_gaz_par", "test_gaz_valide", "intervenants", "intervenants_noms", "photo", "plan",
            "site_gr", "plan_prevention", "plan_prevention_code",
        ]
        read_only_fields = [
            "visa_superviseur_par", "visa_superviseur_le", "visa_hse_par", "visa_hse_le", "visa_dg_par", "visa_dg_le", "prochain_niveau","validateur", "demandeur", 
            "code", "date_validation", "date_cloture", "statut", "gaz_obligatoire",
            "test_gaz_resultat", "test_gaz_valeur", "test_gaz_date", "test_gaz_par", "test_gaz_valide",
            "photo", "plan",
        ]

    def get_intervenants_noms(self, obj):
        return [str(e) for e in obj.intervenants.all()]

    def validate_type_permis(self, value):
        from .ecarts_m6m7 import valider_code

        return valider_code("type_permis", value, self.instance.type_permis if self.instance else None)

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
    document_titre = serializers.CharField(source="document.title", read_only=True, default=None)
    ncr_hse = serializers.SerializerMethodField()

    class Meta:
        model = Incident
        fields = [
            "id", "code", "type_incident", "type_label", "gravite", "gravite_label",
            "date_evenement", "lieu", "description", "personnes_impliquees",
            "cause_immediate", "cause_profonde", "consequences", "consequence_humaine",
            "consequence_humaine_label", "jours_arret", "rapport", "zone", "retour_experience",
            "statut", "statut_label", "archive", "declared_by", "declared_by_name",
            "enqueteur", "enqueteur_name", "date_ouverture_enquete", "date_rapport", "plan_action_le",
            "document", "document_titre", "ncr_hse", "actions_count", "created_at", "updated_at",
        ]
        read_only_fields = ["declared_by", "code", "actions_count", "date_ouverture_enquete", "statut", "archive",
                            "plan_action_le", "document"]

    def get_actions_count(self, obj):
        return obj.actions.count()

    def get_ncr_hse(self, obj):
        return [f"{nc.code} ({nc.get_statut_display()})" for nc in obj.ncr_hse.all()]

    def validate_type_incident(self, value):
        from .ecarts_m6m7 import valider_code

        return valider_code("type_incident", value, self.instance.type_incident if self.instance else None)

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

    participants = serializers.PrimaryKeyRelatedField(many=True, required=False, queryset=Employe.objects.all())
    participants_noms = serializers.SerializerMethodField()

    class Meta:
        model = FormationSecurite
        fields = [
            "participants", "participants_noms", "validite_mois",
            "id", "code", "type_session", "type_label", "theme", "formateur",
            "organisme", "date_session", "duree_heures", "nb_participants",
            "evalue", "statut", "statut_label", "notes", "created_at", "updated_at",
        ]
        read_only_fields = ["code", "nb_participants"]

    def get_participants_noms(self, obj):
        return [str(e) for e in obj.participants.all()]

    def validate(self, attrs):
        participants = attrs.pop("participants", None)  # M2M hors du constructeur (piège AGENTS n°2)
        attrs = _apply_and_validate(self, attrs)
        if participants is not None:
            attrs["participants"] = participants
        return attrs


class EpiSerializer(serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_epi_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    beneficiaire_name = serializers.CharField(
        source="beneficiaire.get_full_name", read_only=True, default=None
    )
    a_renouveler = serializers.BooleanField(read_only=True)

    employe_nom = serializers.SerializerMethodField()

    def get_employe_nom(self, obj):
        return str(obj.employe) if obj.employe_id else None

    class Meta:
        model = Epi
        fields = [
            "employe", "employe_nom",
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
    prestataire_nom = serializers.CharField(source="prestataire.nom", read_only=True, default=None)

    class Meta:
        model = BordereauDechet
        fields = [
            "id", "code", "type_dechet", "type_label", "quantite", "unite",
            "unite_label", "transporteur", "transporteur_name", "numero_bsd",
            "date_enlevement", "destination", "statut", "statut_label", "notes", "document",
            "prestataire", "prestataire_nom", "created_at", "updated_at",
        ]
        read_only_fields = ["code", "document"]

    def validate_type_dechet(self, value):
        from .ecarts_m6m7 import valider_code

        return valider_code("type_dechet", value, self.instance.type_dechet if self.instance else None)

    def validate(self, attrs):
        # BSD émis ou traité : prestataire déchets agréé, en cours de validité, pour ce type (paramètre provisoire).
        statut = attrs.get("statut", self.instance.statut if self.instance else BordereauDechet.Statut.EN_ATTENTE)
        if statut != BordereauDechet.Statut.EN_ATTENTE and (not self.instance or self.instance.statut != statut):
            from .ecarts_m6m7 import controle_prestataire_bsd

            courant = lambda champ: attrs.get(champ, getattr(self.instance, champ, None))  # noqa: E731
            if erreur := controle_prestataire_bsd(courant("type_dechet") or BordereauDechet.TypeDechet.DIB,
                                                  courant("prestataire"), courant("date_enlevement")):
                raise serializers.ValidationError({"prestataire": erreur})
        return attrs


class ExigenceHabilitationSerializer(serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_permis_display", read_only=True)

    class Meta:
        model = ExigenceHabilitation
        fields = ["id", "type_permis", "type_label", "mot_cle", "actif"]

    def validate_type_permis(self, value):
        from .ecarts_m6m7 import valider_code

        return valider_code("type_permis", value, self.instance.type_permis if self.instance else None)

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


class AptitudeMedicaleSerializer(serializers.ModelSerializer):
    employe_nom = serializers.SerializerMethodField()
    resultat_label = serializers.CharField(source="get_resultat_display", read_only=True)

    class Meta:
        model = AptitudeMedicale
        fields = ["id", "employe", "employe_nom", "date_visite", "date_validite", "resultat", "resultat_label",
                  "restrictions", "medecin", "created_at"]

    def get_employe_nom(self, obj):
        return str(obj.employe)

    def validate(self, attrs):
        return _apply_and_validate(self, attrs, exclude=())


class ParametreHseSerializer(serializers.ModelSerializer):
    est_provisoire = serializers.BooleanField(read_only=True)

    class Meta:
        model = ParametreHse
        fields = ["id", "code", "label", "valeur", "unite", "statut_valeur", "est_provisoire", "confirme_par", "confirme_le"]
        read_only_fields = ["code", "label", "unite", "statut_valeur", "confirme_par", "confirme_le"]

    def validate_valeur(self, value):
        from .ecarts_m6m7 import PARAMETRES_BOOLEENS

        if self.instance and self.instance.code in PARAMETRES_BOOLEENS:
            if value not in (0, 1):
                raise serializers.ValidationError("Valeur attendue : 1 (oui) ou 0 (non).")
            return value
        if value <= 0:
            raise serializers.ValidationError("La valeur doit être strictement positive.")
        return value

    def update(self, instance, validated_data):
        if "valeur" in validated_data and validated_data["valeur"] != instance.valeur:
            instance.statut_valeur = ParametreHse.StatutValeur.PROVISOIRE
            instance.confirme_par = None
            instance.confirme_le = None
        return super().update(instance, validated_data)


class PersonnelHseSerializer(serializers.ModelSerializer):
    nom_complet = serializers.SerializerMethodField()

    class Meta:
        model = Employe
        fields = ["id", "code", "nom_complet"]

    def get_nom_complet(self, obj):
        return str(obj)


class ConsommationEnvironnementSerializer(serializers.ModelSerializer):
    ressource_label = serializers.CharField(source="get_ressource_display", read_only=True)
    unite = serializers.CharField(read_only=True)

    class Meta:
        model = ConsommationEnvironnement
        fields = ["id", "code", "ressource", "ressource_label", "periode", "site", "quantite", "unite", "source",
                  "saisi_par", "created_at"]
        read_only_fields = ["code", "saisi_par"]

    def validate_periode(self, value):
        return value.replace(day=1)  # relevé mensuel : le doublon (ressource, mois, site) est refusé en 400

    def validate(self, attrs):
        return _apply_and_validate(self, attrs)


class PlanReductionImpactSerializer(serializers.ModelSerializer):
    ressource_label = serializers.CharField(source="get_ressource_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    avancement = serializers.SerializerMethodField()

    class Meta:
        model = PlanReductionImpact
        fields = ["id", "code", "objectif", "ressource", "ressource_label", "annee_reference", "annee_cible",
                  "reduction_cible_pct", "actions", "responsable", "statut", "statut_label", "avancement", "created_at"]
        read_only_fields = ["code"]

    def get_avancement(self, obj):
        from .services import avancement_plan

        return avancement_plan(obj)

    def validate(self, attrs):
        return _apply_and_validate(self, attrs)


class RevueDirectionHseSerializer(serializers.ModelSerializer):
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)

    class Meta:
        model = RevueDirectionHse
        fields = ["id", "code", "annee", "date_revue", "participants", "conclusions", "decisions", "bilan", "statut",
                  "statut_label", "validee_par", "validee_le", "document", "created_at"]
        read_only_fields = ["code", "bilan", "statut", "validee_par", "validee_le", "document"]
