"""Lot 12 (2026-10-17) — CAPA qualité clôturées sous 5 jours (CDC M6 §8.4 / §8.8).

Une action corrective / préventive naît avec une échéance à J+5 au plus tard ; une échéance plus lointaine est
refusée ; l'API signale les CAPA en retard (échéance dépassée et non clôturées).
"""

from datetime import date, timedelta

from rest_framework.test import APITestCase

from users.models import User

from .models import ActionCorrective, NonConformite


class Capa5JoursTests(APITestCase):
    def setUp(self):
        self.qa = User.objects.create_user(email="qa@etls.ga", password="x-Audit-2026", role=User.Role.QAQC)
        self.client.force_authenticate(self.qa)
        self.nc = NonConformite.objects.create(description="Porosité soudure S-12")

    def creer(self, **kw):
        body = {"non_conformite": str(self.nc.pk), "type": "corrective", "description": "Reprise + re-CND"}
        body.update(kw)
        return self.client.post("/api/qualite/actions-correctives/", body, format="json")

    def test_echeance_par_defaut_a_j_plus_5(self):
        r = self.creer()
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(ActionCorrective.objects.get(pk=r.data["id"]).echeance, date.today() + timedelta(days=5))

    def test_echeance_au_dela_de_5_jours_refusee(self):
        r = self.creer(echeance=str(date.today() + timedelta(days=12)))
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("echeance", r.data)

    def test_capa_en_retard_signalee(self):
        capa = ActionCorrective.objects.create(non_conformite=self.nc, description="Former le soudeur",
                                               echeance=date.today() - timedelta(days=1))
        r = self.client.get(f"/api/qualite/actions-correctives/{capa.pk}/")
        self.assertTrue(r.data["en_retard"], r.data)
        r = self.client.get("/api/qualite/actions-correctives/?en_retard=1")
        self.assertEqual([a["id"] for a in r.data["results"]], [str(capa.pk)])
