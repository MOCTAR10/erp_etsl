from django.contrib.auth import get_user_model
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
