from rest_framework import serializers

from config.serializers import ModelCleanMixin

from .models import (
    AffectationParc,
    ArchiveCompteurGR,
    AuditEquipement,
    HistoriqueEquipement,
    LigneLocationGR,
    ReceptionBLGR,
    ReleveCompteurParc,
    DemandeMobilisation,
    EquipementParc,
    LectureCompteur,
    LocationGR,
    ParametreLogistique,
    TarifGR,
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
    plafond_pct = serializers.SerializerMethodField()
    site_etsl_code = serializers.CharField(source="site_etsl.code", read_only=True, default=None)

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
            "site_etsl",
            "site_etsl_code",
            "plafond_compteur",
            "plafond_pct",
            "is_global_rental",
            "proprietaire",
            "proprietaire_code",
            "proprietaire_gr",
            "signe_618",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "code", "created_at", "updated_at"]

    def validate_plafond_compteur(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Le plafond doit être strictement positif.")
        return value

    def get_plafond_pct(self, obj):
        if not obj.plafond_compteur:
            return None
        return str(round(obj.compteur_value * 100 / obj.plafond_compteur, 2))

    def get_proprietaire_gr(self, obj):
        if not obj.proprietaire:
            return None
        return obj.proprietaire.is_global_rental


class DemandeMobilisationSerializer(ModelCleanMixin, serializers.ModelSerializer):
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
        read_only_fields = ["id", "code", "created_by", "created_by_name", "created_at", "updated_at", "statut"]

    def get_created_by_name(self, obj):
        if not obj.created_by:
            return None
        return (obj.created_by.first_name + " " + obj.created_by.last_name).strip() or obj.created_by.email


class AffectationParcSerializer(ModelCleanMixin, serializers.ModelSerializer):
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
        read_only_fields = ["id", "code", "created_by", "created_at", "updated_at", "statut"]

    def get_responsable_name(self, obj):
        if not obj.responsable:
            return None
        return (obj.responsable.first_name + " " + obj.responsable.last_name).strip() or obj.responsable.email


class LocationGRSerializer(AmountMaskMixin, ModelCleanMixin, serializers.ModelSerializer):
    amount_fields = ["montant_estime", "tarif", "penalite", "facture_ecart", "montant_attendu"]
    tarif_gr_code = serializers.CharField(source="tarif_gr.code", read_only=True, default=None)
    tarif_gr_version = serializers.IntegerField(source="tarif_gr.version", read_only=True, default=None)
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
    bon_commande_code = serializers.CharField(source="bon_commande_achat.code", read_only=True, default=None)
    facture_code = serializers.CharField(source="facture_achat.code", read_only=True, default=None)
    validations = serializers.SerializerMethodField()
    montant_attendu = serializers.SerializerMethodField()

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
            "tarif_gr",
            "tarif_gr_code",
            "tarif_gr_version",
            "emis_le",
            "emis_par",
            "date_retour",
            "jours_retard",
            "penalite",
            "statut",
            "statut_label",
            "lectures_count",
            "valide_m2_par",
            "valide_m2_le",
            "valide_dr_par",
            "valide_dr_le",
            "validations",
            "bon_commande_achat",
            "bon_commande_code",
            "facture_achat",
            "facture_code",
            "facture_ecart",
            "facture_conforme",
            "montant_attendu",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "valide_m2_par", "valide_m2_le", "valide_dr_par", "valide_dr_le", "bon_commande_achat",
            "facture_achat", "facture_ecart", "facture_conforme",
            "id",
            "code",
            "created_by",
            "created_by_name",
            "lectures_count",
            "consommation",
            "created_at",
            "updated_at", "statut", "tarif_gr", "date_retour", "jours_retard", "penalite", "emis_le", "emis_par"]

    def get_validations(self, obj):
        from .services import validations_requises

        req = validations_requises(obj)
        return {"m2": req["m2"], "dr": req["dr"], "m2_ok": bool(obj.valide_m2_le), "dr_ok": bool(obj.valide_dr_le)}

    def get_montant_attendu(self, obj):
        from .services import montant_attendu

        return str(montant_attendu(obj))

    # Champs figés dès le démarrage : la version de grille retenue fait foi (lot 14, CDC M4 §12.4).
    TARIF_FIGE = ("tarif", "periodicite", "partenaire", "equipement", "date_debut")

    def validate(self, attrs):
        if self.instance and self.instance.statut != LocationGR.Statut.BROUILLON:
            figes = [f for f in self.TARIF_FIGE if f in attrs and attrs[f] != getattr(self.instance, f)]
            if figes:
                raise serializers.ValidationError(
                    {f: "Tarif figé au démarrage de la prestation : non modifiable." for f in figes}
                )
        return super().validate(attrs)

    def get_created_by_name(self, obj):
        if not obj.created_by:
            return None
        return (obj.created_by.first_name + " " + obj.created_by.last_name).strip() or obj.created_by.email


