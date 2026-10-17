"""Lot 15 (2026-10-17) — indicateurs TRIR / LTIR / LTIFR (CDC M7 §9.7, reporting pétrolier C2).

- Chaque incident qualifie sa conséquence humaine : aucune, premiers secours, soins médicaux, travail restreint,
  arrêt de travail, décès. Enregistrable (TRIR) = soins médicaux et au-delà ; avec arrêt (LTIR / LTIFR) = arrêt ou décès.
- TRIR = enregistrables × 200 000 / heures travaillées ; LTIR = avec arrêt × 200 000 / heures ;
  LTIFR = avec arrêt × 1 000 000 / heures. Heures = pointages de la période (M9), ou valeur saisie
  (sous-traitants inclus) via `?heures=`.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APITestCase

from rh_paie.models import Employe, SaisieTemps
from users.models import User

from .models import Incident


class IndicateursHseTests(APITestCase):
    URL = "/api/hse/incidents/indicateurs/"

    def setUp(self):
        self.hse = User.objects.create_user(email="hse@etls.ga", password="x-Audit-2026", role=User.Role.HSE)
        self.client.force_authenticate(self.hse)
        self.debut = date.today().replace(month=1, day=1)

    def incident(self, consequence, jours=10, **kw):
        return Incident.objects.create(type_incident="accident", lieu="Atelier", description="Chute",
                                       date_evenement=timezone.now() - timedelta(days=jours),
                                       consequence_humaine=consequence, **kw)

    def test_taux_sur_heures_saisies(self):
        self.incident("premiers_secours")
        self.incident("soins_medicaux")
        self.incident("restriction")
        self.incident("arret", jours_arret=12)
        r = self.client.get(self.URL, {"debut": str(self.debut), "fin": str(date.today()), "heures": "400000"})
        self.assertEqual(r.status_code, 200, r.content)
        d = r.data
        self.assertEqual((d["enregistrables"], d["avec_arret"], d["jours_perdus"]), (3, 1, 12))
        self.assertEqual((d["trir"], d["ltir"], d["ltifr"]), ("1.50", "0.50", "2.50"))

    def test_heures_issues_des_pointages(self):
        emp = Employe.objects.create(code="EMP-1", nom="Mba", prenom="Paul", statut=Employe.Statut.ACTIF)
        SaisieTemps.objects.create(employe=emp, date=date.today() - timedelta(days=3), heures=Decimal("100000"))
        SaisieTemps.objects.create(employe=emp, date=self.debut - timedelta(days=3), heures=Decimal("999999"))  # hors période
        self.incident("arret")
        r = self.client.get(self.URL, {"debut": str(self.debut), "fin": str(date.today())})
        self.assertEqual((r.data["heures"], r.data["ltir"]), ("100000.00", "2.00"))

    def test_sans_heures_taux_non_calculable(self):
        self.incident("arret")
        r = self.client.get(self.URL)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIsNone(r.data["trir"])

    def test_parametres_invalides(self):
        self.assertEqual(self.client.get(self.URL, {"heures": "-5"}).status_code, 400)
        self.assertEqual(self.client.get(self.URL, {"debut": "2026-13-01"}).status_code, 400)

    def test_arret_exige_des_jours_perdus_coherents(self):
        r = self.client.post("/api/hse/incidents/", {"type_incident": "accident", "lieu": "Rack", "description": "x",
                                                    "date_evenement": timezone.now().isoformat(), "consequence_humaine": "aucune",
                                                    "jours_arret": 3}, format="json")
        self.assertEqual(r.status_code, 400, r.content)
