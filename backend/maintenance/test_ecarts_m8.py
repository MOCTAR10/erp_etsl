"""Écarts M8 (2026-10-19) — tests de recette (matrice CDC × code, M8.1 / M8.2 / §13.5 / §13.4).

- Workflow OT tracé : chaque création et changement de statut est horodaté avec son auteur, quel que soit le chemin
  (action d'écran, plan préventif) ; la qualification d'une demande (diagnostic, type, priorité) est attestée.
- Plans préventifs : pré-alerte avant échéance (jours / part de l'intervalle compteur), paramètres provisoires
  modifiables par ETSL ; calendrier mensuel des échéances.
- Un OT correctif ne naît que d'une inspection non conforme ou sous réserve.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APITestCase

from users.models import User

from .models import Actif, HistoriqueStatutOT, Inspection, OrdreTravail, ParametreMaintenance, PlanPreventif
from .preventif import declencher_plans
from .services import calendrier_preventif, get_param_maintenance


class _Base(APITestCase):
    def setUp(self):
        self.maint = User.objects.create_user(email="maint@etls.ga", password="x-Audit-2026", role=User.Role.MAINTENANCE)
        self.chef = User.objects.create_user(email="chef@etls.ga", password="x-Audit-2026", role=User.Role.CHEF_ATELIER)
        self.client.force_authenticate(self.maint)
        self.actif = Actif.objects.create(designation="Compresseur 7 bar", compteur_value=480)

    def creer_ot(self):
        r = self.client.post("/api/maintenance/ordres/", {
            "actif": str(self.actif.pk), "description": "Fuite d'huile", "type_ot": "correctif",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.data["id"]


class HistoriqueStatutTests(_Base):
    def test_chaque_transition_est_horodatee_avec_son_auteur(self):
        ot_id = self.creer_ot()
        self.client.post(f"/api/maintenance/ordres/{ot_id}/planifier/", {}, format="json")
        self.client.force_authenticate(self.chef)
        self.client.post(f"/api/maintenance/ordres/{ot_id}/demarrer/", {}, format="json")
        r = self.client.get(f"/api/maintenance/ordres/{ot_id}/historique/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual([(h["de"], h["vers"]) for h in r.data],
                         [("", "demande"), ("demande", "planifie"), ("planifie", "en_cours")])
        self.assertEqual([h["par"] for h in r.data], [self.maint.pk, self.maint.pk, self.chef.pk])

    def test_ot_genere_par_un_plan_est_trace(self):
        plan = PlanPreventif.objects.create(
            actif=self.actif, libelle="Vidange", periodicite_jours=30, derniere_date=date.today() - timedelta(days=40),
        )
        ot = declencher_plans([self.actif])[0]
        self.assertEqual(ot.plan, plan)
        self.assertEqual(list(ot.historique.values_list("de", "vers")), [("", "demande")])

    def test_sans_changement_de_statut_aucune_trace(self):
        ot = OrdreTravail.objects.get(pk=self.creer_ot())
        ot.description = "Fuite d'huile importante"
        ot.save()
        self.assertEqual(HistoriqueStatutOT.objects.filter(ot=ot).count(), 1)


class QualificationTests(_Base):
    def test_qualification_exige_un_diagnostic_et_est_attestee(self):
        ot_id = self.creer_ot()
        r = self.client.post(f"/api/maintenance/ordres/{ot_id}/qualifier/", {"cause": " "}, format="json")
        self.assertEqual(r.status_code, 400, r.content)
        r = self.client.post(f"/api/maintenance/ordres/{ot_id}/qualifier/", {
            "cause": "Joint de culasse", "priorite": "haute", "type_ot": "urgence",
        }, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.data["priorite"], r.data["type_ot"], r.data["qualifie_par"]), ("haute", "urgence", self.maint.pk))
        self.assertIsNotNone(r.data["qualifie_le"])
        historique = self.client.get(f"/api/maintenance/ordres/{ot_id}/historique/").data
        self.assertEqual(historique[-1]["commentaire"], "Qualification : Joint de culasse")

    def test_qualification_refusee_hors_demande_et_choix_inconnu(self):
        ot_id = self.creer_ot()
        r = self.client.post(f"/api/maintenance/ordres/{ot_id}/qualifier/", {"cause": "x", "priorite": "folle"}, format="json")
        self.assertEqual(r.status_code, 400, r.content)
        self.client.post(f"/api/maintenance/ordres/{ot_id}/planifier/", {}, format="json")
        r = self.client.post(f"/api/maintenance/ordres/{ot_id}/qualifier/", {"cause": "x"}, format="json")
        self.assertEqual(r.status_code, 400, r.content)

    def test_qualification_attestee_cote_serveur(self):
        ot_id = self.creer_ot()
        r = self.client.patch(f"/api/maintenance/ordres/{ot_id}/", {"qualifie_par": self.chef.pk}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIsNone(OrdreTravail.objects.get(pk=ot_id).qualifie_par)


class PrealerteTests(_Base):
    def plan(self, **kw):
        body = {"actif": str(self.actif.pk), "libelle": "Vidange + filtres"}
        body.update(kw)
        r = self.client.post("/api/maintenance/plans/", body, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.data

    def test_prealerte_calendaire_dans_la_fenetre_parametree(self):
        dans_5_jours = self.plan(periodicite_jours=30, derniere_date=str(date.today() - timedelta(days=25)))
        self.assertIsNone(dans_5_jours["echeance"])
        self.assertIn("échéance calendaire le", dans_5_jours["prealerte"])
        lointain = self.plan(periodicite_jours=60, derniere_date=str(date.today()))
        self.assertIsNone(lointain["prealerte"])
        # ETSL élargit la fenêtre : le plan lointain entre en pré-alerte, sans développeur.
        get_param_maintenance("PREVENTIF_PREALERTE_JOURS")
        ParametreMaintenance.objects.filter(code="PREVENTIF_PREALERTE_JOURS").update(valeur=Decimal("90"))
        r = self.client.get(f"/api/maintenance/plans/{lointain['id']}/")
        self.assertIn("échéance calendaire le", r.data["prealerte"])

    def test_prealerte_compteur_et_plan_echu_sans_prealerte(self):
        proche = self.plan(intervalle_compteur="100", dernier_compteur="385")  # reste 5 h <= 10 % de 100
        self.assertIn("seuil compteur proche", proche["prealerte"])
        echu = self.plan(intervalle_compteur="100", dernier_compteur="300")
        self.assertIsNotNone(echu["echeance"])
        self.assertIsNone(echu["prealerte"])

    def test_parametres_de_prealerte_provisoires_et_listes(self):
        r = self.client.get("/api/maintenance/parametres/")
        rows = r.data["results"] if isinstance(r.data, dict) else r.data
        codes = {p["code"]: p for p in rows}
        self.assertTrue(codes["PREVENTIF_PREALERTE_JOURS"]["est_provisoire"])
        self.assertEqual(Decimal(codes["PREVENTIF_PREALERTE_PCT"]["valeur"]), Decimal("10"))


class CalendrierTests(_Base):
    def test_occurrences_du_mois_a_la_periodicite(self):
        aujourdhui = date(2026, 10, 19)
        PlanPreventif.objects.create(actif=self.actif, libelle="Graissage", periodicite_jours=7,
                                     derniere_date=date(2026, 9, 28))  # prochaine 05/10, puis 12, 19, 26/10
        PlanPreventif.objects.create(actif=self.actif, libelle="Vidange", intervalle_compteur=Decimal("500"))
        cal = calendrier_preventif("2026-10", aujourdhui)
        self.assertEqual([o["date"] for o in cal["occurrences"]],
                         [date(2026, 10, 5), date(2026, 10, 12), date(2026, 10, 19), date(2026, 10, 26)])
        self.assertEqual([o["echu"] for o in cal["occurrences"]], [True, True, True, False])
        self.assertEqual([c["libelle"] for c in cal["compteurs"]], ["Vidange"])
        novembre = calendrier_preventif("2026-11", aujourdhui)
        self.assertEqual(novembre["occurrences"][0]["date"], date(2026, 11, 2))
        self.assertFalse(novembre["occurrences"][0]["echu"])

    def test_echeance_passee_non_traitee_reste_visible_ce_mois_ci(self):
        aujourdhui = date(2026, 10, 19)
        PlanPreventif.objects.create(actif=self.actif, libelle="Révision", periodicite_jours=90,
                                     derniere_date=date(2026, 6, 1))  # échue le 30/08, prochaine projection 28/11
        cal = calendrier_preventif("2026-10", aujourdhui)
        self.assertEqual([(o["date"], o["echu"]) for o in cal["occurrences"]], [(date(2026, 8, 30), True)])

    def test_endpoint_et_mois_invalide(self):
        r = self.client.get(f"/api/maintenance/plans/calendrier/?mois={timezone.localdate():%Y-%m}")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn("occurrences", r.data)
        r = self.client.get("/api/maintenance/plans/calendrier/?mois=octobre")
        self.assertEqual(r.status_code, 400, r.content)


class InspectionOtTests(_Base):
    def test_ot_correctif_seulement_depuis_une_inspection_non_conforme(self):
        insp = Inspection.objects.create(actif=self.actif, date_inspection=date.today(),
                                         statut=Inspection.Statut.REALISEE, resultat=Inspection.Resultat.CONFORME)
        r = self.client.post(f"/api/maintenance/inspections/{insp.pk}/creer-ot/")
        self.assertEqual(r.status_code, 400, r.content)
        Inspection.objects.filter(pk=insp.pk).update(resultat=Inspection.Resultat.SOUS_RESERVE)
        r = self.client.post(f"/api/maintenance/inspections/{insp.pk}/creer-ot/")
        self.assertEqual(r.status_code, 201, r.content)
