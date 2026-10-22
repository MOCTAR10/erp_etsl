from decimal import Decimal

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
            "machine_hours",
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
            "replanifie_le",
            "motif_replanification",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "status",
            "id",
            "code",
            "created_by",
            "replanifie_le",
            "motif_replanification",
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
    nature_mo_label = serializers.CharField(source="get_nature_mo_display", read_only=True)
    employe_nom = serializers.SerializerMethodField()

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
            "employe",
            "employe_nom",
            "nature_mo",
            "nature_mo_label",
            "date",
            "hours",
            "hours_type",
            "hours_type_label",
            "status",
            "status_label",
            "validated_by",
            "validated_at",
            "saisi_le",
            "saisie_temps",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "code", "status", "validated_by", "validated_at", "saisie_temps", "created_by", "created_at", "updated_at"]

    def validate_saisi_le(self, value):
        from .terrain_a3 import verifier_saisi_le

        return verifier_saisi_le(value)

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
        employe = attrs.get("employe", getattr(inst, "employe", None))
        if not worker and not name and not employe:
            raise serializers.ValidationError(
                {"worker": "Le pointage doit être rattaché à un opérateur ou un nom libre."}
            )
        if worker and employe and employe.user_id and employe.user_id != worker.pk:
            raise serializers.ValidationError({"employe": "La fiche salarié ne correspond pas à l'opérateur."})
        ordre = attrs.get("ordre", getattr(inst, "ordre", None))
        jour = attrs.get("date", getattr(inst, "date", None))
        if worker and ordre and ordre.scope == OrdreFabrication.Scope.CHANTIER:
            controler_habilitation_chantier(worker, jour, ordre)
        elif employe and ordre and ordre.scope == OrdreFabrication.Scope.CHANTIER:
            _controler_fiche(employe, f"{employe.nom} {employe.prenom}".strip(), jour, ordre)
        from rh_paie.models import Employe

        fiche = employe or (Employe.objects.filter(user=worker).first() if worker else None)
        if fiche is not None and jour:
            from django.core.exceptions import ValidationError as DjangoValidationError

            from .ecarts import controler_pointage_croise

            try:  # croisement avec le planning / les absences M9 et plafond journalier (paramètre provisoire)
                controler_pointage_croise(fiche, jour, hours, exclure=inst.pk if inst else None)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"date": exc.messages})
        return attrs

    def get_worker_name_filled(self, obj):
        if obj.worker_name:
            return obj.worker_name
        if obj.worker:
            return (obj.worker.first_name + " " + obj.worker.last_name).strip() or obj.worker.email
        if obj.employe_id:
            return f"{obj.employe.nom} {obj.employe.prenom}".strip()
        return None

    def get_employe_nom(self, obj):
        return f"{obj.employe.nom} {obj.employe.prenom}".strip() if obj.employe_id else None


class SituationTravauxSerializer(AmountMaskMixin, ModelCleanMixin, serializers.ModelSerializer):
    amount_fields = ["amount"]
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    affaire_code = serializers.CharField(source="affaire.code", read_only=True, default=None)
    created_by_name = serializers.SerializerMethodField()
    validated_by_name = serializers.SerializerMethodField()
    ordered_hours = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    ordres_count = serializers.IntegerField(source="ordres.count", read_only=True)
    montant_attachements = serializers.SerializerMethodField()

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
            "recue_le",
            "recue_signataire",
            "montant_attachements",
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
            "recue_le",
            "recue_signataire",
            "status",  # évolue par les actions `validate` / `marquer-facturee`
        ]

    def get_created_by_name(self, obj):
        if not obj.created_by:
            return None
        return (obj.created_by.first_name + " " + obj.created_by.last_name).strip() or obj.created_by.email

    def get_montant_attachements(self, obj):
        if not self.context.get("can_view_amount", True):
            return None
        return str(sum((a.montant for a in obj.attachements.filter(statut="signe")), Decimal("0")))

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
    _controler_fiche(fiche, nom, jour, ordre)


