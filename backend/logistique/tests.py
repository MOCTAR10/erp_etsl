from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command

from rest_framework import status
from rest_framework.test import APITestCase

from referentiels.models import Currency, Partner

from .models import (
    AffectationParc,
    DemandeMobilisation,
    EquipementParc,
    LectureCompteur,
    LocationGR,
)

User = get_user_model()


def _gr_partner():
    currency, _ = Currency.objects.get_or_create(code="XAF")
    partner, _ = Partner.objects.get_or_create(
        code="GR-TEST",
        defaults={"name": "GLOBAL RENTAL Test", "kind": Partner.Kind.FOURNISSEUR,
                  "currency": currency, "is_global_rental": True},
    )
    return partner


def _non_gr_partner():
    return Partner.objects.get_or_create(
        code="FU-TEST",
        defaults={"name": "Fournisseur Test", "kind": Partner.Kind.FOURNISSEUR,
                  "is_global_rental": False},
    )[0]


class SeedLogistiqueTests(APITestCase):
    def test_seed_is_idempotent(self):
        call_command("seed_logistique_demo")
        call_command("seed_logistique_demo")
        self.assertEqual(EquipementParc.objects.count(), 3)
        self.assertEqual(DemandeMobilisation.objects.count(), 2)
        self.assertEqual(AffectationParc.objects.count(), 1)
        self.assertEqual(LocationGR.objects.count(), 1)
        self.assertEqual(LectureCompteur.objects.count(), 2)


class SequenceTests(APITestCase):
    def test_numbering_by_kind(self):
        partenaire = _gr_partner()
        eq_parc = EquipementParc.objects.create(label="Grue 25 t", categorie="levage")
        dem = DemandeMobilisation.objects.create(label="Besoin grue")
        aff = AffectationParc.objects.create(equipement=eq_parc, date_debut="2026-01-01")
        loc = LocationGR.objects.create(partenaire=partenaire, equipement=eq_parc)
        lecture = LectureCompteur.objects.create(location=loc, date="2026-01-15", valeur=10)
        self.assertEqual(eq_parc.code, "PAR00001")
        self.assertEqual(dem.code, "DEM00001")
        self.assertEqual(aff.code, "AFF00001")
        self.assertEqual(loc.code, "LOC00001")
        self.assertEqual(lecture.code, "CPT00001")
        self.assertEqual(EquipementParc.objects.create(label="Camion").code, "PAR00002")


class LogistiqueBehaviourTests(APITestCase):
    def setUp(self):
        self.gr = _gr_partner()
        self.eq = EquipementParc.objects.create(label="Grue 25 t", categorie="levage")
        self.loc = LocationGR.objects.create(
            partenaire=self.gr, equipement=self.eq, tarif=45_000, montant_estime=1_000_000
        )

    def test_location_requires_global_rental_partner(self):
        loc = LocationGR(partenaire=_non_gr_partner(), equipement=self.eq)
        with self.assertRaises(ValidationError):
            loc.full_clean()

    def test_affectation_rejected_when_equipment_en_location(self):
        self.eq.statut = EquipementParc.Statut.EN_LOCATION
        self.eq.save()
        aff = AffectationParc(equipement=self.eq, date_debut="2026-01-01")
        with self.assertRaises(ValidationError):
            aff.full_clean()

    def test_counters_ordered(self):
        self.loc.lecture_initiale = 100
        self.loc.lecture_finale = 50
        with self.assertRaises(ValidationError):
            self.loc.full_clean()

    def test_consommation(self):
        self.loc.lecture_initiale = 100
        self.loc.lecture_finale = 155
        self.assertEqual(float(self.loc.consommation), 55)

    def test_lecture_rejects_negative(self):
        lecture = LectureCompteur(location=self.loc, date="2026-01-15", valeur=-3)
        with self.assertRaises(ValidationError):
            lecture.full_clean()


