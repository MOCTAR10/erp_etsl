"""Tendances 6 mois du cockpit Direction (non financières) — respect des droits de lecture."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from documents.models import Document, DocumentType
from users.models import User


def mois_precedent(n):
    """(année, mois) d'il y a n mois."""
    t = timezone.localdate().replace(day=1)
    for _ in range(n):
        t = (t - timedelta(days=1)).replace(day=1)
    return t.year, t.month


class TendancesTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="a@etls.ga", password="x-Audit-2026", role=User.Role.ADMIN, is_staff=True
        )
        self.service = User.objects.create_user(
            email="s@etls.ga", password="x-Audit-2026", role=User.Role.CHEF_SERVICE
        )
        self.rh = User.objects.create_user(email="rh@etls.ga", password="x-Audit-2026", role=User.Role.RH)

    def get(self, user):
        c = APIClient()
        c.force_authenticate(user)
        r = c.get("/api/analytics/tendances/")
        self.assertEqual(r.status_code, 200, r.content)
        return r.data

    def doc(self, mois_ago, title="D", type_=None):
        d = Document.objects.create(title=title, type=type_)
        y, m = mois_precedent(mois_ago)
        Document.objects.filter(pk=d.pk).update(created_at=timezone.now().replace(year=y, month=m, day=10))

    def test_six_mois_croissants_se_terminant_ce_mois(self):
        data = self.get(self.admin)
        self.assertEqual(len(data["mois"]), 6)
        self.assertEqual(data["mois"], sorted(data["mois"]))
        y, m = mois_precedent(0)
        self.assertEqual(data["mois"][-1], f"{y}-{m:02d}")
        for serie in ("documents", "incidents", "ordres_travail"):
            self.assertEqual(len(data["series"][serie]), 6)

    def test_documents_comptes_par_mois_de_creation(self):
        self.doc(0)
        self.doc(0)
        self.doc(2)
        self.doc(9)  # hors fenêtre
        s = self.get(self.admin)["series"]["documents"]
        self.assertEqual(s[-1], 2)
        self.assertEqual(s[-3], 1)
        self.assertEqual(sum(s), 3)

    def test_documents_restreints_exclus_pour_les_non_autorises(self):
        paie = DocumentType.objects.create(code="paie-t", label="Paie", is_restricted_rh=True)
        self.doc(0, "bulletin", paie)
        self.doc(0, "normal")
        self.assertEqual(sum(self.get(self.service)["series"]["documents"]), 1)
        self.assertEqual(sum(self.get(self.rh)["series"]["documents"]), 2)

    def test_series_hors_droits_absentes(self):
        s = self.get(self.service)["series"]
        self.assertIsNone(s["incidents"])  # pas de module HSE
        self.assertIsNone(s["ordres_travail"])  # pas de module Maintenance
        s_admin = self.get(self.admin)["series"]
        self.assertIsNotNone(s_admin["incidents"])
        self.assertIsNotNone(s_admin["ordres_travail"])

    def test_anonyme_refuse(self):
        self.assertIn(APIClient().get("/api/analytics/tendances/").status_code, (401, 403))