def _controler_fiche(fiche, nom, jour, ordre=None):
    from django.db.models import Q

    from rh_paie.models import Qualification

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
    absents = serializers.SerializerMethodField()

    class Meta:
        model = AffectationEquipe
        fields = [
            "id", "code", "equipe", "equipe_label", "metier", "ordre", "ordre_code", "date_debut", "date_fin",
            "effectif", "statut", "statut_label", "mobilise_par", "mobilise_le", "created_by", "created_at", "absents",
        ]
        read_only_fields = ["id", "code", "statut", "mobilise_par", "mobilise_le", "created_by", "created_at"]

    def get_absents(self, obj):
        from .ecarts import absents_affectation

        return absents_affectation(obj) if obj.statut != AffectationEquipe.Statut.TERMINEE else []

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
        if employe and jour and statut == PresenceChantier.Statut.PRESENT:
            from .ecarts import indisponibilite

            motif_m9 = indisponibilite(employe, jour)
            if motif_m9:  # croisement avec les absences / congés validés en M9
                raise serializers.ValidationError({"statut": f"Salarié indisponible en M9 ({motif_m9}) : présence incohérente."})
        return attrs


# ----------------------------------------------------------------------------------------------------------------
# Écarts M3 (lot 2)
# ----------------------------------------------------------------------------------------------------------------
from .models import (  # noqa: E402
    Attachement,
    BesoinMatiere,
    BonTransfert,
    EscaladeSurcharge,
    FicheControleChantier,
    FichePreparation,
    ParametreOperations,
    RapportExecution,
    RepartitionAffaireOF,
)


def _nom(user):
    if not user:
        return None
    return (user.first_name + " " + user.last_name).strip() or user.email


class ParametreOperationsSerializer(serializers.ModelSerializer):
    est_provisoire = serializers.BooleanField(read_only=True)
    confirme_par_nom = serializers.SerializerMethodField()

    class Meta:
        model = ParametreOperations
        fields = ["id", "code", "label", "valeur", "unite", "statut_valeur", "est_provisoire", "confirme_par",
                  "confirme_par_nom", "confirme_le"]
        read_only_fields = ["code", "label", "unite", "statut_valeur", "confirme_par", "confirme_le"]

    def get_confirme_par_nom(self, obj):
        return _nom(obj.confirme_par)


def valider_parametre(code, valeur):
    from .ecarts import PARAMETRES_BOOLEENS

    if valeur < 0:
        raise serializers.ValidationError({"valeur": "La valeur doit être positive ou nulle."})
    if code in PARAMETRES_BOOLEENS and valeur not in (0, 1):
        raise serializers.ValidationError({"valeur": "Valeur attendue : 0 ou 1."})
    if code == "METHODE_AVANCEMENT" and valeur not in (1, 2, 3):
        raise serializers.ValidationError({"valeur": "Méthode attendue : 1, 2 ou 3."})
    if code == "JOURS_OUVRES_SEMAINE" and not 1 <= valeur <= 7:
        raise serializers.ValidationError({"valeur": "Entre 1 et 7 jours."})


class FichePreparationSerializer(serializers.ModelSerializer):
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    ordre_code = serializers.CharField(source="ordre.code", read_only=True)
    valide_par_nom = serializers.SerializerMethodField()

    class Meta:
        model = FichePreparation
        fields = ["id", "code", "ordre", "ordre_code", "outillage", "consignes", "statut", "statut_label", "valide_par",
                  "valide_par_nom", "valide_le", "created_by", "created_at"]
        read_only_fields = ["id", "code", "statut", "valide_par", "valide_le", "created_by", "created_at"]

    def get_valide_par_nom(self, obj):
        return _nom(obj.valide_par)

    def validate_ordre(self, ordre):
        if ordre.status in (OrdreFabrication.Status.CLOTURE, OrdreFabrication.Status.ANNULE):
            raise serializers.ValidationError("OF clos ou annulé : préparation impossible.")
        doublon = FichePreparation.objects.filter(ordre=ordre)
        if self.instance:
            doublon = doublon.exclude(pk=self.instance.pk)
        if doublon.exists():
            raise serializers.ValidationError("Une fiche de préparation existe déjà pour cet OF.")
        return ordre


