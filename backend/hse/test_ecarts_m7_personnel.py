"""Écarts M7, personnel (2026-10-19) — tests de recette (M7-04, M7-05, M7-09, §9.6 « fiches personnel habilité »).

- Formation nominative : la session réalisée publie une qualification RH par participant (flux M7 → M9) avec son
  échéance de recyclage ; l'exigence d'habilitation par mot-clé la reconnaît.
- Aptitude médicale : saisie et lecture réservées HSE / RH / direction ; échéance dans les alertes, notifiée.
- Passeport sécurité (JSON / PDF) et fiche individuelle de dotation EPI.
- Paramètres HSE provisoires ; alertes EPI et habilitations aussi destinées au HSE.
"""

from datetime import date, timedelta

from rest_framework.test import APITestCase

from analytics.services import alertes_agregees
from analytics.tasks import notifier_echeances
from rh_paie.models import Employe, Qualification
from users.models import User
from workflow.models import Notification

from .models import AptitudeMedicale, Epi, ExigenceHabilitation, FormationSecurite, PermisTravail
from .services import habilitations_manquantes


class _Base(APITestCase):
    def setUp(self):
        self.hse = User.objects.create_user(email="hse@etls.ga", password="x-Audit-2026", role=User.Role.HSE)
        self.emp = Employe.objects.create(code="EMP-7", nom="Moussavou", prenom="Léa", statut=Employe.Statut.ACTIF)
        self.client.force_authenticate(self.hse)


class FormationNominativeTests(_Base):
    def test_session_realisee_publie_les_qualifications_rh_avec_recyclage(self):
        r = self.client.post("/api/hse/formations/", {
            "type_session": "formation", "theme": "Travail en hauteur", "date_session": "2026-10-01", "validite_mois": 24,
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        fid = r.data["id"]
        self.assertEqual(self.client.post(f"/api/hse/formations/{fid}/realiser/").status_code, 400)  # sans participant
        r = self.client.post(f"/api/hse/formations/{fid}/ajouter-participant/", {"employe": str(self.emp.pk)}, format="json")
        self.assertEqual((r.status_code, r.data["nb_participants"]), (200, 1))
        r = self.client.post(f"/api/hse/formations/{fid}/realiser/")
        self.assertEqual(r.status_code, 200, r.content)
        q = Qualification.objects.get(employe=self.emp)
        self.assertEqual((q.intitule, q.date_validite), ("Formation HSE — Travail en hauteur", date(2028, 10, 1)))
        self.client.post(f"/api/hse/formations/{fid}/realiser/")  # idempotent
        self.assertEqual(Qualification.objects.filter(employe=self.emp).count(), 1)
        # La qualification issue de la formation satisfait l'exigence d'habilitation du permis.
        ExigenceHabilitation.objects.create(type_permis="hauteur", mot_cle="hauteur")
        permis = PermisTravail.objects.create(type_permis="hauteur", emplacement="Rack 4", description="Pose de chemin de câbles",
                                              date_debut=date.today(), demandeur=self.hse)
        permis.intervenants.add(self.emp)
        self.assertEqual(habilitations_manquantes(permis, date(2026, 10, 19)), [])


class AptitudeTests(_Base):
    def test_aptitude_reservee_et_alerte_notifiee(self):
        logistique = User.objects.create_user(email="log@etls.ga", password="x-Audit-2026", role=User.Role.LOGISTIQUE)
        self.client.force_authenticate(logistique)
        self.assertEqual(self.client.get("/api/hse/aptitudes/").status_code, 403)
        self.client.force_authenticate(self.hse)
        r = self.client.post("/api/hse/aptitudes/", {
            "employe": str(self.emp.pk), "date_visite": str(date.today() - timedelta(days=350)),
            "date_validite": str(date.today() + timedelta(days=15)), "resultat": "apte_restrictions",
        }, format="json")
        self.assertEqual(r.status_code, 400, r.content)  # restrictions à préciser
        r = self.client.post("/api/hse/aptitudes/", {
            "employe": str(self.emp.pk), "date_visite": str(date.today() - timedelta(days=350)),
            "date_validite": str(date.today() + timedelta(days=15)), "resultat": "apte",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        items = [i for i in alertes_agregees()["rh"] if i["type"] == "aptitude_medicale"]
        self.assertEqual((len(items), items[0]["bande"]), (1, "j15"))
        notifier_echeances()
        self.assertTrue(Notification.objects.filter(user=self.hse, subject__contains="J-15").exists())


class PasseportEtDotationTests(_Base):
    def test_passeport_et_fiche_de_dotation(self):
        Qualification.objects.create(employe=self.emp, intitule="Habilitation électrique B1V", date_validite=date.today() - timedelta(days=1))
        AptitudeMedicale.objects.create(employe=self.emp, date_visite=date.today(), resultat="apte")
        Epi.objects.create(type_epi="casque", designation="Casque de chantier", employe=self.emp,
                           date_renouvellement=date.today() + timedelta(days=200))
        r = self.client.get(f"/api/hse/personnel/{self.emp.pk}/passeport/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertFalse(r.data["qualifications"][0]["valide"])
        self.assertEqual(r.data["aptitude"]["resultat"], "Apte")
        self.assertEqual(len(r.data["epi"]), 1)
        r = self.client.get(f"/api/hse/personnel/{self.emp.pk}/passeport/?export=pdf")
        self.assertTrue(r.content.startswith(b"%PDF"))
        r = self.client.get(f"/api/hse/epis/fiche-dotation/?employe={self.emp.pk}&export=pdf")
        self.assertEqual((r.status_code, r["Content-Type"]), (200, "application/pdf"))
        chef = User.objects.create_user(email="chef@etls.ga", password="x-Audit-2026", role=User.Role.CHEF_ATELIER)
        self.client.force_authenticate(chef)  # hors cercle médical : pas d'aptitude dans le passeport
        self.assertIsNone(self.client.get(f"/api/hse/personnel/{self.emp.pk}/passeport/").data["aptitude"])


class ParametresEtAlertesTests(_Base):
    def test_epi_a_renouveler_notifie_au_hse_selon_delai_parametre(self):
        Epi.objects.create(type_epi="casque", designation="Casque", employe=self.emp, date_renouvellement=date.today() + timedelta(days=15))
        self.assertEqual(len([i for i in alertes_agregees()["rh"] if i["type"] == "epi"]), 1)
        notifier_echeances()
        self.assertTrue(Notification.objects.filter(user=self.hse, subject__contains="EPI").exists())
        rows = self.client.get("/api/hse/parametres/").data
        rows = rows["results"] if isinstance(rows, dict) else rows
        self.assertTrue(all(p["est_provisoire"] for p in rows))
