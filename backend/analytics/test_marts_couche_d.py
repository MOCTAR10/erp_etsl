"""Couche D — marts dbt manquants (pointages M9, coûts M10, compteurs M8 / GR) : cohérence mart ↔ règle Django.

dbt ne tourne pas en local : le SQL du mart est rendu (`{{ source(...) }}` → table de la base) puis EXÉCUTÉ sur la
base de test, et son résultat comparé à la fonction Django qui porte la règle métier. Une dérive entre le mart et la
règle fait échouer le test.
"""

import re
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from django.db import connection

from controle_gestion.services import compute_marges
from controle_gestion.tests import BaseGestionTest
from logistique.models import EquipementParc, LectureCompteur, LocationGR
from maintenance.models import Actif, PlanPreventif
from referentiels.models import Partner
from rh_paie.models import Employe, ParametrePaie, SaisieTemps
from rh_paie.services import heures_supplementaires

DBT = Path(__file__).resolve().parents[2] / "dbt" / "models"


def rendre_mart(nom):
    """Rend le SQL d'un mart dbt (sources → tables du schéma courant) et l'exécute ; renvoie une liste de dict."""
    sql = (DBT / "marts" / f"{nom}.sql").read_text(encoding="utf-8")
    assert "{{ ref(" not in sql, "les marts de la Couche D lisent les sources directement"
    sql = re.sub(r'\{\{\s*source\("etls_replica",\s*"(\w+)"\)\s*\}\}', r"\1", sql)
    with connection.cursor() as cur:
        cur.execute(sql)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


class PresenceTests(BaseGestionTest):
    def test_marts_documentes_et_sources_declarees(self):
        schema = (DBT / "marts" / "schema.yml").read_text(encoding="utf-8")
        sources = (DBT / "sources.yml").read_text(encoding="utf-8")
        for mart in ("dm_pointages_m9", "dm_couts_m10", "dm_compteurs_parc", "dm_lectures_gr"):
            self.assertIn(f"name: {mart}", schema)
            for table in set(re.findall(r'source\("etls_replica",\s*"(\w+)"\)', (DBT / "marts" / f"{mart}.sql").read_text(encoding="utf-8"))):
                self.assertIn(f"name: {table}\n", sources + "\n", f"{mart} : source {table} non déclarée")


class PointagesM9Tests(BaseGestionTest):
    def test_mart_egal_regle_heures_supplementaires(self):
        emp = Employe.objects.create(code="E1", civilite="M", nom="Dupont", prenom="Jean")
        for code, val in (("DUREE_LEGALE_HEBDO", "40"), ("HS_SEUIL_2", "48"), ("HS_MAJ_1", "20"), ("HS_MAJ_2", "40")):
            ParametrePaie.objects.create(code=code, label=code, valeur=Decimal(val), date_effet=date(2026, 1, 1))
        # semaine du 5 au 11 oct. 2026 : 5 × 10 h = 50 h (10 h en tranche 1 : 8 h, tranche 2 : 2 h) + 4 h de nuit
        for i in range(5):
            SaisieTemps.objects.create(code=f"S{i}", employe=emp, date=date(2026, 10, 5 + i), heures=Decimal("10"))
        SaisieTemps.objects.create(code="SN", employe=emp, date=date(2026, 10, 10), heures=Decimal("4"), type="nuit")
        # semaine suivante : 30 h (aucune heure sup.)
        SaisieTemps.objects.create(code="S9", employe=emp, date=date(2026, 10, 12), heures=Decimal("30"))
        regle = heures_supplementaires(emp, date(2026, 10, 1), Decimal("500000"))
        rows = [r for r in rendre_mart("dm_pointages_m9") if r["employe_id"] == emp.id]
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["periode"], "2026-10")
        self.assertEqual(r["heures_productives"], regle["heures_productives"])
        self.assertEqual(r["heures_tranche_1"], regle["heures_tranche_1"])
        self.assertEqual(r["heures_tranche_2"], regle["heures_tranche_2"])
        self.assertEqual((r["heures_tranche_1"], r["heures_tranche_2"], r["heures_nuit"]), (8, 2, 4))
        self.assertFalse(r["parametres_absents"])

    def test_parametres_absents_signales(self):
        emp = Employe.objects.create(code="E2", civilite="M", nom="Martin", prenom="Luc")
        SaisieTemps.objects.create(code="SX", employe=emp, date=date(2026, 10, 5), heures=Decimal("8"))
        r = [x for x in rendre_mart("dm_pointages_m9") if x["employe_id"] == emp.id][0]
        self.assertTrue(r["parametres_absents"])


