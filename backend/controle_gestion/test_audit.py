"""Audit métier M11 (2026-10-16) — régressions des écarts trouvés.

G1 : marges / écarts calculés en NET (avoirs, extournes) et non en débit seul / crédit seul.
G3 : agrégation en base (pas de N+1 par ligne d'écriture).
G8 : budget clôturé : plus de révision.
"""

from datetime import date
from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework import status

from accounting_kernel.models import AccountMove, AccountMoveLine, Journal, Period
from accounting_kernel.services import post_move, reverse_move
from referentiels.models import Account

from .models import Budget, BudgetLigne
from .services import compute_marges, compute_variance
from .tests import BASE, BaseGestionTest, _auth


class NetCalculationTests(BaseGestionTest):
    def _avoir_fournisseur(self, montant, analytic):
        """Avoir : crédit du compte de charge 601000 (réduit la charge), débit banque."""
        period = Period.objects.get(number=1, fiscal_year__year=2026)
        move = AccountMove.objects.create(
            journal=Journal.objects.get(code="BQ"), period=period, date=date(2026, 1, 25),
            reference="AVOIR", label="Avoir fournisseur",
        )
        AccountMoveLine.objects.create(
            move=move, account=Account.objects.get(code="601000"),
            credit=Decimal(montant), order=1, analytic_account=analytic,
        )
        AccountMoveLine.objects.create(
            move=move, account=Account.objects.get(code="512000"), debit=Decimal(montant), order=2,
        )
        return post_move(move, user=self.admin)

    def test_marges_net_des_avoirs(self):
        self._post_produit("5000000.00", analytic=self.analytic_cc)
        self._post_charge("1200000.00", analytic=self.analytic_cc)
        self._avoir_fournisseur("300000.00", self.analytic_cc)
        res = compute_marges(self._fy.pk)
        self.assertEqual(res["totals"]["charges"], Decimal("900000.00"))
        self.assertEqual(res["totals"]["marge"], Decimal("4100000.00"))

    def test_marges_nulles_apres_extourne_complete(self):
        move = self._post_charge("1200000.00", analytic=self.analytic_cc)
        reverse_move(move, user=self.admin)
        res = compute_marges(self._fy.pk)
        self.assertEqual(res["totals"]["charges"], Decimal("0"))

    def test_variance_net_des_avoirs(self):
        budget = self._budget()
        BudgetLigne.objects.create(
            budget=budget, period=Period.objects.get(number=1, fiscal_year__year=2026),
            montant=Decimal("2000000"),
        )
        self._post_charge("1200000.00", analytic=self.analytic_cc)
        self._avoir_fournisseur("300000.00", self.analytic_cc)
        res = compute_variance(budget)
        self.assertEqual(res["totals"]["realise"], Decimal("900000.00"))

    def test_cout_gr_net_des_avoirs(self):
        self._post_charge_gr("300000.00", analytic=self.analytic_cc)
        move = self._post_charge_gr("100000.00", analytic=self.analytic_cc, ref="GR2")
        reverse_move(move, user=self.admin)
        res = compute_marges(self._fy.pk)
        self.assertEqual(res["totals"]["cout_gr"], Decimal("300000.00"))


class PerformanceTests(BaseGestionTest):
    def test_variance_sans_n_plus_1(self):
        budget = self._budget()
        BudgetLigne.objects.create(
            budget=budget, period=Period.objects.get(number=1, fiscal_year__year=2026),
            montant=Decimal("2000000"),
        )
        for i in range(25):
            self._post_charge("1000.00", analytic=self.analytic_cc, ref=f"R{i}")
        with CaptureQueriesContext(connection) as ctx:
            compute_variance(budget)
        self.assertLess(len(ctx), 12, f"{len(ctx)} requêtes pour 25 écritures (N+1 ?)")

    def test_marges_sans_n_plus_1(self):
        for i in range(25):
            self._post_charge("1000.00", analytic=self.analytic_cc, ref=f"R{i}")
            self._post_produit("2000.00", analytic=self.analytic_cc, ref=f"P{i}")
        with CaptureQueriesContext(connection) as ctx:
            compute_marges(self._fy.pk)
        self.assertLess(len(ctx), 12, f"{len(ctx)} requêtes pour 50 écritures (N+1 ?)")


class RevisionBudgetClotureTests(BaseGestionTest):
    def test_revision_refusee_sur_budget_cloture(self):
        budget = self._budget(statut=Budget.Statut.CLOTURE)
        _auth(self.client, "finance@etls.local")
        resp = self.client.post(
            f"{BASE}revisions/",
            {"budget": str(budget.pk), "date_revision": "2026-06-01", "nouveau_montant": "1.00"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)


class ListeBudgetsSansNPlus1Tests(BaseGestionTest):
    def test_liste_budgets_requetes_constantes(self):
        periods = list(Period.objects.filter(fiscal_year__year=2026).order_by("number"))
        for i in range(4):
            b = self._budget(montant=Decimal("1200000") + i)
            for per in periods:
                BudgetLigne.objects.create(budget=b, period=per, montant=Decimal("100000"))
        _auth(self.client, "finance@etls.local")
        with CaptureQueriesContext(connection) as ctx:
            r = self.client.get(f"{BASE}budgets/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data["results"]), 4)
        # 4 budgets x 12 lignes : sans prefetch/select_related c'était ~27 requêtes par budget
        self.assertLess(len(ctx), 20, f"{len(ctx)} requêtes pour 4 budgets de 12 lignes (N+1 ?)")
