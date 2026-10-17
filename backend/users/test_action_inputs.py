"""Audit lot 9 (2026-10-17) — saisies des actions de workflow : 400 explicite, jamais d'erreur 500.

Les actions DRF (`@action`) lisent `request.data` sans sérialiseur : une date, un choix ou un identifiant mal formé
était affecté tel quel au modèle et faisait planter l'enregistrement (500), ou stockait une valeur hors choix.
"""

from datetime import date, timedelta

from rest_framework.test import APITestCase

from comptabilite.models import ControleInterne
from documents.models import Document
from juridique.models import Assurance
from maintenance.models import Actif, Inspection, OrdreTravail
from rh_paie.models import Employe, Sanction

from .models import User


class ActionInputsTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@etls.ga", password="x-Audit-2026", role=User.Role.ADMIN, is_staff=True
        )
        self.client.force_authenticate(self.admin)
        self.actif = Actif.objects.create(designation="Pont roulant", categorie=Actif.Categorie.MACHINE)

    def post(self, url, data):
        return self.client.post(url, data, format="json")

    def assert400(self, url, data):
        r = self.post(url, data)
        self.assertEqual(r.status_code, 400, (url, data, r.status_code, r.content[:200]))

    def test_inspection_realiser(self):
        insp = Inspection.objects.create(actif=self.actif, date_inspection=date.today())
        url = f"/api/maintenance/inspections/{insp.pk}/realiser/"
        self.assert400(url, {"resultat": "zzz"})
        self.assert400(url, {"prochaine_inspection": "31/31/2026"})
        self.assert400(url, {"intervenant": "pas-un-uuid"})
        insp.refresh_from_db()
        self.assertEqual(insp.statut, Inspection.Statut.PLANIFIEE)

    def test_ot_planifier(self):
        ot = OrdreTravail.objects.create(actif=self.actif, description="Révision")
        url = f"/api/maintenance/ordres/{ot.pk}/planifier/"
        self.assert400(url, {"date_planifiee": "demain"})
        self.assert400(url, {"technicien": "pas-un-uuid"})

    def test_controle_interne_realiser(self):
        c = ControleInterne.objects.create(libelle="Rapprochement caisse")
        self.assert400(f"/api/comptabilite/controles/{c.pk}/realiser/", {"date_realise": "hier"})
        r = self.post(f"/api/comptabilite/controles/{c.pk}/realiser/", {"constat": "RAS"})
        self.assertEqual(r.status_code, 200, r.content)
        c.refresh_from_db()
        self.assertEqual(c.date_realise, date.today())  # un contrôle réalisé est daté

    def test_sanction_decider(self):
        emp = Employe.objects.create(code="EMP-X", civilite="masculin", nom="Test")
        s = Sanction.objects.create(employe=emp, faits="Retards", date_constat=date.today(), statut=Sanction.Statut.INSTRUITE)
        self.assert400(f"/api/rh-paie/sanctions/{s.pk}/decider/", {"date_decision": "32/01/2026"})

    def test_assurance_renouveler(self):
        a = Assurance.objects.create(
            type="rc_pro", numero_police="POL-1", date_debut=date.today() - timedelta(days=300),
            date_echeance=date.today() + timedelta(days=60),
        )
        url = f"/api/juridique/assurances/{a.pk}/renouveler/"
        self.assert400(url, {"date_echeance": "bientôt"})
        self.assert400(url, {"date_echeance": str(date.today())})  # antérieure à l'échéance en cours

    def test_document_rollback_version_mal_formee(self):
        doc = Document.objects.create(title="Procédure soudage", status=Document.Status.DRAFT)
        r = self.post(f"/api/documents/documents/{doc.pk}/rollback/", {"version_id": "abc"})
        self.assertIn(r.status_code, (400, 404), r.content)
