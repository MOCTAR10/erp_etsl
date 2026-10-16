"""Idempotence des saisies terrain (CL-OM-08 : mode hors-ligne, synchronisation bidirectionnelle).

Un mobile hors-ligne rejoue ses saisies au retour du réseau, parfois plusieurs fois (coupure en plein envoi) :
la même `Idempotency-Key` ne doit produire qu'UN seul effet, et renvoyer la même réponse.
"""

from datetime import date

from rest_framework.test import APITestCase

from hse.models import PermisTravail
from operations.models import OrdreFabrication, PointageChantier
from users.models import User

from .models import IdempotencyRecord


def user(email, role):
    return User.objects.create_user(email=email, password="x-Audit-2026", role=role, first_name=email[:3])


class IdempotencePointageTests(APITestCase):
    def setUp(self):
        self.chef = user("atelier@etls.ga", User.Role.CHEF_ATELIER)
        self.autre = user("atelier2@etls.ga", User.Role.CHEF_ATELIER)
        self.of = OrdreFabrication.objects.create(label="OF terrain")
        self.client.force_authenticate(self.chef)

    def post(self, key=None, **extra):
        data = {"ordre": str(self.of.pk), "worker_name": "Ali", "date": "2026-03-10", "hours": "8"}
        data.update(extra)
        headers = {"HTTP_IDEMPOTENCY_KEY": key} if key else {}
        return self.client.post("/api/operations/pointages/", data, format="json", **headers)

    def test_meme_cle_un_seul_pointage_meme_reponse(self):
        r1 = self.post("cle-1")
        r2 = self.post("cle-1")
        self.assertEqual(r1.status_code, 201, r1.content)
        self.assertEqual(r2.status_code, 201, r2.content)
        self.assertEqual(r1.data["id"], r2.data["id"])
        self.assertEqual(PointageChantier.objects.count(), 1)
        self.assertEqual(r2["Idempotent-Replay"], "true")
        self.assertNotIn("Idempotent-Replay", r1)

    def test_cles_differentes_deux_pointages(self):
        self.post("cle-a")
        self.post("cle-b")
        self.assertEqual(PointageChantier.objects.count(), 2)

    def test_sans_cle_comportement_normal(self):
        self.post()
        self.post()
        self.assertEqual(PointageChantier.objects.count(), 2)

    def test_la_cle_est_propre_a_chaque_utilisateur(self):
        self.post("cle-x")
        self.client.force_authenticate(self.autre)
        self.post("cle-x")
        self.assertEqual(PointageChantier.objects.count(), 2)

    def test_echec_de_validation_non_memorise(self):
        r = self.post("cle-ko", hours="0")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(IdempotencyRecord.objects.count(), 0)
        ok = self.post("cle-ko")  # même clé, saisie corrigée : doit passer
        self.assertEqual(ok.status_code, 201, ok.content)

    def test_cle_trop_longue_refusee(self):
        r = self.post("x" * 200)
        self.assertEqual(r.status_code, 400)


class IdempotenceTestGazTests(APITestCase):
    def test_rejeu_du_test_gaz_n_ecrase_pas_la_trace(self):
        hse = user("hse@etls.ga", User.Role.HSE)
        p = PermisTravail.objects.create(
            type_permis="chaud", emplacement="Z", description="d", statut=PermisTravail.Statut.VALIDE,
            date_debut=date.today(),
        )
        self.client.force_authenticate(hse)
        url = f"/api/hse/permis/{p.pk}/test-gaz/"
        r1 = self.client.post(url, {"resultat": "conforme", "valeur": "LIE 0"}, format="json",
                              HTTP_IDEMPOTENCY_KEY="gaz-1")
        p.refresh_from_db()
        premiere = p.test_gaz_date
        r2 = self.client.post(url, {"resultat": "conforme", "valeur": "LIE 0"}, format="json",
                              HTTP_IDEMPOTENCY_KEY="gaz-1")
        p.refresh_from_db()
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2["Idempotent-Replay"], "true")
        self.assertEqual(p.test_gaz_date, premiere)
