"""Audit lot 7 (2026-10-17) — le demandeur d'un permis est l'utilisateur authentifié, jamais une saisie client.

Faille corrigée : `demandeur` modifiable permettait de créer un permis au nom d'un collègue puis de le valider
soi-même, contournant la séparation des tâches H2 (le demandeur ne valide pas son propre permis).
"""

from django.utils import timezone
from rest_framework.test import APITestCase

from users.models import User

from .models import PermisTravail


def user(email, role):
    return User.objects.create_user(email=email, password="x-Audit-2026", role=role, first_name=email[:3])


class DemandeurTests(APITestCase):
    def setUp(self):
        self.hse1 = user("hse1@etls.ga", User.Role.HSE)
        self.hse2 = user("hse2@etls.ga", User.Role.HSE)

    def create(self, who, **extra):
        self.client.force_authenticate(who)
        body = {
            "type_permis": "hauteur", "emplacement": "Rack 3", "description": "Pose de garde-corps",
            "date_debut": timezone.localdate().isoformat(), **extra,
        }
        return self.client.post("/api/hse/permis/", body, format="json")

    def test_demandeur_impose_par_le_serveur(self):
        r = self.create(self.hse1, demandeur=self.hse2.pk)
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(PermisTravail.objects.get(pk=r.data["id"]).demandeur, self.hse1)

    def test_separation_des_taches_non_contournable(self):
        r = self.create(self.hse1, demandeur=self.hse2.pk)
        self.assertEqual(r.status_code, 201, r.content)
        self.client.force_authenticate(self.hse1)
        v = self.client.post(f"/api/hse/permis/{r.data['id']}/valider/", {}, format="json")
        self.assertEqual(v.status_code, 403, v.content)

    def test_patch_ne_change_pas_le_demandeur(self):
        pk = self.create(self.hse1).data["id"]
        self.client.force_authenticate(self.hse1)
        self.client.patch(f"/api/hse/permis/{pk}/", {"demandeur": self.hse2.pk}, format="json")
        self.assertEqual(PermisTravail.objects.get(pk=pk).demandeur, self.hse1)
