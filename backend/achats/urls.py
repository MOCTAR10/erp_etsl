from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ConsultationOfferViewSet,
    ConsultationRequestViewSet,
    GoodsReceiptLineViewSet,
    GoodsReceiptViewSet,
    PurchaseInvoiceLineViewSet,
    PurchaseInvoiceViewSet,
    PurchaseOrderLineViewSet,
    PurchaseOrderViewSet,
    PurchaseRequestLineViewSet,
    PurchaseRequestViewSet,
)

router = DefaultRouter()
router.register("requests", PurchaseRequestViewSet, basename="purchaserequest")
router.register("request-lines", PurchaseRequestLineViewSet, basename="purchaserequestline")
router.register("consultations", ConsultationRequestViewSet, basename="consultation")
router.register("consultation-offers", ConsultationOfferViewSet, basename="consultationoffer")
router.register("orders", PurchaseOrderViewSet, basename="purchaseorder")
router.register("order-lines", PurchaseOrderLineViewSet, basename="purchaseorderline")
router.register("receipts", GoodsReceiptViewSet, basename="goodsreceipt")
router.register("receipt-lines", GoodsReceiptLineViewSet, basename="goodsreceiptline")
router.register("invoices", PurchaseInvoiceViewSet, basename="purchaseinvoice")
router.register("invoice-lines", PurchaseInvoiceLineViewSet, basename="purchaseinvoiceline")

urlpatterns = [
    path("", include(router.urls)),
]