"""Lot 12 (2026-10-17) — aucun salarié non habilité pointé sur un chantier (CDC M9 §10.8 / §10.11, M7 §9.11).

Un salarié (compte relié à une fiche RH) ne peut être pointé sur un OF « chantier » sans habilitation valide à la date
du pointage. Un compte sans fiche RH est refusé (habilitation invérifiable). Le pointage atelier n'est pas concerné ;
l'opérateur saisi par nom libre (sous-traitant, intérimaire) reste possible — point à arbitrer avec ETSL.
"""

from datetime import date, timedelta

from rest_framework.test import APITestCase

from rh_paie.models import Employe, Qualification
from users.models import User

from .models import OrdreFabrication


class HabilitationChantierTests(APITestCase):
    def setUp(self):
        self.chef = User.objects.create_user(email="chef@etls.ga", password="x-Audit-2026", role=User.Role.CHEF_ATELIER)
        self.client.force_authenticate(self.chef)
        self.chantier = OrdreFabrication.objects.create(label="Pose pipeline", scope="chantier")
        self.atelier = OrdreFabrication.objects.create(label="Spool", scope="atelier")
        self.ouvrier = User.objects.create_user(email="ouvrier@etls.ga", password="x-Audit-2026", role=User.Role.CHEF_ATELIER)
        self.fiche = Employe.objects.create(code="EMP-O1", civilite="masculin", nom="Ondo", user=self.ouvrier)

    def pointer(self, ordre, **kw):
        body = {"ordre": str(ordre.pk), "date": str(date.today()), "hours": "8", "worker": str(self.ouvrier.pk)}
        body.update(kw)
        return self.client.post("/api/operations/pointages/", body, format="json")

    def habiliter(self, jours=100):
        Qualification.objects.create(employe=self.fiche, type="habilitation", intitule="Travaux en hauteur",
                                     date_obtention=date.today() - timedelta(days=300),
                                     date_validite=date.today() + timedelta(days=jours))

    def test_salarie_sans_habilitation_refuse_sur_chantier(self):
        r = self.pointer(self.chantier)
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("habilitation", str(r.data).lower())

    def test_habilitation_expiree_refusee(self):
        self.habiliter(jours=-1)
        self.assertEqual(self.pointer(self.chantier).status_code, 400)

    def test_salarie_habilite_accepte(self):
        self.habiliter()
        self.assertEqual(self.pointer(self.chantier).status_code, 201)

    def test_compte_sans_fiche_rh_refuse_sur_chantier(self):
        inconnu = User.objects.create_user(email="x@etls.ga", password="x-Audit-2026", role=User.Role.CHEF_ATELIER)
        self.assertEqual(self.pointer(self.chantier, worker=str(inconnu.pk)).status_code, 400)

    def test_atelier_et_nom_libre_non_concernes(self):
        self.assertEqual(self.pointer(self.atelier).status_code, 201)
        r = self.pointer(self.chantier, worker="", worker_name="Sous-traitant SOGEC")
        self.assertEqual(r.status_code, 201, r.content)
