"""Sérialiseurs M10 — Comptabilité & Trésorerie (RF-ERP-90…94)."""

from rest_framework import serializers

from .models import (
    CompteBancaire,
    ControleInterne,
    DeclarationTva,
    Engagement,
    LigneRapprochement,
    LigneReleve,
    Paiement,
    RapprochementBancaire,
    ReleveBancaire,
    TauxTva,
)


class TauxTvaSerializer(serializers.ModelSerializer):
    class Meta:
        model = TauxTva
        fields = [
            "id",
            "code",
            "label",
            "taux",
            "compte_collecte",
            "compte_deductible",
            "is_default",
            "is_active",
        ]
        read_only_fields = ["code"]


class CompteBancaireSerializer(serializers.ModelSerializer):
    compte_comptable_code = serializers.CharField(
        source="compte_comptable.code", read_only=True
    )
    devise_code = serializers.CharField(source="devise.code", read_only=True, default=None)

    class Meta:
        model = CompteBancaire
        fields = [
            "id",
            "code",
            "label",
            "banque",
            "numero",
            "compte_comptable",
            "compte_comptable_code",
            "devise",
            "devise_code",
            "solde_initial",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["code"]


class LigneReleveSerializer(serializers.ModelSerializer):
    class Meta:
        model = LigneReleve
        fields = ["id", "releve", "date", "libelle", "reference", "debit", "credit", "rapprochee"]
        read_only_fields = ["rapprochee"]


class ReleveBancaireSerializer(serializers.ModelSerializer):
    compte_bancaire_label = serializers.CharField(
        source="compte_bancaire.label", read_only=True
    )
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    source_label = serializers.CharField(source="get_source_display", read_only=True)
    lignes = LigneReleveSerializer(many=True, read_only=True)
    total_debit = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    total_credit = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)

    class Meta:
        model = ReleveBancaire
        fields = [
            "id",
            "code",
            "compte_bancaire",
            "compte_bancaire_label",
            "date_debut",
            "date_fin",
            "solde_initial",
            "solde_final",
            "statut",
            "statut_label",
            "source",
            "source_label",
            "total_debit",
            "total_credit",
            "lignes",
            "created_at",
        ]
        read_only_fields = ["code", "statut"]


class LigneRapprochementSerializer(serializers.ModelSerializer):
    ligne_libelle = serializers.CharField(source="ligne_releve.libelle", read_only=True)
    ligne_date = serializers.DateField(source="ligne_releve.date", read_only=True)
    debit = serializers.DecimalField(source="ligne_releve.debit", max_digits=16, decimal_places=2, read_only=True)
    credit = serializers.DecimalField(source="ligne_releve.credit", max_digits=16, decimal_places=2, read_only=True)

    class Meta:
        model = LigneRapprochement
        fields = ["id", "ligne_releve", "ligne_libelle", "ligne_date", "debit", "credit"]


class RapprochementBancaireSerializer(serializers.ModelSerializer):
    compte_bancaire_label = serializers.CharField(
        source="compte_bancaire.label", read_only=True
    )
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    lignes = LigneRapprochementSerializer(many=True, read_only=True)

    class Meta:
        model = RapprochementBancaire
        fields = [
            "id",
            "code",
            "compte_bancaire",
            "compte_bancaire_label",
            "date",
            "statut",
            "statut_label",
            "notes",
            "lignes",
            "created_at",
        ]
        read_only_fields = ["code", "statut"]


class EngagementSerializer(serializers.ModelSerializer):
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    compte_depense_code = serializers.CharField(source="compte_depense.code", read_only=True, default=None)
    fournisseur_name = serializers.CharField(source="fournisseur.name", read_only=True, default=None)
    demande_par_name = serializers.CharField(
        source="demande_par.get_full_name", read_only=True, default=None
    )
    total_paye = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)

    class Meta:
        model = Engagement
        fields = [
            "id",
            "code",
            "objet",
            "montant",
            "compte_depense",
            "compte_depense_code",
            "fournisseur",
            "fournisseur_name",
            "statut",
            "statut_label",
            "date_engagement",
            "demande_par",
            "demande_par_name",
            "total_paye",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["code", "statut", "date_engagement", "demande_par"]


class PaiementSerializer(serializers.ModelSerializer):
    sens_label = serializers.CharField(source="get_sens_display", read_only=True)
    mode_label = serializers.CharField(source="get_mode_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    compte_bancaire_label = serializers.CharField(
        source="compte_bancaire.label", read_only=True
    )
    tiers_name = serializers.CharField(source="tiers.name", read_only=True, default=None)
    engagement_code = serializers.CharField(source="engagement.code", read_only=True, default=None)
    facture_code = serializers.CharField(source="facture.code", read_only=True, default=None)
    move_number = serializers.CharField(source="move.number", read_only=True, default=None)
    has_amount_access = serializers.SerializerMethodField()

    class Meta:
        model = Paiement
        fields = [
            "id",
            "code",
            "sens",
            "sens_label",
            "mode",
            "mode_label",
            "montant",
            "date",
            "compte_bancaire",
            "compte_bancaire_label",
            "engagement",
            "engagement_code",
            "tiers",
            "tiers_name",
            "facture",
            "facture_code",
            "imputation_618",
            "reference",
            "statut",
            "statut_label",
            "move",
            "move_number",
            "has_amount_access",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["code", "statut", "move", "move_number"]

    def get_has_amount_access(self, obj):
        from .services import can_see_amount

        return can_see_amount(self.context.get("request").user)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        from .services import can_see_amount

        request = self.context.get("request")
        if not can_see_amount(getattr(request, "user", None)):
            data["montant"] = None
            data["has_amount_access"] = False
        return data


class DeclarationTvaSerializer(serializers.ModelSerializer):
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    taux_tva_code = serializers.CharField(source="taux_tva.code", read_only=True)
    has_amount_access = serializers.SerializerMethodField()

    class Meta:
        model = DeclarationTva
        fields = [
            "id",
            "code",
            "mois",
            "taux_tva",
            "taux_tva_code",
            "base_imposable",
            "tva_collectee",
            "tva_deductible",
            "net_a_payer",
            "statut",
            "statut_label",
            "has_amount_access",
            "created_at",
        ]
        read_only_fields = [
            "code",
            "statut",
            "base_imposable",
            "tva_collectee",
            "tva_deductible",
            "net_a_payer",
        ]

    def get_has_amount_access(self, obj):
        from .services import can_see_amount

        return can_see_amount(self.context.get("request").user)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        from .services import can_see_amount

        request = self.context.get("request")
        if not can_see_amount(getattr(request, "user", None)):
            for key in ("base_imposable", "tva_collectee", "tva_deductible", "net_a_payer"):
                data[key] = None
            data["has_amount_access"] = False
        return data


class ControleInterneSerializer(serializers.ModelSerializer):
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    responsable_name = serializers.CharField(
        source="responsable.get_full_name", read_only=True, default=None
    )

    class Meta:
        model = ControleInterne
        fields = [
            "id",
            "code",
            "libelle",
            "reference_procedure",
            "statut",
            "statut_label",
            "responsable",
            "responsable_name",
            "date_prevue",
            "date_realise",
            "constat",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["code", "date_realise"]