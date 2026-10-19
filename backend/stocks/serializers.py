"""Sérialiseurs M5 — Stocks & Traçabilité matière."""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from config.serializers import ModelCleanMixin

from .models import (
    ArticleStock,
    CertificatMatiere,
    Depot,
    Inventaire,
    InventaireLigne,
    LotMatiere,
    ParametreStock,
    MouvementStock,
    PlanInventaireTournant,
    StockQuant,
    ValorisationMensuelle,
)
from .services import can_see_amount


class DepotSerializer(serializers.ModelSerializer):
    responsable_label = serializers.CharField(
        source="responsable.get_full_name", read_only=True, default=None
    )

    class Meta:
        model = Depot
        fields = [
            "id", "code", "label", "site", "responsable", "responsable_label",
            "description", "methode_valorisation", "is_global_rental", "roles_autorises", "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ["code"]


class LotMatiereSerializer(ModelCleanMixin, serializers.ModelSerializer):
    article_code = serializers.CharField(source="article.code", read_only=True, default=None)
    article_label = serializers.CharField(source="article.label", read_only=True, default=None)
    certificats = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    nc_blocage_code = serializers.CharField(source="nc_blocage.code", read_only=True, default=None)
    bloque_par_name = serializers.CharField(source="bloque_par.get_full_name", read_only=True, default=None)

    class Meta:
        model = LotMatiere
        fields = [
            "id", "code", "article", "article_code", "article_label", "numero_lot", "numero_coulee",
            "date_reception", "date_peremption", "quantite_initiale",
            "quantite_restante", "statut", "certificats", "motif_blocage", "bloque_par", "bloque_par_name",
            "bloque_le", "nc_blocage", "nc_blocage_code", "created_at", "updated_at",
        ]
        read_only_fields = ["code", "statut", "quantite_restante", "motif_blocage", "bloque_par", "bloque_le", "nc_blocage"]


class CertificatMatiereSerializer(ModelCleanMixin, serializers.ModelSerializer):
    lot_code = serializers.CharField(source="lot.code", read_only=True, default=None)
    article_code = serializers.CharField(
        source="lot.article.code", read_only=True, default=None
    )
    fournisseur_label = serializers.CharField(
        source="fournisseur.name", read_only=True, default=None
    )
    valide_par_name = serializers.CharField(source="valide_par.get_full_name", read_only=True, default=None)
    document_titre = serializers.CharField(source="document.title", read_only=True, default=None)

    class Meta:
        model = CertificatMatiere
        fields = [
            "id", "code", "lot", "lot_code", "article_code", "type",
            "numero_certificat", "fournisseur", "fournisseur_label", "organisme",
            "date_emission", "date_validation", "valide_par", "valide_par_name", "document", "document_titre",
            "conforme", "notes", "created_at", "updated_at",
        ]
        # Validation QA/QC attestée côté serveur (action `valider`), pièce jointe par `joindre`.
        read_only_fields = ["code", "date_validation", "valide_par", "document"]


class StockQuantSerializer(serializers.ModelSerializer):
    depot_code = serializers.CharField(source="depot.code", read_only=True)
    article_code = serializers.CharField(source="article.code", read_only=True)
    article_label = serializers.CharField(source="article.label", read_only=True)
    lot_code = serializers.CharField(source="lot.code", read_only=True, default=None)
    has_amount_access = serializers.SerializerMethodField()
    unit_cost = serializers.SerializerMethodField()
    stock_value = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)

    class Meta:
        model = StockQuant
        fields = [
            "id", "depot", "depot_code", "article", "article_code", "article_label",
            "lot", "lot_code", "quantity", "unit_cost", "stock_value",
            "has_amount_access", "updated_at",
        ]

    def get_has_amount_access(self, obj):
        return can_see_amount(self.context.get("request").user)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if not can_see_amount(getattr(request, "user", None)):
            data["stock_value"] = None
        return data

    def get_unit_cost(self, obj):
        if float(obj.quantity) <= 0:
            return 0
        return float(obj.stock_value) / float(obj.quantity)


class MouvementStockSerializer(serializers.ModelSerializer):
    article_code = serializers.CharField(source="article.code", read_only=True, default=None)
    article_label = serializers.CharField(source="article.label", read_only=True, default=None)
    source_code = serializers.CharField(source="source.code", read_only=True, default=None)
    destination_code = serializers.CharField(
        source="destination.code", read_only=True, default=None
    )
    lot_code = serializers.CharField(source="lot.code", read_only=True, default=None)
    ordre_code = serializers.CharField(source="ordre.code", read_only=True, default=None)
    type_label = serializers.CharField(source="get_type_mouvement_display", read_only=True)
    document_titre = serializers.CharField(source="document.title", read_only=True, default=None)
    montant_total = serializers.DecimalField(
        max_digits=16, decimal_places=2, read_only=True
    )
    has_amount_access = serializers.SerializerMethodField()

    class Meta:
        model = MouvementStock
        fields = [
            "id", "code", "type_mouvement", "type_label", "article", "article_code",
            "article_label", "quantite", "prix_unitaire", "devise", "source",
            "source_code", "destination", "destination_code", "lot", "lot_code",
            "ordre", "ordre_code", "analytic", "document_reference", "document", "document_titre", "date", "executed",
            "montant_total", "has_amount_access", "created_by", "notes",
            "created_at", "updated_at",
        ]
        read_only_fields = ["created_by", "code", "executed", "montant_total", "document"]

    def get_has_amount_access(self, obj):
        return can_see_amount(self.context.get("request").user)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if not can_see_amount(getattr(request, "user", None)):
            data["prix_unitaire"] = None
            data["montant_total"] = None
        return data

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


