"""Anti brute-force : la route de connexion est limitee (scope `login`)."""

from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from users.models import User


class LoginThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        User.objects.create_user(
            email="throttle@etls.local", password="Good-Pass-2026", role=User.Role.ADMIN
        )

    def test_trop_de_tentatives_renvoie_429(self):
        client = APIClient()
        rates = {**ScopedRateThrottle.THROTTLE_RATES, "login": "3/min"}
        with mock.patch.object(ScopedRateThrottle, "THROTTLE_RATES", rates):
            codes = [
                client.post(
                    "/api/users/token/",
                    {"email": "throttle@etls.local", "password": "mauvais"},
                    format="json",
                ).status_code
                for _ in range(5)
            ]
        self.assertEqual(codes[:3], [401, 401, 401])
        self.assertEqual(codes[3:], [429, 429])
