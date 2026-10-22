"""Lot a9 (correctifs v0.4) : visa CG du budget M11 par le contrôleur de gestion, montants M1 / M3 du chargé
d'affaires, sites de rattachement des comptes démo (restriction par site toujours désactivée par défaut)."""

from datetime import date
from decimal import Decimal

from django.core.management import call_command
from rest_framework.test import APITestCase

from users.models import User


def user(email, role):
    return User.objects.create_user(email=email, password="x-Correctif-2026", role=role, first_name=email[:3])


class RolesA9Tests(APITestCase):
    def test_controleur_de_gestion_prepare_et_vise_le_budget(self):
        from accounting_kernel.models import FiscalYear
        from controle_gestion.models import Budget
        from controle_gestion.services import GESTION_WRITE_ROLES
        from referentiels.models import AnalyticAccount, AnalyticAxis

        self.assertIn(User.Role.CONTROLEUR_GESTION, GESTION_WRITE_ROLES)
        an = date.today().year
        fy = FiscalYear.objects.create(year=an, start_date=date(an, 1, 1), end_date=date(an, 12, 31))
        axe = AnalyticAxis.objects.create(label="Centres", axis_type="centre_cout")
        cg, daf = user("cg@t.ga", User.Role.CONTROLEUR_GESTION), user("daf@t.ga", User.Role.FINANCE)
        self.client.force_authenticate(cg)
        r = self.client.post("/api/controle-gestion/budgets/", {
            "label": "Atelier", "type_budget": "charge", "fiscal_year": fy.pk, "axis": axe.pk,
            "analytic": AnalyticAccount.objects.create(axis=axe, code="C10", label="Atelier").pk, "montant": "5000000",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        url = f"/api/controle-gestion/budgets/{r.data['id']}/approuver/"
        self.client.force_authenticate(daf)
        self.assertEqual(self.client.post(url, {"visa": "daf"}, format="json").status_code, 200)
        self.client.force_authenticate(cg)
        self.assertEqual(self.client.post(url, {"visa": "cg"}, format="json").status_code, 200)
        budget = Budget.objects.get(pk=r.data["id"])
        self.assertEqual((budget.statut, budget.visa_cg_par, budget.montant), ("approuve", cg, Decimal("5000000")))

    def test_charge_d_affaires_voit_les_montants_m1_et_m3(self):
        from commercial.services import COMM_AMOUNT_ROLES
        from operations.services import OPERATION_AMOUNT_ROLES

        self.assertIn(User.Role.CHARGE_AFFAIRES, COMM_AMOUNT_ROLES)
        self.assertIn(User.Role.CHARGE_AFFAIRES, OPERATION_AMOUNT_ROLES)


class SitesComptesDemoTests(APITestCase):
    def test_sites_poses_idempotents_sans_ecraser(self):
        from referentiels.models import Site

        call_command("seed_demo_users")
        sites = dict(User.objects.filter(site_etsl__isnull=False).values_list("email", "site_etsl__code"))
        self.assertEqual(sites["atelier@etls.local"], "POG-ATELIER")
        self.assertEqual(sites["logistique@etls.local"], "POG-DEPOT")
        self.assertNotIn("admin@etls.local", sites)
        autre = Site.objects.get(code="LBV-BASE")
        User.objects.filter(email="atelier@etls.local").update(site_etsl=autre)
        call_command("seed_demo_users")
        self.assertEqual(User.objects.get(email="atelier@etls.local").site_etsl, autre)
