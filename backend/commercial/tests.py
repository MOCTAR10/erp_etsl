from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

from referentiels.models import Article, Currency, Partner, UnitOfMeasure

from .models import (
    Affaire,
    ClientProfile,
    CommercialSequence,
    Contract,
    Estimate,
    EstimateLine,
    EstimateOption,
    Milestone,
    Opportunity,
)

User = get_user_model()


def make_client():
    partner = Partner.objects.create(code="CL-001", name="Client A", kind="client")
    return ClientProfile.objects.create(partner=partner, scoring=90)


class SeedCommercialTests(APITestCase):
    def test_seed_is_idempotent(self):
        call_command("seed_commercial_demo")
        call_command("seed_commercial_demo")
        self.assertGreaterEqual(Opportunity.objects.count(), 5)
        self.assertEqual(Affaire.objects.count(), 1)
        self.assertEqual(Contract.objects.count(), 1)
        self.assertEqual(ClientProfile.objects.count(), 3)

    def test_seed_creates_pipeline_stages(self):
        call_command("seed_commercial_demo")
        self.assertEqual(
            set(Opportunity.objects.values_list("stage", flat=True)),
            {"prospection", "qualification", "offre", "negociation", "gagne"},
        )


class SequenceTests(APITestCase):
    def test_numbering_is_continuous_per_kind(self):
        a1 = Opportunity.objects.create(subject="A")
        a2 = Opportunity.objects.create(subject="B")
        opp_id = a1.code
        a3 = Affaire.objects.create(title="C")
        self.assertEqual(a1.code, "OPP00001")
        self.assertEqual(a2.code, "OPP00002")
        self.assertEqual(opp_id, a1.code)
        self.assertEqual(a3.code, "AFF00001")
        self.assertEqual(a2.code[3:], "00002")


class OpportunityBehaviourTests(APITestCase):
    def test_won_auto_sets_won_date_and_probability(self):
        opp = Opportunity.objects.create(subject="Gain", stage="gagne")
        self.assertIsNotNone(opp.won_date)
        self.assertEqual(opp.probability, 100)

    def test_lost_zeroes_probability(self):
        opp = Opportunity.objects.create(subject="Perte", stage="perdu", probability=70)
        self.assertEqual(opp.probability, 0)


class EstimateBehaviourTests(APITestCase):
    def setUp(self):
        self.currency, _ = Currency.objects.get_or_create(code="XAF")
        self.unit, _ = UnitOfMeasure.objects.get_or_create(code="U")

    def test_line_price_total_computed(self):
        estimate = Estimate.objects.create(title="Est", currency=self.currency)
        line = EstimateLine.objects.create(
            estimate=estimate, label="Presta", quantity=3, unit_price=250_000, unit=self.unit
        )
        self.assertEqual(line.price_total, 750_000)

    def test_multi_option_estimate(self):
        estimate = Estimate.objects.create(title="Multi", currency=self.currency)
        EstimateOption.objects.create(estimate=estimate, label="A", amount=100)
        EstimateOption.objects.create(estimate=estimate, label="B", amount=200, is_selected=True)
        self.assertEqual(estimate.options.count(), 2)
        self.assertTrue(estimate.options.get(label="B").is_selected)


class MilestoneBehaviourTests(APITestCase):
    def setUp(self):
        self.affaire = Affaire.objects.create(title="Aff")

    def test_status_auto_done_when_on_time(self):
        today = timezone.localdate()
        m = Milestone.objects.create(
            affaire=self.affaire, label="J1", planned_date=today - timezone.timedelta(days=1),
            actual_date=today - timezone.timedelta(days=1),
        )
        self.assertEqual(m.status, Milestone.Status.FAIT)

    def test_status_retard_when_overdue(self):
        m = Milestone.objects.create(
            affaire=self.affaire, label="J2",
            planned_date=timezone.localdate() - timezone.timedelta(days=2),
        )
        self.assertEqual(m.status, Milestone.Status.RETARD)


