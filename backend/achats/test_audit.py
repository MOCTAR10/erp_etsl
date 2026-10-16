"""Audit métier M2 (2026-10-16) — régressions des écarts trouvés.

A3 : modifier la quantité d'une ligne de BL / de facture ajuste le BC (delta), sans dérive.
A1 : rapprochement 3-way : facturé <= reçu <= commandé, anomalies listées.
A4 : le statut du BC suit les réceptions dans les deux sens.
"""

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from referentiels.models import Article, Currency, UnitOfMeasure

from .models import (
    GoodsReceipt,
    GoodsReceiptLine,
    PurchaseInvoice,
    PurchaseInvoiceLine,
    PurchaseOrder,
    PurchaseOrderLine,
)


class Base(TestCase):
    def setUp(self):
        Currency.objects.get_or_create(code="XAF")
        self.unit, _ = UnitOfMeasure.objects.get_or_create(code="U")
        self.order = PurchaseOrder.objects.create(
            order_date=timezone.localdate(), status=PurchaseOrder.Status.CONFIRMEE
        )
        self.line = PurchaseOrderLine.objects.create(
            purchase_order=self.order, label="A", quantity=10, unit_price=50, unit=self.unit
        )
        self.receipt = GoodsReceipt.objects.create(purchase_order=self.order)

    def reload(self):
        self.line.refresh_from_db()
        self.order.refresh_from_db()


class QuantityUpdateTests(Base):
    def test_modifier_une_ligne_de_bl_ajuste_la_quantite_recue(self):
        gl = GoodsReceiptLine.objects.create(
            receipt=self.receipt, purchase_order_line=self.line, quantity=4
        )
        gl.quantity = Decimal("6")
        gl.save()
        self.reload()
        self.assertEqual(self.line.received_qty, Decimal("6"))
        gl.quantity = Decimal("2")
        gl.save()
        self.reload()
        self.assertEqual(self.line.received_qty, Decimal("2"))

    def test_modifier_une_ligne_de_facture_ajuste_la_quantite_facturee(self):
        invoice = PurchaseInvoice.objects.create(purchase_order=self.order)
        il = PurchaseInvoiceLine.objects.create(
            invoice=invoice, purchase_order_line=self.line, quantity=3, unit_price=50
        )
        il.quantity = Decimal("7")
        il.save()
        self.reload()
        self.assertEqual(self.line.invoiced_qty, Decimal("7"))
        self.assertEqual(il.price_total, Decimal("350"))


class ThreeWayTests(Base):
    def test_facture_superieure_au_recu_est_une_anomalie(self):
        GoodsReceiptLine.objects.create(
            receipt=self.receipt, purchase_order_line=self.line, quantity=4
        )
        invoice = PurchaseInvoice.objects.create(purchase_order=self.order)
        PurchaseInvoiceLine.objects.create(
            invoice=invoice, purchase_order_line=self.line, quantity=8, unit_price=50
        )
        self.order.refresh_from_db()
        row = self.order.conformity[0]
        self.assertFalse(row["ok"])
        self.assertIn("facture", " ".join(row["anomalies"]).lower())

    def test_surreception_est_une_anomalie(self):
        GoodsReceiptLine.objects.create(
            receipt=self.receipt, purchase_order_line=self.line, quantity=12
        )
        self.order.refresh_from_db()
        row = self.order.conformity[0]
        self.assertFalse(row["ok"])
        self.assertTrue(row["anomalies"])

    def test_cas_nominal_conforme(self):
        GoodsReceiptLine.objects.create(
            receipt=self.receipt, purchase_order_line=self.line, quantity=10
        )
        invoice = PurchaseInvoice.objects.create(purchase_order=self.order)
        PurchaseInvoiceLine.objects.create(
            invoice=invoice, purchase_order_line=self.line, quantity=10, unit_price=50
        )
        self.order.refresh_from_db()
        row = self.order.conformity[0]
        self.assertTrue(row["ok"])
        self.assertEqual(row["anomalies"], [])

    def test_ecart_de_prix_facture_vs_commande_signale(self):
        GoodsReceiptLine.objects.create(
            receipt=self.receipt, purchase_order_line=self.line, quantity=10
        )
        invoice = PurchaseInvoice.objects.create(purchase_order=self.order)
        PurchaseInvoiceLine.objects.create(
            invoice=invoice, purchase_order_line=self.line, quantity=10, unit_price=65
        )
        self.order.refresh_from_db()
        row = self.order.conformity[0]
        self.assertFalse(row["ok"])
        self.assertIn("prix", " ".join(row["anomalies"]).lower())


class OrderStatusTests(Base):
    def test_statut_redescend_quand_la_reception_est_supprimee(self):
        gl = GoodsReceiptLine.objects.create(
            receipt=self.receipt, purchase_order_line=self.line, quantity=4
        )
        self.reload()
        self.assertEqual(self.order.status, PurchaseOrder.Status.PARTIELLE)
        gl.delete()
        self.reload()
        self.assertEqual(self.order.status, PurchaseOrder.Status.CONFIRMEE)

    def test_bc_cloture_automatiquement_rouvert_si_reception_retiree(self):
        gl = GoodsReceiptLine.objects.create(
            receipt=self.receipt, purchase_order_line=self.line, quantity=10
        )
        self.reload()
        self.assertEqual(self.order.status, PurchaseOrder.Status.CLOTUREE)
        gl.delete()
        self.reload()
        self.assertEqual(self.order.status, PurchaseOrder.Status.CONFIRMEE)
