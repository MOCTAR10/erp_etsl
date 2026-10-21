"""Sérialiseurs M10 — Comptabilité & Trésorerie (RF-ERP-90…94)."""

from rest_framework import serializers

from .models import (
    CompteBancaire,
    ControleInterne,
    DeclarationTva,
    Engagement,
    ClotureMensuelle,
    FactureClient,
    Lettrage,
    LigneFactureClient,
    LigneRapprochement,
    ModeleFacture,
    ParametreCompta,
    LigneReleve,
    Paiement,
    RapprochementBancaire,
    ReleveBancaire,
    TauxTva,
    PrevisionTresorerie,
    AutoFacture,
    GabaritEtat,
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
        fields = ["id", "releve", "date", "libelle", "reference", "debit", "credit", "rapprochee", "paiement"]
        read_only_fields = ["rapprochee", "paiement"]


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
            "anomalies",
            "created_at",
        ]
        read_only_fields = ["code", "statut", "anomalies"]


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

    def validate_montant(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError("Le montant doit être strictement positif.")
        return value


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
            "analytic_account",
            "retenue_source",
            "montant_retenue",
            "reference",
            "statut",
            "statut_label",
            "move",
            "move_number",
            "has_amount_access",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["code", "statut", "move", "move_number", "montant_retenue"]

    def validate_montant(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError("Le montant doit être strictement positif.")
        return value

    def get_has_amount_access(self, obj):
        from .services import can_see_amount

        return can_see_amount(self.context.get("request").user)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        from .services import can_see_amount

        request = self.context.get("request")
        if not can_see_amount(getattr(request, "user", None)):
            data["montant"] = None
            data["montant_retenue"] = None
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
            "tva_autoliquidee",
            "retenues_source",
            "source_calcul",
            "document",
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
            "tva_autoliquidee",
            "retenues_source",
            "source_calcul",
            "document",
        ]

    def get_has_amount_access(self, obj):
        from .services import can_see_amount

        return can_see_amount(self.context.get("request").user)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        from .services import can_see_amount

        request = self.context.get("request")
        if not can_see_amount(getattr(request, "user", None)):
            for key in ("base_imposable", "tva_collectee", "tva_deductible", "net_a_payer", "tva_autoliquidee", "retenues_source"):
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
        read_only_fields = ["code", "date_realise", "statut"]

class ParametreComptaSerializer(serializers.ModelSerializer):
    est_provisoire = serializers.BooleanField(read_only=True)

    class Meta:
        model = ParametreCompta
        fields = [
            "id", "code", "label", "valeur", "unite", "statut_valeur", "est_provisoire",
            "confirme_par", "confirme_le",
        ]
        read_only_fields = ["code", "label", "unite", "statut_valeur", "confirme_par", "confirme_le"]

    def validate_valeur(self, value):
        if value < 0:
            raise serializers.ValidationError("La valeur ne peut pas être négative.")
        return value

    def update(self, instance, validated_data):
        # Une valeur modifiée redevient provisoire jusqu'à nouvelle confirmation.
        if "valeur" in validated_data and validated_data["valeur"] != instance.valeur:
            instance.statut_valeur = ParametreCompta.StatutValeur.PROVISOIRE
            instance.confirme_par = None
            instance.confirme_le = None
        return super().update(instance, validated_data)


class LettrageSerializer(serializers.ModelSerializer):
    lignes = serializers.SerializerMethodField()
    compte_code = serializers.CharField(source="compte.code", read_only=True)
    has_amount_access = serializers.SerializerMethodField()

    class Meta:
        model = Lettrage
        fields = [
            "id", "code", "compte", "compte_code", "partner", "date", "ecart", "automatique", "statut",
            "created_by", "created_at", "annule_par", "annule_le", "motif_annulation", "lignes",
            "has_amount_access",
        ]
        read_only_fields = fields

    def _voit(self):
        from .services import can_see_amount

        return can_see_amount(getattr(self.context.get("request"), "user", None))

    def get_has_amount_access(self, obj):
        return self._voit()

    def get_lignes(self, obj):
        voit = self._voit()
        return [
            {
                "id": str(ll.ligne_id),
                "piece": ll.ligne.move.number,
                "date": ll.ligne.move.date,
                "reference": ll.ligne.move.reference,
                "debit": ll.ligne.debit if voit else None,
                "credit": ll.ligne.credit if voit else None,
            }
            for ll in obj.lignes.all()
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not self._voit():
            data["ecart"] = None
        return data


class ModeleFactureSerializer(serializers.ModelSerializer):
    est_provisoire = serializers.BooleanField(read_only=True)

    class Meta:
        model = ModeleFacture
        fields = [
            "id", "code", "entete", "mentions_legales", "conditions_paiement", "coordonnees_bancaires",
            "pied_page", "delai_paiement_jours", "statut_valeur", "est_provisoire", "confirme_par", "confirme_le",
        ]
        read_only_fields = ["code", "statut_valeur", "confirme_par", "confirme_le"]

    def update(self, instance, validated_data):
        # Toute modification du modèle le repasse en provisoire jusqu'à nouvelle confirmation.
        instance.statut_valeur = ModeleFacture.StatutValeur.PROVISOIRE
        instance.confirme_par, instance.confirme_le = None, None
        return super().update(instance, validated_data)


class LigneFactureClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = LigneFactureClient
        fields = ["id", "designation", "quantite", "prix_unitaire", "montant", "compte_produit"]
        read_only_fields = ["montant"]
        extra_kwargs = {"compte_produit": {"required": False}}

    def validate(self, data):
        if data.get("quantite") is not None and data["quantite"] <= 0:
            raise serializers.ValidationError({"quantite": "La quantité doit être strictement positive."})
        if data.get("prix_unitaire") is not None and data["prix_unitaire"] < 0:
            raise serializers.ValidationError({"prix_unitaire": "Le prix ne peut pas être négatif."})
        return data


class FactureClientSerializer(serializers.ModelSerializer):
    lignes = LigneFactureClientSerializer(many=True, required=False)
    client_name = serializers.CharField(source="client.name", read_only=True)
    has_amount_access = serializers.SerializerMethodField()
    avertissement_provisoire = serializers.SerializerMethodField()
    move_number = serializers.CharField(source="move.number", read_only=True, default=None)

    class Meta:
        model = FactureClient
        fields = [
            "id", "code", "nature", "statut", "client", "client_name", "affaire", "jalon", "situation",
            "facture_origine", "objet", "date", "echeance", "taux_tva", "montant_ht", "montant_tva",
            "montant_ttc", "move", "move_number", "document", "emise_par", "emise_le", "lignes",
            "has_amount_access", "avertissement_provisoire", "created_at",
        ]
        read_only_fields = [
            "code", "nature", "statut", "affaire", "jalon", "situation", "facture_origine", "montant_ht",
            "montant_tva", "montant_ttc", "move", "document", "emise_par", "emise_le",
        ]

    def get_has_amount_access(self, obj):
        from .services import can_see_amount

        return can_see_amount(getattr(self.context.get("request"), "user", None))

    def get_avertissement_provisoire(self, obj):
        from .facturation import get_modele

        return obj.modele_provisoire if obj.statut == FactureClient.Statut.EMISE else get_modele().est_provisoire

    def _ecrire_lignes(self, facture, lignes):
        from .facturation import _compte

        facture.lignes.all().delete()
        for item in lignes:
            item.setdefault("compte_produit", _compte("706000"))
            LigneFactureClient.objects.create(facture=facture, **item)
        facture.recalculer()

    def create(self, validated_data):
        lignes = validated_data.pop("lignes", [])
        if not validated_data.get("taux_tva"):
            from .facturation import _taux_defaut

            validated_data["taux_tva"] = _taux_defaut()
        facture = super().create(validated_data)
        self._ecrire_lignes(facture, lignes)
        return facture

    def update(self, instance, validated_data):
        lignes = validated_data.pop("lignes", None)
        facture = super().update(instance, validated_data)
        if lignes is not None:
            self._ecrire_lignes(facture, lignes)
        else:
            facture.recalculer()
        return facture

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not data["has_amount_access"]:
            for cle in ("montant_ht", "montant_tva", "montant_ttc"):
                data[cle] = None
            for l in data["lignes"]:
                l["prix_unitaire"] = l["montant"] = None
        return data


class ClotureMensuelleSerializer(serializers.ModelSerializer):
    periode = serializers.SerializerMethodField()
    periode_statut = serializers.CharField(source="period.status", read_only=True)
    fin_periode = serializers.DateField(source="period.end_date", read_only=True)
    retard = serializers.SerializerMethodField()
    has_amount_access = serializers.SerializerMethodField()

    class Meta:
        model = ClotureMensuelle
        fields = [
            "id", "period", "periode", "periode_statut", "fin_periode", "statut", "demarree_le", "demarree_par",
            "cloturee_le", "cloturee_par", "duree_minutes", "dans_objectif", "objectif_minutes", "echeance_envoi",
            "controles", "synthese", "envoyee_le", "envoyee_par", "destinataires", "emails_envoyes", "document", "reouvertures", "retard",
            "has_amount_access",
        ]
        read_only_fields = fields

    def get_periode(self, obj):
        return str(obj.period)

    def get_retard(self, obj):
        from .cloture import retard_cloture

        return retard_cloture(obj)

    def get_has_amount_access(self, obj):
        from .services import can_see_amount

        return can_see_amount(getattr(self.context.get("request"), "user", None))

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not data["has_amount_access"]:
            data["synthese"] = {}
        return data


class _MasqueMontantsMixin:
    """Montants masqués hors cercle des montants (RF-59) ; `has_amount_access` lu par le SPA."""

    champs_montants: tuple = ()

    def get_has_amount_access(self, obj):
        from .services import can_see_amount

        return can_see_amount(getattr(self.context.get("request"), "user", None))

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not data.get("has_amount_access"):
            for key in self.champs_montants:
                data[key] = None
        return data


class PrevisionTresorerieSerializer(_MasqueMontantsMixin, serializers.ModelSerializer):
    champs_montants = ("montant",)
    sens_label = serializers.CharField(source="get_sens_display", read_only=True)
    categorie_label = serializers.CharField(source="get_categorie_display", read_only=True)
    has_amount_access = serializers.SerializerMethodField()

    class Meta:
        model = PrevisionTresorerie
        fields = [
            "id", "code", "date_prevue", "sens", "sens_label", "categorie", "categorie_label", "libelle", "montant",
            "compte_bancaire", "has_amount_access", "created_at",
        ]
        read_only_fields = ["code", "created_at"]

    def validate_montant(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError("Le montant doit être strictement positif.")
        return value


class AutoFactureSerializer(_MasqueMontantsMixin, serializers.ModelSerializer):
    champs_montants = ("montant_ht", "montant_tva")
    fournisseur_name = serializers.CharField(source="fournisseur.name", read_only=True)
    compte_charge_code = serializers.CharField(source="compte_charge.code", read_only=True)
    taux = serializers.DecimalField(source="taux_tva.taux", max_digits=6, decimal_places=2, read_only=True)
    move_number = serializers.CharField(source="move.number", read_only=True, default=None)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    has_amount_access = serializers.SerializerMethodField()

    class Meta:
        model = AutoFacture
        fields = [
            "id", "code", "fournisseur", "fournisseur_name", "date", "objet", "montant_ht", "taux_tva", "taux",
            "montant_tva", "compte_charge", "compte_charge_code", "analytic", "statut", "statut_label", "move",
            "move_number", "emise_par", "emise_le", "has_amount_access", "created_at",
        ]
        read_only_fields = ["code", "montant_tva", "statut", "move", "emise_par", "emise_le", "created_at"]

    def validate_montant_ht(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError("Le montant HT doit être strictement positif.")
        return value


class GabaritEtatSerializer(serializers.ModelSerializer):
    est_provisoire = serializers.BooleanField(read_only=True)

    class Meta:
        model = GabaritEtat
        fields = ["id", "code", "label", "parametres", "statut_valeur", "est_provisoire", "confirme_par", "confirme_le", "modifie_le"]
        read_only_fields = fields
