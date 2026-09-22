"""Tests M9 — Module RH & Paie (RF-ERP-80…83)."""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from users.models import User

from .models import (
    BulletinLigne,
    BulletinPaie,
    ContratTravail,
    DemandeRecrutement,
    DemandesConge,
    Employe,
    Formation,
    Qualification,
    RhPaieSequence,
    RubriquePaie,
    SaisieTemps,
    Sanction,
)

User = get_user_model()

BASE = "/api/rh-paie/"


def _auth(client, email):
    r = client.post(
        "/api/users/token/", {"email": email, "password": "Etls#Demo2026"}, format="json"
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")


class BaseRHTest(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@etls.local", password="Etls#Demo2026",
            role=User.Role.ADMIN, first_name="Admin",
        )
        self.rh = User.objects.create_user(
            email="rh@etls.local", password="Etls#Demo2026",
            role=User.Role.RH, first_name="RH",
        )
        self.comptable = User.objects.create_user(
            email="compta@etls.local", password="Etls#Demo2026",
            role=User.Role.COMPTABLE, first_name="Compta",
        )
        self.ouvrier = User.objects.create_user(
            email="ouvrier@etls.local", password="Etls#Demo2026",
            role=User.Role.CHEF_ATELIER, first_name="Ouvrier",
        )
        self.employe = Employe.objects.create(
            civilite=Employe.Sexe.MASCULIN, nom="TESTO", prenom="Alice",
            categorie=Employe.Categorie.CADRE, departement="Projets",
            statut=Employe.Statut.ACTIF,
        )
        self.employe2 = Employe.objects.create(
            civilite=Employe.Sexe.FEMININ, nom="SECOND", prenom="Bob",
            categorie=Employe.Categorie.OUVRIER, statut=Employe.Statut.ACTIF,
        )


class SequenceTests(BaseRHTest):
    def test_codes_auto_generes(self):
        self.assertTrue(self.employe.code.startswith("EMP"))
        self.assertTrue(self.employe2.code.startswith("EMP"))
        self.assertNotEqual(self.employe.code, self.employe2.code)

    def test_sequence_increments(self):
        seq = RhPaieSequence.objects.create(kind="CTR", prefix="CTR001", padding=3)
        seq.save()
        n1 = RhPaieSequence.next_for("CTR", "CTR001")
        n2 = RhPaieSequence.next_for("CTR", "CTR001")
        self.assertEqual(n1, "CTR001001")
        self.assertEqual(n2, "CTR001002")


class EmployeTests(BaseRHTest):
    def test_employes_lecture_authentifiee(self):
        _auth(self.client, "compta@etls.local")
        r = self.client.get(f"{BASE}employes/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(r.data["results"]), 2)

    def test_employes_non_authentifie_403(self):
        r = self.client.get(f"{BASE}employes/")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_employes_ecriture_rh_ok(self):
        _auth(self.client, "rh@etls.local")
        r = self.client.post(
            f"{BASE}employes/",
            {
                "civilite": "feminin", "nom": "NOUVEAU", "prenom": "Celine",
                "categorie": "agent_maitrise", "departement": "RH",
                "statut": "actif", "date_embauche": "2024-01-01",
            },
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertTrue(r.json()["code"].startswith("EMP"))
        self.assertEqual(r.json()["nom_complet"], "Celine NOUVEAU")
        self.assertEqual(r.json()["solde_conges"], "30.0")

    def test_employes_ecriture_non_rh_interdite(self):
        _auth(self.client, "compta@etls.local")
        r = self.client.post(
            f"{BASE}employes/",
            {"civilite": "masculin", "nom": "INTERDIT", "statut": "actif"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_solde_conges_decremente_apres_conge_valide(self):
        DemandesConge.objects.create(
            employe=self.employe, type=DemandesConge.Type.ANNUEL,
            date_debut=date(2026, 5, 1), date_fin=date(2026, 5, 25),
            nb_jours=25, statut=DemandesConge.Statut.VALIDE_RH,
        )
        self.assertEqual(self.employe.solde_conges, 5.0)

    def test_stats_dashboard(self):
        _auth(self.client, "rh@etls.local")
        r = self.client.get(f"{BASE}employes/stats/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.json()["effectif"], 2)


class ContratTests(BaseRHTest):
    def setUp(self):
        super().setUp()
        self.contrat = ContratTravail.objects.create(
            employe=self.employe, type=ContratTravail.Type.CDD,
            date_debut=date(2024, 1, 1), salaire_base=1_000_000,
            date_fin=date.today() + timedelta(days=20), statut=ContratTravail.Statut.ACTIF,
        )

    def test_contrat_a_renouveler(self):
        _auth(self.client, "rh@etls.local")
        r = self.client.get(f"{BASE}contrats/?a_renouveler=1")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(r.data["results"]), 1)

    def test_salaire_masque_pour_chef_atelier(self):
        _auth(self.client, "ouvrier@etls.local")
        r = self.client.get(f"{BASE}contrats/")
        self.assertEqual(r.data["results"][0]["salaire_base"], None)

    def test_salaire_visible_pour_rh(self):
        _auth(self.client, "rh@etls.local")
        r = self.client.get(f"{BASE}contrats/")
        self.assertEqual(r.data["results"][0]["salaire_base"], "1000000.00")

    def test_renouvellement_non_detecte(self):
        _auth(self.client, "rh@etls.local")
        self.contrat.date_fin = date.today() + timedelta(days=200)
        self.contrat.save()
        r = self.client.get(f"{BASE}contrats/?a_renouveler=1")
        self.assertEqual(len(r.data["results"]), 0)


class CongeTests(BaseRHTest):
    def setUp(self):
        super().setUp()
        self.conge = DemandesConge.objects.create(
            employe=self.employe, type=DemandesConge.Type.MALADIE,
            date_debut=date(2026, 8, 1), date_fin=date(2026, 8, 10),
            nb_jours=7, statut=DemandesConge.Statut.DEMANDE,
        )

    def test_circuit_validation_complet(self):
        _auth(self.client, "rh@etls.local")
        r = self.client.post(f"{BASE}conges/{self.conge.pk}/approuver/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.json()["statut"], "approuve")
        r = self.client.post(f"{BASE}conges/{self.conge.pk}/valider/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.json()["statut"], "valide")

    def test_approuver_deux_fois_interdit(self):
        _auth(self.client, "rh@etls.local")
        self.client.post(f"{BASE}conges/{self.conge.pk}/approuver/")
        r = self.client.post(f"{BASE}conges/{self.conge.pk}/approuver/")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_refus_apres_validation_interdit(self):
        _auth(self.client, "rh@etls.local")
        self.client.post(f"{BASE}conges/{self.conge.pk}/approuver/")
        self.client.post(f"{BASE}conges/{self.conge.pk}/valider/")
        r = self.client.post(f"{BASE}conges/{self.conge.pk}/refuser/")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


class SanctionTests(BaseRHTest):
    def setUp(self):
        super().setUp()
        self.sanction = Sanction.objects.create(
            employe=self.employe, type=Sanction.Type.AVERTISSEMENT,
            faits="Absence non justifiée", date_constat=date(2026, 7, 1),
            statut=Sanction.Statut.CONSTATE,
        )

    def test_cycle_instruction_decision_archivage(self):
        _auth(self.client, "rh@etls.local")
        r = self.client.post(f"{BASE}sanctions/{self.sanction.pk}/instruire/")
        self.assertEqual(r.json()["statut"], "instruite")
        r = self.client.post(f"{BASE}sanctions/{self.sanction.pk}/decider/")
        self.assertEqual(r.json()["statut"], "decidee")
        self.assertIsNotNone(r.json()["date_decision"])
        r = self.client.post(f"{BASE}sanctions/{self.sanction.pk}/archiver/")
        self.assertEqual(r.json()["statut"], "archivee")


class FormationTests(BaseRHTest):
    def test_cycle_formation(self):
        _auth(self.client, "rh@etls.local")
        f = Formation.objects.create(
            theme="Formation conduite de grue", organisme="AFPA",
            date_session=date(2026, 9, 1), type=Formation.Type.PLANIFIE,
        )
        f.participants.add(self.employe)
        r = self.client.get(f"{BASE}formations/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["results"][0]["nb_participants"], 1)
        r = self.client.post(f"{BASE}formations/{f.pk}/realiser/")
        self.assertEqual(r.json()["type"], "realisee")


class RecrutementTests(BaseRHTest):
    def test_validation_et_integration(self):
        _auth(self.client, "rh@etls.local")
        dr = DemandeRecrutement.objects.create(
            poste="Chef de chantier", type=DemandeRecrutement.Type.REMPLACEMENT,
            justification="Départ retraite", statut=DemandeRecrutement.Statut.DEMANDE,
        )
        r = self.client.post(f"{BASE}recrutements/{dr.pk}/valider/")
        self.assertEqual(r.json()["statut"], "validee")
        r = self.client.post(f"{BASE}recrutements/{dr.pk}/integrer/")
        self.assertEqual(r.json()["statut"], "integre")

    def test_integration_sans_validation_interdite(self):
        _auth(self.client, "rh@etls.local")
        dr = DemandeRecrutement.objects.create(
            poste="Ouvrier", type=DemandeRecrutement.Type.CREATION,
            justification="Besoin", statut=DemandeRecrutement.Statut.DEMANDE,
        )
        r = self.client.post(f"{BASE}recrutements/{dr.pk}/integrer/")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


class TempsTests(BaseRHTest):
    def test_saisie_et_transfert_paie(self):
        _auth(self.client, "rh@etls.local")
        st = SaisieTemps.objects.create(
            employe=self.employe, date=date(2026, 9, 15), heures=8,
            type=SaisieTemps.Type.SUPPLEMENTAIRE, statut=SaisieTemps.Statut.SAISI,
        )
        r = self.client.post(f"{BASE}temps/{st.pk}/transferer-paie/")
        self.assertEqual(r.json()["statut"], "transfere")

    def test_heures_strictement_positives(self):
        _auth(self.client, "rh@etls.local")
        r = self.client.post(
            f"{BASE}temps/",
            {"employe": str(self.employe.pk), "date": "2026-09-15", "heures": -2},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


class BulletinTests(BaseRHTest):
    def setUp(self):
        super().setUp()
        RubriquePaie.objects.create(
            code="SAL", label="Salaire de base", nature="gain", base="salaire", ordre=10
        )
        RubriquePaie.objects.create(
            code="CNS", label="Cotisation CNSS", nature="retenue", base="salaire",
            taux=5, ordre=50,
        )

    def test_bulletin_creation_et_calcul(self):
        _auth(self.client, "rh@etls.local")
        rubs = {r.code: str(r.pk) for r in RubriquePaie.objects.all()}
        r = self.client.post(
            f"{BASE}bulletins/",
            {
                "employe": str(self.employe.pk), "periode": "2026-09-01",
                "salaire_base": "500000",
                "lignes": [
                    {"rubrique": rubs["SAL"], "libelle": "Salaire de base", "montant": "500000"},
                ],
            },
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        data = r.json()
        self.assertEqual(data["statut"], "brouillon")
        self.assertEqual(data["brut"], "500000.00")

    def test_recalcul_avec_retenue(self):
        _auth(self.client, "rh@etls.local")
        rubs = {r.code: str(r.pk) for r in RubriquePaie.objects.all()}
        b = BulletinPaie.objects.create(
            employe=self.employe, periode=date(2026, 9, 1),
            salaire_base=500_000, statut=BulletinPaie.Statut.BROUILLON,
        )
        BulletinLigne.objects.create(
            bulletin=b, rubrique=RubriquePaie.objects.get(code="SAL"),
            libelle="Base", montant=500_000,
        )
        BulletinLigne.objects.create(
            bulletin=b, rubrique=RubriquePaie.objects.get(code="CNS"),
            libelle="Cotisation 5%", montant=25_000,
        )
        r = self.client.post(f"{BASE}bulletins/{b.pk}/calculer/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.json()["brut"], "500000.00")
        self.assertEqual(r.json()["net"], "475000.00")

    def test_validation_puis_cloture(self):
        _auth(self.client, "rh@etls.local")
        b = BulletinPaie.objects.create(
            employe=self.employe, periode=date(2026, 9, 1),
            salaire_base=400_000, statut=BulletinPaie.Statut.BROUILLON,
        )
        r = self.client.post(f"{BASE}bulletins/{b.pk}/valider/")
        self.assertEqual(r.json()["statut"], "valide")
        r = self.client.post(f"{BASE}bulletins/{b.pk}/cloturer/")
        self.assertEqual(r.json()["statut"], "cloture")

    def test_paie_restreinte_non_rh_forbidden(self):
        _auth(self.client, "ouvrier@etls.local")
        r = self.client.get(f"{BASE}bulletins/")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_paie_visible_pour_rh(self):
        _auth(self.client, "rh@etls.local")
        BulletinPaie.objects.create(
            employe=self.employe, periode=date(2026, 9, 1), salaire_base=400_000,
            brut=400_000, net=370_000, statut=BulletinPaie.Statut.VALIDE,
        )
        r = self.client.get(f"{BASE}bulletins/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["results"][0]["net"], "370000.00")

    def test_masse_salariale(self):
        _auth(self.client, "rh@etls.local")
        BulletinPaie.objects.create(
            employe=self.employe, periode=date(2026, 9, 1), salaire_base=400_000,
            brut=400_000, net=370_000, statut=BulletinPaie.Statut.VALIDE,
        )
        BulletinPaie.objects.create(
            employe=self.employe2, periode=date(2026, 9, 1), salaire_base=300_000,
            brut=300_000, net=275_000, statut=BulletinPaie.Statut.VALIDE,
        )
        r = self.client.get(f"{BASE}bulletins/masse/?mois=2026-09")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.json()["bulletins"], 2)
        self.assertEqual(r.json()["brut_total"], "700000.00")


class PermissionTests(BaseRHTest):
    def test_rubriques_lecture_seule_pour_comptable(self):
        _auth(self.client, "compta@etls.local")
        RubriquePaie.objects.create(code="PAN", label="Panier", nature="gain", ordre=1)
        r = self.client.get(f"{BASE}rubriques/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        r = self.client.post(
            f"{BASE}rubriques/",
            {"code": "X", "label": "X", "nature": "gain", "ordre": 99},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_rh_peut_gerer_rubriques(self):
        _auth(self.client, "rh@etls.local")
        r = self.client.post(
            f"{BASE}rubriques/",
            {"code": "PAN", "label": "Prime panier", "nature": "gain", "ordre": 20},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)