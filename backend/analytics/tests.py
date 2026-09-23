"""Tests Couche D — BI / décisionnel (RF-ERP-C0...C3)."""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from users.models import User

from .services import alertes_agregees, dashboard_direction, reporting_petrolier

User = get_user_model()

BASE = "/api/analytics/"


def _auth(client, email, password="Etls#Demo2026"):
    r = client.post("/api/users/token/", {"email": email, "password": password}, format="json")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")


class BaseAnalyticsTest(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@etls.local", password="Etls#Demo2026",
            role=User.Role.ADMIN, first_name="Admin", is_staff=True,
        )
        self.finance = User.objects.create_user(
            email="finance@etls.local", password="Etls#Demo2026",
            role=User.Role.FINANCE, first_name="Finance",
        )
        self.logistique = User.objects.create_user(
            email="logi@etls.local", password="Etls#Demo2026",
            role=User.Role.LOGISTIQUE, first_name="Logi",
        )
        self.pdg = User.objects.create_user(
            email="pdg@etls.local", password="Etls#Demo2026",
            role=User.Role.PDG, first_name="PDG",
        )

    def _seed_kpis(self):
        from commercial.models import Affaire, ClientProfile, Opportunity
        from achats.models import PurchaseOrder, PurchaseOrderLine
        from hse.models import Incident
        from maintenance.models import Actif
        from referentiels.models import Partner

        client = Partner.objects.create(
            code="CLI-X", name="Client pétrolier", kind=Partner.Kind.CLIENT,
        )
        profil = ClientProfile.objects.create(
            partner=client, segment="petrolier",
        )
        Opportunity.objects.create(
            code="OPP-X", subject="Opportunité X", client=profil,
            stage="gagne", amount=Decimal("15000000"), is_active=True,
        )
        Affaire.objects.create(
            code="AFF-X", title="Affaire X", client=profil,
            status=Affaire.Status.EN_COURS,
            contract_amount=Decimal("15000000"), margin=Decimal("3000000"),
        )
        bc = PurchaseOrder.objects.create(
            code="BC-00001", supplier=client, status=PurchaseOrder.Status.CONFIRMEE,
        )
        PurchaseOrderLine.objects.create(
            purchase_order=bc, label="Pièce", quantity=1,
            unit_price=Decimal("500000"),
        )
        Incident.objects.create(
            code="INC-00001", type_incident=Incident.TypeIncident.INCIDENT,
            gravite=Incident.Gravite.MINEURE, statut=Incident.Statut.EN_ENQUETE,
            date_evenement=timezone.now(),
        )
        Actif.objects.create(
            code="EQ-00001", designation="Nacelle", categorie=Actif.Categorie.ENGIN,
            statut=Actif.Statut.OPERATIONNEL,
        )