class BesoinMatiereSerializer(serializers.ModelSerializer):
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    ordre_code = serializers.CharField(source="ordre.code", read_only=True)
    article_code = serializers.CharField(source="article.code", read_only=True)
    article_label = serializers.CharField(source="article.label", read_only=True)
    demande_achat_code = serializers.CharField(source="demande_achat.code", read_only=True, default=None)

    class Meta:
        model = BesoinMatiere
        fields = ["id", "ordre", "ordre_code", "article", "article_code", "article_label", "quantite", "statut",
                  "statut_label", "disponible", "verifie_le", "demande_achat", "demande_achat_code", "created_at"]
        read_only_fields = ["id", "statut", "disponible", "verifie_le", "demande_achat", "created_at"]

    def validate_quantite(self, value):
        if value <= 0:
            raise serializers.ValidationError("La quantité doit être strictement positive.")
        return value

    def validate_ordre(self, ordre):
        if ordre.status in (OrdreFabrication.Status.TERMINE, OrdreFabrication.Status.CLOTURE, OrdreFabrication.Status.ANNULE):
            raise serializers.ValidationError("OF terminé, clos ou annulé : besoin matière non modifiable.")
        return ordre


class RapportExecutionSerializer(ModelCleanMixin, serializers.ModelSerializer):
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    ordre_code = serializers.CharField(source="ordre.code", read_only=True)
    valide_par_nom = serializers.SerializerMethodField()

    class Meta:
        model = RapportExecution
        fields = ["id", "code", "ordre", "ordre_code", "type", "type_label", "date", "quantite_realisee", "quantite_rebut",
                  "avancement", "observations", "statut", "statut_label", "valide_par", "valide_par_nom", "valide_le",
                  "created_by", "created_at"]
        read_only_fields = ["id", "code", "statut", "valide_par", "valide_le", "created_by", "created_at"]

    def get_valide_par_nom(self, obj):
        return _nom(obj.valide_par)

    def validate(self, attrs):
        for champ in ("quantite_realisee", "quantite_rebut"):
            if attrs.get(champ) is not None and attrs[champ] < 0:
                raise serializers.ValidationError({champ: "Valeur positive attendue."})
        avancement = attrs.get("avancement")
        if avancement is not None and avancement > 100:
            raise serializers.ValidationError({"avancement": "L'avancement ne peut dépasser 100 %."})
        ordre = attrs.get("ordre", getattr(self.instance, "ordre", None))
        if ordre and ordre.status in (OrdreFabrication.Status.PREVU, OrdreFabrication.Status.ANNULE, OrdreFabrication.Status.CLOTURE):
            raise serializers.ValidationError({"ordre": "Rapport possible seulement sur un OF lancé, en cours ou terminé."})
        return attrs


class FicheControleChantierSerializer(serializers.ModelSerializer):
    ordre_code = serializers.CharField(source="ordre.code", read_only=True)
    controle_par_nom = serializers.SerializerMethodField()

    class Meta:
        model = FicheControleChantier
        fields = ["id", "code", "ordre", "ordre_code", "date", "objet", "points", "conforme", "controle_par",
                  "controle_par_nom", "created_at"]
        read_only_fields = ["id", "code", "conforme", "controle_par", "created_at"]

    def get_controle_par_nom(self, obj):
        return _nom(obj.controle_par)

    def validate_points(self, points):
        if not isinstance(points, list) or not points:
            raise serializers.ValidationError("Au moins un point de contrôle est requis.")
        propres = []
        for p in points:
            if not isinstance(p, dict) or not str(p.get("libelle", "")).strip():
                raise serializers.ValidationError("Chaque point doit avoir un libellé.")
            propres.append({"libelle": str(p["libelle"]).strip()[:200], "conforme": bool(p.get("conforme"))})
        return propres


class BonTransfertSerializer(serializers.ModelSerializer):
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    ordre_code = serializers.CharField(source="ordre.code", read_only=True)

    class Meta:
        model = BonTransfert
        fields = ["id", "code", "type", "type_label", "ordre", "ordre_code", "origine", "destination", "transporteur",
                  "lignes", "statut", "statut_label", "expedie_par", "expedie_le", "receptionne_par", "receptionne_le",
                  "reserves", "created_by", "created_at"]
        read_only_fields = ["id", "code", "statut", "expedie_par", "expedie_le", "receptionne_par", "receptionne_le",
                            "reserves", "created_by", "created_at"]

    def validate_lignes(self, lignes):
        from decimal import Decimal, InvalidOperation

        if not isinstance(lignes, list) or not lignes:
            raise serializers.ValidationError("Au moins une ligne (désignation, quantité) est requise.")
        propres = []
        for l in lignes:
            if not isinstance(l, dict) or not str(l.get("designation", "")).strip():
                raise serializers.ValidationError("Chaque ligne doit avoir une désignation.")
            try:
                qte = Decimal(str(l.get("quantite", "1")).replace(",", "."))
            except InvalidOperation:
                raise serializers.ValidationError("Quantité invalide.")
            if not qte.is_finite() or qte <= 0:
                raise serializers.ValidationError("Quantité strictement positive attendue.")
            propres.append({"designation": str(l["designation"]).strip()[:200], "quantite": str(qte)})
        return propres

    def validate_ordre(self, ordre):
        if ordre.status in (OrdreFabrication.Status.PREVU, OrdreFabrication.Status.ANNULE):
            raise serializers.ValidationError("OF prévu ou annulé : aucun transfert vers le chantier.")
        return ordre


