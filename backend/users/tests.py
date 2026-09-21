from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()


class AuthAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="alice@etls.local",
            password="MotDePasse#2026",
            first_name="Alice",
            last_name="ETSL",
            role=User.Role.COMPTABLE,
        )

    def test_login_returns_tokens(self):
        resp = self.client.post(
            "/api/users/token/",
            {"email": "alice@etls.local", "password": "MotDePasse#2026"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)

    def test_login_wrong_password(self):
        resp = self.client.post(
            "/api/users/token/",
            {"email": "alice@etls.local", "password": "mauvais"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_returns_new_access(self):
        tokens = self.client.post(
            "/api/users/token/",
            {"email": "alice@etls.local", "password": "MotDePasse#2026"},
            format="json",
        ).data
        resp = self.client.post("/api/users/token/refresh/", {"refresh": tokens["refresh"]}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("access", resp.data)

    def test_me_requires_auth(self):
        resp = self.client.get("/api/users/me/")
        self.assertIn(resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_me_returns_profile(self):
        tokens = self.client.post(
            "/api/users/token/",
            {"email": "alice@etls.local", "password": "MotDePasse#2026"},
            format="json",
        ).data
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        resp = self.client.get("/api/users/me/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["email"], "alice@etls.local")
        self.assertEqual(resp.data["role"], User.Role.COMPTABLE)


class RolePermissionTests(APITestCase):
    """RF-62 : les rôles non-admin ne gèrent pas les utilisateurs."""

    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@etls.local", password="MotDePasse#2026", role=User.Role.ADMIN, is_staff=True
        )
        self.comptable = User.objects.create_user(
            email="compta@etls.local", password="MotDePasse#2026", role=User.Role.COMPTABLE
        )

    def _auth(self, user):
        tokens = self.client.post(
            "/api/users/token/",
            {"email": user.email, "password": "MotDePasse#2026"},
            format="json",
        ).data
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

    def test_non_admin_cannot_list_users(self):
        self._auth(self.comptable)
        resp = self.client.get("/api/users/users/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_list_users(self):
        self._auth(self.admin)
        resp = self.client.get("/api/users/users/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 2)

    def test_admin_can_create_user(self):
        self._auth(self.admin)
        resp = self.client.post(
            "/api/users/users/",
            {
                "email": "rh@etls.local",
                "password": "MotDePasse#2026",
                "first_name": "RH",
                "role": User.Role.RH,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["role"], User.Role.RH)


class RoleModelTests(TestCase):
    """RF-62 / incrément 12 : 12 fonctions ETSL + rôle technique admin."""

    def test_twelve_functions_present(self):
        fonctions = {
            User.Role.PDG,
            User.Role.DGA,
            User.Role.SECRETAIRE_GENERAL,
            User.Role.DIRECTEUR_PROJETS,
            User.Role.DIRECTEUR_OPERATIONS,
            User.Role.RH,
            User.Role.FINANCE,
            User.Role.QAQC,
            User.Role.HSE,
            User.Role.LOGISTIQUE,
            User.Role.MAINTENANCE,
            User.Role.CHEF_ATELIER,
        }
        self.assertEqual(len(fonctions), 12)
        codes = {code for code, _label in User.Role.choices}
        self.assertTrue(fonctions.issubset(codes))
        self.assertIn(User.Role.ADMIN, codes)

    def test_role_values_fit_column_width(self):
        for code, _label in User.Role.choices:
            self.assertLessEqual(len(code), 20)


class SeedDemoUsersTests(TestCase):
    def test_seed_creates_one_account_per_function(self):
        call_command("seed_demo_users")
        emails = set(User.objects.values_list("email", flat=True))
        self.assertEqual(len(emails), len(
            [
                "admin@etls.local",
                "pdg@etls.local",
                "dga@etls.local",
                "secretariat@etls.local",
                "projets@etls.local",
                "operations@etls.local",
                "rh@etls.local",
                "finance@etls.local",
                "qaqc@etls.local",
                "hse@etls.local",
                "logistique@etls.local",
                "maintenance@etls.local",
                "atelier@etls.local",
                "direction@etls.local",
                "service@etls.local",
                "compta@etls.local",
            ]
        ))
        self.assertTrue(
            {User.Role.PDG, User.Role.FINANCE, User.Role.HSE}.issubset(
                set(User.objects.values_list("role", flat=True))
            )
        )

    def test_seed_is_idempotent(self):
        call_command("seed_demo_users")
        count = User.objects.count()
        call_command("seed_demo_users")
        self.assertEqual(User.objects.count(), count)
