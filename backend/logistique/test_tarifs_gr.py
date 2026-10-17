"""Lot 14 (2026-10-17) — pricing GLOBAL RENTAL versionné et pénalités de retard (CDC M4 §12.4 / §12.11).

- Grille tarifaire GR versionnée : un changement de tarif = une nouvelle version datée (date d'effet), jamais une
  réécriture ; une version utilisée par une prestation ne se supprime pas.
- La prestation prend la version en vigueur à sa date de début, la plus spécifique d'abord (équipement, puis
  catégorie, puis grille générale) ; le tarif est figé au démarrage.
- Pénalités de retard : retour après la date de fin prévue → jours de retard × pénalité journalière de la version.
"""

from datetime import date, timedelta

from rest_framework.test import APITestCase

from users.models import User

from .models import EquipementParc, LocationGR, TarifGR
from .tests import _gr_partner, _non_gr_partner


class TarifGRTests(APITestCase):
    def setUp(self):
        self.logi = User.objects.create_user(email="logi@etls.ga", password="x-Audit-2026", role=User.Role.LOGISTIQUE)
        self.dop = User.objects.create_user(email="dop@etls.ga", password="x-Audit-2026", role=User.Role.DIRECTEUR_OPERATIONS)
        self.client.force_authenticate(self.dop)
        self.partner = _gr_partner()
        self.grue = EquipementParc.objects.create(label="Grue 25t", categorie=EquipementParc.Categorie.LEVAGE, is_global_rental=True)
        self.nacelle = EquipementParc.objects.create(label="Nacelle", categorie=EquipementParc.Categorie.LEVAGE, is_global_rental=True)

    def tarif(self, tarif, date_effet, **kw):
        body = {"partenaire": self.partner.pk, "periodicite": "jour", "tarif": tarif, "date_effet": str(date_effet)}
        body.update(kw)
        r = self.client.post("/api/logistique/tarifs-gr/", body, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.data

    def location(self, equipement=None, **kw):
        body = {"partenaire": self.partner.pk, "equipement": str((equipement or self.grue).pk), "periodicite": "jour",
                "date_debut": str(date.today()), "date_fin": str(date.today() + timedelta(days=10)), "tarif": "1"}
        body.update(kw)
        r = self.client.post("/api/logistique/locations/", body, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.data

    def test_versions_successives_numerotees(self):
        v1 = self.tarif("100000", date.today() - timedelta(days=60), categorie="levage")
        v2 = self.tarif("120000", date.today() - timedelta(days=5), categorie="levage")
        self.assertEqual((v1["version"], v2["version"]), (1, 2))

    def test_une_version_ne_se_reecrit_pas(self):
        v1 = self.tarif("100000", date.today())
        r = self.client.patch(f"/api/logistique/tarifs-gr/{v1['id']}/", {"tarif": "1"}, format="json")
        self.assertEqual(r.status_code, 405, r.content)

    def test_partenaire_non_gr_refuse(self):
        r = self.client.post("/api/logistique/tarifs-gr/", {"partenaire": _non_gr_partner().pk, "periodicite": "jour",
                                                             "tarif": "1000", "date_effet": str(date.today())}, format="json")
        self.assertEqual(r.status_code, 400, r.content)

    def test_location_prend_la_version_en_vigueur_la_plus_specifique(self):
        self.tarif("90000", date.today() - timedelta(days=90))  # grille générale
        self.tarif("100000", date.today() - timedelta(days=60), categorie="levage")
        self.tarif("120000", date.today() - timedelta(days=5), categorie="levage")
        self.tarif("150000", date.today() + timedelta(days=30), categorie="levage")  # pas encore en vigueur
        specifique = self.tarif("200000", date.today() - timedelta(days=1), equipement=str(self.grue.pk))
        loc = self.location(self.nacelle)
        self.assertEqual((loc["tarif"], loc["tarif_gr_version"]), ("120000.00", 2))
        loc = self.location(self.grue)
        self.assertEqual((loc["tarif"], str(loc["tarif_gr"])), ("200000.00", str(specifique["id"])))

    def test_sans_grille_le_tarif_saisi_est_conserve(self):
        self.assertEqual(self.location(tarif="75000")["tarif"], "75000.00")

    def test_tarif_fige_au_demarrage(self):
        self.tarif("100000", date.today() - timedelta(days=10))
        loc = self.location()
        r = self.client.post(f"/api/logistique/locations/{loc['id']}/demarrer/", {"lecture_initiale": "10"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        r = self.client.patch(f"/api/logistique/locations/{loc['id']}/", {"tarif": "1"}, format="json")
        self.assertEqual(r.status_code, 400, r.content)
        self.assertEqual(LocationGR.objects.get(pk=loc["id"]).tarif, 100000)

    def test_version_utilisee_non_supprimable(self):
        v1 = self.tarif("100000", date.today() - timedelta(days=10))
        self.location()
        self.assertEqual(self.client.delete(f"/api/logistique/tarifs-gr/{v1['id']}/").status_code, 409)
        self.assertTrue(TarifGR.objects.filter(pk=v1["id"]).exists())

    def demarree(self, **kw):
        loc = self.location(**kw)
        self.client.post(f"/api/logistique/locations/{loc['id']}/demarrer/", {"lecture_initiale": "10"}, format="json")
        return loc

    def test_retour_en_retard_penalise(self):
        self.tarif("100000", date.today() - timedelta(days=30), penalite_jour="25000")
        loc = self.demarree(date_debut=str(date.today() - timedelta(days=20)), date_fin=str(date.today() - timedelta(days=4)))
        r = self.client.post(f"/api/logistique/locations/{loc['id']}/cloturer/", {"lecture_finale": "50", "date_retour": str(date.today())}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.data["jours_retard"], r.data["penalite"]), (4, "100000.00"))

    def test_retour_dans_les_temps_sans_penalite(self):
        self.tarif("100000", date.today() - timedelta(days=10), penalite_jour="25000")
        loc = self.demarree()
        r = self.client.post(f"/api/logistique/locations/{loc['id']}/cloturer/", {"lecture_finale": "50"}, format="json")
        self.assertEqual((r.data["jours_retard"], r.data["penalite"]), (0, "0.00"))

    def test_montants_tarif_masques_hors_roles(self):
        v1 = self.tarif("100000", date.today(), penalite_jour="5000")
        self.client.force_authenticate(self.logi)
        r = self.client.get(f"/api/logistique/tarifs-gr/{v1['id']}/")
        self.assertEqual((r.data["tarif"], r.data["penalite_jour"]), (None, None))
