"""Audit métier Couche D (2026-10-16) — les alertes agrégées respectent les droits de lecture.

B1 : un utilisateur sans accès RH / juridique / maintenance ne reçoit pas leurs alertes
     (contrats nominatifs, qualifications…) ; les documents restreints (paie) n'y figurent pas.
"""

from datetime import timedelta

from django.core.files.base import ContentFile
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from documents.models import Document, DocumentType
from rh_paie.models import ContratTravail, Employe
from users.models import User


class AlertesDroitsTests(TestCase):
    def setUp(self):
        today = timezone.localdate()
        emp = Employe.objects.create(
            civilite=Employe.Sexe.MASCULIN, nom="DUPONT", prenom="Jean",
            categorie=Employe.Categorie.CADRE, statut=Employe.Statut.ACTIF,
        )
        ContratTravail.objects.create(
            employe=emp, type=ContratTravail.Type.CDD, date_debut=today - timedelta(days=300),
            date_fin=today + timedelta(days=20), statut=ContratTravail.Statut.ACTIF,
            salaire_base=500000,
        )
        paie = DocumentType.objects.create(
            code="paie-audit", label="Bulletins", retention_years=1, is_restricted_rh=True
        )
        self.doc_paie = Document(
            title="BULLETIN CONFIDENTIEL DUPONT", type=paie,
            document_date=today - timedelta(days=364),
        )
        self.doc_paie.save()
        self.rh = User.objects.create_user(email="rh@etls.ga", password="x-Audit-2026", role=User.Role.RH)
        self.sans_module = User.objects.create_user(
            email="service@etls.ga", password="x-Audit-2026", role=User.Role.CHEF_SERVICE
        )

    def alertes(self, user):
        c = APIClient()
        c.force_authenticate(user)
        r = c.get("/api/analytics/alertes/")
        self.assertEqual(r.status_code, 200)
        return r.data

    def test_utilisateur_sans_module_ne_voit_ni_rh_ni_documents_restreints(self):
        data = self.alertes(self.sans_module)
        self.assertEqual(data["rh"], [])
        self.assertNotIn("BULLETIN CONFIDENTIEL", str(data["documents"]))
        self.assertEqual(data["juridique"]["conventions"], [])

    def test_rh_voit_ses_contrats_et_les_documents_de_paie(self):
        data = self.alertes(self.rh)
        self.assertTrue(any(i["type"] == "contrat_rh" for i in data["rh"]))
        self.assertIn("BULLETIN CONFIDENTIEL", str(data["documents"]))

    def test_compteurs_coherents_avec_ce_qui_est_visible(self):
        data = self.alertes(self.sans_module)
        self.assertEqual(data["total"], sum(data["compteurs"].values()))
        self.assertEqual(data["total"], len(data["documents"]))
