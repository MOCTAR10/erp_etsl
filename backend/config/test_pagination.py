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


class RechercheTests(APITestCase):
    """`?search=` filtre les listes métier (SearchFilter) et se combine avec la pagination."""

    @classmethod
    def setUpTestData(cls):
        from referentiels.models import Partner

        cls.user = User.objects.create_user(email="adm2@etls.local", password="x", role="admin")
        Partner.objects.bulk_create(
            [Partner(code=f"P{i:03d}", name=f"Fournisseur {i:03d}") for i in range(25)]
            + [Partner(code="PZZZ", name="Zanzibar Logistique")]
        )

    def setUp(self):
        self.client.force_authenticate(self.user)

    def test_recherche_par_nom(self):
        data = self.client.get("/api/referentiels/partners/", {"search": "zanzibar"}).json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["code"], "PZZZ")

    def test_recherche_pagine(self):
        data = self.client.get("/api/referentiels/partners/", {"search": "Fournisseur", "page_size": 10, "page": 3}).json()
        self.assertEqual(data["count"], 25)
        self.assertEqual(len(data["results"]), 5)

    def test_recherche_vide_ne_filtre_pas(self):
        data = self.client.get("/api/referentiels/partners/", {"search": ""}).json()
        self.assertGreaterEqual(data["count"], 26)
