"""Sérialiseurs M6 — Qualité & Contrôle Qualité / Inspection."""

from django.core.exceptions import ValidationError as DjangoValidationError
from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from config.serializers import ModelCleanMixin

from .ecarts import get_param_qualite, qualification_couvrante
from .models import (
    AuditQualite,
    ConstatAuditQualite,
    DocumentQualite,
    ProcessusQualite,
    ResponsabiliteQualite,
    RevueDirectionQualite,
    CritereControle,
    MesureControle,
    DiffusionWps,
    ParametreQualite,
    PunchItem,
    Etalonnage,
    EpreuvePression,
    ImageControle,
    InstrumentMesure,
    JointSoude,
    PointInspection,
    ActionCorrective,
    ControleQualite,
    NonConformite,
    PvControle,
    QualificationSoudeur,
    Soudeur,
    WpsWpqr,
)


class SoudeurSerializer(serializers.ModelSerializer):
    employe_code = serializers.CharField(source="employe.code", read_only=True, default=None)
    employe_nom = serializers.CharField(source="employe.nom_complet", read_only=True, default=None)

    class Meta:
        model = Soudeur
        fields = [
            "id", "code", "nom", "prenoms", "matricule", "qualification",
            "is_active", "display_name", "employe", "employe_code", "employe_nom", "created_at", "updated_at",
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
    wpqr_code = serializers.CharField(source="wpqr.code", read_only=True, default=None)
    ordres_diffusion = serializers.SerializerMethodField()

    class Meta:
        model = WpsWpqr
        fields = [
            "id", "code", "type", "type_label", "reference", "norme", "norme_label",
            "procede", "procede_label", "materiau", "position", "epaisseur",
            "gaz_protection", "parametres", "revue", "statut", "statut_label",
            "validated_by", "validated_by_name", "date_validation", "wpqr", "wpqr_code", "fichier",
            "obsolete_le", "obsolete_motif", "ordres_diffusion", "created_at", "updated_at",
        ]
        read_only_fields = ["statut", "validated_by", "date_validation", "code", "fichier", "obsolete_le", "obsolete_motif"]

    def get_ordres_diffusion(self, obj):
        return [d.ordre.code for d in obj.diffusions.select_related("ordre")]

    def validate_wpqr(self, wpqr):
        if wpqr and wpqr.type != WpsWpqr.Type.WPQR:
            raise serializers.ValidationError("Le support d'un WPS est un WPQR (PQR).")
        if wpqr and self.instance and wpqr.pk == self.instance.pk:
            raise serializers.ValidationError("Un WPS ne peut pas être son propre WPQR.")
        return wpqr


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
            "points", "points_arret_restants", "methode_cnd", "instrument", "instrument_code",
            "approuve_par", "approuve_le", "images_count", "mesures",
        ]
        read_only_fields = [
            "code", "created_by", "points", "points_arret_restants", "approuve_par", "approuve_le", "images_count",
            "mesures",
        ]

    instrument_code = serializers.CharField(source="instrument.code", read_only=True, default=None)
    images_count = serializers.SerializerMethodField()
    mesures = serializers.SerializerMethodField()
    points = serializers.SerializerMethodField()
    points_arret_restants = serializers.SerializerMethodField()

    def get_points(self, obj):
        return PointInspectionSerializer(obj.points.all(), many=True, context=self.context).data

    def get_images_count(self, obj):
        return obj.images.count()

    def get_mesures(self, obj):
        return MesureControleSerializer(obj.mesures.select_related("critere"), many=True).data

    def get_points_arret_restants(self, obj):
        return obj.points.filter(type_point="arret").exclude(statut="leve").count()

    def validate(self, attrs):
        # Un ITP ne se valide pas tant qu'un point d'ARRÊT n'est pas levé (CL-OM-07).
        if (
            self.instance
            and attrs.get("statut") == ControleQualite.Statut.VALIDE
            and self.instance.type_controle == ControleQualite.TypeControle.ITP
            and self.instance.points.filter(type_point="arret").exclude(statut="leve").exists()
        ):
            raise serializers.ValidationError(
                {"statut": "ITP non validable : au moins un point d'arrêt n'est pas levé."}
            )
        instrument = attrs.get("instrument")
        if instrument and (not self.instance or self.instance.instrument_id != instrument.pk) and not instrument.utilisable:
            raise serializers.ValidationError(
                {"instrument": "Instrument hors échéance d'étalonnage ou bloqué : utilisation interdite."}
            )
        type_controle = attrs.get("type_controle") or (self.instance.type_controle if self.instance else None)
        if type_controle == ControleQualite.TypeControle.TTH:
            four = instrument or (self.instance.instrument if self.instance else None)
            if four is None or four.type_equipement != "four_tth":
                raise serializers.ValidationError({"instrument": "Un traitement thermique se trace avec un four TTH validé."})
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
    incident_hse_code = serializers.CharField(source="incident_hse.code", read_only=True, default=None)
    actions_count = serializers.SerializerMethodField()
    actions_ouvertes = serializers.SerializerMethodField()

    class Meta:
        model = NonConformite
        fields = [
            "instrument",
            "id", "code", "controle", "controle_code", "source", "source_label",
            "gravite", "gravite_label", "description", "traitement", "traitement_label",
            "statut", "statut_label", "decided_by", "decided_by_name",
            "date_decision", "archive", "actions_count", "created_at", "updated_at",
            "type_ncr", "joint", "recontrole", "incident_hse", "incident_hse_code", "constat_audit_hse",
            "actions_ouvertes",
        ]
        read_only_fields = ["decided_by", "code", "actions_count", "statut", "recontrole", "actions_ouvertes"]

    def get_actions_count(self, obj):
        return obj.actions_correctives.count()

    def get_actions_ouvertes(self, obj):
        return sum(1 for a in obj.actions_correctives.all() if a.statut != ActionCorrective.Statut.CLOTUREE)

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


