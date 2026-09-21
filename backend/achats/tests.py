from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

from referentiels.models import Article, Currency, Partner, UnitOfMeasure

from .models import (
    GoodsReceipt,
    GoodsReceiptLine,
    PurchaseInvoice,
    PurchaseInvoiceLine,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseRequest,
)

User = get_user_model()


def make_references():
    currency, _ = Currency.objects.get_or_create(code="XAF")
    unit, _ = UnitOfMeasure.objects.get_or_create(code="U")
    article = Article.objects.create(
        code="ART-1", label="Ressort", article_type="matiere", unit=unit
    )
    return currency, unit, article


class SeedAchatsTests(APITestCase):
    def test_seed_is_idempotent(self):
        call_command("seed_achats_demo")
        call_command("seed_achats_demo")
        self.assertEqual(PurchaseRequest.objects.count(), 1)
        self.assertEqual(PurchaseOrder.objects.count(), 2)
        self.assertEqual(GoodsReceipt.objects.count(), 1)
        self.assertEqual(PurchaseInvoice.objects.count(), 1)


class SequenceTests(APITestCase):
    def test_numbering_by_kind(self):
        da = PurchaseRequest.objects.create(title="DA1")
        bc = PurchaseOrder.objects.create(supplier=None)
        bl = GoodsReceipt.objects.create(purchase_order=bc)
        rc = PurchaseInvoice.objects.create(purchase_order=bc)
        self.assertEqual(da.code, "DA00001")
        self.assertEqual(bc.code, "BC00001")
        self.assertEqual(bl.code, "BL00001")
        self.assertEqual(rc.code, "RC00001")
        self.assertEqual(PurchaseRequest.objects.create(title="DA2").code, "DA00002")


class PurchaseOrderBehaviourTests(APITestCase):
    def setUp(self):
        self.currency, self.unit, self.article = make_references()
        self.order = PurchaseOrder.objects.create(order_date=timezone.localdate())

    def test_order_total_computed_from_lines(self):
        for label, qty, price in (("A", 2, 500), ("B", 3, 1_000)):
            PurchaseOrderLine.objects.create(
                purchase_order=self.order, label=label, quantity=qty,
                unit_price=price, unit=self.unit,
            )
        self.assertEqual(float(self.order.total), 4_000)

    def test_global_rental_requires_flagged_supplier(self):
        fournisseur = Partner.objects.create(
            code="F-1", name="Fournisseur", kind="fournisseur"
        )
        order = PurchaseOrder.objects.create(
            supplier=fournisseur, is_global_rental=True, order_date=timezone.localdate()
        )
        with self.assertRaises(ValidationError):
            order.full_clean()

    def test_receipt_updates_qty_and_flips_order_status(self):
        line = PurchaseOrderLine.objects.create(
            purchase_order=self.order, label="A", quantity=10,
            unit_price=50, unit=self.unit,
        )
        self.order.status = PurchaseOrder.Status.CONFIRMEE
        self.order.save()

        receipt = GoodsReceipt.objects.create(purchase_order=self.order)

        GoodsReceiptLine.objects.create(receipt=receipt, purchase_order_line=line, quantity=4)
        self.order.refresh_from_db()
        line.refresh_from_db()
        self.assertEqual(float(line.received_qty), 4)
        self.assertEqual(self.order.status, PurchaseOrder.Status.PARTIELLE)

        GoodsReceiptLine.objects.create(receipt=receipt, purchase_order_line=line, quantity=6)
        self.order.refresh_from_db()
        line.refresh_from_db()
        self.assertEqual(float(line.received_qty), 10)
        self.assertEqual(self.order.status, PurchaseOrder.Status.CLOTUREE)

    def test_receipt_line_delete_rolls_back_qty(self):
        line = PurchaseOrderLine.objects.create(
            purchase_order=self.order, label="A", quantity=10,
            unit_price=50, unit=self.unit,
        )
        receipt = GoodsReceipt.objects.create(purchase_order=self.order)
        gl = GoodsReceiptLine.objects.create(receipt=receipt, purchase_order_line=line, quantity=3)
        gl.delete()
        line.refresh_from_db()
        self.assertEqual(float(line.received_qty), 0)

    def test_invoice_updates_invoiced_qty_and_three_way(self):
        line = PurchaseOrderLine.objects.create(
            purchase_order=self.order, label="A", quantity=10,
            unit_price=50, unit=self.unit,
        )
        receipt = GoodsReceipt.objects.create(purchase_order=self.order)
        GoodsReceiptLine.objects.create(receipt=receipt, purchase_order_line=line, quantity=10)

        invoice = PurchaseInvoice.objects.create(purchase_order=self.order)
        PurchaseInvoiceLine.objects.create(
            invoice=invoice, purchase_order_line=line, quantity=8, unit_price=50,
        )
        line.refresh_from_db()
        self.assertEqual(float(line.invoiced_qty), 8)
        self.assertEqual(float(invoice.total), 400)
        conformity = self.order.conformity[0]
        self.assertEqual(float(conformity["received"]), 10)
        self.assertEqual(float(conformity["invoiced"]), 8)
        self.assertIs(conformity["ok"], True)


class AchatsAPITests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@etls.local", password="MotDePasse#2026",
            role=User.Role.ADMIN, is_staff=True,
        )
        self.logistique = User.objects.create_user(
            email="logistique@etls.local", password="MotDePasse#2026",
            role=User.Role.LOGISTIQUE,
        )
        self.chef = User.objects.create_user(
            email="chef@etls.local", password="MotDePasse#2026",
            role=User.Role.CHEF_SERVICE,
        )
        self.currency, self.unit, _ = make_references()
        self.order = PurchaseOrder.objects.create(order_date=timezone.localdate(), status="confirmee")
        PurchaseOrderLine.objects.create(
            purchase_order=self.order, label="A", quantity=2,
            unit_price=500, unit=self.unit,
        )

    def test_list_requires_auth(self):
        resp = self.client.get("/api/achats/orders/")
        self.assertIn(
            resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        )

    def test_authenticated_can_read_filters(self):
        self.client.force_authenticate(self.chef)
        resp = self.client.get("/api/achats/orders/?status=confirmee")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)

    def test_chef_cannot_create_da(self):
        self.client.force_authenticate(self.chef)
        resp = self.client.post("/api/achats/requests/", {"title": "DA"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_logistique_can_create_da(self):
        self.client.force_authenticate(self.logistique)
        resp = self.client.post(
            "/api/achats/requests/",
            {"title": "DA magasin 2026", "department": "Logistique"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["code"], "DA00001")
        self.assertEqual(str(resp.data["requester"]), str(self.logistique.id))

    def test_amount_masked_for_chef_service(self):
        self.client.force_authenticate(self.chef)
        resp = self.client.get(f"/api/achats/orders/{self.order.id}/")
        self.assertIsNone(resp.data["total"])

    def test_amount_visible_for_logistique(self):
        self.client.force_authenticate(self.logistique)
        resp = self.client.get(f"/api/achats/orders/{self.order.id}/")
        self.assertEqual(resp.data["total"], "1000.00")
        self.assertIn("conformity", resp.data)

    def test_reconciliation_action(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.get(f"/api/achats/orders/{self.order.id}/reconciliation/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["conformity"]), 1)
        self.assertEqual(float(resp.data["conformity"][0]["ordered"]), 2)