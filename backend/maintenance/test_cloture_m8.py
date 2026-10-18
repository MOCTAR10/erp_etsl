"""Clôture M8 Maintenance — tests de recette (CDC M8).

Critères :
- MTBF / MTTR / disponibilité par machine calculés depuis les OT, période d'observation paramétrable, valeurs
  provisoires tant qu'ETSL ne les a pas confirmées (publiés à la Couche D : mart dbt `dm_maintenance_fiabilite`) ;
- coût de maintenance par machine et par mois exposé à M11 (sans écriture comptable ; GR isolé au compte 618) ;
- OT 5 états et seuils compteurs GR → OT auto : déjà couverts (tests.py, test_preventif.py).
"""

from datetime import date, datetime, timedelta, timezone as dt_tz
from decimal import Decimal
from pathlib import Path

from rest_framework.test import APITestCase

from accounting_kernel.models import AccountMove
from users.models import User

from .models import Actif, OrdreTravail, ParametreMaintenance
from .services import PARAMETRES_DEFAUT, fiabilite_actifs, get_param_maintenance

AUJOURDHUI = date(2026, 10, 18)


def _user(email, role):
    return User.objects.create_user(email=email, password="x-Audit-2026", role=role)


def _dt(jour, heure=8):
    return datetime(jour.year, jour.month, jour.day, heure, tzinfo=dt_tz.utc)


class _Base(APITestCase):
    def setUp(self):
        self.maint = _user("maint@etls.ga", User.Role.MAINTENANCE)
        self.dop = _user("dop@etls.ga", User.Role.DIRECTEUR_OPERATIONS)
        self.admin = _user("adm@etls.ga", User.Role.ADMIN)
        self.rh = _user("rh@etls.ga", User.Role.RH)
        self.actif = Actif.objects.create(designation="Groupe électrogène", categorie="machine")
        self.client.force_authenticate(self.maint)

    def ot(self, jour, heures, type_ot="correctif", statut="termine", actif=None, **kw):
        debut = _dt(jour)
        return OrdreTravail.objects.create(
            actif=actif or self.actif, description="Intervention", type_ot=type_ot, statut=statut,
            date_debut=debut, date_fin=debut + timedelta(hours=heures) if heures is not None else None, **kw,
        )

    def regler(self, code, valeur):
        get_param_maintenance(code)
        ParametreMaintenance.objects.filter(code=code).update(valeur=Decimal(str(valeur)))

    def ligne(self, actif=None):
        rows = fiabilite_actifs(AUJOURDHUI)["rows"]
        return next(r for r in rows if r["actif"] == (actif or self.actif).code)