class LogistiqueAPITests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@etls.local", password="MotDePasse#2026",
            role=User.Role.ADMIN, is_staff=True,
        )
        self.log = User.objects.create_user(
            email="log@etls.local", password="MotDePasse#2026",
            role=User.Role.LOGISTIQUE,
        )
        self.rh = User.objects.create_user(
            email="rh@etls.local", password="MotDePasse#2026",
            role=User.Role.RH,
        )
        self.gr = _gr_partner()
        self.eq = EquipementParc.objects.create(
            label="Chargeuse 950", categorie="engin", is_global_rental=True, proprietaire=self.gr
        )
        self.loc = LocationGR.objects.create(
            partenaire=self.gr, equipement=self.eq, tarif=45_000, montant_estime=12_600_000,
            statut=LocationGR.Statut.BROUILLON,
        )

    def test_list_requires_auth(self):
        resp = self.client.get("/api/logistique/equipements/")
        self.assertIn(
            resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        )

    def test_logistique_can_read_and_filter(self):
        self.client.force_authenticate(self.log)
        resp = self.client.get("/api/logistique/equipements/?global_rental=true")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)

    def test_rh_cannot_create_equipement(self):
        self.client.force_authenticate(self.rh)
        resp = self.client.post("/api/logistique/equipements/", {"label": "Grue X"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_logistique_can_create_equipement(self):
        self.client.force_authenticate(self.log)
        resp = self.client.post(
            "/api/logistique/equipements/",
            {"label": "Groupe électrogène 250 kVA", "categorie": "atelier"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["code"], "PAR00002")

    def test_location_created_and_amount_masked_for_rh(self):
        self.client.force_authenticate(self.rh)
        resp = self.client.post(
            "/api/logistique/locations/",
            {"partenaire": self.gr.id, "equipement": self.eq.id, "tarif": 45_000},
            format="json",
        )
        # RH n'a pas le droit d'écrire : refusé avant tout
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_amount_visible_for_admin(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.get(f"/api/logistique/locations/{self.loc.id}/")
        self.assertEqual(resp.data["montant_estime"], "12600000.00")

    def test_amount_masked_for_logistique_write_role_without_amount(self):
        self.client.force_authenticate(self.log)
        resp = self.client.get(f"/api/logistique/locations/{self.loc.id}/")
        self.assertEqual(resp.data["montant_estime"], None)

    def test_demarrer_gr_marks_en_location(self):
        self.client.force_authenticate(self.log)
        resp = self.client.post(
            f"/api/logistique/locations/{self.loc.id}/demarrer/",
            {"lecture_initiale": 1250},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["statut"], "active")
        self.eq.refresh_from_db()
        self.assertEqual(self.eq.statut, EquipementParc.Statut.EN_LOCATION)

    def test_cloturer_gr_computes_consommation_and_releases(self):
        self.loc.statut = LocationGR.Statut.ACTIVE
        self.loc.lecture_initiale = 1250
        self.loc.save()
        self.client.force_authenticate(self.log)
        resp = self.client.post(
            f"/api/logistique/locations/{self.loc.id}/cloturer/",
            {"lecture_finale": 1286},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["statut"], "terminee")
        self.assertEqual(resp.data["consommation"], "36.00")
        self.eq.refresh_from_db()
        self.assertEqual(self.eq.statut, EquipementParc.Statut.DISPONIBLE)

    def test_stats_action(self):
        self.client.force_authenticate(self.log)
        resp = self.client.get("/api/logistique/locations/stats/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["parc"]["total"], 1)
        self.assertIn("parc", resp.data)
        self.assertIn("locations", resp.data)

    def test_patch_lecture_sets_releve_par(self):
        self.client.force_authenticate(self.log)
        resp = self.client.post(
            "/api/logistique/lectures/",
            {"location": self.loc.id, "date": "2026-09-30", "valeur": 1286},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["code"], "CPT00001")
        self.assertEqual(str(resp.data["releve_par"]), str(self.log.id))