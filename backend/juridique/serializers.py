"""Sérialiseurs M12 — Juridique & GED (RF-ERP-B0...B4)."""

from rest_framework import serializers

from .models import (
    Assurance,
    Caution,
    Contentieux,
    Convention,
    Courrier,
    ActionContentieux,
    DossierGlobalRental,
    JalonContentieux,
    LienDocument,
    ParametreJuridique,
    PieceDossier,
    Reunion,
)
from .services import can_see_amount
from config.i18n import tr


class AmountMaskMixin:
    """Masque les montants hors rôles autorisés (pattern RF-59 / RF-ERP-B0)."""

    amount_fields = ()

    def get_has_amount_access(self, obj):
        request = self.context.get("request")
        return can_see_amount(getattr(request, "user", None))

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if not can_see_amount(getattr(request, "user", None)):
            for field in self.amount_fields:
                if field in data:
                    data[field] = None
            data["has_amount_access"] = False
        return data


class CourrierSerializer(serializers.ModelSerializer):
    sens_label = serializers.CharField(source="get_sens_display", read_only=True)
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    tiers_name = serializers.CharField(source="tiers.name", read_only=True, default=None)
    document_title = serializers.CharField(
        source="document.title", read_only=True, default=None
    )

    class Meta:
        model = Courrier
        fields = [
            "id",
            "code",
            "sens",
            "sens_label",
            "type",
            "type_label",
            "objet",
            "reference",
            "tiers",
            "tiers_name",
            "expediteur",
            "destinataire",
            "date_courrier",
            "date_reception",
            "statut",
            "statut_label",
            "document",
            "document_title",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["code", "statut"]


class ConventionSerializer(AmountMaskMixin, serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    partenaire_name = serializers.CharField(source="partenaire.name", read_only=True, default=None)
    affaire_code = serializers.CharField(source="affaire.code", read_only=True, default=None)
    document_title = serializers.CharField(
        source="document.title", read_only=True, default=None
    )
    days_left = serializers.IntegerField(read_only=True)
    expiry_status = serializers.CharField(read_only=True)
    a_renouveler = serializers.BooleanField(read_only=True)
    has_amount_access = serializers.SerializerMethodField()
    completude = serializers.SerializerMethodField()
    amount_fields = ("montant",)

    def get_completude(self, obj):
        from .ecarts import completude

        return completude("convention", obj)

    class Meta:
        model = Convention
        fields = [
            "id",
            "code",
            "type",
            "type_label",
            "titre",
            "partenaire",
            "partenaire_name",
            "montant",
            "date_debut",
            "date_fin",
            "renouvelable",
            "affaire",
            "affaire_code",
            "statut",
            "statut_label",
            "document",
            "document_title",
            "days_left",
            "expiry_status",
            "a_renouveler",
            "has_amount_access",
            "completude",
            "commentaire",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "code",
            "statut",
            "days_left",
            "expiry_status",
            "a_renouveler",
        ]


class ContentieuxSerializer(AmountMaskMixin, serializers.ModelSerializer):
    nature_label = serializers.CharField(source="get_nature_display", read_only=True)
    phase_label = serializers.CharField(source="get_phase_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    document_title = serializers.CharField(
        source="document.title", read_only=True, default=None
    )
    has_amount_access = serializers.SerializerMethodField()
    completude = serializers.SerializerMethodField()
    probabilite_label = serializers.CharField(source="get_probabilite_display", read_only=True)
    amount_fields = ("montant_en_jeu",)

    def get_completude(self, obj):
        from .ecarts import completude

        return completude("contentieux", obj)

    def validate_juridiction(self, value):
        from .ecarts import parametre

        if value and value not in (parametre("juridictions") or []):
            raise serializers.ValidationError("Juridiction hors de la liste paramétrée (paramètres M12).")
        return value

    class Meta:
        model = Contentieux
        fields = [
            "id",
            "code",
            "nature",
            "nature_label",
            "objet",
            "partie_adverse",
            "conseil_ext",
            "montant_en_jeu",
            "reference",
            "date_ouverture",
            "phase",
            "phase_label",
            "statut",
            "statut_label",
            "decision",
            "juridiction",
            "probabilite",
            "probabilite_label",
            "completude",
            "document",
            "document_title",
            "has_amount_access",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["code", "statut", "phase"]


class CautionSerializer(AmountMaskMixin, serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    emetteur_name = serializers.CharField(source="emetteur.name", read_only=True, default=None)
    convention_code = serializers.CharField(
        source="convention.code", read_only=True, default=None
    )
    document_title = serializers.CharField(
        source="document.title", read_only=True, default=None
    )
    days_left = serializers.IntegerField(read_only=True)
    expiry_status = serializers.CharField(read_only=True)
    has_amount_access = serializers.SerializerMethodField()
    en_attente_dg = serializers.SerializerMethodField()
    amount_fields = ("montant",)

    def get_en_attente_dg(self, obj):
        return obj.valide_dg_le is None

    class Meta:
        model = Caution
        fields = [
            "id",
            "code",
            "type",
            "type_label",
            "emetteur",
            "emetteur_name",
            "beneficiaire",
            "objet",
            "montant",
            "numero_instrument",
            "date_emission",
            "date_echeance",
            "statut",
            "statut_label",
            "convention",
            "convention_code",
            "document",
            "document_title",
            "days_left",
            "expiry_status",
            "has_amount_access",
            "valide_dg_par",
            "valide_dg_le",
            "en_attente_dg",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["valide_dg_par", "valide_dg_le", "code", "statut", "days_left", "expiry_status"]


class AssuranceSerializer(AmountMaskMixin, serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    assureur_name = serializers.CharField(source="assureur.name", read_only=True, default=None)
    document_title = serializers.CharField(
        source="document.title", read_only=True, default=None
    )
    days_left = serializers.IntegerField(read_only=True)
    expiry_status = serializers.CharField(read_only=True)
    has_amount_access = serializers.SerializerMethodField()
    en_attente_dg = serializers.SerializerMethodField()
    amount_fields = ("prime_annuelle",)

    def get_en_attente_dg(self, obj):
        return obj.valide_dg_le is None

    class Meta:
        model = Assurance
        fields = [
            "id",
            "code",
            "type",
            "type_label",
            "assureur",
            "assureur_name",
            "numero_police",
            "prime_annuelle",
            "date_debut",
            "date_echeance",
            "objets_couverts",
            "statut",
            "statut_label",
            "nb_sinistres",
            "sinistres",
            "document",
            "document_title",
            "days_left",
            "expiry_status",
            "has_amount_access",
            "valide_dg_par",
            "valide_dg_le",
            "en_attente_dg",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["valide_dg_par", "valide_dg_le", "code", "statut", "days_left", "expiry_status", "sinistres"]


class ReunionSerializer(serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    animateur_name = serializers.CharField(
        source="animateur.get_full_name", read_only=True, default=None
    )
    compte_rendu_title = serializers.CharField(
        source="compte_rendu.title", read_only=True, default=None
    )
    participants = serializers.PrimaryKeyRelatedField(
        many=True, read_only=True
    )
    participants_names = serializers.SerializerMethodField()
    nb_decisions = serializers.IntegerField(read_only=True)
    nb_decisions_ouvertes = serializers.IntegerField(read_only=True)

    class Meta:
        model = Reunion
        fields = [
            "id",
            "code",
            "type",
            "type_label",
            "objet",
            "date_reunion",
            "lieu",
            "animateur",
            "animateur_name",
            "participants",
            "participants_names",
            "compte_rendu",
            "compte_rendu_title",
            "affaire",
            "statut",
            "statut_label",
            "decisions",
            "nb_decisions",
            "nb_decisions_ouvertes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["code", "statut"]

    def get_participants_names(self, obj):
        return [p.get_full_name() for p in obj.participants.all()]


class DossierGlobalRentalSerializer(AmountMaskMixin, serializers.ModelSerializer):
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    partenaire_gr_name = serializers.CharField(
        source="partenaire_gr.name", read_only=True
    )
    affaire_code = serializers.CharField(source="affaire.code", read_only=True, default=None)
    has_amount_access = serializers.SerializerMethodField()
    controle = serializers.SerializerMethodField()
    amount_fields = ("montant_estime",)

    def get_controle(self, obj):
        from .ecarts import controle_gr

        return controle_gr(obj)

    class Meta:
        model = DossierGlobalRental
        fields = [
            "id",
            "code",
            "partenaire_gr",
            "partenaire_gr_name",
            "affaire",
            "affaire_code",
            "reference_contrat",
            "objet",
            "montant_estime",
            "signe_618",
            "date_debut",
            "date_fin",
            "statut",
            "statut_label",
            "references_documents",
            "commentaire",
            "has_amount_access",
            "mandat_reference",
            "mandat_date_fin",
            "date_revue",
            "revu_par",
            "controle",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["code", "statut", "date_revue", "revu_par"]

    def validate(self, attrs):
        partenaire = attrs.get("partenaire_gr")
        if partenaire is not None and not partenaire.is_global_rental:
            raise serializers.ValidationError(
                {"partenaire_gr": "Le partenaire doit être flaggé GLOBAL RENTAL (RF-ERP-B4)."}
            )
        return attrs

class LienDocumentSerializer(serializers.ModelSerializer):
    document_title = serializers.CharField(source="document.title", read_only=True)

    class Meta:
        model = LienDocument
        fields = [
            "id", "document", "document_title", "objet_type", "objet_id", "objet_label", "module", "note",
            "created_by", "created_at",
        ]
        read_only_fields = ["objet_label", "module", "created_by", "created_at"]

    def validate(self, attrs):
        from documents.services import visible_documents

        from .services import resoudre_objet

        request = self.context["request"]
        if not visible_documents(request.user).filter(pk=attrs["document"].pk).exists():
            raise serializers.ValidationError({"document": "Document inaccessible."})
        try:
            attrs["objet_label"], attrs["module"] = resoudre_objet(attrs["objet_type"], attrs["objet_id"])
        except ValueError as exc:
            raise serializers.ValidationError({"objet_id": str(exc)})
        if LienDocument.objects.filter(
            document=attrs["document"], objet_type=attrs["objet_type"], objet_id=attrs["objet_id"]
        ).exists():
            raise serializers.ValidationError({"detail": "Ce document est déjà lié à cet objet."})
        return attrs



# --------------------------------------------------------------------------------------------------
# Écarts M12
# --------------------------------------------------------------------------------------------------
class ParametreJuridiqueSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParametreJuridique
        fields = ["id", "cle", "libelle", "valeur", "provisoire", "modifie_par", "modifie_le", "confirme_par", "confirme_le"]
        read_only_fields = fields


class JalonContentieuxSerializer(serializers.ModelSerializer):
    contentieux_code = serializers.CharField(source="contentieux.code", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    days_left = serializers.IntegerField(read_only=True)

    class Meta:
        model = JalonContentieux
        fields = [
            "id", "contentieux", "contentieux_code", "libelle", "date_prevue", "date_realisee", "statut",
            "statut_label", "days_left", "cree_par", "created_at",
        ]
        read_only_fields = ["date_realisee", "statut", "cree_par", "created_at"]


class ActionContentieuxSerializer(serializers.ModelSerializer):
    contentieux_code = serializers.CharField(source="contentieux.code", read_only=True)
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    auteur_name = serializers.CharField(source="auteur.get_full_name", read_only=True, default=None)

    class Meta:
        model = ActionContentieux
        fields = [
            "id", "contentieux", "contentieux_code", "date_action", "type", "type_label", "description", "auteur",
            "auteur_name", "created_at",
        ]
        read_only_fields = ["auteur", "created_at"]


class PieceDossierSerializer(serializers.ModelSerializer):
    document_title = serializers.CharField(source="document.title", read_only=True)

    class Meta:
        model = PieceDossier
        fields = ["id", "dossier_type", "dossier_id", "piece", "document", "document_title", "ajoute_par", "created_at"]
        read_only_fields = ["ajoute_par", "created_at"]
        validators = []  # doublon normalisé dans validate()

    def validate(self, attrs):
        from documents.services import visible_documents

        from .ecarts import pieces_requises, resoudre_dossier

        request = self.context["request"]
        try:
            dossier = resoudre_dossier(attrs["dossier_type"], attrs["dossier_id"])
        except ValueError as exc:
            raise serializers.ValidationError({"dossier_id": str(exc)})
        attrs["dossier_id"] = str(dossier.pk)
        requises = pieces_requises(attrs["dossier_type"], dossier)
        if attrs["piece"] not in requises:
            raise serializers.ValidationError(
                {"piece": tr("Pièce non prévue pour ce dossier (attendues : %(liste)s).") % {"liste": ", ".join(requises)}}
            )
        if not visible_documents(request.user).filter(pk=attrs["document"].pk).exists():
            raise serializers.ValidationError({"document": "Document inaccessible."})
        if PieceDossier.objects.filter(
            dossier_type=attrs["dossier_type"], dossier_id=attrs["dossier_id"], piece=attrs["piece"]
        ).exists():
            raise serializers.ValidationError({"piece": "Cette pièce est déjà versée au dossier."})
        return attrs