class TarifGRSerializer(AmountMaskMixin, ModelCleanMixin, serializers.ModelSerializer):
    amount_fields = ["tarif", "penalite_jour"]
    partenaire_code = serializers.CharField(source="partenaire.code", read_only=True, default=None)
    equipement_code = serializers.CharField(source="equipement.code", read_only=True, default=None)
    categorie_label = serializers.CharField(source="get_categorie_display", read_only=True)
    periodicite_label = serializers.CharField(source="get_periodicite_display", read_only=True)

    class Meta:
        model = TarifGR
        fields = [
            "id", "code", "partenaire", "partenaire_code", "equipement", "equipement_code",
            "categorie", "categorie_label", "periodicite", "periodicite_label", "tarif",
            "penalite_jour", "date_effet", "version", "created_by", "created_at",
        ]
        read_only_fields = ["id", "code", "version", "created_by", "created_at"]


class LectureCompteurSerializer(ModelCleanMixin, serializers.ModelSerializer):
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

class ParametreLogistiqueSerializer(serializers.ModelSerializer):
    est_provisoire = serializers.BooleanField(read_only=True)

    class Meta:
        model = ParametreLogistique
        fields = [
            "id", "code", "label", "valeur", "unite", "statut_valeur", "est_provisoire",
            "confirme_par", "confirme_le",
        ]
        read_only_fields = ["code", "label", "unite", "statut_valeur", "confirme_par", "confirme_le"]

    def validate_valeur(self, value):
        if value <= 0:
            raise serializers.ValidationError("La valeur doit être strictement positive.")
        return value

    def update(self, instance, validated_data):
        # Une valeur modifiée redevient provisoire jusqu'à nouvelle confirmation.
        if "valeur" in validated_data and validated_data["valeur"] != instance.valeur:
            instance.statut_valeur = ParametreLogistique.StatutValeur.PROVISOIRE
            instance.confirme_par = None
            instance.confirme_le = None
        return super().update(instance, validated_data)


# --------------------------------------------------------------------------------------------------
# Écarts M4
# --------------------------------------------------------------------------------------------------
def _nom(user):
    if not user:
        return None
    return (user.first_name + " " + user.last_name).strip() or user.email


class ReleveCompteurParcSerializer(serializers.ModelSerializer):
    equipement_code = serializers.CharField(source="equipement.code", read_only=True)
    source_label = serializers.CharField(source="get_source_display", read_only=True)
    saisi_par_name = serializers.SerializerMethodField()

    class Meta:
        model = ReleveCompteurParc
        fields = [
            "id", "equipement", "equipement_code", "date", "valeur", "source", "source_label", "commentaire",
            "saisi_par", "saisi_par_name", "created_at",
        ]
        read_only_fields = ["id", "source", "saisi_par", "created_at"]

    def validate_valeur(self, value):
        if value < 0:
            raise serializers.ValidationError("La valeur du compteur ne peut être négative.")
        return value

    def get_saisi_par_name(self, obj):
        return _nom(obj.saisi_par)


