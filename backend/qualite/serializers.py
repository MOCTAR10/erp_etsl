"""Sérialiseurs M6 — Qualité & Contrôle Qualité / Inspection."""

from django.core.exceptions import ValidationError as DjangoValidationError
from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from config.serializers import ModelCleanMixin

from .models import (
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
        read_only_fields = ["statut", "validated_by", "date_validation", "code"]


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
            "approuve_par", "approuve_le", "images_count",
        ]
        read_only_fields = [
            "code", "created_by", "points", "points_arret_restants", "approuve_par", "approuve_le", "images_count",
        ]

    instrument_code = serializers.CharField(source="instrument.code", read_only=True, default=None)
    images_count = serializers.SerializerMethodField()
    points = serializers.SerializerMethodField()
    points_arret_restants = serializers.SerializerMethodField()

    def get_points(self, obj):
        return PointInspectionSerializer(obj.points.all(), many=True, context=self.context).data

    def get_images_count(self, obj):
        return obj.images.count()

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
            "type_ncr", "joint", "recontrole",
        ]
        read_only_fields = ["decided_by", "code", "actions_count", "statut", "recontrole"]

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


CAPA_DELAI_JOURS = 5


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
            "statut_label", "efficace", "closed_at", "created_at", "updated_at",
        ]
        read_only_fields = ["code", "closed_at", "statut"]

    def validate_echeance(self, value):
        # CDC M6 §8.8 : clôture des CAPA sous 5 jours.
        limite = timezone.localdate() + timedelta(days=CAPA_DELAI_JOURS)
        if value and value > limite:
            raise serializers.ValidationError(
                f"Échéance au plus tard le {limite:%d/%m/%Y} : les CAPA se clôturent sous {CAPA_DELAI_JOURS} jours (CDC M6)."
            )
        return value

    def create(self, validated_data):
        validated_data.setdefault("echeance", None)
        if not validated_data["echeance"]:
            validated_data["echeance"] = timezone.localdate() + timedelta(days=CAPA_DELAI_JOURS)
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
            "validated_by", "validated_by_name", "notes", "created_at", "updated_at",
        ]
        read_only_fields = ["validated_by", "levee_reserve", "code", "statut"]


class PointInspectionSerializer(ModelCleanMixin, serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_point_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    leve_par_name = serializers.CharField(source="leve_par.get_full_name", read_only=True, default=None)

    class Meta:
        model = PointInspection
        fields = [
            "id", "controle", "ordre", "description", "type_point", "type_label",
            "responsable_levee", "statut", "statut_label", "leve_par", "leve_par_name",
            "leve_le", "commentaire",
        ]
        read_only_fields = ["statut", "leve_par", "leve_le"]

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
        fields = ["id", "date", "echeance", "conforme", "certificat"]


class InstrumentMesureSerializer(ModelCleanMixin, serializers.ModelSerializer):
    utilisable = serializers.BooleanField(read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    etalonnages = EtalonnageSerializer(many=True, read_only=True)

    class Meta:
        model = InstrumentMesure
        fields = [
            "id", "code", "designation", "numero_serie", "date_etalonnage", "echeance_etalonnage",
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
            "numero_coulee", "consommable", "date_soudage", "created_at",
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
