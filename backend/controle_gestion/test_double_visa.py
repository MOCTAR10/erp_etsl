"""Lot 11 (2026-10-17) — versions budgétaires scellées, double visa DAF + CG (CDC M11 §4.4 / §4.11).

Une version budgétaire (V0 ou révision R1-R4) n'entre en vigueur qu'avec deux visas — DAF et Contrôle de gestion —
apposés par deux personnes distinctes ; une fois approuvé, le budget est scellé (modifiable par révision seulement).
"""

from datetime import date
from decimal import Decimal

from rest_framework.test import APITestCase

from accounting_kernel.models import FiscalYear
from referentiels.models import AnalyticAccount, AnalyticAxis
from users.models import User

from .models import Budget, BudgetRevision

BASE = "/api/controle-gestion/"


def user(email, role, **kw):
    return User.objects.create_user(email=email, password="x-Audit-2026", role=role, first_name=email[:3], **kw)


class DoubleVisaTests(APITestCase):
    def setUp(self):
        self.daf = user("daf@etls.ga", User.Role.FINANCE)
        self.cg = user("cg@etls.ga", User.Role.DGA)
        fy = FiscalYear.objects.create(year=date.today().year, start_date=date(date.today().year, 1, 1),
                                       end_date=date(date.today().year, 12, 31))
        axe = AnalyticAxis.objects.create(label="Centres", axis_type="centre_cout")
        self.budget = Budget.objects.create(label="Atelier", type_budget="charge", fiscal_year=fy, axis=axe,
                                            analytic=AnalyticAccount.objects.create(axis=axe, code="C10", label="Atelier"),
                                            montant=Decimal("5000000"))

    def viser(self, who, url, visa):
        self.client.force_authenticate(who)
        return self.client.post(url, {"visa": visa}, format="json")

    def test_un_seul_visa_n_approuve_pas(self):
        url = f"{BASE}budgets/{self.budget.pk}/approuver/"
        self.assertEqual(self.viser(self.daf, url, "daf").status_code, 200)
        self.budget.refresh_from_db()
        self.assertEqual(self.budget.statut, Budget.Statut.BROUILLON)
        self.assertEqual(self.budget.visa_daf_par, self.daf)

    def test_deux_visas_distincts_approuvent(self):
        url = f"{BASE}budgets/{self.budget.pk}/approuver/"
        self.viser(self.daf, url, "daf")
        self.assertEqual(self.viser(self.cg, url, "cg").status_code, 200)
        self.budget.refresh_from_db()
        self.assertEqual(self.budget.statut, Budget.Statut.APPROUVE)

    def test_meme_personne_ne_donne_pas_les_deux_visas(self):
        url = f"{BASE}budgets/{self.budget.pk}/approuver/"
        self.viser(self.daf, url, "daf")
        r = self.viser(self.daf, url, "cg")
        self.assertEqual(r.status_code, 400, r.content)
        self.budget.refresh_from_db()
        self.assertEqual(self.budget.statut, Budget.Statut.BROUILLON)

    def test_visa_obligatoire_et_non_redonne(self):
        url = f"{BASE}budgets/{self.budget.pk}/approuver/"
        self.assertEqual(self.viser(self.daf, url, "").status_code, 400)
        self.viser(self.daf, url, "daf")
        self.assertEqual(self.viser(self.cg, url, "daf").status_code, 400)  # visa DAF déjà posé

    def test_budget_approuve_scelle(self):
        url = f"{BASE}budgets/{self.budget.pk}/approuver/"
        self.viser(self.daf, url, "daf")
        self.viser(self.cg, url, "cg")
        self.client.force_authenticate(self.daf)
        r = self.client.patch(f"{BASE}budgets/{self.budget.pk}/", {"montant": "9000000"}, format="json")
        self.assertEqual(r.status_code, 400, r.content)
        self.budget.refresh_from_db()
        self.assertEqual(self.budget.montant, Decimal("5000000"))

    def test_revision_appliquee_apres_double_visa(self):
        self.budget.statut = Budget.Statut.APPROUVE
        self.budget.save()
        rev = BudgetRevision.objects.create(budget=self.budget, numero=1, date_revision=date.today(),
                                            ancien_montant=Decimal("5000000"), nouveau_montant=Decimal("5500000"))
        url = f"{BASE}revisions/{rev.pk}/appliquer/"
        self.viser(self.daf, url, "daf")
        self.budget.refresh_from_db()
        self.assertEqual(self.budget.montant, Decimal("5000000"))  # un visa : pas encore appliquée
        self.assertEqual(self.viser(self.cg, url, "cg").status_code, 200)
        self.budget.refresh_from_db()
        self.assertEqual(self.budget.montant, Decimal("5500000"))

    def test_lignes_et_suppression_scellees_apres_approbation(self):
        from accounting_kernel.models import Period

        self.client.force_authenticate(self.daf)
        periode = Period.objects.filter(fiscal_year=self.budget.fiscal_year).first() or Period.objects.create(
            fiscal_year=self.budget.fiscal_year, number=1,
            start_date=self.budget.fiscal_year.start_date, end_date=date(self.budget.fiscal_year.year, 1, 31))
        # Brouillon : la ligne se crée, se modifie, se supprime.
        r = self.client.post(f"{BASE}budget-lignes/", {"budget": str(self.budget.pk), "period": periode.pk, "montant": "100"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        ligne = r.json()["id"]
        self.assertEqual(self.client.patch(f"{BASE}budget-lignes/{ligne}/", {"montant": "150"}, format="json").status_code, 200)
        # Approuvé : plus de création, modification ni suppression de ligne, ni suppression du budget.
        url = f"{BASE}budgets/{self.budget.pk}/approuver/"
        self.viser(self.daf, url, "daf")
        self.viser(self.cg, url, "cg")
        self.client.force_authenticate(self.daf)
        self.assertEqual(self.client.patch(f"{BASE}budget-lignes/{ligne}/", {"montant": "999"}, format="json").status_code, 400)
        self.assertEqual(self.client.delete(f"{BASE}budget-lignes/{ligne}/").status_code, 400)
        r = self.client.post(f"{BASE}budget-lignes/", {"budget": str(self.budget.pk), "period": periode.pk, "montant": "1"}, format="json")
        self.assertEqual(r.status_code, 400, r.content)
        self.assertEqual(self.client.delete(f"{BASE}budgets/{self.budget.pk}/").status_code, 400)
        self.assertTrue(Budget.objects.filter(pk=self.budget.pk).exists())

    def test_budget_brouillon_supprimable(self):
        self.client.force_authenticate(self.daf)
        self.assertEqual(self.client.delete(f"{BASE}budgets/{self.budget.pk}/").status_code, 204)
