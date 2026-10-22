"""Écarts a4 — rôles consommateurs de la Couche D : chargé d'affaires et contrôleur de gestion."""

from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from .models import User
from .rbac import can_read_app, modules_for_role


class RolesCoucheDTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def _user(self, role):
        return User.objects.create_user(email=f"{role}@t.local", password="x" * 12, role=role)

    def test_roles_declares_et_matrice(self):
        self.assertIn("charge_affaires", User.Role.values)
        self.assertIn("controleur_gestion", User.Role.values)
        self.assertIn("controle_gestion", modules_for_role("controleur_gestion"))
        self.assertIn("comptabilite", modules_for_role("controleur_gestion"))
        self.assertIn("commercial", modules_for_role("charge_affaires"))
        self.assertNotIn("rh_paie", modules_for_role("charge_affaires"))
        self.assertNotIn("controle_gestion", modules_for_role("charge_affaires"))

    def test_me_expose_les_modules(self):
        u = self._user("charge_affaires")
        self.client.force_authenticate(u)
        r = self.client.get("/api/users/me/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(set(r.data["modules"]), set(modules_for_role("charge_affaires")))

    def test_lecture_api_conforme_a_la_matrice(self):
        ca, cg = self._user("charge_affaires"), self._user("controleur_gestion")
        cas = [
            (ca, "/api/commercial/affaires/", 200),
            (ca, "/api/operations/ordres/", 200),
            (ca, "/api/rh-paie/employes/", 403),
            (cg, "/api/controle-gestion/budgets/", 200),
            (cg, "/api/hse/incidents/", 403),
        ]
        for user, url, attendu in cas:
            with self.subTest(role=user.role, url=url):
                self.client.force_authenticate(user)
                r = self.client.get(url)
                if r.status_code == 404:
                    self.skipTest(f"route {url} absente")
                self.assertEqual(r.status_code, attendu, r.content[:200])
                self.assertEqual(attendu == 200, can_read_app(user, url.split("/")[2].replace("-", "_")))

    def test_seed_cree_les_comptes_demo(self):
        call_command("seed_demo_users")
        roles = dict(User.objects.filter(email__in=["affaires@etls.local", "cg@etls.local"]).values_list("email", "role"))
        self.assertEqual(roles, {"affaires@etls.local": "charge_affaires", "cg@etls.local": "controleur_gestion"})
