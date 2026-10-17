"""Audit lot 8 (2026-10-17) — rattachement compte ↔ fiche salarié réservé au cercle paie (RF-33).

Faille corrigée : tout rôle d'écriture RH (chef d'atelier, directions projets/opérations, SG) pouvait rattacher
SON compte à la fiche d'un autre salarié, puis lire ses bulletins via « Mon espace ».
"""

from datetime import date

from django.utils import timezone
from rest_framework.test import APITestCase

from users.models import User

from .models import BulletinPaie, Employe


def user(email, role):
    return User.objects.create_user(email=email, password="x-Audit-2026", role=role, first_name=email[:3])


class RattachementCompteTests(APITestCase):
    def setUp(self):
        self.atelier = user("atelier@etls.ga", User.Role.CHEF_ATELIER)
        self.rh = user("rh@etls.ga", User.Role.RH)
        self.cible = Employe.objects.create(code="EMP-PDG", civilite="masculin", nom="Directeur")
        BulletinPaie.objects.create(
            employe=self.cible, periode=date(2026, 9, 1), brut=5_000_000, net=4_000_000,
            disponible_le=timezone.now(),
        )

    def test_role_rh_hors_paie_ne_rattache_pas_un_compte(self):
        self.client.force_authenticate(self.atelier)
        r = self.client.patch(f"/api/rh-paie/employes/{self.cible.pk}/", {"user": str(self.atelier.pk)}, format="json")
        self.assertEqual(r.status_code, 403, r.content)
        self.cible.refresh_from_db()
        self.assertIsNone(self.cible.user)
        # …et donc aucun accès aux bulletins d'autrui par « Mon espace ».
        self.assertNotEqual(self.client.get("/api/rh-paie/mon-espace/bulletins/").status_code, 200)

    def test_cercle_paie_rattache_un_compte(self):
        self.client.force_authenticate(self.rh)
        r = self.client.patch(f"/api/rh-paie/employes/{self.cible.pk}/", {"user": str(self.atelier.pk)}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.cible.refresh_from_db()
        self.assertEqual(self.cible.user, self.atelier)

    def test_role_rh_hors_paie_peut_modifier_les_autres_champs(self):
        self.client.force_authenticate(self.atelier)
        r = self.client.patch(f"/api/rh-paie/employes/{self.cible.pk}/", {"telephone": "+241 01 02 03"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
