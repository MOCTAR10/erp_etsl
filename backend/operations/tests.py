from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command

from rest_framework import status
from rest_framework.test import APITestCase

from .models import (
    GammeOperatoire,
    GammeOperation,
    OrdreFabrication,
    PointageChantier,
    SituationTravaux,
)

User = get_user_model()


class SeedOperationsTests(APITestCase):
    def test_seed_is_idempotent(self):
        call_command("seed_operations_demo")
        call_command("seed_operations_demo")
        self.assertEqual(GammeOperatoire.objects.count(), 1)
        self.assertEqual(OrdreFabrication.objects.count(), 1)
        self.assertEqual(PointageChantier.objects.count(), 1)
        self.assertEqual(SituationTravaux.objects.count(), 1)


class SequenceTests(APITestCase):
    def test_numbering_by_kind(self):
        gamme = GammeOperatoire.objects.create(label="G1")
        of = OrdreFabrication.objects.create(label="OF1")
        pt = PointageChantier.objects.create(ordre=of, worker_name="Ali", date="2026-01-15", hours=8)
        sit = SituationTravaux.objects.create(
            label="S1", period_start="2026-01-01", period_end="2026-01-31"
        )
        self.assertEqual(gamme.code, "GAM00001")
        self.assertEqual(of.code, "OF00001")
        self.assertEqual(pt.code, "PTS00001")
        self.assertEqual(sit.code, "SIT00001")
        self.assertEqual(GammeOperatoire.objects.create(label="G2").code, "GAM00002")


class OrdreFabricationBehaviourTests(APITestCase):
    def setUp(self):
        self.of = OrdreFabrication.objects.create(label="Tuyauterie DN200")

    def test_pointage_hours_accumulate(self):
        PointageChantier.objects.create(ordre=self.of, worker_name="A", date="2026-01-10", hours=8)
        PointageChantier.objects.create(ordre=self.of, worker_name="B", date="2026-01-11", hours=4)
        self.assertEqual(float(self.of.pointage_hours), 12)

    def test_planned_dates_ordered(self):
        self.of.planned_start = "2026-02-20"
        self.of.planned_end = "2026-02-10"
        with self.assertRaises(ValidationError):
            self.of.full_clean()

    def test_gamme_total_hours(self):
        gamme = GammeOperatoire.objects.create(label="Soudure")
        GammeOperation.objects.create(gamme=gamme, sequence=1, label="Préparation", planned_hours=8)
        GammeOperation.objects.create(gamme=gamme, sequence=2, label="Soudure", planned_hours=24)
        self.assertEqual(float(gamme.total_planned_hours), 32)

    def test_pointage_rejects_zero_hours(self):
        pt = PointageChantier(ordre=self.of, worker_name="A", date="2026-01-10", hours=0)
        with self.assertRaises(ValidationError):
            pt.full_clean()

    def test_situation_links_ordres_and_reports_hours(self):
        sit = SituationTravaux.objects.create(
            label="Situation n°1", period_start="2026-01-01", period_end="2026-01-31"
        )
        PointageChantier.objects.create(ordre=self.of, worker_name="A", date="2026-01-10", hours=6)
        sit.ordres.add(self.of)
        sit.refresh_from_db()
        self.assertEqual(float(sit.ordered_hours), 6)


class OperationsAPITests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@etls.local", password="MotDePasse#2026",
            role=User.Role.ADMIN, is_staff=True,
        )
        self.chef = User.objects.create_user(
            email="chef@etls.local", password="MotDePasse#2026",
            role=User.Role.CHEF_ATELIER,
        )
        self.chef_service = User.objects.create_user(
            email="chef_service@etls.local", password="MotDePasse#2026",
            role=User.Role.CHEF_SERVICE,
        )
        self.of = OrdreFabrication.objects.create(label="OF principal", scope="chantier")
        self.sit = SituationTravaux.objects.create(
            label="Situation TX", period_start="2026-01-01", period_end="2026-01-31",
            amount=18_000_000,
        )

    def test_list_requires_auth(self):
        resp = self.client.get("/api/operations/ordres/")
        self.assertIn(
            resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        )

    def test_chef_atelier_can_read_and_filter(self):
        self.client.force_authenticate(self.chef)
        resp = self.client.get("/api/operations/ordres/?scope=chantier")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)

    def test_chef_service_cannot_create_of(self):
        self.client.force_authenticate(self.chef_service)
        resp = self.client.post("/api/operations/ordres/", {"label": "OF X"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_chef_atelier_can_create_of(self):
        self.client.force_authenticate(self.chef)
        resp = self.client.post(
            "/api/operations/ordres/",
            {"label": "OF atelier 2026", "scope": "atelier"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["code"], "OF00002")

    def test_chef_atelier_can_create_pointage(self):
        self.client.force_authenticate(self.chef)
        resp = self.client.post(
            "/api/operations/pointages/",
            {"ordre": str(self.of.id), "worker_name": "Ali D.", "date": "2026-02-01",
             "hours": 8},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["code"], "PTS00001")
        self.assertEqual(str(resp.data["created_by"]), str(self.chef.id))

    def test_amount_masked_for_chef_service(self):
        self.client.force_authenticate(self.chef_service)
        resp = self.client.get(f"/api/operations/situations/{self.sit.id}/")
        self.assertEqual(resp.data["amount"], None)

    def test_amount_visible_for_finance(self):
        finance = User.objects.create_user(
            email="finance@etls.local", password="MotDePasse#2026",
            role=User.Role.FINANCE,
        )
        self.client.force_authenticate(finance)
        resp = self.client.get(f"/api/operations/situations/{self.sit.id}/")
        self.assertEqual(resp.data["amount"], "18000000.00")

    def test_chef_atelier_cannot_see_situation_amount(self):
        self.client.force_authenticate(self.chef)
        resp = self.client.get(f"/api/operations/situations/{self.sit.id}/")
        self.assertIsNone(resp.data["amount"])

    def test_charge_stats_action(self):
        self.client.force_authenticate(self.chef)
        resp = self.client.get("/api/operations/ordres/charge/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("totals", resp.data)
        self.assertIn("chantier", resp.data["totals"])

    def test_validate_situation_marks_validated(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(f"/api/operations/situations/{self.sit.id}/validate/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], "validee")
        self.assertEqual(str(resp.data["validated_by"]), str(self.admin.id))