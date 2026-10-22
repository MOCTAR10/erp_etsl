from rest_framework import serializers

from config.serializers import ModelCleanMixin

from .models import (
    LitigeFournisseur,
    ConsultationOffer,
    ConsultationRequest,
    GoodsReceipt,
    GoodsReceiptLine,
    PurchaseInvoice,
    PurchaseInvoiceLine,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseRequest,
    PurchaseRequestLine,
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


class PurchaseRequestSerializer(serializers.ModelSerializer):
    requester_name = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    lines_count = serializers.IntegerField(source="lines.count", read_only=True)
    affaire_code = serializers.CharField(source="affaire.code", read_only=True, default=None)

    class Meta:
        model = PurchaseRequest
        fields = [
            "id",
            "code",
            "title",
            "requester",
            "requester_name",
            "department",
            "expected_date",
            "status",
            "status_label",
            "is_urgent",
            "affaire",
            "affaire_code",
            "notes",
            "analytic",
            "visa_dg_par",
            "visa_dg_motif",
            "visa_dg_le",
            "lines_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "requester", "id", "code", "status", "visa_dg_par", "visa_dg_motif", "visa_dg_le", "created_at", "updated_at",
        ]

    def get_requester_name(self, obj):
        if not obj.requester:
            return None
        return (obj.requester.first_name + " " + obj.requester.last_name).strip() or obj.requester.email


class PurchaseRequestLineSerializer(serializers.ModelSerializer):
    article_code = serializers.CharField(source="article.code", read_only=True, default=None)
    unit_label = serializers.CharField(source="unit.label", read_only=True, default=None)

    class Meta:
        model = PurchaseRequestLine
        fields = [
            "id",
            "request",
            "article",
            "article_code",
            "label",
            "quantity",
            "unit",
            "unit_label",
            "estimated_price",
        ]
        read_only_fields = ["id"]


class ConsultationRequestSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    request_code = serializers.CharField(source="request.code", read_only=True, default=None)
    offers_total = serializers.IntegerField(source="offers.count", read_only=True)

    class Meta:
        model = ConsultationRequest
        fields = [
            "id",
            "code",
            "request",
            "request_code",
            "subject",
            "due_date",
            "status",
            "status_label",
            "items",
            "notes",
            "offers_total",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "code", "status", "created_at", "updated_at"]

    def validate_request(self, value):
        # Une consultation / un BC ne s'appuie que sur une DA approuvée (validation hiérarchique préalable).
        if value is not None and value.status not in (
            PurchaseRequest.Status.APPROUVEE, PurchaseRequest.Status.CONVERTIE
        ):
            raise serializers.ValidationError(
                f"DA {value.code} non approuvée ({value.get_status_display().lower()}) : consultation / commande impossible."
            )
        return value


class ConsultationOfferSerializer(AmountMaskMixin, serializers.ModelSerializer):
    amount_fields = ["amount"]

    supplier_name = serializers.CharField(source="supplier.name", read_only=True, default=None)
    consultation_code = serializers.CharField(source="consultation.code", read_only=True)

    class Meta:
        model = ConsultationOffer
        fields = [
            "id",
            "consultation",
            "consultation_code",
            "supplier",
            "supplier_name",
            "amount",
            "delivery_days",
            "is_selected",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class PurchaseOrderLineSerializer(AmountMaskMixin, serializers.ModelSerializer):
    amount_fields = ["unit_price", "price_total"]

    article_code = serializers.CharField(source="article.code", read_only=True, default=None)
    unit_label = serializers.CharField(source="unit.label", read_only=True, default=None)
    order_code = serializers.CharField(source="purchase_order.code", read_only=True)

    class Meta:
        model = PurchaseOrderLine
        fields = [
            "id",
            "purchase_order",
            "order_code",
            "article",
            "article_code",
            "label",
            "quantity",
            "unit",
            "unit_label",
            "unit_price",
            "price_total",
            "received_qty",
            "invoiced_qty",
        ]
        read_only_fields = ["id", "price_total", "received_qty", "invoiced_qty"]


class PurchaseOrderSerializer(AmountMaskMixin, ModelCleanMixin, serializers.ModelSerializer):
    amount_fields = ["total"]

    supplier_name = serializers.CharField(source="supplier.name", read_only=True, default=None)
    request_code = serializers.CharField(source="request.code", read_only=True, default=None)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    conformity = serializers.JSONField(read_only=True)
    lines_count = serializers.IntegerField(source="lines.count", read_only=True)
    created_by_name = serializers.SerializerMethodField()
    affaire_code = serializers.CharField(source="affaire.code", read_only=True, default=None)
    location_gr_code = serializers.CharField(source="location_gr.code", read_only=True, default=None)

    class Meta:
        model = PurchaseOrder
        fields = [
            "id",
            "code",
            "supplier",
            "supplier_name",
            "request",
            "request_code",
            "consultation",
            "order_date",
            "expected_date",
            "status",
            "status_label",
            "currency",
            "is_global_rental",
            "affaire",
            "affaire_code",
            "location_gr",
            "location_gr_code",
            "reference_ds",
            "document_ged",
            "notes",
            "analytic",
            "visa_dg_par",
            "visa_dg_motif",
            "visa_dg_le",
            "total",
            "conformity",
            "lines_count",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "code",
            "status",
            "visa_dg_par",
            "visa_dg_motif",
            "visa_dg_le",
            "total",
            "conformity",
            "document_ged",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def get_created_by_name(self, obj):
        if not obj.created_by:
            return None
        return (obj.created_by.first_name + " " + obj.created_by.last_name).strip() or obj.created_by.email

    def validate_request(self, value):
        # Une consultation / un BC ne s'appuie que sur une DA approuvée (validation hiérarchique préalable).
        if value is not None and value.status not in (
            PurchaseRequest.Status.APPROUVEE, PurchaseRequest.Status.CONVERTIE
        ):
            raise serializers.ValidationError(
                f"DA {value.code} non approuvée ({value.get_status_display().lower()}) : consultation / commande impossible."
            )
        return value


class GoodsReceiptSerializer(serializers.ModelSerializer):
    order_code = serializers.CharField(source="purchase_order.code", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    received_by_name = serializers.SerializerMethodField()

    controle_qualite = serializers.SerializerMethodField()
    controles = serializers.SerializerMethodField()

    class Meta:
        model = GoodsReceipt
        fields = [
            "id",
            "code",
            "purchase_order",
            "order_code",
            "received_at",
            "status",
            "status_label",
            "received_by",
            "received_by_name",
            "notes",
            "controle_qualite",
            "controles",
            "document_ged",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "code", "status", "received_by", "document_ged", "created_at", "updated_at"]

    def get_controles(self, obj):
        """Tous les contrôles M6 de la réception (réception + ITP / CND exigés par les règles d'inspection)."""
        return [
            {"id": str(c.pk), "code": c.code, "type": c.type_controle, "statut": c.statut, "resultat": c.resultat}
            for c in obj.controles_qualite.order_by("created_at")
        ]

    def get_controle_qualite(self, obj):
        ctrl = obj.controles_qualite.order_by("-created_at").first()
        if ctrl is None:
            return None
        return {"id": str(ctrl.pk), "code": ctrl.code, "statut": ctrl.statut, "resultat": ctrl.resultat}

    def get_received_by_name(self, obj):
        if not obj.received_by:
            return None
        return (obj.received_by.first_name + " " + obj.received_by.last_name).strip() or obj.received_by.email


class GoodsReceiptLineSerializer(serializers.ModelSerializer):
    order_line_label = serializers.CharField(
        source="purchase_order_line.label", read_only=True
    )
    lot_code = serializers.CharField(source="lot.code", read_only=True, default=None)

    class Meta:
        model = GoodsReceiptLine
        fields = [
            "id",
            "receipt",
            "purchase_order_line",
            "order_line_label",
            "quantity",
            "comment",
            "numero_lot",
            "numero_coulee",
            "date_peremption",
            "certificat_type",
            "numero_certificat",
            "organisme_certificat",
            "lot",
            "lot_code",
            "saisi_le",
        ]
        read_only_fields = ["id", "lot"]

    def validate_saisi_le(self, value):
        from operations.terrain_a3 import verifier_saisi_le

        return verifier_saisi_le(value)

    def validate(self, attrs):
        get = lambda k: attrs.get(k, getattr(self.instance, k, "") if self.instance else "")  # noqa: E731
        if get("certificat_type") and not (get("numero_certificat") or "").strip():
            raise serializers.ValidationError({"numero_certificat": "N° de certificat MTC / CoC requis."})
        if (get("certificat_type") or (get("numero_certificat") or "").strip()) and not (get("numero_lot") or "").strip():
            raise serializers.ValidationError({"numero_lot": "Un certificat matière se rattache à un lot : n° de lot requis."})
        return attrs


class PurchaseInvoiceSerializer(AmountMaskMixin, serializers.ModelSerializer):
    amount_fields = ["total", "total_tva", "total_ttc"]

    order_code = serializers.CharField(source="purchase_order.code", read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True, default=None)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    total_tva = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    total_ttc = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    move_number = serializers.CharField(source="move.number", read_only=True, default=None)
    lines_count = serializers.IntegerField(source="lines.count", read_only=True)

    class Meta:
        model = PurchaseInvoice
        fields = [
            "id",
            "code",
            "purchase_order",
            "order_code",
            "supplier",
            "supplier_name",
            "invoice_ref",
            "invoice_date",
            "status",
            "status_label",
            "currency",
            "total",
            "total_tva",
            "total_ttc",
            "move",
            "move_number",
            "comptabilise_le",
            "lines_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id", "code", "status", "total", "total_tva", "total_ttc",
            "move", "comptabilise_le", "created_at", "updated_at",
        ]


class PurchaseInvoiceLineSerializer(AmountMaskMixin, serializers.ModelSerializer):
    amount_fields = ["unit_price", "price_total"]

    order_line_label = serializers.CharField(
        source="purchase_order_line.label", read_only=True
    )
    article_code = serializers.CharField(
        source="purchase_order_line.article.code", read_only=True, default=None
    )

    class Meta:
        model = PurchaseInvoiceLine
        fields = [
            "id",
            "invoice",
            "purchase_order_line",
            "order_line_label",
            "article_code",
            "quantity",
            "unit_price",
            "price_total",
            "taux_tva",
        ]
        read_only_fields = ["id", "price_total"]


class LitigeFournisseurSerializer(AmountMaskMixin, ModelCleanMixin, serializers.ModelSerializer):
    amount_fields = ["montant_en_jeu"]
    order_code = serializers.CharField(source="purchase_order.code", read_only=True)
    fournisseur_name = serializers.CharField(source="purchase_order.supplier.name", read_only=True, default=None)
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    contentieux_code = serializers.CharField(source="contentieux.code", read_only=True, default=None)

    class Meta:
        model = LitigeFournisseur
        fields = [
            "id", "code", "purchase_order", "order_code", "fournisseur_name", "receipt", "invoice", "type", "type_label",
            "description", "montant_en_jeu", "statut", "statut_label", "nb_relances", "derniere_relance_le",
            "contentieux", "contentieux_code", "resolution", "resolu_le", "document_ged", "created_by", "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "code", "statut", "nb_relances", "derniere_relance_le", "contentieux", "resolution",
                            "resolu_le", "document_ged", "created_by", "created_at", "updated_at"]

    def validate(self, attrs):
        if self.instance and self.instance.statut == LitigeFournisseur.Statut.RESOLU:
            raise serializers.ValidationError({"detail": "Litige résolu : pièce scellée."})
        return super().validate(attrs)
