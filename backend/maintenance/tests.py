"""Tests M8 — Maintenance & GMAO : parc machines & équipements (RF-ERP-70…73)."""

from datetime import date, timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from logistique.models import EquipementParc
from maintenance.models import Actif, Inspection, MaintenanceSequence, OrdreTravail
from users.models import User


def make_user(role=User.Role.MAINTENANCE):
    return User.objects.create_user(
        email=f"{role.lower()}@etls.ga",
        password="test1234",
        first_name=role,
        last_name="Test",
        role=role,
    )


class M8BaseTest(APITestCase):
    def setUp(self):
        self.maint = make_user(User.Role.MAINTENANCE)
        self.dir_op = make_user(User.Role.DIRECTEUR_OPERATIONS)
        self.rh = make_user(User.Role.RH)
        self.comptable = make_user(User.Role.COMPTABLE)
        self.actif = Actif.objects.create(
            designation="Groupe de soudage",
            categorie=Actif.Categorie.MACHINE,
            numero_serie="SN-1",
        )
        self.gr = EquipementParc.objects.create(
            label="Grue GR 25t",
            categorie=EquipementParc.Categorie.LEVAGE,
            compteur_type=EquipementParc.Compteur.HEURES,
            compteur_value=1500,
            is_global_rental=True,
            signe_618=True,
        )

    def auth(self, user=None):
        self.client.force_authenticate(user or self.maint)


class SequencesTests(M8BaseTest):
    def test_actif_code_sequence(self):
        a = Actif.objects.create(designation="Chariot")
        self.assertTrue(a.code.startswith("EQ"))

    def test_ot_code_sequence(self):
        ot = OrdreTravail.objects.create(actif=self.actif, description="Vidange")
        self.assertTrue(ot.code.startswith("OT"))
        ot2 = OrdreTravail.objects.create(actif=self.actif, description="Réglage")
        self.assertNotEqual(ot.code, ot2.code)

    def test_inspection_code_sequence(self):
        insp = Inspection.objects.create(
            actif=self.actif, date_inspection=date.today()
        )
        self.assertTrue(insp.code.startswith("INS"))


class ParcTests(M8BaseTest):
    def test_compteur_gr_lecture_seule(self):
        gr_actif = Actif.objects.create(
            designation="Grue liée GR",
            is_global_rental=True,
            equipement_gr=self.gr,
            compteur_value=10,
        )
        self.assertEqual(gr_actif.compteur_lecture, 1500)
        self.assertEqual(gr_actif.compteur_lecture, self.gr.compteur_value)

    def test_actif_gr_requiert_lien(self):
        try:
            Actif.objects.create(designation="GR sans lien", is_global_rental=True)
            self.fail("clean n'a pas levé ValidationError")
        except Exception:
            pass

    def test_filtres_arretes_et_gr(self):
        self.auth()
        Actif.objects.create(designation="En panne", statut=Actif.Statut.EN_PANNE)
        Actif.objects.create(
            designation="Grue GR", is_global_rental=True, equipement_gr=self.gr
        )
        res = self.client.get("/api/maintenance/actifs/?arretes=1")
        self.assertEqual(len(res.data["results"]), 1)
        res = self.client.get("/api/maintenance/actifs/?global_rental=1")
        self.assertEqual(len(res.data["results"]), 1)
        self.assertIs(res.data["results"][0]["is_global_rental"], True)