CAPA_DELAI_JOURS = 5  # défaut provisoire : la valeur en vigueur est le paramètre CAPA_DELAI_JOURS (écran Qualité)


class ActionCorrectiveSerializer(serializers.ModelSerializer):
    non_conformite_code = serializers.CharField(
        source="non_conformite.code", read_only=True
    )
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    responsable_name = serializers.CharField(
        source="responsable.get_full_name", read_only=True, default=None
    )

    en_retard = serializers.BooleanField(read_only=True)

    class Meta:
        model = ActionCorrective
        fields = [
            "id", "code", "non_conformite", "non_conformite_code", "type", "type_label",
            "description", "responsable", "responsable_name", "echeance", "en_retard", "statut",
            "statut_label", "efficace", "closed_at", "escaladee_le", "created_at", "updated_at",
        ]
        read_only_fields = ["code", "closed_at", "statut", "escaladee_le"]

    def validate_non_conformite(self, nc):
        if nc.statut == NonConformite.Statut.CLOTUREE:
            raise serializers.ValidationError("NC clôturée : ouvrir une nouvelle NC pour une nouvelle action.")
        return nc

    def validate_echeance(self, value):
        # CDC M6 §8.8 : clôture des CAPA sous 5 jours (délai paramétrable par ETSL).
        delai = int(get_param_qualite("CAPA_DELAI_JOURS"))
        limite = timezone.localdate() + timedelta(days=delai)
        if value and value > limite:
            raise serializers.ValidationError(
                f"Échéance au plus tard le {limite:%d/%m/%Y} : les CAPA se clôturent sous {delai} jours (CDC M6)."
            )
        return value

    def create(self, validated_data):
        validated_data.setdefault("echeance", None)
        if not validated_data["echeance"]:
            validated_data["echeance"] = timezone.localdate() + timedelta(days=int(get_param_qualite("CAPA_DELAI_JOURS")))
        return super().create(validated_data)


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
            "validated_by", "validated_by_name", "notes", "dossier_document", "created_at", "updated_at",
        ]
        read_only_fields = ["validated_by", "levee_reserve", "code", "statut", "dossier_document", "date_archivage"]


