"""Écarts a4 — Couche D : CAPA dans les marts, staging des modules manquants, fraîcheur de l'ETL horaire,
compose de production (planificateur dbt par défaut, Superset provisionné), consommateurs CG / chargé d'affaires."""

from datetime import timedelta
from decimal import Decimal
from io import StringIO
from pathlib import Path

import yaml
from django.db import connection
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from hse.models import ActionHse
from qualite.models import ActionCorrective, NonConformite
from users.models import User

from . import bi_etat, pilotage
from .models import ParametreCube

RACINE = Path(__file__).resolve().parents[2]
DBT = RACINE / "dbt" / "models"


def executer(nom):
    with connection.cursor() as cur:
        cur.execute(pilotage.rendre_sql_mart(nom))
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


class CapaMartTests(TestCase):
    def setUp(self):
        today = timezone.localdate()
        nc = NonConformite.objects.create(description="Porosité")
        mk = ActionCorrective.objects.create
        mk(non_conformite=nc, description="Échue", echeance=today - timedelta(days=3))
        mk(non_conformite=nc, description="En cours", statut="en_cours", echeance=today + timedelta(days=3))
        c1 = mk(non_conformite=nc, description="Close efficace", statut="cloturee", efficace=True)
        c2 = mk(non_conformite=nc, description="Close inefficace", statut="cloturee", efficace=False)
        now = timezone.now()
        ActionCorrective.objects.filter(pk=c1.pk).update(created_at=now - timedelta(days=10), closed_at=now)
        ActionCorrective.objects.filter(pk=c2.pk).update(created_at=now - timedelta(days=5), closed_at=now)
        ActionHse.objects.create(description="Garde-corps", echeance=today - timedelta(days=1))

    def test_mart_egal_regle_django(self):
        mart = {r["origine"]: r for r in executer("dm_capa")}
        regle = {r["origine"]: r for r in bi_etat.indicateurs_capa()}
        self.assertEqual(set(mart), {"qualite", "hse"})
        for origine, attendu in regle.items():
            for cle, valeur in attendu.items():
                self.assertEqual(mart[origine][cle], valeur, f"{origine}.{cle}")
        q = regle["qualite"]
        self.assertEqual((q["total"], q["ouvertes"], q["echues"], q["cloturees"]), (4, 2, 1, 2))
        self.assertEqual(q["delai_moyen_cloture_jours"], Decimal("7.5"))
        self.assertEqual(q["taux_efficacite_pct"], Decimal("50.0"))
        self.assertEqual((regle["hse"]["echues"], regle["hse"]["taux_efficacite_pct"]), (1, None))

    def test_mart_sans_capa(self):
        ActionCorrective.objects.all().delete()
        ActionHse.objects.all().delete()
        for r in executer("dm_capa"):
            self.assertEqual((r["total"], r["delai_moyen_cloture_jours"], r["taux_efficacite_pct"]), (0, None, None))

    def test_staging_capa(self):
        rows = executer("stg_erp_capa")
        self.assertEqual(len(rows), 5)
        self.assertEqual(sum(1 for r in rows if r["is_echue"]), 2)


class DbtModelesTests(TestCase):
    def test_tous_les_modeles_s_executent(self):
        """Chaque staging et chaque mart s'exécute sur le schéma réel : une colonne renommée casse la CI."""
        for nom in bi_etat.modeles_staging() + pilotage.marts_disponibles():
            with self.subTest(modele=nom):
                executer(nom)

    def test_staging_des_modules_manquants(self):
        for nom in ("stg_erp_capa", "stg_erp_achats", "stg_erp_operations", "stg_erp_stocks",
                    "stg_erp_comptabilite", "stg_erp_controle_gestion"):
            self.assertIn(nom, bi_etat.modeles_staging())

    def test_sources_declarees_et_marts_documentes(self):
        import re

        sources = (DBT / "sources.yml").read_text(encoding="utf-8")
        schema = (DBT / "marts" / "schema.yml").read_text(encoding="utf-8")
        for dossier in ("staging", "marts"):
            for f in (DBT / dossier).glob("*.sql"):
                for table in set(re.findall(r'source\("etls_replica",\s*"(\w+)"\)', f.read_text(encoding="utf-8"))):
                    self.assertRegex(sources, rf"name: {table}\n", f"{f.stem} : source {table} non déclarée")
        for mart in ("dm_capa", "dm_fraicheur_bi"):
            self.assertIn(f"name: {mart}", schema)
        self.assertIn("freshness:", sources)


class FraicheurTests(TestCase):
    def test_jamais_rafraichi_puis_a_jour_puis_en_retard(self):
        self.assertEqual(bi_etat.fraicheur_couche_d()["statut"], "jamais")
        with connection.cursor() as cur:
            cur.execute("create schema if not exists marts")
            cur.execute(f"create table marts.dm_fraicheur_bi as {pilotage.rendre_sql_mart('dm_fraicheur_bi')}")
        f = bi_etat.fraicheur_couche_d()
        self.assertEqual((f["statut"], f["seuil_minutes"]), ("a_jour", 120))
        retard = bi_etat.fraicheur_couche_d(now=timezone.now() + timedelta(hours=3))
        self.assertEqual(retard["statut"], "en_retard")
        ParametreCube.objects.filter(code="BI_FRAICHEUR_MAX_MIN").update(valeur=Decimal("300"))
        self.assertEqual(bi_etat.fraicheur_couche_d(now=timezone.now() + timedelta(hours=3))["statut"], "a_jour")


class EtatEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        nc = NonConformite.objects.create(description="Porosité")
        ActionCorrective.objects.create(non_conformite=nc, description="A")
        ActionHse.objects.create(description="B")

    def _get(self, role):
        user = User.objects.create_user(email=f"{role}@t.local", password="x" * 12, role=role)
        self.client.force_authenticate(user)
        r = self.client.get("/api/analytics/etat-bi/")
        self.assertEqual(r.status_code, 200, r.content)
        return r.data

    def test_capa_filtrees_par_lecture_du_module(self):
        self.assertEqual([c["origine"] for c in self._get("qaqc")["capa"]], ["qualite", "hse"][:1])
        self.assertEqual([c["origine"] for c in self._get("hse")["capa"]], ["qualite", "hse"])
        data = self._get("charge_affaires")
        self.assertEqual([c["origine"] for c in data["capa"]], ["qualite"])
        self.assertIn("dm_capa", data["marts"])
        self.assertIn("stg_erp_capa", data["staging"])
        self.assertTrue(data["fraicheur_provisoire"])
        self.assertEqual(data["fraicheur"]["statut"], "jamais")

    def test_controleur_de_gestion_lit_les_cubes(self):
        cg = User.objects.create_user(email="cg@t.local", password="x" * 12, role="controleur_gestion")
        self.client.force_authenticate(cg)
        self.assertEqual(self.client.get("/api/analytics/pilotage/").status_code, 200)
        self.assertEqual(self.client.post("/api/analytics/cubes/alimenter/", {}, format="json").status_code, 403)
        ca = User.objects.create_user(email="ca@t.local", password="x" * 12, role="charge_affaires")
        self.client.force_authenticate(ca)
        self.assertEqual(self.client.get("/api/analytics/pilotage/").status_code, 403)


class ComposeProdTests(TestCase):
    def setUp(self):
        self.compose = yaml.safe_load((RACINE / "docker-compose.prod.yml").read_text(encoding="utf-8"))
        self.services = self.compose["services"]

    def test_planificateur_dbt_demarre_par_defaut(self):
        sched = self.services["dbt-scheduler"]
        self.assertNotIn("profiles", sched)
        script = "\n".join(sched["command"])
        self.assertIn("dbt build", script)
        self.assertIn("dbt source freshness", script)
        self.assertIn("DBT_REFRESH_SECONDS:-3600", sched["environment"]["DBT_REFRESH_SECONDS"])
        self.assertIn("POSTGRES_REPLICA_HOST", sched["environment"]["DBT_HOST"])

    def test_superset_provisionne(self):
        init = self.services["superset-init"]
        self.assertNotIn("profiles", init)
        self.assertIn("provision_superset.py", "\n".join(init["command"]))
        self.assertEqual(self.services["superset"]["depends_on"]["superset-init"]["condition"],
                         "service_completed_successfully")
        self.assertIn("POSTGRES_REPLICA_HOST", init["environment"]["ETSL_MARTS_URI"])
        self.assertTrue((RACINE / "infra" / "superset" / "provision_superset.py").is_file())
        montages = " ".join(init["volumes"])
        self.assertIn("./dbt/models/marts:", montages)


class VolumetriePerfTests(TestCase):
    def _module(self, nom):
        import importlib.util

        spec = importlib.util.spec_from_file_location(f"perf_{nom}", RACINE / "backend" / "perf" / f"{nom}.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_seed_volumetrie_idempotent_et_chrono(self):
        from django.core.management import call_command

        from accounting_kernel.models import AccountMove
        from commercial.models import Affaire
        from referentiels.models import Account
        from rh_paie.models import Employe

        Account.objects.get_or_create(code="601000", defaults={"label": "Achats", "account_class": 6, "account_type": "expense"})
        Account.objects.get_or_create(code="401000", defaults={"label": "Fournisseurs", "account_class": 4,
                                                               "account_type": "liability"})
        for _ in range(2):
            call_command("seed_volumetrie", salaries=3, affaires=2, ecritures=5, stdout=StringIO())
        self.assertEqual(Employe.objects.filter(code__startswith="VOL-").count(), 3)
        self.assertEqual(Affaire.objects.filter(code__startswith="VOL-").count(), 2)
        moves = AccountMove.objects.filter(number__startswith="VOL-")
        self.assertEqual(moves.count(), 5)
        for m in moves:
            self.assertEqual(m.total_debit, m.total_credit)
        chrono = self._module("chrono_traitements")
        paie = chrono.paie_complete(timezone.localdate().replace(day=1))
        self.assertEqual(paie["bulletins"] + paie["erreurs"], 3)

    def test_rapport_compare_aux_seuils(self):
        rapport = self._module("rapport")
        seuils = {"consultation_p95_ms": 3000, "taux_erreur_max_pct": 1, "traitement_lourd_s": 30,
                  "paie_complete_s": 1800, "bulletins_pdf_s": 900}
        locust = [{"Name": "consultation: affaires", "95%": "4200"},
                  {"Name": "Aggregated", "Request Count": "1000", "Failure Count": "2", "Requests/s": "12.5"}]
        chrono = {"paie_complete_s": 120.0, "paie": {"erreurs": 0, "exemples_erreurs": []}, "bulletins_pdf_s": 60.0,
                  "traitements": {"cube_mois_s": 3.2}}
        verdicts = {m: ok for m, _v, _s, ok in rapport.evaluer(seuils, locust, chrono)}
        self.assertFalse(verdicts["consultation: affaires — p95 (ms)"])
        self.assertTrue(verdicts["Taux d'erreur global (%)"])
        self.assertTrue(verdicts["Paie complète du mois (s)"])
        self.assertTrue(verdicts["Traitement lourd cube_mois_s"])
