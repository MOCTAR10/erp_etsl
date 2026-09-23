"""Tests M7 — HSE : Hygiène, Sécurité & Environnement (RF-ERP-60…63)."""

from datetime import date, timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from commercial.models import Affaire
from hse.models import (
    ActionHse,
    BordereauDechet,
    Epi,
    EquipementAtex,
    EvaluationRisque,
    FormationSecurite,
    Incident,
    PermisTravail,
)
from referentiels.models import Partner
from users.models import User


def make_user(role=User.Role.HSE):
    return User.objects.create_user(
        email=f"{role.lower()}@etls.ga",
        password="test1234",
        first_name=role,
        last_name="Test",
        role=role,
    )


class M7BaseTest(APITestCase):
    def setUp(self):
        self.hse = make_user(User.Role.HSE)
        self.dir_op = make_user(User.Role.DIRECTEUR_OPERATIONS)
        self.rh = make_user(User.Role.RH)
        self.comptable = make_user(User.Role.COMPTABLE)
        self.affaire = Affaire.objects.create(title="Chantier pipeline Line A")
        self.transporteur = Partner.objects.create(
            code="PAR-TR-01", name="Fret Services Gabon", kind=Partner.Kind.AUTRE
        )

    def auth(self, user=None):
        self.client.force_authenticate(user or self.hse)


class SequencesTests(M7BaseTest):
    def test_permis_code_sequence(self):
        p = PermisTravail.objects.create(
            type_permis=PermisTravail.TypePermis.CHAUD,
            emplacement="Zone A",
            description="Soudure",
            date_debut=date.today(),
            date_fin=date.today() + timedelta(days=1),
        )
        self.assertTrue(p.code.startswith("PERM"))
        p2 = PermisTravail.objects.create(
            type_permis=PermisTravail.TypePermis.HAUTEUR,
            emplacement="Zone B",
            description="Travaux hauteur",
            date_debut=date.today(),
        )
        self.assertNotEqual(p.code, p2.code)
        self.assertTrue(p2.code.startswith("PERM"))

    def test_code_prefixes_all_entities(self):
        self.assertTrue(EvaluationRisque.objects.create(
            lieux="Z20", description="Incendie", probabilite=3, gravite=3
        ).code.startswith("EVR"))
        self.assertTrue(EquipementAtex.objects.create(
            designation="Scie"
        ).code.startswith("ATX"))
        inc = Incident.objects.create(
            type_incident=Incident.TypeIncident.INCIDENT,
            date_evenement=timezone.now(),
            lieu="Depot",
            description="Test",
        )
        self.assertTrue(inc.code.startswith("INC"))
        self.assertTrue(ActionHse.objects.create(
            description="Act", incident=inc
        ).code.startswith("ACT"))
        self.assertTrue(FormationSecurite.objects.create(
            theme="Securite", date_session=date.today()
        ).code.startswith("FOR"))
        self.assertTrue(Epi.objects.create(
            designation="Casque"
        ).code.startswith("EPI"))
        self.assertTrue(BordereauDechet.objects.create(
            type_dechet=BordereauDechet.TypeDechet.DIB,
            quantite=1,
        ).code.startswith("BSD"))


