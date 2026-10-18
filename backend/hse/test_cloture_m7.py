"""Clôture M7 HSE (2026-10-18) — tests de recette par critère CDC.

Critères : habilitations contrôlées / aucun départ sans habilitation ; audits & inspections HSE ; DUER formel ;
plans d'urgence et exercices (ISO 14001).
"""

from datetime import date, timedelta

from rest_framework.test import APITestCase

from rh_paie.models import Employe, Qualification
from users.models import User

from .models import ActionHse, PermisTravail


def user(email, role):
    return User.objects.create_user(email=email, password="x-M7-2026", role=role, first_name=email[:3])


def employe(code, nom):
    return Employe.objects.create(code=code, nom=nom, prenom="X", statut=Employe.Statut.ACTIF)


class HabilitationPermisTests(APITestCase):
    """Aucun départ (démarrage de permis) sans habilitation valide de chaque intervenant."""

    def setUp(self):
        self.hse = user("hse@etls.ga", User.Role.HSE)
        self.client.force_authenticate(self.hse)
        self.e1 = employe("EMP-H1", "Alpha")
        self.e2 = employe("EMP-H2", "Beta")
        self.client.post("/api/hse/exigences-habilitation/", {"type_permis": "hauteur", "mot_cle": "hauteur"}, format="json")
        self.permis = PermisTravail.objects.create(
            type_permis="hauteur", emplacement="Rack", description="Travaux", date_debut=date.today(),
            statut=PermisTravail.Statut.VALIDE,
        )
        self.permis.intervenants.set([self.e1, self.e2])

    def qualif(self, emp, validite):
        return Qualification.objects.create(employe=emp, intitule="Habilitation travail en hauteur", date_validite=validite)

    def demarrer(self):
        return self.client.post(f"/api/hse/permis/{self.permis.pk}/demarrer/")

    def test_exigence_creee(self):
        r = self.client.get("/api/hse/exigences-habilitation/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["count"], 1)

    def test_demarrage_bloque_sans_habilitation(self):
        self.qualif(self.e1, date.today() + timedelta(days=100))
        r = self.demarrer()
        self.assertEqual(r.status_code, 400)
        self.assertIn("Beta", str(r.data["detail"]))
        self.assertNotIn("Alpha", str(r.data["detail"]))

    def test_demarrage_bloque_habilitation_expiree(self):
        self.qualif(self.e1, date.today() + timedelta(days=100))
        self.qualif(self.e2, date.today() - timedelta(days=1))
        self.assertEqual(self.demarrer().status_code, 400)

    def test_demarrage_ok_si_tous_habilites(self):
        self.qualif(self.e1, date.today() + timedelta(days=100))
        self.qualif(self.e2, None)  # sans date de fin = sans péremption
        r = self.demarrer()
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["statut"], "actif")

    def test_pas_d_exigence_pour_autre_type(self):
        p = PermisTravail.objects.create(
            type_permis="froid", emplacement="Z", description="d", date_debut=date.today(),
            statut=PermisTravail.Statut.VALIDE,
        )
        p.intervenants.set([self.e1])
        r = self.client.post(f"/api/hse/permis/{p.pk}/demarrer/")
        self.assertEqual(r.status_code, 200, r.content)

    def test_intervenants_via_api(self):
        r = self.client.post("/api/hse/permis/", {
            "type_permis": "hauteur", "emplacement": "Z", "description": "d",
            "intervenants": [str(self.e1.pk)],
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual([str(i) for i in r.data["intervenants"]], [str(self.e1.pk)])


class AuditHseTests(APITestCase):
    def setUp(self):
        self.hse = user("hse@etls.ga", User.Role.HSE)
        self.client.force_authenticate(self.hse)
        r = self.client.post("/api/hse/audits/", {
            "type_audit": "inspection", "zone": "Atelier soudure", "date_prevue": str(date.today()),
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.audit = r.data["id"]
        self.assertTrue(r.data["code"].startswith("AUD"))
        self.assertEqual(r.data["statut"], "planifie")

    def constat(self, **kw):
        data = {"audit": self.audit, "description": "Extincteur périmé", "gravite": "majeur", **kw}
        return self.client.post("/api/hse/constats-audit/", data, format="json")

    def test_statut_en_lecture_seule(self):
        r = self.client.patch(f"/api/hse/audits/{self.audit}/", {"statut": "cloture"}, format="json")
        self.assertEqual(r.data["statut"], "planifie")

    def test_cloture_exige_realisation(self):
        r = self.client.post(f"/api/hse/audits/{self.audit}/cloturer/")
        self.assertEqual(r.status_code, 400)

    def test_cloture_bloquee_par_ecart_sans_action(self):
        self.client.post(f"/api/hse/audits/{self.audit}/realiser/", {"score": 72}, format="json")
        self.constat()
        r = self.client.post(f"/api/hse/audits/{self.audit}/cloturer/")
        self.assertEqual(r.status_code, 400)
        self.assertIn("action", str(r.data["detail"]).lower())

    def test_cloture_bloquee_par_action_ouverte_puis_ok(self):
        self.client.post(f"/api/hse/audits/{self.audit}/realiser/", {"score": 72}, format="json")
        c = self.constat().data
        act = ActionHse.objects.create(description="Remplacer extincteur")
        self.client.patch(f"/api/hse/constats-audit/{c['id']}/", {"action": str(act.pk)}, format="json")
        self.assertEqual(self.client.post(f"/api/hse/audits/{self.audit}/cloturer/").status_code, 400)
        self.client.post(f"/api/hse/actions/{act.pk}/cloturer/")
        r = self.client.post(f"/api/hse/audits/{self.audit}/cloturer/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["statut"], "cloture")

    def test_constat_conforme_ne_demande_pas_d_action(self):
        self.client.post(f"/api/hse/audits/{self.audit}/realiser/", {"score": 95}, format="json")
        self.constat(gravite="conforme", description="EPI conformes")
        self.assertEqual(self.client.post(f"/api/hse/audits/{self.audit}/cloturer/").status_code, 200)

    def test_audit_clos_scelle(self):
        self.client.post(f"/api/hse/audits/{self.audit}/realiser/", {"score": 95}, format="json")
        self.client.post(f"/api/hse/audits/{self.audit}/cloturer/")
        self.assertEqual(self.constat().status_code, 400)
        r = self.client.patch(f"/api/hse/audits/{self.audit}/", {"zone": "autre"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_score_borne(self):
        r = self.client.post(f"/api/hse/audits/{self.audit}/realiser/", {"score": 140}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_auditeur_pose_cote_serveur(self):
        self.client.post(f"/api/hse/audits/{self.audit}/realiser/", {"score": 80}, format="json")
        r = self.client.get(f"/api/hse/audits/{self.audit}/")
        self.assertEqual(r.data["realise_par"], self.hse.pk)


class DuerTests(APITestCase):
    def setUp(self):
        self.hse = user("hse@etls.ga", User.Role.HSE)
        self.dg = user("dg@etls.ga", User.Role.PDG)
        self.client.force_authenticate(self.hse)
        r = self.client.post("/api/hse/duer/", {"annee": 2026, "perimetre": "Site de Port-Gentil"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.duer = r.data["id"]

    def risque(self, **kw):
        data = {"lieux": "Atelier", "description": "Chute", "probabilite": 4, "gravite": 4, "duer": self.duer, **kw}
        return self.client.post("/api/hse/evaluations-risques/", data, format="json")

    def approuver(self):
        return self.client.post(f"/api/hse/duer/{self.duer}/approuver/")

    def test_approbation_exige_des_risques(self):
        self.assertEqual(self.approuver().status_code, 400)

    def test_risque_eleve_sans_mesure_bloque(self):
        self.assertEqual(self.risque().status_code, 201)
        r = self.approuver()
        self.assertEqual(r.status_code, 400)
        self.assertIn("mesure", str(r.data["detail"]).lower())

    def test_approbation_ok_puis_scelle(self):
        self.risque(mesure="Garde-corps")
        r = self.approuver()
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["statut"], "approuve")
        self.assertEqual(r.data["approuve_par"], self.hse.pk)
        self.assertEqual(r.data["nb_risques"], 1)
        # scellé : plus de modification ni de nouveau risque rattaché
        self.assertEqual(self.client.patch(f"/api/hse/duer/{self.duer}/", {"perimetre": "x"}, format="json").status_code, 400)
        self.assertEqual(self.risque(mesure="m").status_code, 400)

    def test_une_seule_version_approuvee_par_annee_et_perimetre(self):
        self.risque(mesure="Garde-corps")
        self.approuver()
        r = self.client.post("/api/hse/duer/", {"annee": 2026, "perimetre": "Site de Port-Gentil"}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["version"], 2)

    def test_revue_annuelle(self):
        from django.utils import timezone

        from .models import Duer

        self.risque(mesure="m")
        self.approuver()
        Duer.objects.filter(pk=self.duer).update(approuve_le=timezone.now() - timedelta(days=400))
        r = self.client.get(f"/api/hse/duer/{self.duer}/")
        self.assertTrue(r.data["a_revoir"])


class PlanUrgenceTests(APITestCase):
    def setUp(self):
        self.hse = user("hse@etls.ga", User.Role.HSE)
        self.client.force_authenticate(self.hse)
        r = self.client.post("/api/hse/plans-urgence/", {
            "type_plan": "incendie", "intitule": "Évacuation atelier", "periodicite_mois": 6,
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.plan = r.data["id"]

    def exercice(self, d, **kw):
        data = {"plan": self.plan, "date_exercice": str(d), "participants": 25, "resultat": "satisfaisant", **kw}
        return self.client.post("/api/hse/exercices-urgence/", data, format="json")

    def test_sans_exercice_en_retard(self):
        r = self.client.get(f"/api/hse/plans-urgence/{self.plan}/")
        self.assertTrue(r.data["en_retard"])
        self.assertIsNone(r.data["dernier_exercice"])

    def test_exercice_recent_pas_en_retard(self):
        self.assertEqual(self.exercice(date.today() - timedelta(days=30)).status_code, 201)
        r = self.client.get(f"/api/hse/plans-urgence/{self.plan}/")
        self.assertFalse(r.data["en_retard"])
        self.assertEqual(r.data["dernier_exercice"], str(date.today() - timedelta(days=30)))
        self.assertTrue(r.data["prochain_exercice"] > str(date.today()))

    def test_exercice_ancien_en_retard(self):
        self.exercice(date.today() - timedelta(days=400))
        r = self.client.get("/api/hse/plans-urgence/?en_retard=1")
        self.assertEqual(r.data["count"], 1)

    def test_exercice_futur_refuse(self):
        self.assertEqual(self.exercice(date.today() + timedelta(days=3)).status_code, 400)

    def test_exercice_non_satisfaisant_exige_observations(self):
        self.assertEqual(self.exercice(date.today(), resultat="insuffisant").status_code, 400)
        self.assertEqual(self.exercice(date.today(), resultat="insuffisant", observations="Alarme inaudible").status_code, 201)

    def test_periodicite_positive(self):
        r = self.client.post("/api/hse/plans-urgence/", {"type_plan": "incendie", "intitule": "x", "periodicite_mois": 0}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_lecture_chef_service_refusee(self):
        self.client.force_authenticate(user("cs@etls.ga", User.Role.CHEF_SERVICE))
        self.assertEqual(self.client.get("/api/hse/plans-urgence/").status_code, 403)
