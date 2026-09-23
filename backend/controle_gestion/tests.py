"""Tests M11 — Module Contrôle de gestion (RF-ERP-A0…A4)."""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APITestCase

from accounting_kernel.models import AccountMove, AccountMoveLine, FiscalYear, Journal, Period
from accounting_kernel.services import period_for_date, post_move
from referentiels.models import Account, AnalyticAccount, AnalyticAxis
from users.models import User

from .models import Budget, BudgetLigne, BudgetRevision, ClotureGestion
from .services import compute_clotures_stats, compute_marges, compute_variance

User = get_user_model()

BASE = "/api/controle-gestion/"


def _auth(client, email):
    r = client.post(
        "/api/users/token/", {"email": email, "password": "Etls#Demo2026"}, format="json"
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")


class BaseGestionTest(APITestCase):
    def setUp(self):
        call_command("seed_accounting", year=2026)
        self.admin = User.objects.create_user(
            email="admin@etls.local", password="Etls#Demo2026",
            role=User.Role.ADMIN, first_name="Admin", is_staff=True,
        )
        self.finance = User.objects.create_user(
            email="finance@etls.local", password="Etls#Demo2026",
            role=User.Role.FINANCE, first_name="Finance",
        )
        self.comptable = User.objects.create_user(
            email="compta@etls.local", password="Etls#Demo2026",
            role=User.Role.COMPTABLE, first_name="Compta",
        )
        self.logistique = User.objects.create_user(
            email="logi@etls.local", password="Etls#Demo2026",
            role=User.Role.LOGISTIQUE, first_name="Logi",
        )
        self._make_accounts()
        self._make_analytics()

    def _make_accounts(self):
        accounts = {
            "701000": (7, Account.AccountType.INCOME, "Ventes produits"),
            "601000": (6, Account.AccountType.EXPENSE, "Achats consommables"),
            "618000": (6, Account.AccountType.EXPENSE, "Refacturations GR"),
            "512000": (5, Account.AccountType.ASSET, "Banques"),
        }
        for code, (cls, atype, label) in accounts.items():
            Account.objects.get_or_create(
                code=code,
                defaults=dict(label=label, account_class=cls, account_type=atype),
            )

    def _make_analytics(self):
        self.axis_cc, _ = AnalyticAxis.objects.get_or_create(
            code="AX-CC", defaults={"label": "Centre de coût", "axis_type": AnalyticAxis.AxisType.CENTRE_COUT}
        )
        self.axis_proj, _ = AnalyticAxis.objects.get_or_create(
            code="AX-PROJ", defaults={"label": "Projet / affaire", "axis_type": AnalyticAxis.AxisType.PROJET}
        )
        self.analytic_cc, _ = AnalyticAccount.objects.get_or_create(
            axis=self.axis_cc, code="CC-TOLERIE",
            defaults={"label": "Centre Tôlerie"},
        )
        self.analytic_aff, _ = AnalyticAccount.objects.get_or_create(
            axis=self.axis_proj, code="AFF-PIPE-001",
            defaults={"label": "Affaire Maintenance pipelines"},
        )

    def _post_produit(self, montant="5000000.00", analytic=None, ref="BUD2026E"):
        journal = Journal.objects.get(code="VTE")
        period = Period.objects.get(number=1, fiscal_year__year=2026)
        move = AccountMove.objects.create(
            journal=journal, period=period, date=date(2026, 1, 15),
            reference=ref, label="Vente F", status=AccountMove.Status.DRAFT,
        )
        AccountMoveLine.objects.create(
            move=move, account=Account.objects.get(code="701000"),
            credit=Decimal(montant), order=1, analytic_account=analytic,
        )
        AccountMoveLine.objects.create(
            move=move, account=Account.objects.get(code="512000"),
            debit=Decimal(montant), order=2,
        )
        return post_move(move, user=self.admin)

    def _post_charge(self, montant="1200000.00", analytic=None, ref="RSC2026E"):
        journal = Journal.objects.get(code="BQ")
        period = Period.objects.get(number=1, fiscal_year__year=2026)
        move = AccountMove.objects.create(
            journal=journal, period=period, date=date(2026, 1, 20),
            reference=ref, label="Achat", status=AccountMove.Status.DRAFT,
        )
        AccountMoveLine.objects.create(
            move=move, account=Account.objects.get(code="601000"),
            debit=Decimal(montant), order=1, analytic_account=analytic,
        )
        AccountMoveLine.objects.create(
            move=move, account=Account.objects.get(code="512000"),
            credit=Decimal(montant), order=2,
        )
        return post_move(move, user=self.admin)

    def _post_charge_gr(self, montant="300000.00", analytic=None, ref="GR2026E"):
        journal = Journal.objects.get(code="BQ")
        period = Period.objects.get(number=1, fiscal_year__year=2026)
        move = AccountMove.objects.create(
            journal=journal, period=period, date=date(2026, 1, 22),
            reference=ref, label="Refacturation GR", status=AccountMove.Status.DRAFT,
        )
        AccountMoveLine.objects.create(
            move=move, account=Account.objects.get(code="618000"),
            debit=Decimal(montant), order=1, analytic_account=analytic,
        )
        AccountMoveLine.objects.create(
            move=move, account=Account.objects.get(code="512000"),
            credit=Decimal(montant), order=2,
        )
        return post_move(move, user=self.admin)

    def _budget(self, type_budget=Budget.TypeBudget.CHARGE, **kw):
        return Budget.objects.create(
            label="Budget test",
            type_budget=type_budget,
            fiscal_year=self._fy,
            axis=self.axis_cc,
            analytic=self.analytic_cc,
            montant=kw.pop("montant", Decimal("15000000")),
            **kw,
        )

    @property
    def _fy(self):
        return FiscalYear.objects.get(year=2026)


class CrudBudgetTests(BaseGestionTest):
    def test_creer_budget_puislignes(self):
        _auth(self.client, "finance@etls.local")
        resp = self.client.post(
            f"{BASE}budgets/",
            {
                "label": "Budget charges Tôlerie",
                "type_budget": Budget.TypeBudget.CHARGE,
                "fiscal_year": self._fy.pk,
                "axis": self.axis_cc.pk,
                "analytic": self.analytic_cc.pk,
                "montant": "15000000.00",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertTrue(resp.data["code"].startswith("BUD"))
        self.assertEqual(resp.data["statut"], Budget.Statut.BROUILLON)

        budget_id = resp.data["id"]
        period = Period.objects.get(number=1, fiscal_year__year=2026)
        line = self.client.post(
            f"{BASE}budget-lignes/",
            {"budget": budget_id, "period": period.pk, "montant": "1250000.00"},
            format="json",
        )
        self.assertEqual(line.status_code, status.HTTP_201_CREATED, line.data)
        dup = self.client.post(
            f"{BASE}budget-lignes/",
            {"budget": budget_id, "period": period.pk, "montant": "1250000.00"},
            format="json",
        )
        self.assertEqual(dup.status_code, status.HTTP_400_BAD_REQUEST)

    def test_ecriture_reservee_au_cercle_financier(self):
        _auth(self.client, "logi@etls.local")
        resp = self.client.post(
            f"{BASE}budgets/",
            {"label": "X", "type_budget": "charge", "fiscal_year": self._fy.pk, "montant": "1000.00"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        # Lecture : autorisée mais montants masqués (RF-59).
        resp = self.client.get(f"{BASE}budgets/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        budget = self._budget()
        resp = self.client.get(f"{BASE}budgets/{budget.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNone(resp.data["montant"])
        self.assertFalse(resp.data["has_amount_access"])

    def test_montant_visible_cercle_financial(self):
        _auth(self.client, "compta@etls.local")
        budget = self._budget()
        resp = self.client.get(f"{BASE}budgets/{budget.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(resp.data["montant"]), Decimal("15000000"))

    def test_approuver_puis_cloturer(self):
        _auth(self.client, "admin@etls.local")
        budget = self._budget()
        r1 = self.client.post(f"{BASE}budgets/{budget.pk}/approuver/")
        self.assertEqual(r1.status_code, status.HTTP_200_OK, r1.data)
        budget.refresh_from_db()
        self.assertEqual(budget.statut, Budget.Statut.APPROUVE)
        r2 = self.client.post(f"{BASE}budgets/{budget.pk}/cloturer/")
        self.assertEqual(r2.status_code, status.HTTP_200_OK, r2.data)
        budget.refresh_from_db()
        self.assertEqual(budget.statut, Budget.Statut.CLOTURE)


class RevisionTests(BaseGestionTest):
    def test_creation_revision_et_application(self):
        _auth(self.client, "finance@etls.local")
        budget = self._budget(montant=Decimal("15000000"))
        r = self.client.post(
            f"{BASE}revisions/",
            {
                "budget": budget.pk,
                "nouveau_montant": "16500000.00",
                "date_revision": "2026-04-15",
                "commentaire": "R1 hausse consommables",
            },
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        self.assertEqual(r.data["numero"], 1)
        self.assertEqual(r.data["ancien_montant"], "15000000.00")
        self.assertEqual(r.data["statut"], BudgetRevision.Statut.BROUILLON)

        _auth(self.client, "admin@etls.local")
        r2 = self.client.post(f"{BASE}revisions/{r.data['id']}/appliquer/")
        self.assertEqual(r2.status_code, status.HTTP_200_OK, r2.data)
        budget.refresh_from_db()
        self.assertEqual(budget.montant, Decimal("16500000"))
        rev = BudgetRevision.objects.get(pk=r.data["id"])
        self.assertEqual(rev.statut, BudgetRevision.Statut.APPLIQUEE)

    def test_max_quatre_revisions(self):
        _auth(self.client, "finance@etls.local")
        budget = self._budget()
        for _ in range(4):
            r = self.client.post(
                f"{BASE}revisions/",
                {"budget": budget.pk, "nouveau_montant": "16000000.00", "date_revision": "2026-05-01"},
                format="json",
            )
            self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        r5 = self.client.post(
            f"{BASE}revisions/",
            {"budget": budget.pk, "nouveau_montant": "17000000.00", "date_revision": "2026-06-01"},
            format="json",
        )
        self.assertEqual(r5.status_code, status.HTTP_400_BAD_REQUEST)


class MargesTests(BaseGestionTest):
    def test_compute_marges_avec_618_iso_et_axes(self):
        self._post_produit(analytic=self.analytic_aff)
        self._post_charge(analytic=self.analytic_cc)
        self._post_charge_gr(analytic=self.analytic_cc)
        result = compute_marges(self._fy.pk)
        rows = {r["analytic"]: r for r in result["rows"]}
        self.assertIn(self.analytic_aff.pk, rows)
        self.assertEqual(rows[self.analytic_aff.pk]["produits"], Decimal("5000000"))
        self.assertEqual(rows[self.analytic_aff.pk]["charges"], Decimal("0"))
        self.assertEqual(rows[self.analytic_aff.pk]["marge"], Decimal("5000000"))
        self.assertIn(self.analytic_cc.pk, rows)
        # Charge 601 : 1 200 000 ; coût GR 618 isolé (A4) — 300 000 non inclus.
        self.assertEqual(rows[self.analytic_cc.pk]["charges"], Decimal("1200000"))
        self.assertEqual(result["totals"]["cout_gr"], Decimal("300000"))
        self.assertEqual(result["totals"]["marge_hors_gr"], Decimal("5000000") - Decimal("1200000") - Decimal("300000"))

    def test_filtre_par_axe(self):
        self._post_produit(analytic=self.analytic_aff)
        self._post_charge(analytic=self.analytic_cc)
        result = compute_marges(self._fy.pk, axis=self.axis_proj.pk)
        rows = {r["analytic"]: r for r in result["rows"]}
        self.assertIn(self.analytic_aff.pk, rows)
        self.assertNotIn(self.analytic_cc.pk, rows)

    def test_api_marges(self):
        _auth(self.client, "finance@etls.local")
        self._post_produit(analytic=self.analytic_aff)
        resp = self.client.get(f"{BASE}marges/?fiscal_year={self._fy.pk}")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["totals"]["produits"], Decimal("5000000"))

    def test_marges_rejette_params_non_numeriques(self):
        _auth(self.client, "finance@etls.local")
        resp = self.client.get(f"{BASE}marges/?fiscal_year=abc")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        resp = self.client.get(f"{BASE}marges/?fiscal_year={self._fy.pk}&axis=^")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        resp = self.client.get(f"{BASE}marges/?fiscal_year={self._fy.pk}&analytic=aP")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class VarianceTests(BaseGestionTest):
    def test_variance_budget_charges(self):
        budget = self._budget()
        p1 = Period.objects.get(number=1, fiscal_year__year=2026)
        BudgetLigne.objects.create(budget=budget, period=p1, montant=Decimal("1250000"))
        self._post_charge(analytic=self.analytic_cc, montant="1200000.00")
        result = compute_variance(budget)
        self.assertEqual(result["totals"]["montant"], Decimal("1250000"))
        self.assertEqual(result["totals"]["realise"], Decimal("1200000"))
        self.assertEqual(result["totals"]["ecart"], Decimal("50000"))
        self.assertLess(Decimal(result["totals"]["taux"]), 1)

    def test_variance_realise_zero(self):
        budget = self._budget()
        p1 = Period.objects.get(number=1, fiscal_year__year=2026)
        BudgetLigne.objects.create(budget=budget, period=p1, montant=Decimal("1250000"))
        result = compute_variance(budget)
        self.assertEqual(result["totals"]["realise"], Decimal("0"))
        self.assertTrue(result["totals"]["sous_activite"])


class ClotureGestionTests(BaseGestionTest):
    def test_realiser_cloture_conforme_j4(self):
        _auth(self.client, "finance@etls.local")
        p1 = Period.objects.get(number=1, fiscal_year__year=2026)
        c = ClotureGestion.objects.create(period=p1)
        self.assertEqual(c.statut, ClotureGestion.Statut.EN_ATTENTE)
        _auth(self.client, "admin@etls.local")
        r = self.client.post(
            f"{BASE}clotures/{c.pk}/realiser/",
            {"date_cloture": p1.end_date + timedelta(days=2)},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        c.refresh_from_db()
        self.assertEqual(c.statut, ClotureGestion.Statut.REALISEE)
        self.assertEqual(c.jours_ecoulement, 2)
        self.assertTrue(c.conforme_j4)

    def test_cloture_hors_j4_non_conforme(self):
        _auth(self.client, "admin@etls.local")
        p1 = Period.objects.get(number=1, fiscal_year__year=2026)
        c = ClotureGestion.objects.create(
            period=p1, date_cloture=p1.end_date + timedelta(days=6),
            statut=ClotureGestion.Statut.REALISEE,
        )
        self.assertEqual(c.jours_ecoulement, 6)
        self.assertFalse(c.conforme_j4)

    def test_stats_clotures(self):
        p1 = Period.objects.get(number=1, fiscal_year__year=2026)
        p2 = Period.objects.get(number=2, fiscal_year__year=2026)
        ClotureGestion.objects.create(
            period=p1, date_cloture=p1.end_date + timedelta(days=2),
            statut=ClotureGestion.Statut.REALISEE,
        )
        ClotureGestion.objects.create(period=p2)
        stats = compute_clotures_stats(self._fy.pk)
        self.assertEqual(stats["periodes"], 12)
        self.assertEqual(stats["realisees"], 1)
        self.assertEqual(stats["conformes_j4"], 1)
        self.assertEqual(stats["en_attente"], 11)

    def test_retention_rejette_fiscal_year_non_numerique(self):
        _auth(self.client, "finance@etls.local")
        resp = self.client.get(f"{BASE}clotures/stats/?fiscal_year=abc")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)