class ContractTests(APITestCase):
    def setUp(self):
        self.currency, _ = Currency.objects.get_or_create(code="XAF")
        self.client = make_client()
        self.won = Opportunity.objects.create(subject="W", stage="gagne", client=self.client)
        self.affaire = Affaire.objects.create(title="Aff", opportunity=self.won, client=self.client)

    def test_expiry_status_buckets(self):
        today = timezone.localdate()
        c = Contract.objects.create(
            affaire=self.affaire, client=self.client, profile="marche_travaux",
            start_date=today - timezone.timedelta(days=50),
            end_date=today + timezone.timedelta(days=25), months=18, currency=self.currency,
        )
        self.assertEqual(c.expiry_status, "J30")
        c.end_date = today - timezone.timedelta(days=1)
        self.assertEqual(c.expiry_status, "EXPIRED")
        c.end_date = today + timezone.timedelta(days=75)
        self.assertEqual(c.expiry_status, "J90")
        c.end_date = today + timezone.timedelta(days=45)
        self.assertEqual(c.expiry_status, "J60")

    def test_clean_rejects_end_before_start(self):
        today = timezone.localdate()
        c = Contract.objects.create(
            affaire=self.affaire, client=self.client, profile="maintenance",
            start_date=today, end_date=today - timezone.timedelta(days=5),
        )
        with self.assertRaises(ValidationError):
            c.full_clean()

    def test_maintenance_contract(self):
        today = timezone.localdate()
        c = Contract.objects.create(
            affaire=self.affaire, client=self.client, profile="maintenance",
            start_date=today, end_date=today + timezone.timedelta(days=365), months=12,
            sla="Intervention < 24h",
        )
        self.assertEqual(c.get_profile_display(), "Contrat de maintenance")
        self.assertEqual(c.services.count(), 0)


class CommercialAPITests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@etls.local", password="MotDePasse#2026",
            role=User.Role.ADMIN, is_staff=True,
        )
        self.projets = User.objects.create_user(
            email="projets@etls.local", password="MotDePasse#2026",
            role=User.Role.DIRECTEUR_PROJETS,
        )
        self.chef = User.objects.create_user(
            email="chef@etls.local", password="MotDePasse#2026",
            role=User.Role.CHEF_SERVICE,
        )
        self.client_profile = make_client()
        self.opp = Opportunity.objects.create(
            client=self.client_profile, subject="Opp 1", amount=100_000_000,
            stage="qualification",
        )

    def test_list_requires_auth(self):
        resp = self.client.get("/api/commercial/opportunities/")
        self.assertIn(
            resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        )

    def test_authenticated_can_read_and_filter(self):
        self.client.force_authenticate(self.chef)
        resp = self.client.get("/api/commercial/opportunities/?stage=qualification")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["code"], "OPP00001")

    def test_chef_cannot_create(self):
        self.client.force_authenticate(self.chef)
        resp = self.client.post(
            "/api/commercial/opportunities/", {"subject": "Non"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_directeur_projets_can_create(self):
        self.client.force_authenticate(self.projets)
        resp = self.client.post(
            "/api/commercial/opportunities/",
            {"subject": "Nouvelle opp", "client": str(self.client_profile.id),
             "amount": 50_000_000},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["code"], "OPP00002")

    def test_amount_masked_for_chef_service(self):
        self.client.force_authenticate(self.chef)
        resp = self.client.get(f"/api/commercial/opportunities/{self.opp.id}/")
        self.assertIsNone(resp.data["amount"])

    def test_amount_visible_for_directeur_projets(self):
        self.client.force_authenticate(self.projets)
        resp = self.client.get(f"/api/commercial/opportunities/{self.opp.id}/")
        self.assertEqual(resp.data["amount"], "100000000.00")

    def test_admin_sees_amount(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.get(f"/api/commercial/opportunities/{self.opp.id}/")
        self.assertEqual(resp.data["amount"], "100000000.00")

    def test_pipeline_stats_endpoint(self):
        self.client.force_authenticate(self.admin)
        self.opp.stage = "gagne"
        self.opp.save()
        resp = self.client.get("/api/commercial/opportunities/pipeline/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data
        self.assertIn("gagne", data["by_stage"])
        self.assertEqual(len(data["by_stage"]), 1)
        self.assertGreaterEqual(data["conversion_rate"], 0)
        self.assertEqual(data["won_total"], 100_000_000.0)

    def test_contracts_expiring_filter(self):
        self.client.force_authenticate(self.admin)
        today = timezone.localdate()
        Contract.objects.create(
            client=self.client_profile, profile="maintenance",
            start_date=today - timezone.timedelta(days=10),
            end_date=today + timezone.timedelta(days=20), status="actif",
            months=12,
        )
        Contract.objects.create(
            client=self.client_profile, profile="maintenance",
            start_date=today - timezone.timedelta(days=10),
            end_date=today + timezone.timedelta(days=200), status="actif",
            months=12,
        )
        resp = self.client.get("/api/commercial/contracts/?expiring=30")
        self.assertEqual(resp.data["count"], 1)

    def test_contracts_serializer_exposes_expiry(self):
        self.client.force_authenticate(self.admin)
        today = timezone.localdate()
        c = Contract.objects.create(
            client=self.client_profile, profile="maintenance",
            start_date=today, end_date=today + timezone.timedelta(days=15),
            status="actif", months=12,
        )
        resp = self.client.get(f"/api/commercial/contracts/{c.id}/")
        self.assertEqual(resp.data["expiry_status"], "J30")