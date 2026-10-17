"""Audit lot 8 (2026-10-17) — bureau d'ordre (§3.3) : un courrier archivé ne « revient » pas en arrière."""

from rest_framework.test import APITestCase

from users.models import User

from .models import Courrier


class CycleCourrierTests(APITestCase):
    def setUp(self):
        self.sg = User.objects.create_user(email="sg@etls.ga", password="x-Audit-2026", role=User.Role.SECRETAIRE_GENERAL)
        self.client.force_authenticate(self.sg)

    def courrier(self, statut):
        return Courrier.objects.create(sens="entrant", type="lettre", objet="Mise en demeure", statut=statut)

    def test_archive_ne_se_desarchive_pas(self):
        c = self.courrier(Courrier.Statut.ARCHIVE)
        for action in ("enregistrer", "classer"):
            r = self.client.post(f"/api/juridique/courriers/{c.pk}/{action}/")
            self.assertEqual(r.status_code, 400, (action, r.content))
        c.refresh_from_db()
        self.assertEqual(c.statut, Courrier.Statut.ARCHIVE)

    def test_cycle_normal(self):
        c = self.courrier(Courrier.Statut.RECU)
        for action, attendu in (("enregistrer", "enregistre"), ("classer", "classe"), ("archiver", "archive")):
            r = self.client.post(f"/api/juridique/courriers/{c.pk}/{action}/")
            self.assertEqual(r.status_code, 200, r.content)
            self.assertEqual(r.data["statut"], attendu)