class OtWorkflowTests(M8BaseTest):
    def _ot(self, statut=OrdreTravail.Statut.DEMANDE, actif=None):
        return OrdreTravail.objects.create(
            actif=actif or self.actif,
            type_ot=OrdreTravail.TypeOT.CORRECTIF,
            description="Panne compresseur",
            demandeur=self.maint,
            statut=statut,
        )

    def test_workflow_complet(self):
        self.auth()
        ot = self._ot()
        res = self.client.post(
            f"/api/maintenance/ordres/{ot.pk}/planifier/",
            {"date_planifiee": str(date.today() + timedelta(days=1))},
            format="json",
        )
        ot.refresh_from_db()
        self.assertEqual(ot.statut, OrdreTravail.Statut.PLANIFIE)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        res = self.client.post(f"/api/maintenance/ordres/{ot.pk}/demarrer/")
        ot.refresh_from_db()
        self.assertEqual(ot.statut, OrdreTravail.Statut.EN_COURS)
        self.assertEqual(ot.actif.statut, Actif.Statut.EN_MAINTENANCE)

        res = self.client.post(
            f"/api/maintenance/ordres/{ot.pk}/terminer/",
            {"rapport": "Fait", "heures_mo": "3", "cout_pieces": "4500"},
            format="json",
        )
        ot.refresh_from_db()
        self.assertEqual(ot.statut, OrdreTravail.Statut.TERMINE)
        self.assertEqual(float(ot.cout_pieces), 4500.0)

        res = self.client.post(f"/api/maintenance/ordres/{ot.pk}/cloturer/")
        ot.refresh_from_db()
        self.assertEqual(ot.statut, OrdreTravail.Statut.CLOTURE)
        self.assertEqual(ot.actif.statut, Actif.Statut.OPERATIONNEL)

    def test_cloture_mise_hors_service(self):
        self.auth()
        ot = self._ot(statut=OrdreTravail.Statut.EN_COURS)
        self.client.post(
            f"/api/maintenance/ordres/{ot.pk}/terminer/",
            {"decision": "mise_hors_service"},
            format="json",
        )
        self.client.post(f"/api/maintenance/ordres/{ot.pk}/cloturer/")
        ot.refresh_from_db()
        self.assertEqual(ot.actif.statut, Actif.Statut.HORS_SERVICE)

    def test_cloture_reforme(self):
        self.auth()
        ot = self._ot(statut=OrdreTravail.Statut.EN_COURS)
        self.client.post(
            f"/api/maintenance/ordres/{ot.pk}/terminer/",
            {"decision": "reforme"},
            format="json",
        )
        self.client.post(f"/api/maintenance/ordres/{ot.pk}/cloturer/")
        ot.refresh_from_db()
        self.assertEqual(ot.actif.statut, Actif.Statut.REFORME)

    def test_annulation(self):
        self.auth()
        ot = self._ot()
        res = self.client.post(f"/api/maintenance/ordres/{ot.pk}/annuler/")
        ot.refresh_from_db()
        self.assertEqual(ot.statut, OrdreTravail.Statut.ANNULE)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_planification_double_refusee(self):
        self.auth()
        ot = self._ot(statut=OrdreTravail.Statut.PLANIFIE)
        res = self.client.post(f"/api/maintenance/ordres/{ot.pk}/planifier/", {}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)


class CostTrackingTests(M8BaseTest):
    def test_calculs_couts(self):
        ot = OrdreTravail.objects.create(
            actif=self.actif,
            description="Grosse révision",
            heures_mo=4,
            tarif_horaire=1500,
            cout_pieces=6000,
        )
        self.assertEqual(ot.cout_main_oeuvre, 4 * 1500)
        self.assertEqual(ot.cout_total, 4 * 1500 + 6000)

    def test_montants_masques_hors_roles(self):
        self.auth(self.rh)
        ot = OrdreTravail.objects.create(
            actif=self.actif,
            description="Révision",
            heures_mo=2,
            tarif_horaire=1000,
            cout_pieces=500,
        )
        res = self.client.get(f"/api/maintenance/ordres/{ot.pk}/")
        self.assertIsNone(res.data["cout_total"])
        self.assertIs(res.data["has_amount_access"], False)


