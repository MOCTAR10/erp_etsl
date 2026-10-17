"""API module M2 — Achats & Approvisionnements (RF-ERP-10…13)."""

from integrations.idempotency import idempotent
from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

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
from .serializers import (
    ConsultationOfferSerializer,
    ConsultationRequestSerializer,
    GoodsReceiptLineSerializer,
    GoodsReceiptSerializer,
    PurchaseInvoiceLineSerializer,
    PurchaseInvoiceSerializer,
    PurchaseOrderLineSerializer,
    PurchaseOrderSerializer,
    PurchaseRequestLineSerializer,
    PurchaseRequestSerializer,
)
from users.permissions import can_read_module
from .services import CanApproveDa, CanManageAchats, can_see_amount


class _CommonViewSet(viewsets.ModelViewSet):
    """Lecture authentifiée ; écriture réservée aux rôles Achats/Finance."""

    http_method_names = ["get", "post", "patch", "delete"]

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [can_read_module("achats")()]
        return [CanManageAchats()]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["can_view_amount"] = can_see_amount(self.request.user)
        return context


class PurchaseRequestViewSet(_CommonViewSet):
    serializer_class = PurchaseRequestSerializer

    def get_permissions(self):
        # _CommonViewSet.get_permissions ignore les permission_classes d'action : l'approbation est déclarée ici.
        if self.action in ("approuver", "rejeter"):
            return [CanManageAchats(), CanApproveDa()]
        return super().get_permissions()

    def get_queryset(self):
        qs = PurchaseRequest.objects.select_related("requester").all()
        status_ = self.request.query_params.get("status")
        if status_:
            qs = qs.filter(status=status_)
        if self.request.query_params.get("requester"):
            qs = qs.filter(requester_id=self.request.query_params["requester"])
        return qs

    def perform_create(self, serializer):
        serializer.save(requester=self.request.user)

    def _transition(self, frm, to, extra_note=None):
        da = PurchaseRequest.objects.select_for_update().get(pk=self.get_object().pk)
        if da.status != frm:
            return Response(
                {"detail": f"DA {da.get_status_display().lower()} : action impossible."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        da.status = to
        fields = ["status", "updated_at"]
        if extra_note:
            da.notes = f"{da.notes}\n{extra_note}".strip()
            fields.append("notes")
        da.save(update_fields=fields)
        return Response(self.get_serializer(da).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def soumettre(self, request, pk=None):
        return self._transition(PurchaseRequest.Status.BROUILLON, PurchaseRequest.Status.SOUMISE)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def approuver(self, request, pk=None):
        return self._transition(PurchaseRequest.Status.SOUMISE, PurchaseRequest.Status.APPROUVEE)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def rejeter(self, request, pk=None):
        motif = (request.data.get("motif") or "").strip()
        if not motif:
            return Response({"motif": "Motif du rejet obligatoire."}, status=status.HTTP_400_BAD_REQUEST)
        who = request.user.get_full_name() or request.user.email
        return self._transition(
            PurchaseRequest.Status.SOUMISE, PurchaseRequest.Status.REJETEE, f"Rejet ({who}) : {motif}"
        )


class PurchaseRequestLineViewSet(_CommonViewSet):
    serializer_class = PurchaseRequestLineSerializer

    def get_queryset(self):
        qs = PurchaseRequestLine.objects.select_related("article", "unit").all()
        request_id = self.request.query_params.get("request")
        if request_id:
            qs = qs.filter(request_id=request_id)
        return qs


class ConsultationRequestViewSet(_CommonViewSet):
    serializer_class = ConsultationRequestSerializer

    def get_queryset(self):
        qs = ConsultationRequest.objects.select_related("request").all()
        status_ = self.request.query_params.get("status")
        if status_:
            qs = qs.filter(status=status_)
        return qs


class ConsultationOfferViewSet(_CommonViewSet):
    serializer_class = ConsultationOfferSerializer

    def get_queryset(self):
        qs = ConsultationOffer.objects.select_related("consultation", "supplier").all()
        consultation = self.request.query_params.get("consultation")
        if consultation:
            qs = qs.filter(consultation_id=consultation)
        return qs


class PurchaseOrderViewSet(_CommonViewSet):
    serializer_class = PurchaseOrderSerializer

    def get_queryset(self):
        qs = PurchaseOrder.objects.select_related(
            "supplier", "request", "consultation", "currency"
        ).prefetch_related("lines__invoice_lines")
        status_ = self.request.query_params.get("status")
        if status_:
            qs = qs.filter(status=status_)
        if self.request.query_params.get("supplier"):
            qs = qs.filter(supplier_id=self.request.query_params["supplier"])
        if self.request.query_params.get("global_rental") is not None:
            gr = self.request.query_params["global_rental"].lower() in ("1", "true", "yes")
            qs = qs.filter(is_global_rental=gr)
        return qs

    @transaction.atomic
    def perform_create(self, serializer):
        order = serializer.save(created_by=self.request.user)
        # La DA approuvée à l'origine du BC est désormais « convertie en commande ».
        if order.request_id and order.request.status == PurchaseRequest.Status.APPROUVEE:
            order.request.status = PurchaseRequest.Status.CONVERTIE
            order.request.save(update_fields=["status", "updated_at"])

    @action(detail=True, methods=["get"], url_path="reconciliation")
    def reconciliation(self, request, pk=None):
        """Rapprochement 3-way (RF-ERP-12) : commandé / reçu / facturé par ligne."""
        order = self.get_object()
        return Response({"code": order.code, "conformity": order.conformity})


class PurchaseOrderLineViewSet(_CommonViewSet):
    serializer_class = PurchaseOrderLineSerializer

    def get_queryset(self):
        qs = PurchaseOrderLine.objects.select_related("purchase_order", "article", "unit").all()
        purchase_order = self.request.query_params.get("purchase_order")
        if purchase_order:
            qs = qs.filter(purchase_order_id=purchase_order)
        return qs


class GoodsReceiptViewSet(_CommonViewSet):
    serializer_class = GoodsReceiptSerializer

    def get_queryset(self):
        qs = GoodsReceipt.objects.select_related("purchase_order", "received_by").all()
        purchase_order = self.request.query_params.get("purchase_order")
        if purchase_order:
            qs = qs.filter(purchase_order_id=purchase_order)
        return qs

    def perform_create(self, serializer):
        serializer.save(received_by=self.request.user)


class GoodsReceiptLineViewSet(_CommonViewSet):
    serializer_class = GoodsReceiptLineSerializer

    def get_queryset(self):
        qs = GoodsReceiptLine.objects.select_related("receipt", "purchase_order_line").all()
        receipt = self.request.query_params.get("receipt")
        if receipt:
            qs = qs.filter(receipt_id=receipt)
        return qs

    @idempotent
    def create(self, request, *args, **kwargs):  # réception magasin rejouable (hors-ligne)
        return super().create(request, *args, **kwargs)


class PurchaseInvoiceViewSet(_CommonViewSet):
    serializer_class = PurchaseInvoiceSerializer

    def get_queryset(self):
        qs = PurchaseInvoice.objects.select_related("purchase_order", "supplier", "currency").all()
        purchase_order = self.request.query_params.get("purchase_order")
        if purchase_order:
            qs = qs.filter(purchase_order_id=purchase_order)
        return qs


class PurchaseInvoiceLineViewSet(_CommonViewSet):
    serializer_class = PurchaseInvoiceLineSerializer

    def get_queryset(self):
        qs = PurchaseInvoiceLine.objects.select_related("invoice", "purchase_order_line").all()
        invoice = self.request.query_params.get("invoice")
        if invoice:
            qs = qs.filter(invoice_id=invoice)
        return qs