class PermisTravailTests(M7BaseTest):
    def _permis(self):
        return PermisTravail.objects.create(
            type_permis=PermisTravail.TypePermis.CHAUD,
            emplacement="Chantier A",
            description="Soudure raccord",
            affaire=self.affaire,
            demandeur=self.rh,
            date_debut=date.today(),
            date_fin=date.today() + timedelta(days=2),
        )

    def test_workflow_valider_demarrer_cloturer(self):
        self.auth()
        p = self._permis()
        url = f"/api/hse/permis/{p.pk}/valider/"
        res = self.client.post(url, {}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        p.refresh_from_db()
        self.assertEqual(p.statut, PermisTravail.Statut.VALIDE)
        self.assertEqual(p.validateur, self.hse)
        self.assertIsNotNone(p.date_validation)

        res = self.client.post(f"/api/hse/permis/{p.pk}/demarrer/")
        p.refresh_from_db()
        self.assertEqual(p.statut, PermisTravail.Statut.ACTIF)

        res = self.client.post(f"/api/hse/permis/{p.pk}/cloturer/")
        p.refresh_from_db()
        self.assertEqual(p.statut, PermisTravail.Statut.CLOTURE)

    def test_refus_permis(self):
        self.auth()
        p = self._permis()
        res = self.client.post(
            f"/api/hse/permis/{p.pk}/valider/", {"accept": False, "motif": "Zone non prête"},
            format="json",
        )
        p.refresh_from_db()
        self.assertEqual(p.statut, PermisTravail.Statut.REFUSE)
        self.assertIn("Zone non prête", p.notes)

    def test_permis_cloture_n_conduit_pas_a_reecrire(self):
        self.auth()
        p = self._permis()
        self.client.post(f"/api/hse/permis/{p.pk}/valider/")
        self.client.post(f"/api/hse/permis/{p.pk}/demarrer/")

    def test_validation_refusee_sans_droit(self):
        self.auth(self.comptable)
        p = self._permis()
        res = self.client.post(f"/api/hse/permis/{p.pk}/valider/", {}, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_creation_par_lecture_seule_refusee(self):
        self.auth(self.comptable)
        res = self.client.post(
            "/api/hse/permis/",
            {
                "type_permis": "chaud",
                "emplacement": "Zone C",
                "description": "Test",
                "date_debut": str(date.today()),
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_tri_type_et_statut(self):
        p = self._permis()
        self.client.force_authenticate(self.hse)
        res = self.client.get("/api/hse/permis/?type=chaud&statut=demande")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["count"], 1)
        self.assertEqual(res.data["results"][0]["id"], str(p.pk))


class EvaluationRisqueTests(M7BaseTest):
    def test_matice_criticite(self):
        self.auth()
        r = EvaluationRisque.objects.create(
            lieux="Z20", description="Incendie", probabilite=4, gravite=5
        )
        self.assertEqual(r.score, 20)
        self.assertEqual(r.criticite, EvaluationRisque.Criticite.CRITIQUE)
        r2 = EvaluationRisque.objects.create(
            lieux="Atelier", description="Coupure", probabilite=2, gravite=2
        )
        self.assertEqual(r2.criticite, EvaluationRisque.Criticite.MOYENNE)

    def test_api_critiques_filter(self):
        self.auth()
        r = EvaluationRisque.objects.create(
            lieux="Z20", description="Critique", probabilite=5, gravite=5
        )
        EvaluationRisque.objects.create(
            lieux="Bureaux", description="Faible", probabilite=1, gravite=1
        )
        res = self.client.get("/api/hse/evaluations-risques/?critiques=1")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data["results"]), 1)
        self.assertEqual(res.data["results"][0]["id"], str(r.pk))
        self.assertEqual(res.data["results"][0]["criticite"], "critique")


class EquipementAtexTests(M7BaseTest):
    def test_quarantaine_certificat_expire(self):
        self.auth()
        eq = EquipementAtex.objects.create(
            designation="Projecteur",
            date_expiration_certificat=date.today() - timedelta(days=5),
            statut=EquipementAtex.Statut.QUARANTAINE,
        )
        self.assertTrue(eq.certificat_expire)
        res = self.client.get("/api/hse/equipements-atex/?expires=1")
        self.assertEqual(len(res.data["results"]), 1)
        self.assertIs(res.data["results"][0]["certificat_expire"], True)


class IncidentTests(M7BaseTest):
    def _incident(self):
        return Incident.objects.create(
            type_incident=Incident.TypeIncident.QUASI_ACCIDENT,
            gravite=Incident.Gravite.MINEURE,
            date_evenement=timezone.now(),
            lieu="Depot",
            description="Near miss declaration",
            declared_by=self.hse,
        )

    def test_enquete_et_cloture(self):
        self.auth()
        inc = self._incident()
        res = self.client.post(f"/api/hse/incidents/{inc.pk}/ouvrir-enquete/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        inc.refresh_from_db()
        self.assertEqual(inc.statut, Incident.Statut.EN_ENQUETE)
        self.assertEqual(inc.enqueteur, self.hse)
        self.assertIsNotNone(inc.date_ouverture_enquete)

        res = self.client.post(
            f"/api/hse/incidents/{inc.pk}/cloturer/",
            {"rapport": "Rapport final", "date_rapport": str(date.today())},
            format="json",
        )
        inc.refresh_from_db()
        self.assertEqual(inc.statut, Incident.Statut.CLOTURE)
        self.assertTrue(inc.archive)
        self.assertEqual(inc.rapport, "Rapport final")

    def test_enquete_impossible_apres_cloture(self):
        self.auth()
        inc = self._incident()
        self.client.post(f"/api/hse/incidents/{inc.pk}/cloturer/")
        res = self.client.post(f"/api/hse/incidents/{inc.pk}/ouvrir-enquete/")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_description_requise(self):
        self.auth()
        res = self.client.post(
            "/api/hse/incidents/",
            {
                "type_incident": "incident",
                "date_evenement": timezone.now().isoformat(),
                "lieu": "Depot",
                "description": "   ",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_stats_dashboard(self):
        self.auth()
        inc = self._incident()
        # Ajout d'un accident récent pour vérifier le compteur « jours sans accident ».
        Incident.objects.create(
            type_incident=Incident.TypeIncident.ACCIDENT,
            gravite=Incident.Gravite.MAJEURE,
            date_evenement=timezone.now() - timedelta(days=2),
            lieu="Chantier",
            description="Blessure au doigt",
        )
        res = self.client.get("/api/hse/incidents/stats/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["incidents_ouverts"], 2)
        self.assertEqual(res.data["jours_sans_accident"], 2)


class ActionHseTests(M7BaseTest):
    def test_cloture_action(self):
        self.auth()
        inc = Incident.objects.create(
            type_incident=Incident.TypeIncident.POLLUTION,
            date_evenement=timezone.now(),
            lieu="Aire lavage",
            description="Déversement",
        )
        act = ActionHse.objects.create(
            incident=inc,
            type=ActionHse.TypeAction.CORRECTIVE,
            description="Confiner",
            responsable=self.hse,
            echeance=date.today() + timedelta(days=3),
        )
        res = self.client.post(
            f"/api/hse/actions/{act.pk}/cloturer/",
            {"efficace": True},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        act.refresh_from_db()
        self.assertEqual(act.statut, ActionHse.Statut.CLOTUREE)
        self.assertIs(act.efficace, True)
        self.assertIsNotNone(act.closed_at)


class FormationSecuriteTests(M7BaseTest):
    def test_realisation_et_filtres(self):
        self.auth()
        FormationSecurite.objects.create(
            type_session=FormationSecurite.TypeSession.CAUSERIE,
            theme="Causerie hauteur",
            date_session=date.today() + timedelta(days=3),
            statut=FormationSecurite.Statut.PLANIFIEE,
        )
        FormationSecurite.objects.create(
            type_session=FormationSecurite.TypeSession.FORMATION,
            theme="Habilitation ATEX",
            date_session=date.today() - timedelta(days=5),
            statut=FormationSecurite.Statut.REALISEE,
        )
        res = self.client.get("/api/hse/formations/?prevues=1")
        self.assertEqual(len(res.data["results"]), 1)
        self.assertEqual(res.data["results"][0]["theme"], "Causerie hauteur")


class EpiTests(M7BaseTest):
    def test_renouvellement_property(self):
        epi = Epi.objects.create(
            type_epi=Epi.TypeEpi.CASQUE,
            designation="Casque",
            beneficiaire=self.rh,
            date_dotation=date.today() - timedelta(days=100),
            date_renouvellement=date.today() + timedelta(days=10),
            statut=Epi.Statut.EN_USAGE,
        )
        self.assertTrue(epi.a_renouveler)

    def test_filtre_a_renouveler(self):
        self.auth()
        Epi.objects.create(
            designation="Casque", date_renouvellement=date.today() + timedelta(days=5),
            statut=Epi.Statut.EN_USAGE,
        )
        Epi.objects.create(
            designation="Lunettes", date_renouvellement=date.today() + timedelta(days=200),
            statut=Epi.Statut.EN_USAGE,
        )
        res = self.client.get("/api/hse/epis/?a_renouveler=1")
        self.assertEqual(len(res.data["results"]), 1)
        self.assertEqual(res.data["results"][0]["designation"], "Casque")


class BordereauDechetTests(M7BaseTest):
    def test_selection_offre_et_transporteur_partner(self):
        self.auth()
        bsd = BordereauDechet.objects.create(
            type_dechet=BordereauDechet.TypeDechet.HUILES,
            quantite=120,
            unite=BordereauDechet.Unite.L,
            transporteur=self.transporteur,
            numero_bsd="BSD-2026-001",
            statut=BordereauDechet.Statut.EMIS,
        )
        self.assertEqual(bsd.transporteur, self.transporteur)
        res = self.client.get("/api/hse/bordereaux-dechets/?dangereux=1")
        self.assertEqual(len(res.data["results"]), 1)
        self.assertEqual(res.data["results"][0]["transporteur_name"], "Fret Services Gabon")


class SerializerCrudRegressionTests(M7BaseTest):
    """Régression Schemathesis : le sérialiseur renvoyait self au lieu d'attrs
    (TypeError 'PermisTravailSerializer' object is not a mapping) — les POST/PATCH
    API avec données valides crashaient en 500."""

    def _valid_permis_payload(self):
        return {
            "type_permis": PermisTravail.TypePermis.CHAUD,
            "affaire": self.affaire.id,
            "emplacement": "Zone chaufferie",
            "description": "Soudure raccord vapeur",
            "date_debut": str(date.today()),
            "date_fin": str(date.today() + timedelta(days=1)),
        }

    def test_api_post_permis_creates(self):
        self.auth()
        res = self.client.post("/api/hse/permis/", self._valid_permis_payload(), format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.assertTrue(res.data["code"].startswith("PERM"))

    def test_api_patch_permis_updates(self):
        p = PermisTravail.objects.create(
            type_permis=PermisTravail.TypePermis.HAUTEUR,
            emplacement="V1",
            description="Avant",
            date_debut=date.today(),
        )
        self.auth()
        res = self.client.patch(
            f"/api/hse/permis/{p.pk}/",
            {"description": "Après mise à jour"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)


class PermissionsTests(M7BaseTest):
    def test_lecture_ouverte_a_tous_authentifies(self):
        self.auth(self.comptable)
        res = self.client.get("/api/hse/incidents/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_ecriture_reservee_roles_hse(self):
        self.auth(self.comptable)
        res = self.client.post(
            "/api/hse/incidents/",
            {
                "type_incident": "incident",
                "date_evenement": timezone.now().isoformat(),
                "lieu": "Depot",
                "description": "Non autorisé",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_rh_peut_gerer_epi_et_formations(self):
        self.auth(self.rh)
        res = self.client.post(
            "/api/hse/epis/",
            {"designation": "Gants", "type_epi": "gants", "date_dotation": str(date.today())},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        res = self.client.post(
            "/api/hse/formations/",
            {"theme": "Briefing", "date_session": str(date.today() + timedelta(days=1))},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    def test_validation_permis_reservee_hse_ou_hierarchie(self):
        self.auth(self.rh)
        p = PermisTravail.objects.create(
            type_permis=PermisTravail.TypePermis.CHAUD,
            emplacement="Zone A",
            description="Soudure",
            date_debut=date.today(),
        )
        res = self.client.post(f"/api/hse/permis/{p.pk}/valider/", {}, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.dir_op)
        res = self.client.post(f"/api/hse/permis/{p.pk}/valider/", {}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)