class InspectionTests(M8BaseTest):
    def test_realisation_et_generation_ot(self):
        self.auth()
        insp = Inspection.objects.create(
            actif=self.actif,
            date_inspection=date.today(),
            statut=Inspection.Statut.PLANIFIEE,
        )
        res = self.client.post(
            f"/api/maintenance/inspections/{insp.pk}/realiser/",
            {"resultat": "non_conforme", "constat": "Usure couronne"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        insp.refresh_from_db()
        self.assertEqual(insp.statut, Inspection.Statut.REALISEE)
        self.assertEqual(insp.resultat, Inspection.Resultat.NON_CONFORME)

        res = self.client.post(f"/api/maintenance/inspections/{insp.pk}/creer-ot/")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        insp.refresh_from_db()
        self.assertIsNotNone(insp.ot_genere)
        self.assertEqual(insp.ot_genere.actif, self.actif)
        self.assertEqual(insp.ot_genere.type_ot, OrdreTravail.TypeOT.CORRECTIF)

    def test_double_generation_refusee(self):
        self.auth()
        ot = OrdreTravail.objects.create(actif=self.actif, description="OT existant")
        insp = Inspection.objects.create(
            actif=self.actif,
            date_inspection=date.today(),
            statut=Inspection.Statut.REALISEE,
            resultat=Inspection.Resultat.NON_CONFORME,
            ot_genere=ot,
        )
        res = self.client.post(f"/api/maintenance/inspections/{insp.pk}/creer-ot/")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_realisation_double_refusee(self):
        self.auth()
        insp = Inspection.objects.create(
            actif=self.actif,
            date_inspection=date.today(),
            statut=Inspection.Statut.REALISEE,
        )
        res = self.client.post(f"/api/maintenance/inspections/{insp.pk}/realiser/", {}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)


class DashboardStatsTests(M8BaseTest):
    def test_stats(self):
        self.auth()
        self.actif.statut = Actif.Statut.EN_PANNE
        self.actif.save(update_fields=["statut"])
        OrdreTravail.objects.create(
            actif=self.actif,
            type_ot=OrdreTravail.TypeOT.URGENCE,
            priorite=OrdreTravail.Priorite.CRITIQUE,
            description="Urgent",
            statut=OrdreTravail.Statut.EN_COURS,
            heures_mo=2,
            tarif_horaire=1000,
        )
        Inspection.objects.create(
            actif=self.actif, date_inspection=date.today(),
            statut=Inspection.Statut.PLANIFIEE,
        )
        res = self.client.get("/api/maintenance/ordres/stats/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["ot_ouverts"], 1)
        self.assertEqual(res.data["ot_en_cours"], 1)
        self.assertEqual(res.data["ot_critiques"], 1)
        self.assertEqual(res.data["actifs_arret"], 1)
        self.assertEqual(res.data["inspections_prevues"], 1)
        self.assertEqual(res.data["cout_total"], 2000)


class PermissionsTests(M8BaseTest):
    def test_lecture_authentifiee(self):
        self.auth(self.comptable)
        res = self.client.get("/api/maintenance/actifs/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_ecriture_reservee(self):
        self.auth(self.comptable)
        res = self.client.post(
            "/api/maintenance/actifs/", {"designation": "Machine interdite"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_rh_interdit_mais_maintenance_autorise(self):
        self.auth(self.rh)
        res = self.client.post(
            "/api/maintenance/actifs/", {"designation": "Machine RH"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.dir_op)
        res = self.client.post(
            "/api/maintenance/actifs/",
            {"designation": "Machine", "categorie": "machine"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(res.data["code"].startswith("EQ"))

    def test_montants_visibles_pour_finance(self):
        self.auth(self.comptable)
        ot = OrdreTravail.objects.create(
            actif=self.actif, description="Révision", cout_pieces=999
        )
        res = self.client.get(f"/api/maintenance/ordres/{ot.pk}/")
        self.assertEqual(float(res.data["cout_pieces"]), 999)
        self.assertIs(res.data["has_amount_access"], True)