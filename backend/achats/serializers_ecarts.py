"""Sérialiseurs des écarts M2 : paramètres provisoires, agréments, règles d'inspection, avoirs fournisseurs."""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from config.serializers import ModelCleanMixin

from .ecarts import valider_valeur_parametre
from .models import (
    AgrementFournisseur,
    AvoirFournisseur,
    ParametreAchats,
    PurchaseInvoice,
    RegleInspectionReception,
)
from .serializers import AmountMaskMixin
from config.i18n import tr


class ParametreAchatsSerializer(serializers.ModelSerializer):
    est_provisoire = serializers.BooleanField(read_only=True)

    class Meta:
        model = ParametreAchats
        fields = ["id", "code", "label", "valeur", "unite", "statut_valeur", "est_provisoire", "confirme_par", "confirme_le"]
        read_only_fields = ["code", "label", "unite", "statut_valeur", "confirme_par", "confirme_le"]

    def validate_valeur(self, value):
        try:
            valider_valeur_parametre(self.instance.code if self.instance else "", value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages)
        return value

    def update(self, instance, validated_data):
        # Une valeur modifiée redevient provisoire jusqu'à nouvelle confirmation.
        if "valeur" in validated_data and validated_data["valeur"] != instance.valeur:
            instance.statut_valeur = ParametreAchats.StatutValeur.PROVISOIRE
            instance.confirme_par = None
            instance.confirme_le = None
        return super().update(instance, validated_data)


class AgrementFournisseurSerializer(ModelCleanMixin, serializers.ModelSerializer):
    fournisseur_nom = serializers.CharField(source="fournisseur.name", read_only=True)
    domaine_label = serializers.CharField(source="get_domaine_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)

    class Meta:
        model = AgrementFournisseur
        fields = [
            "id", "code", "fournisseur", "fournisseur_nom", "domaine", "domaine_label", "reference", "date_evaluation",
            "date_fin", "note_evaluation", "observations", "statut", "statut_label", "motif_refus", "valide_par",
            "valide_le", "created_by", "created_at",
        ]
        read_only_fields = ["id", "code", "statut", "motif_refus", "valide_par", "valide_le", "created_by", "created_at"]

    def validate(self, attrs):
        if self.instance and self.instance.statut != AgrementFournisseur.Statut.DEMANDE:
            raise serializers.ValidationError({"detail": "Agrément décidé : pièce scellée (nouvelle demande pour renouveler)."})
        return super().validate(attrs)


class RegleInspectionReceptionSerializer(ModelCleanMixin, serializers.ModelSerializer):
    est_provisoire = serializers.BooleanField(read_only=True)
    article_code = serializers.CharField(source="article.code", read_only=True, default=None)
    article_type_label = serializers.CharField(source="get_article_type_display", read_only=True)

    class Meta:
        model = RegleInspectionReception
        fields = [
            "id", "article_type", "article_type_label", "article", "article_code", "exige_itp", "exige_cnd", "methode_cnd",
            "is_active", "statut_valeur", "est_provisoire", "confirme_par", "confirme_le",
        ]
        read_only_fields = ["id", "statut_valeur", "confirme_par", "confirme_le"]

    def update(self, instance, validated_data):
        instance.statut_valeur = RegleInspectionReception.StatutValeur.PROVISOIRE
        instance.confirme_par = None
        instance.confirme_le = None
        return super().update(instance, validated_data)


class AvoirFournisseurSerializer(AmountMaskMixin, serializers.ModelSerializer):
    amount_fields = ["montant_ht"]

    facture_code = serializers.CharField(source="facture.code", read_only=True)
    fournisseur_nom = serializers.CharField(source="facture.supplier.name", read_only=True, default=None)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    move_number = serializers.CharField(source="move.number", read_only=True, default=None)
    document_ged_code = serializers.CharField(source="document_ged.reference", read_only=True, default=None)

    class Meta:
        model = AvoirFournisseur
        fields = [
            "id", "code", "facture", "facture_code", "fournisseur_nom", "litige", "reference_fournisseur", "date_avoir",
            "montant_ht", "motif", "statut", "statut_label", "move", "move_number", "comptabilise_par", "comptabilise_le",
            "document_ged", "document_ged_code", "created_by", "created_at",
        ]
        read_only_fields = [
            "id", "code", "statut", "move", "comptabilise_par", "comptabilise_le", "document_ged", "created_by", "created_at",
        ]

    def validate_montant_ht(self, value):
        if value <= 0:
            raise serializers.ValidationError("Montant HT strictement positif.")
        return value

    def validate(self, attrs):
        if self.instance and self.instance.statut != AvoirFournisseur.Statut.BROUILLON:
            raise serializers.ValidationError({"detail": "Avoir comptabilisé : pièce scellée."})
        facture = attrs.get("facture") or (self.instance.facture if self.instance else None)
        if facture is not None and facture.status != PurchaseInvoice.Status.COMPTABILISEE:
            raise serializers.ValidationError({"facture": "Un avoir porte sur une facture comptabilisée."})
        litige = attrs.get("litige")
        if litige is not None and facture is not None and litige.purchase_order_id != facture.purchase_order_id:
            raise serializers.ValidationError({"litige": "Litige d'un autre bon de commande."})
        montant = attrs.get("montant_ht") or (self.instance.montant_ht if self.instance else None)
        if facture is not None and montant is not None:
            autres = facture.avoirs.exclude(pk=self.instance.pk if self.instance else None)
            cumul = sum((a.montant_ht for a in autres), montant)
            if cumul > facture.total:
                raise serializers.ValidationError({"montant_ht": tr("Avoirs cumulés (%(cumul)s) supérieurs au HT de la facture (%(facture_total)s).") % {"cumul": format(cumul, '.2f'), "facture_total": format(facture.total, '.2f')}})
        return attrs
