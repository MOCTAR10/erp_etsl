"""Lot A M2 (2026-10-18) — comptabilisation de la facture fournisseur et imputation 618 des BC GLOBAL RENTAL.

Avant : aucune écriture n'était générée pour une facture fournisseur (seul le paiement l'était, avec une case
`imputation_618` cochée à la main). Après : action `comptabiliser` (Dr charge HT + Dr TVA déductible / Cr 401),
charge au 618000 et dette au 401100 pour un BC GR, facture scellée, paiement qui solde le 401.
"""

from datetime import date
from decimal import Decimal

from django.core.management import call_command
from rest_framework.test import APITestCase

from accounting_kernel.models import AccountMove
from comptabilite.models import CompteBancaire, Paiement, TauxTva
from referentiels.models import Account, Article, Partner
from users.models import User

from .models import GoodsReceipt, GoodsReceiptLine, PurchaseInvoice, PurchaseInvoiceLine, PurchaseOrder, PurchaseOrderLine

COMPTES = {
    "512000": (5, Account.AccountType.ASSET),
    "401000": (4, Account.AccountType.LIABILITY),
    "401100": (4, Account.AccountType.LIABILITY),
    "445000": (4, Account.AccountType.ASSET),
    "601000": (6, Account.AccountType.EXPENSE),
    "602000": (6, Account.AccountType.EXPENSE),
    "618000": (6, Account.AccountType.EXPENSE),
}


