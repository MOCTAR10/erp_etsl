"""Audit métier M3 (2026-10-16) — situations de travaux : workflow non contournable.

O1 : le statut ne change que par l'action `validate` (pas de PATCH status), une seule fois.
O2 : une situation validée/facturée n'est plus modifiable ni supprimable.
"""

from rest_framework import status
from rest_framework.test import APITestCase

from users.models import User

from .models import SituationTravaux


class SituationWorkflowTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@etls.ga", password="x-Audit-2026", role=User.Role.ADMIN, is_staff=True
        )
        self.client.force_authenticate(self.admin)
        self.sit = SituationTravaux.objects.create(
            label="S1", period_start="2026-01-01", period_end="2026-01-31", amount=1000
        )

    def url(self, suffix=""):
        return f"/api/operations/situations/{self.sit.pk}/{suffix}"

    def test_statut_non_modifiable_par_patch(self):
        self.client.patch(self.url(), {"status": "validee"}, format="json")
        self.sit.refresh_from_db()
        self.assertEqual(self.sit.status, SituationTravaux.Status.BROUILLON)

    def test_validation_une_seule_fois(self):
        self.assertEqual(self.client.post(self.url("validate/")).status_code, 200)
        r = self.client.post(self.url("validate/"))
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST, r.content)

    def test_situation_validee_non_modifiable_ni_supprimable(self):
        self.client.post(self.url("validate/"))
        r = self.client.patch(self.url(), {"amount": "1"}, format="json")
        self.assertEqual(r.status_code, 400, r.content)
        self.assertEqual(self.client.delete(self.url()).status_code, 400)
        self.sit.refresh_from_db()
        self.assertEqual(self.sit.amount, 1000)