class DashboardDirectionTests(BaseAnalyticsTest):
    def test_authentification_requise(self):
        r = self.client.get(f"{BASE}dashboard/")
        self.assertIn(
            r.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        )

    def test_dashboard_admin(self):
        _auth(self.client, "admin@etls.local")
        r = self.client.get(f"{BASE}dashboard/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        data = r.json()
        for cle in ("documents", "workflow", "referentiels", "registres",
                    "commercial", "achats", "operations", "logistique",
                    "stocks", "qualite", "hse", "maintenance",
                    "rh_paie", "comptabilite", "controle_gestion", "juridique"):
            self.assertIn(cle, data)

    def test_montants_masques_hors_roles(self):
        from achats.models import PurchaseOrder, PurchaseOrderLine
        from referentiels.models import Partner

        fournisseur = Partner.objects.create(
            code="FOU-X", name="Fournisseur", kind=Partner.Kind.FOURNISSEUR,
        )
        bc = PurchaseOrder.objects.create(
            code="BC-00001", supplier=fournisseur, status=PurchaseOrder.Status.CONFIRMEE,
        )
        PurchaseOrderLine.objects.create(
            purchase_order=bc, label="Pièce", quantity=1, unit_price=Decimal("500000"),
        )
        _auth(self.client, "logi@etls.local")
        r = self.client.get(f"{BASE}dashboard/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        data = r.json()
        self.assertIsNone(data["achats"]["montant_bc"])
        self.assertIsNone(data["stocks"]["valorisation"])

    def test_montants_visibles_finance(self):
        from referentiels.models import Partner
        from achats.models import PurchaseOrder, PurchaseOrderLine

        fournisseur = Partner.objects.create(
            code="FOU-X", name="Fournisseur", kind=Partner.Kind.FOURNISSEUR,
        )
        bc = PurchaseOrder.objects.create(
            code="BC-00001", supplier=fournisseur, status=PurchaseOrder.Status.CONFIRMEE,
        )
        PurchaseOrderLine.objects.create(
            purchase_order=bc, label="Pièce", quantity=1, unit_price=Decimal("500000"),
        )
        _auth(self.client, "finance@etls.local")
        r = self.client.get(f"{BASE}dashboard/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.json()["achats"]["montant_bc"], 500000.0)

    def test_agregation_services(self):
        self._seed_kpis()
        data = dashboard_direction(self.admin)
        self.assertGreaterEqual(data["commercial"]["affaires_actives"], 1)
        self.assertGreaterEqual(data["achats"]["bc"], 1)
        self.assertGreaterEqual(data["maintenance"]["actifs"], 1)


class ReportingPetrolierTests(BaseAnalyticsTest):
    def test_authentification_requise(self):
        r = self.client.get(f"{BASE}petrolier/")
        self.assertIn(
            r.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        )

    def test_structure(self):
        _auth(self.client, "admin@etls.local")
        r = self.client.get(f"{BASE}petrolier/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        data = r.json()
        for cle in ("asmr", "hse", "qualite"):
            self.assertIn(cle, data)
        self.assertIn("taux_disponibilite", data["asmr"])

    def test_disponibilite(self):
        self._seed_kpis()
        data = reporting_petrolier(self.admin)
        self.assertGreaterEqual(data["asmr"]["equipements"], 1)
        self.assertIn("jours_sans_accident", data["hse"])


class AlertesAgregeesTests(BaseAnalyticsTest):
    def test_authentification_requise(self):
        r = self.client.get(f"{BASE}alertes/")
        self.assertIn(
            r.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        )

    def test_structure(self):
        _auth(self.client, "admin@etls.local")
        r = self.client.get(f"{BASE}alertes/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        data = r.json()
        for cle in ("documents", "juridique", "rh", "maintenance", "compteurs", "total"):
            self.assertIn(cle, data)
        for bande in ("expiree", "j30", "j60", "j90"):
            self.assertIn(bande, data["compteurs"])

    def test_agrege_rh_et_juridique(self):
        from juridique.models import Convention
        from rh_paie.models import ContratTravail, Employe
        from referentiels.models import Partner

        partenaire = Partner.objects.create(
            code="P-X", name="Partenaire", kind=Partner.Kind.FOURNISSEUR,
        )
        Convention.objects.create(
            type="maintenance", titre="Convention expirante",
            partenaire=partenaire, montant=Decimal("1000000"),
            date_debut=date(2026, 1, 1),
            date_fin=date.today() + timedelta(days=45),
            statut=Convention.Statut.SIGNE,
        )
        emp = Employe.objects.create(
            code="EMP-X", nom="Doe", prenom="John",
            statut=Employe.Statut.ACTIF,
        )
        ContratTravail.objects.create(
            code="CTR-X", employe=emp, type="cdd",
            date_debut=date.today() - timedelta(days=60),
            date_fin=date.today() + timedelta(days=20),
            statut=ContratTravail.Statut.ACTIF,
        )

        data = alertes_agregees()
        self.assertGreaterEqual(data["total"], 1)
        self.assertGreaterEqual(
            data["compteurs"]["j30"] + data["compteurs"]["j60"], 1
        )
        self.assertTrue(any(it["type"] == "contrat_rh" for it in data["rh"]))


class PermissionsTests(BaseAnalyticsTest):
    def test_lecture_tous_roles_authentifies(self):
        _auth(self.client, "logi@etls.local")
        for ep in ("dashboard/", "petrolier/", "alertes/"):
            r = self.client.get(f"{BASE}{ep}")
            self.assertEqual(r.status_code, status.HTTP_200_OK, ep)