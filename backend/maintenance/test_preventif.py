"""Lot 14 (2026-10-17) — maintenance préventive automatisée et archivage des OT (CDC M8 §13.4 / §13.11, M4 §12.11).

- Plans préventifs par machine / composant : périodicité calendaire et / ou intervalle compteur.
- « Dépassement de seuil compteur → OT de maintenance M8 automatique » ; le préventif calendaire échu génère
  aussi son OT (tâche Celery quotidienne). Pas de doublon tant qu'un OT du plan est ouvert ; la clôture de l'OT
  réarme le plan (dernière date / dernier compteur).
- Compteur GLOBAL RENTAL : lecture seule côté M8, le relevé logistique déclenche le seuil.
- OT en 5 états jusqu'à « archivé » : un OT clos est une pièce scellée (ni modification ni suppression) ;
  l'archivage exige le rapport d'intervention et trace qui archive.
"""

from datetime import date, timedelta

from rest_framework.test import APITestCase

from logistique.models import EquipementParc, LocationGR
from logistique.tests import _gr_partner
from users.models import User

from .models import Actif, OrdreTravail, PlanPreventif
from .preventif import declencher_plans
from .tasks import declencher_plans_preventifs


class PlanPreventifTests(APITestCase):
    def setUp(self):
        self.maint = User.objects.create_user(email="maint@etls.ga", password="x-Audit-2026", role=User.Role.MAINTENANCE)
        self.client.force_authenticate(self.maint)
        self.actif = Actif.objects.create(designation="Compresseur 7 bar", compteur_value=480)

    def plan(self, **kw):
        body = {"actif": str(self.actif.pk), "libelle": "Vidange + filtres"}
        body.update(kw)
        r = self.client.post("/api/maintenance/plans/", body, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return PlanPreventif.objects.get(pk=r.data["id"])

    def releve(self, valeur, actif=None):
        return self.client.post(f"/api/maintenance/actifs/{(actif or self.actif).pk}/releve-compteur/", {"valeur": valeur}, format="json")

    def test_plan_sans_declencheur_refuse(self):
        r = self.client.post("/api/maintenance/plans/", {"actif": str(self.actif.pk), "libelle": "Rien"}, format="json")
        self.assertEqual(r.status_code, 400, r.content)

    def test_depassement_de_seuil_compteur_genere_un_ot(self):
        plan = self.plan(intervalle_compteur="250", dernier_compteur="400")
        r = self.releve("700")  # seuil = 400 + 250 = 650
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["compteur_value"], "700.00")
        ot = OrdreTravail.objects.get(plan=plan)
        self.assertEqual((ot.type_ot, ot.statut), (OrdreTravail.TypeOT.PREVENTIF, OrdreTravail.Statut.DEMANDE))
        self.assertIn(ot.code, r.data["ot_generes"])
        self.assertIn("compteur", ot.description.lower())
        self.releve("800")  # OT du plan encore ouvert : pas de doublon
        self.assertEqual(OrdreTravail.objects.filter(plan=plan).count(), 1)

    def test_releve_sous_le_seuil_sans_ot(self):
        self.plan(intervalle_compteur="250", dernier_compteur="400")
        self.assertEqual(self.releve("649.5").status_code, 200)
        self.assertFalse(OrdreTravail.objects.exists())

    def test_releve_compteur_ne_recule_pas(self):
        self.assertEqual(self.releve("100").status_code, 400)
        self.assertEqual(self.releve("abc").status_code, 400)

    def test_preventif_calendaire_echu_genere_l_ot_par_la_tache(self):
        plan = self.plan(periodicite_jours=30, derniere_date=str(date.today() - timedelta(days=31)))
        pas_echu = self.plan(periodicite_jours=90, derniere_date=str(date.today() - timedelta(days=10)))
        declencher_plans_preventifs()
        self.assertEqual(OrdreTravail.objects.filter(plan=plan).count(), 1)
        self.assertFalse(OrdreTravail.objects.filter(plan=pas_echu).exists())
        declencher_plans_preventifs()
        self.assertEqual(OrdreTravail.objects.filter(plan=plan).count(), 1)

    def test_cloture_de_l_ot_rearme_le_plan(self):
        plan = self.plan(intervalle_compteur="250", dernier_compteur="400")
        self.releve("660")
        ot = OrdreTravail.objects.get(plan=plan)
        for action in ("demarrer", "terminer", "cloturer"):
            self.assertEqual(self.client.post(f"/api/maintenance/ordres/{ot.pk}/{action}/", {}, format="json").status_code, 200)
        plan.refresh_from_db()
        self.assertEqual((plan.dernier_compteur, plan.derniere_date), (660, date.today()))
        self.releve("700")  # prochain seuil = 910
        self.assertEqual(OrdreTravail.objects.filter(plan=plan).count(), 1)

    def test_plan_inactif_ou_actif_reforme_ignore(self):
        self.plan(intervalle_compteur="10", dernier_compteur="0", en_vigueur=False)
        reforme = Actif.objects.create(designation="Vieux poste", statut=Actif.Statut.REFORME)
        PlanPreventif.objects.create(actif=reforme, libelle="X", periodicite_jours=1, derniere_date=date.today() - timedelta(days=5))
        self.assertEqual(declencher_plans(), [])


