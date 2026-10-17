"""Lot 12 (2026-10-17) — cycle de l'ordre de fabrication sous contrôle (CDC M3 §6.8 / §6.11, M6 §8.10-8.11, M7 §9.10).

- Statut en lecture seule : transitions par actions `lancer` → `demarrer` → `terminer` → `liberer`, ou `annuler`.
- Démarrage d'un OF chantier : permis HSE en vigueur obligatoire (« aucun démarrage de chantier sans identification HSE »).
- Démarrage : qualifications des soudeurs affectés valides (« contrôlées à chaque OF »).
- Libération : conformité qualité (« aucun OF libéré sans conformité CND / ITP ») — au moins un contrôle validé
  conforme, aucun contrôle en attente ou non conforme, aucune NC ouverte.
"""

from datetime import date, timedelta

from rest_framework.test import APITestCase

from hse.models import PermisTravail
from qualite.models import ControleQualite, NonConformite, QualificationSoudeur, Soudeur
from users.models import User

from .models import OrdreFabrication


class CycleOfTests(APITestCase):
    def setUp(self):
        self.ops = User.objects.create_user(email="ops@etls.ga", password="x-Audit-2026", role=User.Role.DIRECTEUR_OPERATIONS)
        self.client.force_authenticate(self.ops)

    def of(self, scope="atelier", status=OrdreFabrication.Status.PREVU):
        return OrdreFabrication.objects.create(label="Spool 12 pouces", scope=scope, status=status)

    def act(self, of, action):
        return self.client.post(f"/api/operations/ordres/{of.pk}/{action}/", {}, format="json")

    def soudeur(self, valide=True):
        s = Soudeur.objects.create(nom="Mba", prenoms="Paul")
        QualificationSoudeur.objects.create(
            soudeur=s, norme="iso9606", procede="smaw", date_qualification=date.today() - timedelta(days=400),
            date_validite=date.today() + (timedelta(days=100) if valide else timedelta(days=-1)),
        )
        return s

    def test_statut_non_modifiable_par_patch(self):
        of = self.of()
        self.client.patch(f"/api/operations/ordres/{of.pk}/", {"status": "cloture"}, format="json")
        of.refresh_from_db()
        self.assertEqual(of.status, OrdreFabrication.Status.PREVU)

    def test_cycle_atelier_complet(self):
        of = self.of()
        for action, attendu in (("lancer", "lance"), ("demarrer", "en_cours"), ("terminer", "termine")):
            r = self.act(of, action)
            self.assertEqual(r.status_code, 200, (action, r.content))
            self.assertEqual(r.data["status"], attendu)
        ControleQualite.objects.create(type_controle="cnd", ordre=of, resultat="conforme", statut="valide")
        r = self.act(of, "liberer")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["status"], "cloture")

    def test_transition_hors_ordre_refusee(self):
        self.assertEqual(self.act(self.of(), "terminer").status_code, 400)

    def test_chantier_sans_permis_hse_ne_demarre_pas(self):
        of = self.of(scope="chantier", status=OrdreFabrication.Status.LANCE)
        r = self.act(of, "demarrer")
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("permis", str(r.data).lower())
        PermisTravail.objects.create(type_permis="chaud", emplacement="Rack 4", description="Soudure", ordre=of,
                                     statut=PermisTravail.Statut.VALIDE, date_debut=date.today())
        self.assertEqual(self.act(of, "demarrer").status_code, 200)

    def test_soudeur_a_qualification_expiree_bloque_le_demarrage(self):
        of = self.of(status=OrdreFabrication.Status.LANCE)
        of.soudeurs.add(self.soudeur(valide=True), self.soudeur(valide=False))
        r = self.act(of, "demarrer")
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("qualification", str(r.data).lower())

    def test_liberation_exige_la_conformite_qualite(self):
        of = self.of(status=OrdreFabrication.Status.TERMINE)
        self.assertEqual(self.act(of, "liberer").status_code, 400)  # aucun contrôle
        ctrl = ControleQualite.objects.create(type_controle="itp", ordre=of, resultat="conforme", statut="en_cours")
        self.assertEqual(self.act(of, "liberer").status_code, 400)  # ITP non validé
        ControleQualite.objects.filter(pk=ctrl.pk).update(statut="valide")
        nc = NonConformite.objects.create(description="Défaut d'alignement", controle=ctrl)
        r = self.act(of, "liberer")
        self.assertEqual(r.status_code, 400, r.content)  # NC ouverte
        self.assertIn("nc", str(r.data).lower())
        NonConformite.objects.filter(pk=nc.pk).update(statut=NonConformite.Statut.CLOTUREE)
        self.assertEqual(self.act(of, "liberer").status_code, 200)

    def test_annulation_impossible_apres_terminaison(self):
        self.assertEqual(self.act(self.of(status=OrdreFabrication.Status.TERMINE), "annuler").status_code, 400)
        self.assertEqual(self.act(self.of(), "annuler").status_code, 200)
