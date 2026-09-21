from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Account, AnalyticAxis, Annexe, Currency, Partner, UnitOfMeasure

User = get_user_model()


class AnnexeSeedTests(APITestCase):
    """Seed des 270 annexes du MANUEL (ch.10, §10.4)."""

    def test_seed_creates_270_with_expected_totals(self):
        call_command("seed_annexes")

        self.assertEqual(Annexe.objects.count(), 270)
        # Totaux par nature.
        self.assertEqual(Annexe.objects.filter(kind="F").count(), 108)
        self.assertEqual(Annexe.objects.filter(kind="R").count(), 56)
        self.assertEqual(Annexe.objects.filter(kind="M").count(), 55)
        self.assertEqual(Annexe.objects.filter(kind="TS").count(), 51)
        # Totaux par domaine.
        self.assertEqual(Annexe.objects.filter(domain="ADM").count(), 35)
        self.assertEqual(Annexe.objects.filter(domain="FIN").count(), 35)
        self.assertEqual(Annexe.objects.filter(domain="TEC").count(), 54)
        self.assertEqual(Annexe.objects.filter(domain="COM").count(), 32)
        self.assertEqual(Annexe.objects.filter(domain="RH").count(), 42)
        self.assertEqual(Annexe.objects.filter(domain="JUR").count(), 30)
        self.assertEqual(Annexe.objects.filter(domain="HSE").count(), 42)

    def test_seed_is_idempotent(self):
        call_command("seed_annexes")
        call_command("seed_annexes")
        self.assertEqual(Annexe.objects.count(), 270)

    def test_known_manual_labels(self):
        call_command("seed_annexes")
        self.assertEqual(
            Annexe.objects.get(code="ANN-F-ADM-001").label, "Formulaire administratif"
        )
        self.assertEqual(
            Annexe.objects.get(code="ANN-R-ADM-001").label, "Registre administratif"
        )
        self.assertEqual(
            Annexe.objects.get(code="ANN-TS-ADM-001").label,
            "Tableau de suivi administratif",
        )
        self.assertEqual(
            Annexe.objects.get(code="ANN-F-TEC-001").label, "Formulaire technique"
        )


class AnnexeAPITests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@etls.local", password="MotDePasse#2026",
            role=User.Role.ADMIN, is_staff=True,
        )
        self.chef = User.objects.create_user(
            email="chef@etls.local", password="MotDePasse#2026",
            role=User.Role.CHEF_SERVICE,
        )
        Annexe.objects.create(code="ANN-F-ADM-001", label="F ADM", kind="F", domain="ADM")
        Annexe.objects.create(code="ANN-R-FIN-001", label="R FIN", kind="R", domain="FIN")
        Annexe.objects.create(code="ANN-R-FIN-002", label="R FIN 002", kind="R", domain="FIN")

    def test_list_requires_auth(self):
        resp = self.client.get("/api/referentiels/annexes/")
        self.assertIn(
            resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        )

    def test_list_and_filter(self):
        self.client.force_authenticate(self.chef)
        resp = self.client.get("/api/referentiels/annexes/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 3)

        resp = self.client.get("/api/referentiels/annexes/?kind=R")
        self.assertEqual(resp.data["count"], 2)

        resp = self.client.get("/api/referentiels/annexes/?domain=FIN&kind=R")
        self.assertEqual(resp.data["count"], 2)

    def test_non_admin_cannot_create(self):
        self.client.force_authenticate(self.chef)
        resp = self.client.post(
            "/api/referentiels/annexes/",
            {"code": "ANN-M-ADM-001", "label": "Modèle", "kind": "M", "domain": "ADM"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_create(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/referentiels/annexes/",
            {"code": "ANN-M-ADM-001", "label": "Modèle administratif", "kind": "M", "domain": "ADM"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Annexe.objects.filter(code="ANN-M-ADM-001").count(), 1)


class SeedReferentielsTests(APITestCase):
    """Noyau partagé : devises, unités, plan SYSCOHADA, axes, tiers GR (incr.14)."""

    def test_seed_creates_core_data(self):
        call_command("seed_referentiels")

        self.assertEqual(Currency.objects.count(), 3)
        self.assertEqual(UnitOfMeasure.objects.count(), 11)
        self.assertEqual(Account.objects.count(), 36)
        self.assertEqual(AnalyticAxis.objects.count(), 4)

        xaf = Currency.objects.get(code="XAF")
        self.assertEqual(xaf.symbol, "FCFA")
        self.assertEqual(xaf.decimals, 0)

        # Fil rouge GLOBAL RENTAL : compte 618 + tiers intra-groupe.
        self.assertEqual(Account.objects.get(code="618000").account_class, 6)
        self.assertTrue(Partner.objects.get(code="GR-0001").is_global_rental)

    def test_seed_is_idempotent(self):
        call_command("seed_referentiels")
        call_command("seed_referentiels")
        self.assertEqual(Account.objects.count(), 36)
        self.assertEqual(Currency.objects.count(), 3)
        self.assertEqual(Partner.objects.count(), 1)


class ReferentielAPITests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@etls.local", password="MotDePasse#2026",
            role=User.Role.ADMIN, is_staff=True,
        )
        self.chef = User.objects.create_user(
            email="chef@etls.local", password="MotDePasse#2026",
            role=User.Role.CHEF_SERVICE,
        )
        self.xaf = Currency.objects.create(code="XAF", label="Franc CFA", symbol="FCFA")
        Account.objects.create(
            code="411000", label="Clients", account_class=4,
            account_type=Account.AccountType.ASSET,
        )
        Account.objects.create(
            code="601000", label="Achats", account_class=6,
            account_type=Account.AccountType.EXPENSE,
        )
        Partner.objects.create(
            code="CLI-001", name="Client A", kind=Partner.Kind.CLIENT, currency=self.xaf
        )
        Partner.objects.create(
            code="GR-0001", name="GLOBAL RENTAL", kind=Partner.Kind.BOTH,
            is_global_rental=True,
        )

    def test_list_requires_auth(self):
        resp = self.client.get("/api/referentiels/currencies/")
        self.assertIn(
            resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        )

    def test_filter_accounts_by_class(self):
        self.client.force_authenticate(self.chef)
        resp = self.client.get("/api/referentiels/accounts/?account_class=4")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["code"], "411000")

    def test_non_admin_cannot_create_account(self):
        self.client.force_authenticate(self.chef)
        resp = self.client.post(
            "/api/referentiels/accounts/",
            {"code": "701000", "label": "Ventes", "account_class": 7, "account_type": "income"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_create_partner(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/referentiels/partners/",
            {"code": "FOU-001", "name": "Fournisseur B", "kind": "fournisseur"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_filter_partners_by_kind(self):
        self.client.force_authenticate(self.chef)
        resp = self.client.get("/api/referentiels/partners/?kind=client")
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["code"], "CLI-001")

    def test_articles_filter_by_type(self):
        self.client.force_authenticate(self.chef)
        self.client.post(
            "/api/referentiels/articles/",
            {"code": "ART-001", "label": "Tôle", "article_type": "matiere", "is_stockable": True},
            format="json",
        )
        # création admin requise : on repasse en admin
        self.client.force_authenticate(self.admin)
        self.client.post(
            "/api/referentiels/articles/",
            {"code": "ART-002", "label": "Soudure", "article_type": "service"},
            format="json",
        )
        self.client.force_authenticate(self.chef)
        resp = self.client.get("/api/referentiels/articles/?article_type=service")
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["code"], "ART-002")
