"""Lot 11 (2026-10-17) — rapprochement 3-way obligatoire avant comptabilisation (CDC M2 §5.8 / §5.11).

Avant : le statut « rapprochée » d'une facture fournisseur se posait par PATCH et un paiement lié à une facture
non rapprochée se comptabilisait. Après : action `rapprocher` (3-way BR/BC/facture sans anomalie) et paiement
non comptabilisable tant que sa facture n'est pas rapprochée.
"""

from datetime import date
from decimal import Decimal

from rest_framework.test import APITestCase

from comptabilite.models import CompteBancaire, Paiement
from referentiels.models import Account
from users.models import User

from .models import GoodsReceipt, GoodsReceiptLine, PurchaseInvoice, PurchaseInvoiceLine, PurchaseOrder, PurchaseOrderLine


class ThreeWayTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(email="admin@etls.ga", password="x-Audit-2026", role=User.Role.ADMIN, is_staff=True)
        self.client.force_authenticate(self.admin)
        self.order = PurchaseOrder.objects.create(status=PurchaseOrder.Status.CONFIRMEE)
        self.ligne = PurchaseOrderLine.objects.create(purchase_order=self.order, label="Tube", quantity=10, unit_price=Decimal("100"))

    def recevoir(self, qty):
        br = GoodsReceipt.objects.create(purchase_order=self.order)
        GoodsReceiptLine.objects.create(receipt=br, purchase_order_line=self.ligne, quantity=qty)

    def facture(self, qty, prix="100"):
        inv = PurchaseInvoice.objects.create(purchase_order=self.order)
        PurchaseInvoiceLine.objects.create(invoice=inv, purchase_order_line=self.ligne, quantity=qty, unit_price=Decimal(prix))
        return inv

    def test_statut_facture_non_modifiable_par_patch(self):
        inv = self.facture(5)
        self.client.patch(f"/api/achats/invoices/{inv.pk}/", {"status": "rapprochee"}, format="json")
        inv.refresh_from_db()
        self.assertEqual(inv.status, PurchaseInvoice.Status.EN_ATTENTE)

    def test_facture_sans_reception_non_rapprochable(self):
        inv = self.facture(5)
        r = self.client.post(f"/api/achats/invoices/{inv.pk}/rapprocher/")
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("reçu", str(r.data))

    def test_ecart_de_prix_non_rapprochable(self):
        self.recevoir(10)
        self.assertEqual(self.client.post(f"/api/achats/invoices/{self.facture(10, '120').pk}/rapprocher/").status_code, 400)

    def test_3_way_conforme_rapproche(self):
        self.recevoir(10)
        inv = self.facture(10)
        self.assertEqual(self.client.post(f"/api/achats/invoices/{inv.pk}/rapprocher/").status_code, 200)
        inv.refresh_from_db()
        self.assertEqual(inv.status, PurchaseInvoice.Status.RAPPROCHEE)

    def test_paiement_d_une_facture_non_rapprochee_non_comptabilisable(self):
        compte, _ = Account.objects.get_or_create(code="512000", defaults=dict(label="Banque", account_class=5, account_type=Account.AccountType.ASSET))
        banque = CompteBancaire.objects.create(label="BGFI", banque="BGFI", compte_comptable=compte)
        p = Paiement.objects.create(sens="sortie", mode="virement", montant=Decimal("1000"), compte_bancaire=banque,
                                    facture=self.facture(10), date=date.today())
        r = self.client.post(f"/api/comptabilite/paiements/{p.pk}/comptabiliser/")
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("3-way", str(r.data))
