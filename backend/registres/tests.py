from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APITestCase

from referentiels.models import Annexe

from .models import Registre, RegistreEntry

User = get_user_model()


class SeedRegistresTests(APITestCase):
    """Les 9 modules de registres (proposition §6.5)."""

    def test_seed_creates_nine_registres(self):
        call_command("seed_registres", year=2026)
        self.assertEqual(Registre.objects.filter(year=2026).count(), 9)
        self.assertEqual(
            set(Registre.objects.filter(year=2026).values_list("kind", flat=True)),
            {choice[0] for choice in Registre.Kind.choices},
        )

    def test_seed_is_idempotent(self):
        call_command("seed_registres", year=2026)
        call_command("seed_registres", year=2026)
        self.assertEqual(Registre.objects.filter(year=2026).count(), 9)

    def test_seed_links_known_annexe(self):
        Annexe.objects.create(
            code="ANN-R-ADM-001", label="Registre administratif", kind="R", domain="ADM"
        )
        call_command("seed_registres", year=2026)
        registre = Registre.objects.get(kind=Registre.Kind.COURRIER, year=2026)
        self.assertEqual(registre.annexe.code, "ANN-R-ADM-001")


class RegistreNumberingTests(APITestCase):
    def setUp(self):
        self.registre = Registre.objects.create(kind=Registre.Kind.COURRIER, year=2026)
        self.autre = Registre.objects.create(kind=Registre.Kind.STOCK_MAGASIN, year=2026)

    def test_numbering_is_continuous_per_registre(self):
        a1 = RegistreEntry.objects.create(registre=self.registre, data={"objet": "A"})
        a2 = RegistreEntry.objects.create(registre=self.registre, data={"objet": "B"})
        b1 = RegistreEntry.objects.create(registre=self.autre, data={"objet": "C"})
        self.assertEqual([a1.number, a2.number, b1.number], [1, 2, 1])


class RegistreAPITests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@etls.local", password="MotDePasse#2026",
            role=User.Role.ADMIN, is_staff=True,
        )
        self.chef = User.objects.create_user(
            email="chef@etls.local", password="MotDePasse#2026",
            role=User.Role.CHEF_SERVICE,
        )
        self.registre = Registre.objects.create(kind=Registre.Kind.COURRIER, year=2026)

    def test_list_requires_auth(self):
        resp = self.client.get("/api/registres/registres/")
        self.assertIn(
            resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        )

    def test_list_and_filter_by_kind(self):
        self.client.force_authenticate(self.chef)
        resp = self.client.get("/api/registres/registres/?kind=courrier")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)
        resp = self.client.get("/api/registres/registres/?kind=stock_magasin")
        self.assertEqual(resp.data["count"], 0)

    def test_non_admin_cannot_create_registre(self):
        self.client.force_authenticate(self.chef)
        resp = self.client.post(
            "/api/registres/registres/",
            {"kind": "formations", "label": "Formations", "year": 2026},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_create_registre(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/registres/registres/",
            {"kind": "formations", "label": "Formations", "year": 2026},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_entry_create_autonumbers_and_records_author(self):
        self.client.force_authenticate(self.chef)
        resp = self.client.post(
            "/api/registres/entries/",
            {
                "registre": str(self.registre.id),
                "entry_date": "2026-01-05",
                "data": {"objet": "Courrier arrivée"},
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["number"], 1)
        self.assertEqual(resp.data["created_by"], self.chef.id)

    def test_entry_filter_by_kind(self):
        RegistreEntry.objects.create(registre=self.registre, data={})
        self.client.force_authenticate(self.chef)
        resp = self.client.get("/api/registres/entries/?kind=courrier")
        self.assertEqual(resp.data["count"], 1)
        resp = self.client.get("/api/registres/entries/?kind=formations")
        self.assertEqual(resp.data["count"], 0)

    def test_export_csv_and_xlsx(self):
        RegistreEntry.objects.create(registre=self.registre, data={"objet": "Test"})
        self.client.force_authenticate(self.chef)
        resp = self.client.get("/api/registres/entries/export/?export=csv")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("text/csv", resp["Content-Type"])
        resp = self.client.get("/api/registres/entries/export/?export=xlsx")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("spreadsheetml", resp["Content-Type"])

    def test_export_rejects_bad_format(self):
        self.client.force_authenticate(self.chef)
        resp = self.client.get("/api/registres/entries/export/?export=pdf")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
