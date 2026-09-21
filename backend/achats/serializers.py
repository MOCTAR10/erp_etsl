from rest_framework import serializers

from .models import (
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
            "notes",
            "lines_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "code", "created_at", "updated_at"]

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
        read_only_fields = ["id", "code", "created_at", "updated_at"]


class ConsultationOfferSerializer(AmountMaskMixin, serializers.ModelSerializer):
    amount_fields = ["amount"]

    supplier_name = serializers.CharField(source="supplier.name", read_only=True, default=None)

    class Meta:
        model = ConsultationOffer
        fields = [
            "id",
            "consultation",
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

    class Meta:
        model = PurchaseOrderLine
        fields = [
            "id",
            "purchase_order",
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


class PurchaseOrderSerializer(AmountMaskMixin, serializers.ModelSerializer):
    amount_fields = ["total"]

    supplier_name = serializers.CharField(source="supplier.name", read_only=True, default=None)
    request_code = serializers.CharField(source="request.code", read_only=True, default=None)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    conformity = serializers.JSONField(read_only=True)
    lines_count = serializers.IntegerField(source="lines.count", read_only=True)
    created_by_name = serializers.SerializerMethodField()

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
            "notes",
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
            "total",
            "conformity",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def get_created_by_name(self, obj):
        if not obj.created_by:
            return None
        return (obj.created_by.first_name + " " + obj.created_by.last_name).strip() or obj.created_by.email


class GoodsReceiptSerializer(serializers.ModelSerializer):
    order_code = serializers.CharField(source="purchase_order.code", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    received_by_name = serializers.SerializerMethodField()

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
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "code", "received_by", "created_at", "updated_at"]

    def get_received_by_name(self, obj):
        if not obj.received_by:
            return None
        return (obj.received_by.first_name + " " + obj.received_by.last_name).strip() or obj.received_by.email


class GoodsReceiptLineSerializer(serializers.ModelSerializer):
    order_line_label = serializers.CharField(
        source="purchase_order_line.label", read_only=True
    )

    class Meta:
        model = GoodsReceiptLine
        fields = [
            "id",
            "receipt",
            "purchase_order_line",
            "order_line_label",
            "quantity",
            "comment",
        ]
        read_only_fields = ["id"]


class PurchaseInvoiceSerializer(AmountMaskMixin, serializers.ModelSerializer):
    amount_fields = ["total"]

    order_code = serializers.CharField(source="purchase_order.code", read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True, default=None)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
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
            "lines_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "code", "total", "created_at", "updated_at"]


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
        ]
        read_only_fields = ["id", "price_total"]