class InventaireLigneSerializer(ModelCleanMixin, serializers.ModelSerializer):
    article_code = serializers.CharField(source="article.code", read_only=True, default=None)
    article_label = serializers.CharField(source="article.label", read_only=True, default=None)
    lot_code = serializers.CharField(source="lot.code", read_only=True, default=None)
    ecart = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = InventaireLigne
        fields = [
            "id", "inventaire", "article", "article_code", "article_label", "lot",
            "lot_code", "quantite_systeme", "quantite_reelle", "comptee", "ecart", "updated_at",
        ]
        read_only_fields = ["comptee"]

    def create(self, validated_data):
        return super().create({**validated_data, "comptee": True})

    def update(self, instance, validated_data):
        if "quantite_reelle" in validated_data:
            validated_data["comptee"] = True  # la saisie du comptage vaut pointage
        return super().update(instance, validated_data)


class InventaireSerializer(serializers.ModelSerializer):
    depot_label = serializers.CharField(source="depot.label", read_only=True, default=None)
    responsable_label = serializers.CharField(
        source="responsable.get_full_name", read_only=True, default=None
    )
    created_by_label = serializers.CharField(
        source="created_by.get_full_name", read_only=True, default=None
    )
    ecart_total = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    lignes = InventaireLigneSerializer(many=True, read_only=True)

    class Meta:
        model = Inventaire
        fields = [
            "id", "code", "type", "plan", "depot", "depot_label", "date", "statut", "responsable",
            "responsable_label", "note", "created_by", "created_by_label",
            "ecart_total", "lignes", "created_at", "updated_at",
        ]
        read_only_fields = ["code", "created_by", "statut", "type", "plan"]


class ArticleStockSerializer(serializers.ModelSerializer):
    article_code = serializers.CharField(source="article.code", read_only=True, default=None)
    article_label = serializers.CharField(source="article.label", read_only=True, default=None)

    class Meta:
        model = ArticleStock
        fields = [
            "id", "article", "article_code", "article_label", "methode",
            "prix_standard", "seuil_minimal", "gestion_lots", "certificat_requis", "lot_obligatoire", "is_active",
            "created_at", "updated_at",
        ]


class ValorisationEntrySerializer(serializers.Serializer):
    depot = serializers.CharField()
    article = serializers.CharField()
    label = serializers.CharField()
    quantity = serializers.FloatField()
    value = serializers.FloatField()
    unit_cost = serializers.FloatField()
    method = serializers.CharField()
    lot = serializers.CharField(allow_null=True)


class TraceabiliteEntrySerializer(serializers.Serializer):
    code = serializers.CharField()
    date = serializers.DateField()
    type = serializers.CharField()
    type_label = serializers.CharField()
    article = serializers.CharField()
    quantite = serializers.FloatField()
    prix_unitaire = serializers.FloatField(allow_null=True)
    source = serializers.CharField(allow_null=True)
    destination = serializers.CharField(allow_null=True)
    lot = serializers.CharField(allow_null=True)
    ordre = serializers.CharField(allow_null=True)
    reference = serializers.CharField()


class PlanInventaireTournantSerializer(ModelCleanMixin, serializers.ModelSerializer):
    depot_label = serializers.CharField(source="depot.label", read_only=True, default=None)

    class Meta:
        model = PlanInventaireTournant
        fields = [
            "id", "code", "depot", "depot_label", "periodicite_jours", "articles_par_passage",
            "curseur", "prochaine_date", "responsable", "actif", "created_at", "updated_at",
        ]
        read_only_fields = ["code", "curseur"]


class ValorisationMensuelleSerializer(serializers.ModelSerializer):
    depot_code = serializers.CharField(source="depot.code", read_only=True)
    move_number = serializers.CharField(source="move.number", read_only=True, default=None)
    has_amount_access = serializers.SerializerMethodField()

    def get_has_amount_access(self, obj):
        return can_see_amount(self.context["request"].user)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not data["has_amount_access"]:  # RF-59 : valeurs masquées hors rôles autorisés
            data["valeur_stock"] = data["consommation"] = None
            data["ventilation"] = [{**v, "valeur": None} for v in data["ventilation"]]
        return data

    class Meta:
        model = ValorisationMensuelle
        fields = [
            "id", "periode", "depot", "depot_code", "quantite", "valeur_stock",
            "consommation", "ventilation", "has_amount_access", "move_number", "motif_ecriture", "created_at",
        ]


class ParametreStockSerializer(serializers.ModelSerializer):
    est_provisoire = serializers.BooleanField(read_only=True)

    class Meta:
        model = ParametreStock
        fields = ["id", "code", "label", "valeur", "unite", "statut_valeur", "est_provisoire", "confirme_par", "confirme_le"]
        read_only_fields = ["code", "label", "unite", "statut_valeur", "confirme_par", "confirme_le"]

    def validate_valeur(self, value):
        if value <= 0:
            raise serializers.ValidationError("La valeur doit être strictement positive.")
        return value

    def update(self, instance, validated_data):
        # Une valeur modifiée redevient provisoire jusqu'à nouvelle confirmation.
        if "valeur" in validated_data and validated_data["valeur"] != instance.valeur:
            instance.statut_valeur = ParametreStock.StatutValeur.PROVISOIRE
            instance.confirme_par = None
            instance.confirme_le = None
        return super().update(instance, validated_data)