class FiabiliteTests(_Base):
    def setUp(self):
        super().setUp()
        self.regler("OBSERVATION_JOURS", 100)  # 100 j × 24 h = 2400 h requises
        self.regler("HEURES_PAR_JOUR", 24)

    def test_mtbf_mttr_disponibilite(self):
        self.ot(AUJOURDHUI - timedelta(days=50), 10)
        self.ot(AUJOURDHUI - timedelta(days=20), 20, type_ot="urgence")
        r = self.ligne()
        self.assertEqual(r["pannes"], 2)
        self.assertEqual(r["heures_arret"], Decimal("30.00"))
        self.assertEqual(r["mttr_h"], Decimal("15.00"))
        self.assertEqual(r["mtbf_h"], Decimal("1185.00"))  # (2400 - 30) / 2
        self.assertEqual(r["disponibilite_pct"], Decimal("98.75"))

    def test_preventif_baisse_la_disponibilite_sans_compter_comme_panne(self):
        self.ot(AUJOURDHUI - timedelta(days=30), 24, type_ot="preventif")
        r = self.ligne()
        self.assertEqual(r["pannes"], 0)
        self.assertIsNone(r["mtbf_h"])
        self.assertIsNone(r["mttr_h"])
        self.assertEqual(r["disponibilite_pct"], Decimal("99.00"))  # (2400 - 24) / 2400

    def test_sans_intervention_disponibilite_pleine(self):
        r = self.ligne()
        self.assertEqual((r["pannes"], r["disponibilite_pct"]), (0, Decimal("100.00")))

    def test_ot_hors_fenetre_annule_ou_non_termine_ignores(self):
        self.ot(AUJOURDHUI - timedelta(days=300), 10)                      # hors fenêtre
        self.ot(AUJOURDHUI - timedelta(days=10), 10, statut="annule")      # annulé
        self.ot(AUJOURDHUI - timedelta(days=5), None, statut="en_cours")   # sans fin
        self.assertEqual(self.ligne()["pannes"], 0)

    def test_fenetre_bornee_par_la_mise_en_service(self):
        self.actif.date_mise_en_service = AUJOURDHUI - timedelta(days=50)
        self.actif.save()
        self.ot(AUJOURDHUI - timedelta(days=10), 12)
        r = self.ligne()
        self.assertEqual(r["heures_requises"], Decimal("1200.00"))  # 50 j × 24 h
        self.assertEqual(r["disponibilite_pct"], Decimal("99.00"))

    def test_periode_observation_parametrable(self):
        self.ot(AUJOURDHUI - timedelta(days=50), 10)
        self.regler("OBSERVATION_JOURS", 30)  # la panne sort de la fenêtre
        self.assertEqual(self.ligne()["pannes"], 0)

    def test_valeurs_provisoires_jusqu_a_confirmation(self):
        self.assertTrue(fiabilite_actifs(AUJOURDHUI)["provisoire"])
        ParametreMaintenance.objects.update(statut_valeur="confirme")
        self.assertFalse(fiabilite_actifs(AUJOURDHUI)["provisoire"])

    def test_endpoint_fiabilite(self):
        r = self.client.get("/api/maintenance/actifs/fiabilite/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.data["provisoire"])
        self.assertEqual(r.data["observation_jours"], 100)
        self.assertEqual([x["actif"] for x in r.data["rows"]], [self.actif.code])


class ParametresMaintenanceTests(_Base):
    def test_defauts_provisoires_crees_a_la_volee(self):
        r = self.client.get("/api/maintenance/parametres/")
        self.assertEqual(r.status_code, 200, r.content)
        rows = r.data["results"] if isinstance(r.data, dict) else r.data
        self.assertEqual({p["code"] for p in rows}, set(PARAMETRES_DEFAUT))
        self.assertTrue(all(p["est_provisoire"] for p in rows))

    def test_modifier_repasse_en_provisoire_et_confirmer_est_reserve_a_la_direction(self):
        p = ParametreMaintenance.objects.get_or_create(
            code="OBSERVATION_JOURS", defaults={"label": "x", "valeur": Decimal("365")})[0]
        self.client.force_authenticate(self.dop)
        r = self.client.post(f"/api/maintenance/parametres/{p.pk}/confirmer/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["confirme_par"], self.dop.pk)
        self.client.force_authenticate(self.maint)
        r = self.client.patch(f"/api/maintenance/parametres/{p.pk}/", {"valeur": "180"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["statut_valeur"], "provisoire")
        r = self.client.post(f"/api/maintenance/parametres/{p.pk}/confirmer/")
        self.assertEqual(r.status_code, 403)

    def test_valeur_non_positive_refusee_et_creation_interdite(self):
        p = ParametreMaintenance.objects.get_or_create(
            code="HEURES_PAR_JOUR", defaults={"label": "x", "valeur": Decimal("24")})[0]
        r = self.client.patch(f"/api/maintenance/parametres/{p.pk}/", {"valeur": "0"}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/maintenance/parametres/", {"code": "X", "valeur": "1"}, format="json")
        self.assertEqual(r.status_code, 405)

    def test_rh_ne_peut_pas_modifier(self):
        p = ParametreMaintenance.objects.get_or_create(
            code="HEURES_PAR_JOUR", defaults={"label": "x", "valeur": Decimal("24")})[0]
        self.client.force_authenticate(self.rh)
        r = self.client.patch(f"/api/maintenance/parametres/{p.pk}/", {"valeur": "10"}, format="json")
        self.assertEqual(r.status_code, 403)


class CoutsM11Tests(_Base):
    def setUp(self):
        super().setUp()
        self.gr = Actif.objects.create(designation="Grue GR", categorie="levage", is_global_rental=True, signe_618=True)
        self.client.force_authenticate(self.admin)

    def terminer(self, actif, jour, heures_mo, tarif, pieces):
        return self.ot(jour, 4, actif=actif, heures_mo=Decimal(heures_mo), tarif_horaire=Decimal(tarif),
                       cout_pieces=Decimal(pieces))

    def test_cout_par_machine_et_par_mois(self):
        self.terminer(self.actif, date(2026, 9, 10), "5", "2000", "30000")   # 40 000
        self.terminer(self.actif, date(2026, 9, 25), "2", "2000", "0")       # 4 000
        self.terminer(self.actif, date(2026, 10, 2), "1", "2000", "0")       # autre mois
        r = self.client.get("/api/controle-gestion/maintenance-couts/?periode=2026-09")
        self.assertEqual(r.status_code, 200, r.content)
        ligne = next(x for x in r.data["rows"] if x["actif"] == self.actif.code)
        self.assertEqual(ligne["nb_ot"], 2)
        self.assertEqual(Decimal(ligne["main_oeuvre"]), Decimal("14000.00"))
        self.assertEqual(Decimal(ligne["pieces"]), Decimal("30000.00"))
        self.assertEqual(Decimal(ligne["total"]), Decimal("44000.00"))

    def test_gr_isole_au_compte_618_et_totaux_separes(self):
        self.terminer(self.actif, date(2026, 9, 10), "1", "1000", "0")
        self.terminer(self.gr, date(2026, 9, 11), "1", "5000", "0")
        r = self.client.get("/api/controle-gestion/maintenance-couts/?periode=2026-09")
        par_code = {x["actif"]: x for x in r.data["rows"]}
        self.assertEqual(par_code[self.gr.code]["compte"], "618000")
        self.assertEqual(par_code[self.actif.code]["compte"], "624000")
        self.assertEqual(Decimal(r.data["totaux"]["gr_618"]), Decimal("5000.00"))
        self.assertEqual(Decimal(r.data["totaux"]["hors_gr"]), Decimal("1000.00"))

    def test_ot_non_termine_ou_annule_non_compte(self):
        self.ot(date(2026, 9, 10), None, statut="en_cours", cout_pieces=Decimal("999"))
        self.ot(date(2026, 9, 12), 3, statut="annule", cout_pieces=Decimal("999"))
        r = self.client.get("/api/controle-gestion/maintenance-couts/?periode=2026-09")
        self.assertEqual(r.data["rows"], [])

    def test_aucune_ecriture_comptable(self):
        self.terminer(self.actif, date(2026, 9, 10), "1", "1000", "100")
        avant = AccountMove.objects.count()
        self.client.get("/api/controle-gestion/maintenance-couts/?periode=2026-09")
        self.assertEqual(AccountMove.objects.count(), avant)

    def test_periode_requise_et_valide(self):
        self.assertEqual(self.client.get("/api/controle-gestion/maintenance-couts/").status_code, 400)
        self.assertEqual(self.client.get("/api/controle-gestion/maintenance-couts/?periode=2026-13").status_code, 400)

    def test_rh_sans_acces_m11(self):
        self.client.force_authenticate(self.rh)
        r = self.client.get("/api/controle-gestion/maintenance-couts/?periode=2026-09")
        self.assertEqual(r.status_code, 403)


class CoucheDTests(APITestCase):
    def test_mart_dbt_publie_et_documente(self):
        dbt = Path(__file__).resolve().parents[2] / "dbt" / "models"
        sql = (dbt / "marts" / "dm_maintenance_fiabilite.sql").read_text(encoding="utf-8")
        for mot in ("mtbf_h", "mttr_h", "disponibilite_pct", "maintenance_parametremaintenance"):
            self.assertIn(mot, sql)
        self.assertIn("dm_maintenance_fiabilite", (dbt / "marts" / "schema.yml").read_text(encoding="utf-8"))
        self.assertIn("maintenance_parametremaintenance", (dbt / "sources.yml").read_text(encoding="utf-8"))