class HistoriqueEquipementSerializer(serializers.ModelSerializer):
    equipement_code = serializers.CharField(source="equipement.code", read_only=True)
    modifie_par_name = serializers.SerializerMethodField()

    class Meta:
        model = HistoriqueEquipement
        fields = [
            "id", "equipement", "equipement_code", "champ", "ancienne_valeur", "nouvelle_valeur",
            "modifie_par", "modifie_par_name", "modifie_le",
        ]
        read_only_fields = fields

    def get_modifie_par_name(self, obj):
        return _nom(obj.modifie_par)


class AuditEquipementSerializer(serializers.ModelSerializer):
    equipement_code = serializers.CharField(source="equipement.code", read_only=True)
    etat_label = serializers.CharField(source="get_etat_display", read_only=True)
    auditeur_name = serializers.SerializerMethodField()

    class Meta:
        model = AuditEquipement
        fields = [
            "id", "code", "equipement", "equipement_code", "date_audit", "etat", "etat_label", "compteur",
            "observations", "photo", "photo_sha256", "conserver_jusqu_au", "auditeur", "auditeur_name", "created_at",
        ]
        read_only_fields = ["id", "code", "photo_sha256", "conserver_jusqu_au", "auditeur", "created_at"]

    def validate_photo(self, value):
        nom = (value.name or "").lower()
        if not nom.endswith((".jpg", ".jpeg", ".png", ".webp", ".heic")):
            raise serializers.ValidationError("Photo attendue (jpg, png, webp, heic).")
        return value

    def get_auditeur_name(self, obj):
        return _nom(obj.auditeur)


class LigneLocationGRSerializer(AmountMaskMixin, ModelCleanMixin, serializers.ModelSerializer):
    amount_fields = ["prix_unitaire", "montant"]
    location_code = serializers.CharField(source="location.code", read_only=True)
    montant = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)

    class Meta:
        model = LigneLocationGR
        fields = [
            "id", "location", "location_code", "designation", "quantite", "unite", "prix_unitaire", "montant",
            "quantite_livree", "created_at",
        ]
        read_only_fields = ["id", "quantite_livree", "created_at"]

    def validate(self, attrs):
        location = attrs.get("location") or (self.instance.location if self.instance else None)
        if location is not None and (location.statut != LocationGR.Statut.BROUILLON or location.emis_le):
            raise serializers.ValidationError({"location": "Lignes du BC figées après émission du BC / GR."})
        if self.instance and "location" in attrs and attrs["location"] != self.instance.location:
            raise serializers.ValidationError({"location": "Une ligne ne change pas de prestation."})
        return super().validate(attrs)


class ReceptionBLGRSerializer(serializers.ModelSerializer):
    location_code = serializers.CharField(source="location.code", read_only=True)
    contentieux_code = serializers.CharField(source="contentieux.code", read_only=True, default=None)
    dossier_gr_code = serializers.CharField(source="dossier_gr.code", read_only=True, default=None)
    recu_par_name = serializers.SerializerMethodField()

    class Meta:
        model = ReceptionBLGR
        fields = [
            "id", "code", "location", "location_code", "reference_bl", "date_reception", "lignes", "ecart_pct",
            "reserves", "litige", "contentieux", "contentieux_code", "dossier_gr", "dossier_gr_code", "recu_par",
            "recu_par_name", "created_at",
        ]
        read_only_fields = fields

    def get_recu_par_name(self, obj):
        return _nom(obj.recu_par)


class ArchiveCompteurGRSerializer(serializers.ModelSerializer):
    location_code = serializers.CharField(source="location.code", read_only=True)
    integre = serializers.SerializerMethodField()

    class Meta:
        model = ArchiveCompteurGR
        fields = ["id", "location", "location_code", "contenu", "sha256", "integre", "conserver_jusqu_au", "created_at"]
        read_only_fields = fields

    def get_integre(self, obj):
        from .services import archive_integre

        return archive_integre(obj)
