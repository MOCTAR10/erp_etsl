"""Lot 11 (2026-10-17) — contrôle budgétaire des achats et agrément fournisseur (CDC ETSL-CDC-001).

Couche D §2.4 / M2 RG-M2.08 : budget consommé ≥ 90 % → alerte ; > 100 % → blocage de la DA ;
> 110 % → aucun engagement (confirmation de BC) ; escalade DG avec visa exceptionnel tracé.
M2 §5.8 : aucun BC émis vers un fournisseur non agréé qualité/HSE.
"""

from datetime import date, timedelta
from decimal import Decimal

from rest_framework.test import APITestCase

from accounting_kernel.models import FiscalYear
from controle_gestion.models import Budget
from referentiels.models import AnalyticAccount, AnalyticAxis, Partner
from users.models import User
from workflow.models import Notification

from .models import PurchaseOrder, PurchaseOrderLine, PurchaseRequest, PurchaseRequestLine


def user(email, role):
    return User.objects.create_user(email=email, password="x-Audit-2026", role=role, first_name=email[:3])


class ControleBudgetaireBase(APITestCase):
    def setUp(self):
        today = date.today()
        self.logistique = user("log@etls.ga", User.Role.LOGISTIQUE)
        self.finance = user("fin@etls.ga", User.Role.FINANCE)
        self.pdg = user("dg@etls.ga", User.Role.PDG)
        fy = FiscalYear.objects.create(year=today.year, start_date=date(today.year, 1, 1), end_date=date(today.year, 12, 31))
        axe = AnalyticAxis.objects.create(label="Affaires", axis_type="projet")
        self.compte = AnalyticAccount.objects.create(axis=axe, code="AFF-01", label="Pipeline Line A")
        Budget.objects.create(label="Achats AFF-01", type_budget="charge", fiscal_year=fy, axis=axe,
                              analytic=self.compte, montant=Decimal("1000000"), statut=Budget.Statut.APPROUVE)
        self.fournisseur = Partner.objects.create(
            code="F-AGR", name="Fournisseur agréé", kind="fournisseur",
            agree_qualite_jusqu=today + timedelta(days=200), agree_hse_jusqu=today + timedelta(days=200),
        )

    def bc(self, montant, fournisseur=None, statut=PurchaseOrder.Status.BROUILLON):
        order = PurchaseOrder.objects.create(supplier=fournisseur or self.fournisseur, analytic=self.compte, status=statut)
        PurchaseOrderLine.objects.create(purchase_order=order, label="Tube", quantity=1, unit_price=Decimal(montant))
        return order

    def da(self, montant):
        da = PurchaseRequest.objects.create(title="Consommables", requester=self.logistique, analytic=self.compte)
        PurchaseRequestLine.objects.create(request=da, label="Disques", quantity=1, estimated_price=Decimal(montant))
        return da

    def post(self, who, url, data=None):
        self.client.force_authenticate(who)
        return self.client.post(url, data or {}, format="json")


class BlocageDaTests(ControleBudgetaireBase):
    def test_da_qui_depasse_100_pourcent_est_bloquee(self):
        self.bc("700000", statut=PurchaseOrder.Status.CONFIRMEE)
        r = self.post(self.logistique, f"/api/achats/requests/{self.da('400000').pk}/soumettre/")
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("budget", str(r.data).lower())

    def test_da_dans_le_budget_passe_et_alerte_a_90_pourcent(self):
        self.bc("700000", statut=PurchaseOrder.Status.CONFIRMEE)
        r = self.post(self.logistique, f"/api/achats/requests/{self.da('250000').pk}/soumettre/")
        self.assertEqual(r.status_code, 200, r.content)  # 95 % : pas bloqué…
        self.assertTrue(Notification.objects.filter(user=self.finance, subject__icontains="budget").exists())  # …mais alerte

    def test_visa_dg_leve_le_blocage_et_est_trace(self):
        self.bc("700000", statut=PurchaseOrder.Status.CONFIRMEE)
        da = self.da("400000")
        self.assertEqual(self.post(self.finance, f"/api/achats/requests/{da.pk}/visa-dg/", {"motif": "Urgence"}).status_code, 403)
        self.assertEqual(self.post(self.pdg, f"/api/achats/requests/{da.pk}/visa-dg/").status_code, 400)  # motif obligatoire
        self.assertEqual(self.post(self.pdg, f"/api/achats/requests/{da.pk}/visa-dg/", {"motif": "Arrêt client"}).status_code, 200)
        self.assertEqual(self.post(self.logistique, f"/api/achats/requests/{da.pk}/soumettre/").status_code, 200)
        da.refresh_from_db()
        self.assertEqual(da.visa_dg_par, self.pdg)


class EngagementBcTests(ControleBudgetaireBase):
    def test_bc_au_dela_de_110_pourcent_non_confirmable(self):
        self.bc("1000000", statut=PurchaseOrder.Status.CONFIRMEE)
        order = self.bc("150000")
        r = self.post(self.finance, f"/api/achats/orders/{order.pk}/confirmer/")
        self.assertEqual(r.status_code, 400, r.content)
        order.refresh_from_db()
        self.assertEqual(order.status, PurchaseOrder.Status.BROUILLON)

    def test_bc_entre_100_et_110_pourcent_confirmable(self):
        self.bc("1000000", statut=PurchaseOrder.Status.CONFIRMEE)
        self.assertEqual(self.post(self.finance, f"/api/achats/orders/{self.bc('50000').pk}/confirmer/").status_code, 200)

    def test_statut_du_bc_non_modifiable_par_patch(self):
        order = self.bc("1000")
        self.client.force_authenticate(self.finance)
        self.client.patch(f"/api/achats/orders/{order.pk}/", {"status": "confirmee"}, format="json")
        order.refresh_from_db()
        self.assertEqual(order.status, PurchaseOrder.Status.BROUILLON)


class AgrementFournisseurTests(ControleBudgetaireBase):
    def test_bc_vers_fournisseur_non_agree_refuse(self):
        inconnu = Partner.objects.create(code="F-NA", name="Non agréé", kind="fournisseur")
        r = self.post(self.finance, f"/api/achats/orders/{self.bc('1000', fournisseur=inconnu).pk}/confirmer/")
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("agr", str(r.data).lower())

    def test_agrement_expire_refuse(self):
        expire = Partner.objects.create(code="F-EX", name="Expiré", kind="fournisseur",
                                        agree_qualite_jusqu=date.today() - timedelta(days=1),
                                        agree_hse_jusqu=date.today() + timedelta(days=100))
        self.assertEqual(self.post(self.finance, f"/api/achats/orders/{self.bc('1000', fournisseur=expire).pk}/confirmer/").status_code, 400)

    def test_bc_vide_non_confirmable(self):
        order = PurchaseOrder.objects.create(supplier=self.fournisseur, analytic=self.compte)
        self.assertEqual(self.post(self.finance, f"/api/achats/orders/{order.pk}/confirmer/").status_code, 400)