class CoutsM10Tests(BaseGestionTest):
    def test_mart_egal_compute_marges_et_isole_618(self):
        self._post_produit("5000000.00", analytic=self.analytic_aff)
        self._post_charge("1200000.00", analytic=self.analytic_aff)
        self._post_charge_gr("300000.00", analytic=self.analytic_aff)
        regle = compute_marges(self._fy.pk)
        rows = rendre_mart("dm_couts_m10")
        self.assertEqual(sum(r["produits"] for r in rows), regle["totals"]["produits"])
        self.assertEqual(sum(r["charges"] for r in rows), regle["totals"]["charges"])
        self.assertEqual(sum(r["cout_gr"] for r in rows), regle["totals"]["cout_gr"])
        ligne = next(r for r in rows if r["analytique_code"] == "AFF-PIPE-001")
        self.assertEqual((ligne["periode"], ligne["axis_type"]), ("2026-01", "projet"))
        self.assertEqual(ligne["charges"], Decimal("1200000.00"))  # le 618 n'est PAS dans les charges
        self.assertEqual(ligne["cout_gr"], Decimal("300000.00"))

    def test_brouillon_exclu(self):
        from accounting_kernel.models import AccountMove

        self._post_charge("100.00", analytic=self.analytic_cc)
        AccountMove.objects.filter(reference="RSC2026E").update(status=AccountMove.Status.DRAFT)
        self.assertEqual(sum(r["charges"] for r in rendre_mart("dm_couts_m10")), 0)


class CompteursM8Tests(BaseGestionTest):
    def test_mart_egal_motif_echeance(self):
        actif = Actif.objects.create(designation="Compresseur", compteur_value=Decimal("1050"))
        seuil = PlanPreventif.objects.create(
            actif=actif, libelle="Vidange", intervalle_compteur=Decimal("500"), dernier_compteur=Decimal("500"),
            derniere_date=date.today(),
        )
        calendaire = PlanPreventif.objects.create(
            actif=actif, libelle="Inspection", periodicite_jours=30, derniere_date=date.today() - timedelta(days=45),
        )
        calme = PlanPreventif.objects.create(
            actif=actif, libelle="Graissage", intervalle_compteur=Decimal("500"), dernier_compteur=Decimal("900"),
            derniere_date=date.today(),
        )
        rows = {r["plan_id"]: r for r in rendre_mart("dm_compteurs_parc")}
        for plan, attendu in ((seuil, "compteur"), (calendaire, "calendaire"), (calme, None)):
            plan.refresh_from_db()
            motif = plan.motif_echeance()
            self.assertEqual(bool(motif), attendu is not None)
            self.assertEqual(rows[plan.id]["motif_echeance"], attendu)
        self.assertEqual(rows[seuil.id]["prochain_compteur"], Decimal("1000"))

    def test_actif_gr_lit_le_compteur_logistique(self):
        eq = EquipementParc.objects.create(label="Grue", categorie="levage", is_global_rental=True, compteur_value=Decimal("700"))
        actif = Actif.objects.create(designation="Grue GR", is_global_rental=True, equipement_gr=eq, compteur_value=Decimal("0"))
        plan = PlanPreventif.objects.create(
            actif=actif, libelle="Révision", intervalle_compteur=Decimal("500"), dernier_compteur=Decimal("100"),
            derniere_date=date.today(),
        )
        r = {x["plan_id"]: x for x in rendre_mart("dm_compteurs_parc")}[plan.id]
        self.assertEqual(r["compteur_lu"], Decimal("700"))
        self.assertEqual(r["motif_echeance"], "compteur")
        self.assertTrue(plan.motif_echeance())

    def test_lectures_gr(self):
        partner = Partner.objects.create(code="GR-1", name="GLOBAL RENTAL", kind="fournisseur", is_global_rental=True)
        eq = EquipementParc.objects.create(label="Grue", categorie="levage", is_global_rental=True)
        loc = LocationGR.objects.create(equipement=eq, partenaire=partner, statut=LocationGR.Statut.ACTIVE, lecture_initiale=100, tarif=1000)
        for i, v in enumerate(("100", "180", "260")):
            LectureCompteur.objects.create(location=loc, date=date(2026, 10, 1 + i), valeur=Decimal(v))
        r = [x for x in rendre_mart("dm_lectures_gr") if x["location_id"] == loc.id][0]
        self.assertEqual((r["nb_lectures"], r["premiere_valeur"], r["derniere_valeur"], r["consommation"]), (3, 100, 260, 160))