class AttachementSerializer(AmountMaskMixin, serializers.ModelSerializer):
    amount_fields = ["prix_unitaire", "montant"]
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    ordre_code = serializers.CharField(source="ordre.code", read_only=True)
    situation_code = serializers.CharField(source="situation.code", read_only=True, default=None)
    montant = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)

    class Meta:
        model = Attachement
        fields = ["id", "code", "ordre", "ordre_code", "situation", "situation_code", "date", "designation", "unite",
                  "quantite", "prix_unitaire", "montant", "statut", "statut_label", "signataire_client", "signe_le",
                  "created_by", "created_at"]
        read_only_fields = ["id", "code", "statut", "signataire_client", "signe_le", "created_by", "created_at"]

    def validate(self, attrs):
        if attrs.get("quantite") is not None and attrs["quantite"] <= 0:
            raise serializers.ValidationError({"quantite": "La quantité métrée doit être strictement positive."})
        if attrs.get("prix_unitaire") is not None and attrs["prix_unitaire"] < 0:
            raise serializers.ValidationError({"prix_unitaire": "Prix positif attendu."})
        situation = attrs.get("situation", getattr(self.instance, "situation", None))
        if situation is not None and situation.status in (SituationTravaux.Status.VALIDEE, SituationTravaux.Status.FACTUREE):
            raise serializers.ValidationError({"situation": "Situation validée ou facturée : rattachement impossible."})
        return attrs


class RepartitionAffaireOFSerializer(serializers.ModelSerializer):
    ordre_code = serializers.CharField(source="ordre.code", read_only=True)
    affaire_code = serializers.CharField(source="affaire.code", read_only=True)

    class Meta:
        model = RepartitionAffaireOF
        fields = ["id", "ordre", "ordre_code", "affaire", "affaire_code", "part_pct"]
        read_only_fields = ["id"]

    def validate(self, attrs):
        from decimal import Decimal

        from .ecarts import param

        if not param("MULTI_AFFAIRES_ACTIF"):
            raise serializers.ValidationError("Multi-affaires désactivé (paramètre MULTI_AFFAIRES_ACTIF = 0).")
        part = attrs.get("part_pct", getattr(self.instance, "part_pct", None))
        if part is None or part <= 0 or part > 100:
            raise serializers.ValidationError({"part_pct": "Part entre 0 et 100 %."})
        ordre = attrs.get("ordre", getattr(self.instance, "ordre", None))
        affaire = attrs.get("affaire", getattr(self.instance, "affaire", None))
        autres = RepartitionAffaireOF.objects.filter(ordre=ordre)
        if self.instance:
            autres = autres.exclude(pk=self.instance.pk)
        if affaire is not None and autres.filter(affaire=affaire).exists():
            raise serializers.ValidationError({"affaire": "Affaire déjà répartie sur cet OF."})
        total = sum((r.part_pct for r in autres), Decimal("0")) + part
        if total > 100:
            raise serializers.ValidationError({"part_pct": f"Total des parts {total} % > 100 %."})
        return attrs


class EscaladeSurchargeSerializer(serializers.ModelSerializer):
    escalade_par_nom = serializers.SerializerMethodField()

    class Meta:
        model = EscaladeSurcharge
        fields = ["id", "scope", "resource", "semaine", "surcharge_pct", "escalade_par", "escalade_par_nom", "created_at"]
        read_only_fields = fields

    def get_escalade_par_nom(self, obj):
        return _nom(obj.escalade_par)
