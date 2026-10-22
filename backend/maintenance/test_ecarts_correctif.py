"""Lot correctif — une seule charge 618 pour la maintenance d'un équipement GLOBAL RENTAL.

Règle : la facture d'achat GLOBAL RENTAL (M2, Dr 618 / Cr 401100) porte la charge. Un OT GR rattaché à un BC GR ne
passe pas d'OD 618 à la clôture ; rattaché après coup, son OD est extournée. OT GR + sa facture GR ⇒ un seul 618.
"""

from datetime import date
from decimal import Decimal

from django.core.management import call_command
from django.db.models import Sum
from django.utils import timezone
from rest_framework.test import APITestCase

from accounting_kernel.models import AccountMove, AccountMoveLine
from achats.models import GoodsReceipt, GoodsReceiptLine, PurchaseInvoice, PurchaseInvoiceLine, PurchaseOrder, PurchaseOrderLine
from comptabilite.models import TauxTva
from referentiels.models import Account, Partner
from users.models import User

from .models import Actif, OrdreTravail

COMPTES = {
    "401000": (4, Account.AccountType.LIABILITY), "401100": (4, Account.AccountType.LIABILITY),
    "445000": (4, Account.AccountType.ASSET), "601000": (6, Account.AccountType.EXPENSE),
    "618000": (6, Account.AccountType.EXPENSE), "624000": (6, Account.AccountType.EXPENSE),
    "661000": (6, Account.AccountType.EXPENSE), "603300": (6, Account.AccountType.EXPENSE),
}


class Double618Tests(APITestCase):
    def setUp(self):
        call_command("seed_accounting", year=timezone.localdate().year)
        for code, (cls, typ) in COMPTES.items():
            Account.objects.get_or_create(code=code, defaults=dict(label=code, account_class=cls, account_type=typ))
        TauxTva.objects.create(code="TVA18", label="TVA 18", taux=Decimal("18.00"),
                               compte_deductible=Account.objects.get(code="445000"), is_default=True)
        self.gr = Partner.objects.create(code="GR", name="GLOBAL RENTAL", kind=Partner.Kind.FOURNISSEUR,
                                         is_global_rental=True)
        self.maint = User.objects.create_user(email="maint@etls.ga", password="x-Audit-2026", role=User.Role.MAINTENANCE)
        self.finance = User.objects.create_user(email="fin@etls.ga", password="x-Audit-2026", role=User.Role.FINANCE)
        self.grue = Actif.objects.create(designation="Grue GR 50 t", categorie="levage", is_global_rental=True)
        self.ot = OrdreTravail.objects.create(
            actif=self.grue, description="Réparation vérin", statut=OrdreTravail.Statut.TERMINE,
            heures_mo=Decimal("4"), tarif_horaire=Decimal("10000"), cout_pieces=Decimal("0"), date_fin=timezone.now())
        self.bc = PurchaseOrder.objects.create(status=PurchaseOrder.Status.CONFIRMEE, supplier=self.gr,
                                               is_global_rental=True)

    def as_(self, u):
        self.client.force_authenticate(u)
        return self.client

    def cloturer(self):
        r = self.as_(self.maint).post(f"/api/maintenance/ordres/{self.ot.pk}/cloturer/")
        self.assertEqual(r.status_code, 200, r.content)
        self.ot.refresh_from_db()

    def lier(self, bc=None):
        return self.as_(self.maint).post(f"/api/maintenance/ordres/{self.ot.pk}/lier-bc-gr/",
                                         {"bc": str((bc or self.bc).pk)}, format="json")

    def facture_gr(self, montant="40000"):
        ligne = PurchaseOrderLine.objects.create(purchase_order=self.bc, label="Prestation maintenance GR",
                                                 quantity=1, unit_price=Decimal(montant))
        br = GoodsReceipt.objects.create(purchase_order=self.bc)
        GoodsReceiptLine.objects.create(receipt=br, purchase_order_line=ligne, quantity=1)
        inv = PurchaseInvoice.objects.create(purchase_order=self.bc, supplier=self.gr, invoice_date=date.today())
        PurchaseInvoiceLine.objects.create(invoice=inv, purchase_order_line=ligne, quantity=1, unit_price=Decimal(montant))
        self.as_(self.finance)
        self.assertEqual(self.client.post(f"/api/achats/invoices/{inv.pk}/rapprocher/").status_code, 200)
        r = self.client.post(f"/api/achats/invoices/{inv.pk}/comptabiliser/")
        self.assertEqual(r.status_code, 200, r.content)

    def charge_618(self):
        lignes = AccountMoveLine.objects.filter(account__code="618000").exclude(move__status=AccountMove.Status.DRAFT)
        agg = lignes.aggregate(d=Sum("debit"), c=Sum("credit"))
        return (agg["d"] or 0) - (agg["c"] or 0)

    def test_sans_bc_l_ot_gr_passe_l_od_618(self):
        self.cloturer()
        self.assertIsNotNone(self.ot.ecriture)
        self.assertEqual(self.charge_618(), Decimal("40000.00"))

    def test_bc_lie_avant_cloture_une_seule_charge(self):
        self.assertEqual(self.lier().status_code, 200)
        self.cloturer()
        self.assertIsNone(self.ot.ecriture)
        self.assertIn("pas de double charge", self.ot.motif_ecriture)
        self.facture_gr()
        self.assertEqual(self.charge_618(), Decimal("40000.00"))

    def test_bc_lie_apres_cloture_od_extournee(self):
        self.cloturer()
        od = self.ot.ecriture
        self.facture_gr()
        self.assertEqual(self.charge_618(), Decimal("80000.00"))  # le double que le lot supprime
        r = self.lier()
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["bc_gr_code"], self.bc.code)
        self.assertEqual(r.data["ecriture_statut"], AccountMove.Status.REVERSED)
        od.refresh_from_db()
        self.assertEqual(od.status, AccountMove.Status.REVERSED)
        self.assertEqual(self.charge_618(), Decimal("40000.00"))
        self.assertIn("extournée", r.data["motif_ecriture"])
        # Un seul rattachement.
        self.assertEqual(self.lier().status_code, 400)

    def test_garde_fous(self):
        poste = Actif.objects.create(designation="Poste MIG", categorie="machine")
        ot = OrdreTravail.objects.create(actif=poste, description="x", statut=OrdreTravail.Statut.TERMINE)
        r = self.as_(self.maint).post(f"/api/maintenance/ordres/{ot.pk}/lier-bc-gr/", {"bc": str(self.bc.pk)})
        self.assertEqual(r.status_code, 400)
        autre = PurchaseOrder.objects.create(status=PurchaseOrder.Status.CONFIRMEE, supplier=self.gr)
        self.assertEqual(self.lier(autre).status_code, 400)
        self.assertEqual(self.as_(self.maint).post(f"/api/maintenance/ordres/{self.ot.pk}/lier-bc-gr/", {"bc": "x"}).status_code, 400)
        codes = [b["code"] for b in self.as_(self.maint).get("/api/maintenance/ordres/bc-gr/").data]
        self.assertEqual(codes, [self.bc.code])