class FactureComptaTests(APITestCase):
    def setUp(self):
        call_command("seed_accounting", year=2026)
        for code, (cls, typ) in COMPTES.items():
            Account.objects.get_or_create(code=code, defaults=dict(label=code, account_class=cls, account_type=typ))
        self.tva = TauxTva.objects.create(
            code="TVA18", label="TVA 18", taux=Decimal("18.00"),
            compte_collecte=None, compte_deductible=Account.objects.get(code="445000"), is_default=True,
        )
        self.finance = User.objects.create_user(email="fin@etls.ga", password="x-Audit-2026", role=User.Role.FINANCE)
        self.logistique = User.objects.create_user(email="log@etls.ga", password="x-Audit-2026", role=User.Role.LOGISTIQUE)
        self.client.force_authenticate(self.finance)

    def _facture(self, gr=False, article=None, rapprochee=True):
        fournisseur = Partner.objects.create(
            code="F-GR" if gr else "F-X", name="Fournisseur", kind=Partner.Kind.FOURNISSEUR, is_global_rental=gr
        )
        order = PurchaseOrder.objects.create(
            status=PurchaseOrder.Status.CONFIRMEE, supplier=fournisseur, is_global_rental=gr
        )
        ligne = PurchaseOrderLine.objects.create(
            purchase_order=order, label="Tube", quantity=10, unit_price=Decimal("100"), article=article
        )
        br = GoodsReceipt.objects.create(purchase_order=order)
        GoodsReceiptLine.objects.create(receipt=br, purchase_order_line=ligne, quantity=10)
        inv = PurchaseInvoice.objects.create(
            purchase_order=order, supplier=fournisseur, invoice_date=date(2026, 3, 10)
        )
        PurchaseInvoiceLine.objects.create(invoice=inv, purchase_order_line=ligne, quantity=10, unit_price=Decimal("100"))
        if rapprochee:
            self.assertEqual(self.client.post(f"/api/achats/invoices/{inv.pk}/rapprocher/").status_code, 200)
        inv.refresh_from_db()
        return inv

    def _comptabiliser(self, inv):
        return self.client.post(f"/api/achats/invoices/{inv.pk}/comptabiliser/")

    def _lignes(self, inv):
        inv.refresh_from_db()
        return {l.account.code: (l.debit, l.credit) for l in inv.move.lines.select_related("account")}

    def test_ecriture_charge_tva_fournisseur(self):
        inv = self._facture()
        r = self._comptabiliser(inv)
        self.assertEqual(r.status_code, 200, r.content)
        inv.refresh_from_db()
        self.assertEqual(inv.status, PurchaseInvoice.Status.COMPTABILISEE)
        self.assertEqual(inv.move.status, AccountMove.Status.POSTED)
        self.assertEqual(inv.move.journal.code, "ACH")
        self.assertEqual(
            self._lignes(inv),
            {"601000": (Decimal("1000.00"), 0), "445000": (Decimal("180.00"), 0), "401000": (0, Decimal("1180.00"))},
        )

    def test_article_porte_son_compte_de_charge(self):
        article = Article.objects.create(code="ART-M", label="Matière", account=Account.objects.get(code="602000"))
        inv = self._facture(article=article)
        self._comptabiliser(inv)
        self.assertIn("602000", self._lignes(inv))

    def test_bc_global_rental_impute_au_618_et_401100(self):
        inv = self._facture(gr=True)
        self.assertEqual(self._comptabiliser(inv).status_code, 200)
        lignes = self._lignes(inv)
        self.assertEqual(lignes["618000"][0], Decimal("1000.00"))
        self.assertEqual(lignes["401100"][1], Decimal("1180.00"))
        self.assertNotIn("601000", lignes)

    def test_facture_non_rapprochee_refusee(self):
        inv = self._facture(rapprochee=False)
        r = self._comptabiliser(inv)
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("rapproch", str(r.data))
        self.assertFalse(AccountMove.objects.filter(source="M2").exists())

    def test_double_comptabilisation_refusee(self):
        inv = self._facture()
        self.assertEqual(self._comptabiliser(inv).status_code, 200)
        self.assertEqual(self._comptabiliser(inv).status_code, 400)
        self.assertEqual(AccountMove.objects.filter(source="M2", source_ref=inv.code).count(), 1)

    def test_role_non_autorise(self):
        inv = self._facture()
        self.client.force_authenticate(self.logistique)
        self.assertEqual(self._comptabiliser(inv).status_code, 403)

    def test_lignes_scellees_apres_comptabilisation(self):
        inv = self._facture()
        self._comptabiliser(inv)
        ligne = inv.lines.first()
        r = self.client.patch(f"/api/achats/invoice-lines/{ligne.pk}/", {"unit_price": "1"}, format="json")
        self.assertEqual(r.status_code, 400, r.content)
        self.assertEqual(self.client.delete(f"/api/achats/invoice-lines/{ligne.pk}/").status_code, 400)

    def _paiement(self, inv, **kw):
        banque = CompteBancaire.objects.create(
            label="BGFI", banque="BGFI", compte_comptable=Account.objects.get(code="512000")
        )
        return Paiement.objects.create(
            sens="sortie", mode="virement", montant=Decimal("1180"), compte_bancaire=banque,
            facture=inv, tiers=inv.supplier, date=date(2026, 3, 20), **kw,
        )

    def test_paiement_solde_le_401_sans_double_charge(self):
        inv = self._facture()
        self._comptabiliser(inv)
        p = self._paiement(inv, imputation_618=True)  # la case manuelle ne doit pas recharger un compte de charge
        r = self.client.post(f"/api/comptabilite/paiements/{p.pk}/comptabiliser/")
        self.assertEqual(r.status_code, 200, r.content)
        p.refresh_from_db()
        lignes = {l.account.code: (l.debit, l.credit) for l in p.move.lines.select_related("account")}
        self.assertEqual(lignes, {"401000": (Decimal("1180.00"), 0), "512000": (0, Decimal("1180.00"))})

    def test_paiement_d_une_facture_rapprochee_non_comptabilisee_refuse(self):
        inv = self._facture()
        p = self._paiement(inv)
        r = self.client.post(f"/api/comptabilite/paiements/{p.pk}/comptabiliser/")
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("comptabilis", str(r.data))
