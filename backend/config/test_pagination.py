from rest_framework.test import APITestCase

from config.pagination import StandardPagination
from referentiels.models import Currency
from users.models import User


class PaginationTests(APITestCase):
    """`?page_size=` respecté, plafonné à 500, défaut inchangé (20)."""

    url = "/api/referentiels/currencies/"

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="adm@etls.local", password="x", role="admin")
        Currency.objects.bulk_create([Currency(code=f"A{i:02d}", label=f"Devise {i}") for i in range(30)])

    def setUp(self):
        self.client.force_authenticate(self.user)

    def test_defaut_20(self):
        data = self.client.get(self.url).json()
        self.assertEqual(len(data["results"]), 20)
        self.assertGreaterEqual(data["count"], 30)
        self.assertIsNotNone(data["next"])

    def test_page_size_respecte(self):
        data = self.client.get(self.url, {"page_size": 5}).json()
        self.assertEqual(len(data["results"]), 5)

    def test_page_size_plafonne(self):
        self.assertEqual(StandardPagination.max_page_size, 500)
        data = self.client.get(self.url, {"page_size": 100000}).json()
        self.assertLessEqual(len(data["results"]), 500)
        self.assertEqual(len(data["results"]), data["count"])

    def test_page_deux(self):
        data = self.client.get(self.url, {"page": 2}).json()
        self.assertGreaterEqual(len(data["results"]), 10)