class SeuilCompteurGlobalRentalTests(APITestCase):
    def setUp(self):
        self.logi = User.objects.create_user(email="logi@etls.ga", password="x-Audit-2026", role=User.Role.LOGISTIQUE)
        self.client.force_authenticate(self.logi)
        self.equipement = EquipementParc.objects.create(label="Grue 25t", categorie=EquipementParc.Categorie.LEVAGE,
                                                        compteur_value=1000, is_global_rental=True)
        self.actif = Actif.objects.create(designation="Grue GR", is_global_rental=True, equipement_gr=self.equipement)
        self.plan = PlanPreventif.objects.create(actif=self.actif, libelle="Révision 250 h", intervalle_compteur=250, dernier_compteur=1000)
        self.location = LocationGR.objects.create(partenaire=_gr_partner(), equipement=self.equipement,
                                                  statut=LocationGR.Statut.ACTIVE, lecture_initiale=1000)

    def test_compteur_gr_en_lecture_seule_cote_maintenance(self):
        r = self.client.post(f"/api/maintenance/actifs/{self.actif.pk}/releve-compteur/", {"valeur": "1300"}, format="json")
        self.assertEqual(r.status_code, 400, r.content)

    def test_releve_logistique_au_dela_du_seuil_declenche_l_ot(self):
        r = self.client.post("/api/logistique/lectures/", {"location": str(self.location.pk), "date": str(date.today()), "valeur": "1180"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.equipement.refresh_from_db()
        self.assertEqual(self.equipement.compteur_value, 1180)
        self.assertFalse(OrdreTravail.objects.filter(plan=self.plan).exists())
        self.client.post("/api/logistique/lectures/", {"location": str(self.location.pk), "date": str(date.today()), "valeur": "1260"}, format="json")
        self.assertTrue(OrdreTravail.objects.filter(plan=self.plan, type_ot=OrdreTravail.TypeOT.PREVENTIF).exists())

    def test_cloture_location_reporte_le_compteur_final(self):
        r = self.client.post(f"/api/logistique/locations/{self.location.pk}/cloturer/", {"lecture_finale": "1400"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.equipement.refresh_from_db()
        self.assertEqual(self.equipement.compteur_value, 1400)
        self.assertTrue(OrdreTravail.objects.filter(plan=self.plan).exists())


class ArchivageOtTests(APITestCase):
    def setUp(self):
        self.maint = User.objects.create_user(email="maint@etls.ga", password="x-Audit-2026", role=User.Role.MAINTENANCE)
        self.client.force_authenticate(self.maint)
        self.actif = Actif.objects.create(designation="Poste TIG")

    def ot(self, statut=OrdreTravail.Statut.CLOTURE, rapport="Remplacement torche, essais OK"):
        return OrdreTravail.objects.create(actif=self.actif, description="Torche HS", statut=statut, rapport=rapport)

    def test_archivage_d_un_ot_clos_trace(self):
        ot = self.ot()
        r = self.client.post(f"/api/maintenance/ordres/{ot.pk}/archiver/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["statut"], OrdreTravail.Statut.ARCHIVE)
        ot.refresh_from_db()
        self.assertEqual(ot.archive_par, self.maint)
        self.assertIsNotNone(ot.archive_le)

    def test_archivage_exige_ot_clos_et_rapport(self):
        self.assertEqual(self.client.post(f"/api/maintenance/ordres/{self.ot(OrdreTravail.Statut.EN_COURS).pk}/archiver/").status_code, 400)
        r = self.client.post(f"/api/maintenance/ordres/{self.ot(rapport='').pk}/archiver/")
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("rapport", str(r.data).lower())

    def test_ot_clos_ou_archive_scelle(self):
        for statut in (OrdreTravail.Statut.CLOTURE, OrdreTravail.Statut.ARCHIVE):
            ot = self.ot(statut)
            r = self.client.patch(f"/api/maintenance/ordres/{ot.pk}/", {"description": "Réécrit"}, format="json")
            self.assertEqual(r.status_code, 400, r.content)
            self.assertEqual(self.client.delete(f"/api/maintenance/ordres/{ot.pk}/").status_code, 400)
            ot.refresh_from_db()
            self.assertEqual(ot.description, "Torche HS")

    def test_ot_archive_hors_des_ot_ouverts(self):
        self.ot(OrdreTravail.Statut.ARCHIVE)
        self.assertEqual(self.client.get("/api/maintenance/ordres/stats/").data["ot_ouverts"], 0)
        self.assertEqual(self.client.get("/api/maintenance/ordres/?ouverts=1").data["results"], [])
