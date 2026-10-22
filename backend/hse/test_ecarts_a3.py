"""Lot a3 (CL-OM-08) : permis, signalement et test gaz saisis hors ligne — horodatage de saisie, rejeu idempotent,
conflit d'une mesure plus ancienne que celle du serveur."""

from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from users.models import User

from .models import Incident, PermisTravail


class HseHorsLigneTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(email="admin-a3h@etls.ga", password="x-Terrain-2026", role=User.Role.ADMIN)
        self.client.force_authenticate(self.admin)

    def test_demande_de_permis_hors_ligne_rejouable_et_horodatee(self):
        saisi = timezone.now() - timedelta(hours=2)
        corps = {"type_permis": "froid", "emplacement": "Rack 3", "description": "Montage supports",
                 "saisi_le": saisi.isoformat()}
        r = self.client.post("/api/hse/permis/", corps, format="json", HTTP_IDEMPOTENCY_KEY="permis-a3-1")
        self.assertEqual(r.status_code, 201, r.content)
        r2 = self.client.post("/api/hse/permis/", corps, format="json", HTTP_IDEMPOTENCY_KEY="permis-a3-1")
        self.assertEqual(r2.status_code, 201)
        self.assertEqual(PermisTravail.objects.filter(emplacement="Rack 3").count(), 1)
        self.assertEqual(PermisTravail.objects.get(pk=r.data["id"]).saisi_le, saisi)

    def test_signalement_hors_ligne_sans_doublon(self):
        corps = {"type_incident": "situation_dangereuse", "gravite": "mineure", "lieu": "Quai",
                 "date_evenement": timezone.now().isoformat(), "zone": "chantier", "description": "Câble au sol",
                 "saisi_le": timezone.now().isoformat()}
        for _ in range(2):
            r = self.client.post("/api/hse/incidents/", corps, format="json", HTTP_IDEMPOTENCY_KEY="inc-a3-1")
            self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Incident.objects.filter(lieu="Quai").count(), 1)

    def test_test_gaz_hors_ligne_horodate_et_conflit_si_plus_ancien(self):
        permis = PermisTravail.objects.create(type_permis="chaud", emplacement="Bac", description="Soudure",
                                              statut=PermisTravail.Statut.VALIDE)
        url = f"/api/hse/permis/{permis.pk}/test-gaz/"
        recent = timezone.now() - timedelta(minutes=10)
        r = self.client.post(url, {"resultat": "conforme", "valeur": "LIE 0 %", "saisi_le": recent.isoformat()}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        permis.refresh_from_db()
        self.assertEqual(permis.test_gaz_date, recent)  # heure de la mesure, pas de la synchronisation
        ancien = (timezone.now() - timedelta(hours=1)).isoformat()
        r = self.client.post(url, {"resultat": "non_conforme", "saisi_le": ancien}, format="json")
        self.assertEqual(r.status_code, 409)
        permis.refresh_from_db()
        self.assertEqual(permis.test_gaz_resultat, "conforme")
        r = self.client.post(url, {"resultat": "non_conforme", "saisi_le": ancien, "forcer": True}, format="json")
        self.assertEqual(r.status_code, 200)

    def test_horodatage_invalide_refuse(self):
        permis = PermisTravail.objects.create(type_permis="chaud", emplacement="Bac", description="Soudure",
                                              statut=PermisTravail.Statut.VALIDE)
        r = self.client.post(f"/api/hse/permis/{permis.pk}/test-gaz/", {"resultat": "conforme", "saisi_le": "hier"},
                             format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("saisi_le", r.data)
