from rest_framework import serializers

from config.serializers import ModelCleanMixin

from .models import (
    AffectationEquipe,
    CapaciteAtelier,
    Equipe,
    PresenceChantier,
    DossierOperationnel,
    GammeOperatoire,
    GammeOperation,
    OrdreFabrication,
    PointageChantier,
    SituationTravaux,
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


class GammeOperatoireSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    operations_count = serializers.IntegerField(source="operations.count", read_only=True)
    total_planned_hours = serializers.DecimalField(
        max_digits=18, decimal_places=2, read_only=True
    )

    class Meta:
        model = GammeOperatoire
        fields = [
            "id",
            "code",
            "label",
            "status",
            "status_label",
            "is_global_rental",
            "operations_count",
            "total_planned_hours",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "code", "created_at", "updated_at"]


class GammeOperationSerializer(serializers.ModelSerializer):
    poste_label = serializers.CharField(source="get_poste_display", read_only=True)
    gamme_code = serializers.CharField(source="gamme.code", read_only=True, default=None)

    class Meta:
        model = GammeOperation
        fields = [
            "id",
            "gamme",
            "gamme_code",
            "sequence",
            "label",
            "poste",
            "poste_label",
            "planned_hours",
        ]
        read_only_fields = ["id"]


class OrdreFabricationSerializer(AmountMaskMixin, ModelCleanMixin, serializers.ModelSerializer):
    amount_fields = []
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    scope_label = serializers.CharField(source="get_scope_display", read_only=True)
    affaire_code = serializers.CharField(source="affaire.code", read_only=True, default=None)
    gamme_code = serializers.CharField(source="gamme.code", read_only=True, default=None)
    article_code = serializers.CharField(source="article.code", read_only=True, default=None)
    responsible_name = serializers.SerializerMethodField()
    pointage_hours = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    pointages_count = serializers.IntegerField(source="pointages.count", read_only=True)

    class Meta:
        model = OrdreFabrication
        fields = [
            "id",
            "code",
            "label",
            "affaire",
            "affaire_code",
            "gamme",
            "gamme_code",
            "scope",
            "scope_label",
            "article",
            "article_code",
            "quantity",
            "status",
            "status_label",
            "planned_start",
            "planned_end",
            "calculated_hours",
            "responsible",
            "responsible_name",
            "soudeurs",
            "created_by",
            "pointage_hours",
            "pointages_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "status",
            "id",
            "code",
            "created_by",
            "pointage_hours",
            "pointages_count",
            "created_at",
            "updated_at",
        ]

    def get_responsible_name(self, obj):
        if not obj.responsible:
            return None
        return (obj.responsible.first_name + " " + obj.responsible.last_name).strip() or obj.responsible.email


class PointageChantierSerializer(ModelCleanMixin, serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    hours_type_label = serializers.CharField(source="get_hours_type_display", read_only=True)
    ordre_code = serializers.CharField(source="ordre.code", read_only=True, default=None)
    worker_name_filled = serializers.SerializerMethodField()

    class Meta:
        model = PointageChantier
        fields = [
            "id",
            "code",
            "ordre",
            "ordre_code",
            "worker",
            "worker_name",
            "worker_name_filled",
            "date",
            "hours",
            "hours_type",
            "hours_type_label",
            "status",
            "status_label",
            "validated_by",
            "validated_at",
            "saisie_temps",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "code", "status", "validated_by", "validated_at", "saisie_temps", "created_by", "created_at", "updated_at"]

    def validate(self, attrs):
        # `clean()` du modèle n'est pas appelé par DRF : sans cela un pointage à 0 h ou sans opérateur passait.
        inst = self.instance
        hours = attrs.get("hours", getattr(inst, "hours", None))
        if hours is None or hours <= 0:
            raise serializers.ValidationError({"hours": "Le nombre d'heures doit être strictement positif."})
        if hours > 24:
            raise serializers.ValidationError({"hours": "Un pointage ne peut dépasser 24 h."})
        worker = attrs.get("worker", getattr(inst, "worker", None))
        name = attrs.get("worker_name", getattr(inst, "worker_name", ""))
        if not worker and not name:
            raise serializers.ValidationError(
                {"worker": "Le pointage doit être rattaché à un opérateur ou un nom libre."}
            )
        ordre = attrs.get("ordre", getattr(inst, "ordre", None))
        jour = attrs.get("date", getattr(inst, "date", None))
        if worker and ordre and ordre.scope == OrdreFabrication.Scope.CHANTIER:
            controler_habilitation_chantier(worker, jour, ordre)
        return attrs

    def get_worker_name_filled(self, obj):
        if obj.worker_name:
            return obj.worker_name
        if obj.worker:
            return (obj.worker.first_name + " " + obj.worker.last_name).strip() or obj.worker.email
        return None


class SituationTravauxSerializer(AmountMaskMixin, ModelCleanMixin, serializers.ModelSerializer):
    amount_fields = ["amount"]
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    affaire_code = serializers.CharField(source="affaire.code", read_only=True, default=None)
    created_by_name = serializers.SerializerMethodField()
    validated_by_name = serializers.SerializerMethodField()
    ordered_hours = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    ordres_count = serializers.IntegerField(source="ordres.count", read_only=True)

    class Meta:
        model = SituationTravaux
        fields = [
            "id",
            "code",
            "affaire",
            "affaire_code",
            "label",
            "period_start",
            "period_end",
            "amount",
            "progress",
            "facture_ref",
            "facture_le",
            "status",
            "status_label",
            "ordres",
            "ordres_count",
            "ordered_hours",
            "created_by",
            "created_by_name",
            "validated_by",
            "validated_by_name",
            "validated_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "code",
            "created_by",
            "created_by_name",
            "validated_by",
            "validated_by_name",
            "validated_at",
            "ordered_hours",
            "ordres_count",
            "created_at",
            "updated_at",
            "facture_ref",
            "facture_le",
            "status",  # évolue par les actions `validate` / `marquer-facturee`
        ]

    def get_created_by_name(self, obj):
        if not obj.created_by:
            return None
        return (obj.created_by.first_name + " " + obj.created_by.last_name).strip() or obj.created_by.email

    def get_validated_by_name(self, obj):
        if not obj.validated_by:
            return None
        return (obj.validated_by.first_name + " " + obj.validated_by.last_name).strip() or obj.validated_by.email


def controler_habilitation_chantier(worker, jour, ordre=None):
    """CDC M9 §10.8 / M7 §9.11 : aucun salarié non habilité affecté à un chantier (habilitation valide à la date)."""
    from django.db.models import Q

    from rh_paie.models import Employe, Qualification

    fiche = Employe.objects.filter(user=worker).first()
    nom = worker.get_full_name() or worker.email
    if fiche is None:
        raise serializers.ValidationError(
            {"worker": f"{nom} n'est rattaché à aucune fiche salarié : habilitation chantier invérifiable."}
        )
    habilite = Qualification.objects.filter(
        employe=fiche, type=Qualification.Type.HABILITATION,
    ).filter(Q(date_obtention__isnull=True) | Q(date_obtention__lte=jour)).filter(
        Q(date_validite__isnull=True) | Q(date_validite__gte=jour)
    ).exists()
    if not habilite:
        raise serializers.ValidationError(
            {"worker": f"{nom} n'a aucune habilitation valide au {jour:%d/%m/%Y} : affectation chantier interdite (CDC M9 §10.8)."}
        )
    from rh_paie.formation_m9c import habilitations_manquantes

    manquantes = habilitations_manquantes(fiche, ordre, jour)
    if manquantes:  # matrice habilitation ↔ poste (CDC M9.4)
        raise serializers.ValidationError(
            {"worker": f"{nom} n'a pas l'habilitation exigée par le poste ({', '.join(manquantes)}) : affectation chantier interdite."}
        )


class CapaciteAtelierSerializer(serializers.ModelSerializer):
    class Meta:
        model = CapaciteAtelier
        fields = ["id", "scope", "resource", "hours_per_week"]

    def validate_hours_per_week(self, value):
        if value <= 0:
            raise serializers.ValidationError("La capacité doit être strictement positive.")
        return value


class DossierOperationnelSerializer(serializers.ModelSerializer):
    ordre_code = serializers.CharField(source="ordre.code", read_only=True)

    class Meta:
        model = DossierOperationnel
        fields = ["id", "ordre", "ordre_code", "contenu", "sha256", "retention_years", "created_at"]
        read_only_fields = fields


class EquipeSerializer(serializers.ModelSerializer):
    metier_label = serializers.CharField(source="get_metier_display", read_only=True)
    effectif = serializers.IntegerField(source="membres.count", read_only=True)

    class Meta:
        model = Equipe
        fields = ["id", "code", "label", "metier", "metier_label", "chef", "membres", "effectif", "actif", "created_at"]
        read_only_fields = ["id", "code", "created_at"]


class AffectationEquipeSerializer(ModelCleanMixin, serializers.ModelSerializer):
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    equipe_label = serializers.CharField(source="equipe.label", read_only=True)
    metier = serializers.CharField(source="equipe.metier", read_only=True)
    ordre_code = serializers.CharField(source="ordre.code", read_only=True)

    class Meta:
        model = AffectationEquipe
        fields = [
            "id", "code", "equipe", "equipe_label", "metier", "ordre", "ordre_code", "date_debut", "date_fin",
            "effectif", "statut", "statut_label", "mobilise_par", "mobilise_le", "created_by", "created_at",
        ]
        read_only_fields = ["id", "code", "statut", "mobilise_par", "mobilise_le", "created_by", "created_at"]

    def validate(self, attrs):
        # `clean()` n'est pas appelé par DRF pour les règles transverses (piège backend n°1).
        debut = attrs.get("date_debut", getattr(self.instance, "date_debut", None))
        fin = attrs.get("date_fin", getattr(self.instance, "date_fin", None))
        if debut and fin and fin < debut:
            raise serializers.ValidationError({"date_fin": "La fin doit être postérieure au début."})
        equipe = attrs.get("equipe", getattr(self.instance, "equipe", None))
        if equipe is not None and not equipe.actif:
            raise serializers.ValidationError({"equipe": "Équipe inactive : affectation impossible."})
        return attrs


class PresenceChantierSerializer(ModelCleanMixin, serializers.ModelSerializer):
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    employe_nom = serializers.SerializerMethodField()
    ordre_code = serializers.CharField(source="ordre.code", read_only=True)

    class Meta:
        model = PresenceChantier
        fields = [
            "id", "ordre", "ordre_code", "employe", "employe_nom", "date", "statut", "statut_label", "motif",
            "releve_par", "created_at",
        ]
        read_only_fields = ["id", "releve_par", "created_at"]

    def get_employe_nom(self, obj):
        return f"{obj.employe.nom} {obj.employe.prenom}".strip()

    def validate(self, attrs):
        statut = attrs.get("statut", getattr(self.instance, "statut", PresenceChantier.Statut.PRESENT))
        motif = attrs.get("motif", getattr(self.instance, "motif", ""))
        if statut != PresenceChantier.Statut.PRESENT and not motif:
            raise serializers.ValidationError({"motif": "Un motif est obligatoire pour une absence ou un retard."})
        ordre = attrs.get("ordre", getattr(self.instance, "ordre", None))
        employe = attrs.get("employe", getattr(self.instance, "employe", None))
        jour = attrs.get("date", getattr(self.instance, "date", None))
        if ordre and employe and jour:
            doublon = PresenceChantier.objects.filter(ordre=ordre, employe=employe, date=jour)
            if self.instance:
                doublon = doublon.exclude(pk=self.instance.pk)
            if doublon.exists():
                raise serializers.ValidationError("Présence déjà relevée pour ce salarié, cet OF et ce jour.")
        return attrs