class PointInspectionSerializer(ModelCleanMixin, serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_point_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    leve_par_name = serializers.CharField(source="leve_par.get_full_name", read_only=True, default=None)

    class Meta:
        model = PointInspection
        fields = [
            "id", "controle", "ordre", "description", "type_point", "type_label",
            "responsable_levee", "date_prevue", "en_retard", "statut", "statut_label", "leve_par", "leve_par_name",
            "leve_le", "commentaire",
        ]
        read_only_fields = ["statut", "leve_par", "leve_le", "en_retard"]

    en_retard = serializers.BooleanField(read_only=True)

    def validate(self, attrs):
        controle = attrs.get("controle") or (self.instance.controle if self.instance else None)
        if controle and controle.type_controle != ControleQualite.TypeControle.ITP:
            raise serializers.ValidationError(
                {"controle": "Des points d'inspection se rattachent à un contrôle de type ITP."}
            )
        if controle and controle.approuve_le:
            raise serializers.ValidationError({"controle": "ITP approuvé : plan figé (aucun point ajouté ni modifié)."})
        if controle and controle.statut in (ControleQualite.Statut.VALIDE, ControleQualite.Statut.ANNULE):
            raise serializers.ValidationError({"controle": "ITP validé ou annulé : plan figé."})
        return attrs


class EtalonnageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Etalonnage
        fields = ["id", "date", "echeance", "conforme", "type_operation", "organisme", "certificat"]


class InstrumentMesureSerializer(ModelCleanMixin, serializers.ModelSerializer):
    utilisable = serializers.BooleanField(read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    type_label = serializers.CharField(source="get_type_equipement_display", read_only=True)
    operation_attendue = serializers.CharField(read_only=True)
    etalonnages = EtalonnageSerializer(many=True, read_only=True)

    class Meta:
        model = InstrumentMesure
        fields = [
            "id", "code", "designation", "type_equipement", "type_label", "periodicite_mois", "organisme", "localisation",
            "numero_serie", "date_etalonnage", "echeance_etalonnage", "operation_attendue",
            "statut", "statut_label", "utilisable", "etalonnages",
        ]
        read_only_fields = ["code", "statut"]


class JointSoudeSerializer(serializers.ModelSerializer):
    ordre_code = serializers.CharField(source="ordre.code", read_only=True, default=None)
    soudeur_nom = serializers.CharField(source="soudeur.display_name", read_only=True)
    wps_code = serializers.CharField(source="wps.code", read_only=True, default=None)

    class Meta:
        model = JointSoude
        fields = [
            "id", "code", "ordre", "ordre_code", "repere", "soudeur", "soudeur_nom", "wps", "wps_code",
            "numero_coulee", "consommable", "poste", "date_soudage", "created_at",
        ]
        read_only_fields = ["code"]

    def validate(self, attrs):
        # ITP approuvé avant soudage ; soudeur qualifié (CDC §8.11).
        if not ControleQualite.objects.filter(
            type_controle=ControleQualite.TypeControle.ITP, ordre=attrs["ordre"], approuve_le__isnull=False
        ).exists():
            raise serializers.ValidationError({"ordre": "Aucun ITP approuvé pour cet OF : soudage interdit."})
        if not any(q.est_valide for q in attrs["soudeur"].qualifications.all()):
            raise serializers.ValidationError({"soudeur": "Soudeur sans qualification valide (ISO 9606-1 / ASME IX)."})
        # Le joint se soude selon un WPS validé, diffusé sur l'OF, que la qualification du soudeur couvre.
        wps = attrs.get("wps")
        if wps is None:
            raise serializers.ValidationError({"wps": "WPS obligatoire : un joint se soude selon une procédure qualifiée."})
        if wps.statut != WpsWpqr.Statut.VALIDE or wps.type != WpsWpqr.Type.WPS:
            raise serializers.ValidationError({"wps": f"WPS {wps.code} non validé ou obsolète : soudage interdit."})
        if not DiffusionWps.objects.filter(wps=wps, ordre=attrs["ordre"]).exists():
            raise serializers.ValidationError({"wps": f"WPS {wps.code} non diffusé sur l'OF {attrs['ordre'].code}."})
        poste = attrs.get("poste")
        if poste and (poste.type_equipement != "poste_souder" or not poste.utilisable):
            raise serializers.ValidationError({"poste": f"Poste {poste.code} non vérifié, bloqué ou pas un poste à souder."})
        if qualification_couvrante(attrs["soudeur"], wps) is None:
            raise serializers.ValidationError({"soudeur": (
                f"Qualification du soudeur hors domaine du WPS {wps.code} "
                f"(procédé {wps.get_procede_display()}, position {wps.position or '—'})."
            )})
        return attrs


class ImageControleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImageControle
        fields = ["id", "controle", "fichier", "legende", "sha256", "created_at"]
        read_only_fields = ["sha256"]

    def validate_controle(self, controle):
        if controle.type_controle != ControleQualite.TypeControle.CND:
            raise serializers.ValidationError("Les images d'archive se rattachent à un contrôle CND.")
        return controle


class EpreuvePressionSerializer(serializers.ModelSerializer):
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    ordre_code = serializers.CharField(source="ordre.code", read_only=True, default=None)

    class Meta:
        model = EpreuvePression
        fields = [
            "id", "code", "ordre", "ordre_code", "joint", "instrument", "type_epreuve", "pression_essai",
            "duree_minutes", "chute_max", "releves", "statut", "statut_label", "resultat", "conclu_par",
            "conclu_le", "created_at",
        ]
        read_only_fields = ["code", "releves", "statut", "resultat", "conclu_par", "conclu_le"]

    def validate_instrument(self, instrument):
        if instrument and not instrument.utilisable:
            raise serializers.ValidationError("Instrument hors échéance d'étalonnage ou bloqué.")
        return instrument


class DiffusionWpsSerializer(serializers.ModelSerializer):
    wps_code = serializers.CharField(source="wps.code", read_only=True)
    ordre_code = serializers.CharField(source="ordre.code", read_only=True)

    class Meta:
        model = DiffusionWps
        fields = ["id", "wps", "wps_code", "ordre", "ordre_code", "diffuse_par", "diffuse_le"]
        read_only_fields = fields


class PunchItemSerializer(ModelCleanMixin, serializers.ModelSerializer):
    ordre_code = serializers.CharField(source="ordre.code", read_only=True)
    categorie_label = serializers.CharField(source="get_categorie_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    en_retard = serializers.BooleanField(read_only=True)

    class Meta:
        model = PunchItem
        fields = [
            "id", "code", "ordre", "ordre_code", "itp", "repere", "description", "categorie", "categorie_label",
            "responsable", "echeance", "en_retard", "statut", "statut_label", "leve_par", "leve_le", "commentaire",
            "created_at",
        ]
        read_only_fields = ["code", "statut", "leve_par", "leve_le", "commentaire", "en_retard"]

    def validate(self, attrs):
        itp = attrs.get("itp")
        if itp and itp.type_controle != ControleQualite.TypeControle.ITP:
            raise serializers.ValidationError({"itp": "Une réserve se rattache à un ITP."})
        if itp and itp.ordre_id and itp.ordre_id != attrs["ordre"].pk:
            raise serializers.ValidationError({"itp": "ITP d'un autre OF."})
        return super().validate(attrs)


class ParametreQualiteSerializer(serializers.ModelSerializer):
    est_provisoire = serializers.BooleanField(read_only=True)

    class Meta:
        model = ParametreQualite
        fields = ["id", "code", "label", "valeur", "unite", "statut_valeur", "est_provisoire", "confirme_par", "confirme_le"]
        read_only_fields = ["code", "label", "unite", "statut_valeur", "confirme_par", "confirme_le"]

    def validate_valeur(self, valeur):
        if valeur < 0:
            raise serializers.ValidationError("Valeur positive attendue.")
        return valeur


class CritereControleSerializer(ModelCleanMixin, serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_controle_display", read_only=True)
    est_provisoire = serializers.BooleanField(read_only=True)

    class Meta:
        model = CritereControle
        fields = [
            "id", "type_controle", "type_label", "code", "libelle", "unite", "mini", "maxi", "norme", "actif",
            "statut_valeur", "est_provisoire", "confirme_par", "confirme_le",
        ]
        read_only_fields = ["statut_valeur", "confirme_par", "confirme_le"]

    def validate_code(self, code):
        return code.strip().upper()


class MesureControleSerializer(serializers.ModelSerializer):
    critere_libelle = serializers.CharField(source="critere.libelle", read_only=True)
    unite = serializers.CharField(source="critere.unite", read_only=True)

    class Meta:
        model = MesureControle
        fields = ["id", "controle", "critere", "critere_libelle", "unite", "valeur", "mini", "maxi", "conforme", "repere", "saisi_le"]
        read_only_fields = ["mini", "maxi", "conforme"]


# ----------------------------------------------------------------------------------------------------------------
# Écarts M6-C : système de management de la qualité (CDC M6.2)
# ----------------------------------------------------------------------------------------------------------------


class ProcessusQualiteSerializer(ModelCleanMixin, serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_processus_display", read_only=True)
    pilote_nom = serializers.CharField(source="pilote.get_full_name", read_only=True, default=None)
    cible_atteinte = serializers.BooleanField(read_only=True, allow_null=True)

    class Meta:
        model = ProcessusQualite
        fields = [
            "id", "code", "libelle", "type_processus", "type_label", "pilote", "pilote_nom", "finalite", "indicateur",
            "unite", "cible", "sens", "valeur", "date_mesure", "cible_atteinte", "actif",
        ]
        read_only_fields = ["code", "valeur", "date_mesure"]


class ResponsabiliteQualiteSerializer(ModelCleanMixin, serializers.ModelSerializer):
    titulaire_nom = serializers.CharField(source="titulaire.get_full_name", read_only=True, default=None)
    suppleant_nom = serializers.CharField(source="suppleant.get_full_name", read_only=True, default=None)
    processus_code = serializers.CharField(source="processus.code", read_only=True, default=None)

    class Meta:
        model = ResponsabiliteQualite
        fields = [
            "id", "fonction", "titulaire", "titulaire_nom", "suppleant", "suppleant_nom", "rattachement", "missions",
            "autorites", "processus", "processus_code",
        ]


class DocumentQualiteSerializer(ModelCleanMixin, serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_doc_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    affaire_code = serializers.CharField(source="affaire.code", read_only=True, default=None)
    processus_code = serializers.CharField(source="processus.code", read_only=True, default=None)
    approuve_par_nom = serializers.CharField(source="approuve_par.get_full_name", read_only=True, default=None)
    revue_echue = serializers.SerializerMethodField()

    class Meta:
        model = DocumentQualite
        fields = [
            "id", "reference", "version", "type_doc", "type_label", "titre", "processus", "processus_code", "affaire",
            "affaire_code", "fichier", "motif_revision", "periodicite_revue_mois", "date_revue", "revue_echue", "statut",
            "statut_label", "redige_par", "approuve_par", "approuve_par_nom", "approuve_le", "document", "created_at",
        ]
        read_only_fields = ["reference", "version", "date_revue", "statut", "redige_par", "approuve_par", "approuve_le", "document"]

    def get_revue_echue(self, obj):
        return bool(obj.statut == DocumentQualite.Statut.APPROUVE and obj.date_revue and obj.date_revue < timezone.localdate())


class ConstatAuditQualiteSerializer(ModelCleanMixin, serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_constat_display", read_only=True)
    nc_code = serializers.CharField(source="nc.code", read_only=True, default=None)
    nc_statut = serializers.CharField(source="nc.statut", read_only=True, default=None)

    class Meta:
        model = ConstatAuditQualite
        fields = ["id", "audit", "type_constat", "type_label", "exigence", "description", "nc", "nc_code", "nc_statut", "created_at"]
        read_only_fields = ["nc"]

    def validate_audit(self, audit):
        if audit.statut == AuditQualite.Statut.CLOTURE:
            raise serializers.ValidationError("Audit clôturé : constats scellés.")
        return audit


class AuditQualiteSerializer(ModelCleanMixin, serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_audit_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    fournisseur_nom = serializers.CharField(source="fournisseur.name", read_only=True, default=None)
    agrement_jusqu = serializers.DateField(source="fournisseur.agree_qualite_jusqu", read_only=True, default=None)
    processus_code = serializers.CharField(source="processus.code", read_only=True, default=None)
    constats = ConstatAuditQualiteSerializer(many=True, read_only=True)
    nc_ouvertes = serializers.SerializerMethodField()

    class Meta:
        model = AuditQualite
        fields = [
            "id", "code", "type_audit", "type_label", "referentiel", "perimetre", "processus", "processus_code",
            "fournisseur", "fournisseur_nom", "agrement_jusqu", "organisme", "auditeur", "date_prevue", "date_realisation",
            "score", "conclusion", "agrement_accorde", "statut", "statut_label", "constats", "nc_ouvertes", "rapport",
            "created_at",
        ]
        read_only_fields = [
            "code", "date_realisation", "score", "agrement_accorde", "statut", "rapport",
        ]

    def get_nc_ouvertes(self, obj):
        return obj.nc_ouvertes.count()


class RevueDirectionQualiteSerializer(serializers.ModelSerializer):
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    validee_par_nom = serializers.CharField(source="validee_par.get_full_name", read_only=True, default=None)

    class Meta:
        model = RevueDirectionQualite
        fields = [
            "id", "code", "annee", "date_revue", "participants", "conclusions", "decisions", "bilan", "statut",
            "statut_label", "validee_par", "validee_par_nom", "validee_le", "document", "created_at",
        ]
        read_only_fields = ["code", "bilan", "statut", "validee_par", "validee_le", "document"]
