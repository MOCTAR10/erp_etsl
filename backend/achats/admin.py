from django.contrib import admin

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


@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "requester", "department", "status", "is_urgent")
    list_filter = ("status", "is_urgent")


@admin.register(PurchaseRequestLine)
class PurchaseRequestLineAdmin(admin.ModelAdmin):
    list_display = ("label", "request", "quantity", "estimated_price")


@admin.register(ConsultationRequest)
class ConsultationRequestAdmin(admin.ModelAdmin):
    list_display = ("code", "subject", "due_date", "status")
    list_filter = ("status",)


@admin.register(ConsultationOffer)
class ConsultationOfferAdmin(admin.ModelAdmin):
    list_display = ("consultation", "supplier", "amount", "delivery_days", "is_selected")


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ("code", "supplier", "order_date", "status", "is_global_rental")
    list_filter = ("status", "is_global_rental")


@admin.register(PurchaseOrderLine)
class PurchaseOrderLineAdmin(admin.ModelAdmin):
    list_display = ("label", "purchase_order", "quantity", "unit_price", "price_total")


@admin.register(GoodsReceipt)
class GoodsReceiptAdmin(admin.ModelAdmin):
    list_display = ("code", "purchase_order", "received_at", "status")
    list_filter = ("status",)


@admin.register(GoodsReceiptLine)
class GoodsReceiptLineAdmin(admin.ModelAdmin):
    list_display = ("purchase_order_line", "receipt", "quantity")


@admin.register(PurchaseInvoice)
class PurchaseInvoiceAdmin(admin.ModelAdmin):
    list_display = ("code", "invoice_ref", "purchase_order", "invoice_date", "status")
    list_filter = ("status",)


@admin.register(PurchaseInvoiceLine)
class PurchaseInvoiceLineAdmin(admin.ModelAdmin):
    list_display = ("purchase_order_line", "invoice", "quantity", "unit_price", "price_total")