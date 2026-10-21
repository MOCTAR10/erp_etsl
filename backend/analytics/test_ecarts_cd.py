"""Écarts Couche D (BI / pilotage) — tests de recette par critère du CDC.

Marts marges M11 / pipe / qualité ITP-CND (SQL rendu et exécuté), reporting pétrolier ITP / CND, exports Excel / PDF,
cash-flow 13 semaines, pipe → budget, alertes calendaires (garantie, agrément, audit interne, revue de direction) et
palier J-60, seuils budgétaires 90 / 100 / 110 % planifiés, publication après clôture M11, archive GED des cubes,
scellement des marts et purge des archives échues.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError

from accounting_kernel.models import Period
from analytics import cubes, pilotage
from analytics.models import CubeArchive, ParametreCube, ScelleMart
from analytics.services import reporting_petrolier
from analytics.tasks import notifier_echeances
from commercial.models import Affaire, Opportunity
from controle_gestion.models import Budget, BudgetLigne, ClotureGestion
from controle_gestion.services import compute_marges
from controle_gestion.tests import BaseGestionTest
from documents.services import visible_documents
from maintenance.models import Actif
from qualite.models import AuditQualite, ControleQualite, PointInspection, RevueDirectionQualite
from referentiels.models import Partner
from users.models import User
from workflow.models import Notification

from .test_marts_couche_d import rendre_mart

BASE = "/api/analytics/"


def _param(code, valeur):
    cubes.get_param_cube(code)
    ParametreCube.objects.filter(code=code).update(valeur=Decimal(valeur))


class _Base(BaseGestionTest):
    def setUp(self):
        super().setUp()
        self.pdg = User.objects.create_user(email="pdg@etls.ga", password="x-Audit-2026", role=User.Role.PDG)
        self.affaire = Affaire.objects.create(title="Maintenance pipelines", affaire_type="maintenance", analytic=self.analytic_aff)


class MartsTests(_Base):
    def test_tous_les_marts_s_executent(self):
        """Équivalent CI de `dbt build` : chaque mart (sources + staging en CTE) s'exécute sur le schéma courant."""
        from django.db import connection, transaction

        noms = pilotage.marts_disponibles()
        self.assertIn("dm_marges_m11", noms)
        for nom in noms:
            with self.subTest(mart=nom), transaction.atomic(), connection.cursor() as cur:
                cur.execute(pilotage.rendre_sql_mart(nom))

    def test_marges_m11_egales_compute_marges(self):
        self._post_produit("5000000.00", analytic=self.analytic_aff, ref="M1")
        self._post_charge("1200000.00", analytic=self.analytic_aff, ref="M2")
        self._post_charge_gr("300000.00", analytic=self.analytic_aff, ref="M3")
        self._post_charge("999.00", analytic=self.analytic_cc, ref="M4")  # hors affaire : absent du mart
        regle = compute_marges(self._fy.pk, analytic=self.analytic_aff.pk)["totals"]
        rows = rendre_mart("dm_marges_m11")
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual((r["produits"], r["charges"], r["cout_gr"]), (regle["produits"], regle["charges"], regle["cout_gr"]))
        self.assertEqual(r["marge"], Decimal("3500000.00"))
        self.assertEqual(r["taux_marge_pct"], Decimal("70.00"))

    def test_pipe_affaires_egal_pipe_pondere(self):
        from commercial.services import pipe_pondere

        client = None  # opportunité sans fiche client : seul le pipe compte
        for stage, montant in (("gagne", "1000"), ("offre", "2000"), ("prospection", "4000"), ("perdu", "9999")):
            Opportunity.objects.create(client=client, subject=stage, stage=stage, amount=Decimal(montant))
        rows = [r for r in rendre_mart("dm_pipe_affaires") if r["objet"] == "opportunite"]
        self.assertEqual(sum(r["montant_pondere"] for r in rows), Decimal(str(pipe_pondere()["total"])))

    def test_qualite_itp_cnd_egal_reporting(self):
        _qualite()
        r = rendre_mart("dm_qualite_itp_cnd")[0]
        p = reporting_petrolier(self.admin)
        self.assertEqual((r["itp_plans"], r["itp_points"], r["itp_points_leves"]), (p["itp"]["plans"], p["itp"]["points"], p["itp"]["points_leves"]))
        self.assertEqual((r["cnd_controles"], r["cnd_non_conformes"]), (p["cnd"]["controles"], p["cnd"]["non_conformes"]))


def _qualite():
    itp = ControleQualite.objects.create(code="ITP-1", type_controle="itp", statut="en_cours")
    PointInspection.objects.create(controle=itp, ordre=1, description="Soudure", type_point="arret", statut="leve")
    PointInspection.objects.create(controle=itp, ordre=2, description="Peinture", type_point="arret")
    ControleQualite.objects.create(code="CND-1", type_controle="cnd", methode_cnd="RT", statut="valide", resultat="conforme")
    ControleQualite.objects.create(code="CND-2", type_controle="cnd", methode_cnd="UT", statut="valide", resultat="non_conforme")
    ControleQualite.objects.create(code="CND-3", type_controle="cnd", methode_cnd="UT", statut="en_attente")


class PetrolierEtExportsTests(_Base):
    def test_indicateurs_itp_cnd(self):
        _qualite()
        p = reporting_petrolier(self.admin)
        self.assertEqual((p["itp"]["plans"], p["itp"]["points"], p["itp"]["points_arret_en_attente"]), (1, 2, 1))
        self.assertEqual(p["itp"]["taux_levee"], 0.5)
        self.assertEqual((p["cnd"]["controles"], p["cnd"]["en_cours"], p["cnd"]["par_methode"]), (3, 1, {"RT": 1, "UT": 2}))
        self.assertEqual(p["cnd"]["taux_rejet"], 0.5)

    def test_exports_xlsx_et_pdf(self):
        self.client.force_authenticate(self.finance)
        for url in ("dashboard/", "petrolier/", "cubes/?axes=periode", "pilotage/"):
            sep = "&" if "?" in url else "?"
            r = self.client.get(f"{BASE}{url}{sep}export=xlsx")
            self.assertEqual(r.status_code, 200, url)
            self.assertTrue(r.content.startswith(b"PK"), url)
            self.assertIn("attachment", r["Content-Disposition"])
            r = self.client.get(f"{BASE}{url}{sep}export=pdf")
            self.assertEqual((r.status_code, r["Content-Type"]), (200, "application/pdf"), url)
            self.assertTrue(r.content.startswith(b"%PDF"))
        self.assertEqual(self.client.get(f"{BASE}petrolier/?export=doc").status_code, 400)

    def test_export_cube_reserve_au_cercle_des_montants(self):
        self.client.force_authenticate(self.logistique)
        self.assertEqual(self.client.get(f"{BASE}cubes/?export=xlsx").status_code, 403)
        self.assertEqual(self.client.get(f"{BASE}pilotage/?export=pdf").status_code, 403)
        self.assertEqual(self.client.get(f"{BASE}petrolier/?export=pdf").status_code, 200)


class DirectionTests(_Base):
    def test_cashflow_13_semaines(self):
        from comptabilite.models import Engagement, FactureClient
        from referentiels.models import Account

        client = Partner.objects.create(code="CL-2", name="Perenco", kind="client")
        today = date(2026, 10, 21)  # mercredi
        FactureClient.objects.create(client=client, statut="emise", date=today, echeance=today + timedelta(days=10),
                                     montant_ht=Decimal("1000000"), montant_ttc=Decimal("1180000"))
        FactureClient.objects.create(client=client, statut="emise", date=today - timedelta(days=60), echeance=today - timedelta(days=30),
                                     montant_ttc=Decimal("500000"))  # en retard : semaine 1
        FactureClient.objects.create(client=client, statut="brouillon", date=today, montant_ttc=Decimal("7"))
        Engagement.objects.create(objet="Location grue", montant=Decimal("400000"), statut="approuve",
                                  compte_depense=Account.objects.get(code="601000"), date_engagement=today)
        cf = pilotage.cashflow_13_semaines(today)
        self.assertEqual(len(cf["semaines"]), 13)
        self.assertEqual(cf["semaines"][0]["debut"], "2026-10-19")
        self.assertEqual(Decimal(cf["semaines"][0]["encaissements"]), Decimal("500000"))
        self.assertEqual(Decimal(cf["semaines"][1]["encaissements"]), Decimal("1180000"))
        # Engagement : date + 30 jours (paramètre provisoire) = 20/11 → semaine 5.
        self.assertEqual(Decimal(cf["semaines"][4]["decaissements"]), Decimal("400000"))
        self.assertEqual(Decimal(cf["solde_final"]), Decimal("1280000"))
        _param("TRESO_DELAI_DECAISSEMENT", "0")
        self.assertEqual(Decimal(pilotage.cashflow_13_semaines(today)["semaines"][0]["decaissements"]), Decimal("400000"))

    def test_pipe_vers_budget(self):
        Budget.objects.create(label="CA 2026", type_budget="produit", fiscal_year=self._fy, montant=Decimal("10000000"), statut="approuve")
        self._post_produit("2000000.00", analytic=self.analytic_aff, ref="P1")
        client = None
        Opportunity.objects.create(client=client, subject="x", stage="offre", amount=Decimal("5000000"))
        pb = pilotage.pipe_vers_budget(2026)
        self.assertEqual((pb["budget_produits"], pb["realise"], pb["pipe_pondere"]["total"]), ("10000000.00", "2000000.00", "3000000.00"))
        self.assertEqual((pb["atterrissage"], pb["reste_a_couvrir"], pb["couverture_pct"]), ("5000000.00", "5000000.00", "50.0"))

    def test_api_pilotage_et_droits(self):
        self.client.force_authenticate(self.finance)
        r = self.client.get(BASE + "pilotage/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(set(r.json()) >= {"cashflow", "pipe_budget", "seuils_budget", "retention"}, True)
        self.client.force_authenticate(self.logistique)
        self.assertEqual(self.client.get(BASE + "pilotage/").status_code, 403)


class AlertesCalendairesTests(_Base):
    def setUp(self):
        super().setUp()
        self.today = date.today()
        self.maint = User.objects.create_user(email="maint@etls.ga", password="x-Audit-2026", role=User.Role.MAINTENANCE)
        self.qaqc = User.objects.create_user(email="qa@etls.ga", password="x-Audit-2026", role=User.Role.QAQC)

    def test_quatre_familles_et_palier_j60(self):
        Actif.objects.create(designation="Compresseur", garanti_jusqu=self.today + timedelta(days=60))
        Partner.objects.create(code="F-1", name="Aciers SA", kind="fournisseur", agree_qualite_jusqu=self.today + timedelta(days=30))
        AuditQualite.objects.create(type_audit="interne", perimetre="Atelier soudure", date_prevue=self.today + timedelta(days=15))
        RevueDirectionQualite.objects.create(annee=self.today.year - 1, date_revue=pilotage._ajouter_mois(self.today, -12) + timedelta(days=90),
                                             statut="validee")
        types = {i["type"]: i for i in pilotage.alertes_calendaires()}
        self.assertEqual(set(types), {"garantie", "agrement_fournisseur", "audit_interne", "revue_direction"})
        self.assertEqual((types["garantie"]["bande"], types["revue_direction"]["jours"]), ("j60", 90))
        notifier_echeances()
        self.assertTrue(Notification.objects.filter(user=self.maint, subject__contains="J-60").exists())
        self.assertTrue(Notification.objects.filter(user=self.qaqc, subject__contains="J-30").exists())
        self.assertTrue(Notification.objects.filter(user=self.pdg, subject__contains="Revue de direction").exists())

    def test_palier_j60_desactivable_et_droits(self):
        Actif.objects.create(designation="Pompe", garanti_jusqu=self.today + timedelta(days=60))
        _param("PALIER_ALERTE_J60", "0")
        notifier_echeances()
        self.assertFalse(Notification.objects.filter(user=self.maint).exists())
        self.client.force_authenticate(self.maint)
        r = self.client.get(BASE + "alertes-calendaires/")
        self.assertIn("garantie", [i["type"] for i in r.json()["items"]])  # + revue de direction annuelle par défaut
        self.assertNotIn(60, r.json()["paliers"])
        self.assertEqual(self.client.get(BASE + "alertes/").json()["calendrier"][0]["type"], "garantie")


class SeuilsBudgetairesTests(_Base):
    def _budget(self, montant):
        b = Budget.objects.create(label="Charges atelier", type_budget="charge", fiscal_year=self._fy, analytic=self.analytic_cc,
                                  montant=Decimal(montant), statut="approuve")
        BudgetLigne.objects.create(budget=b, period=Period.objects.get(number=1, fiscal_year=self._fy), montant=Decimal(montant))
        return b

    def test_alerte_90_puis_depassement_110_notifies_une_fois(self):
        b = self._budget("1000000")
        self._post_charge("950000.00", analytic=self.analytic_cc, ref="S1")
        self.assertEqual(pilotage.seuils_budgetaires()[0]["niveau"], "alerte")
        self.assertEqual(pilotage.controler_seuils_budgetaires(), 2)  # finance + PDG
        self.assertEqual(pilotage.controler_seuils_budgetaires(), 0)
        self._post_charge("200000.00", analytic=self.analytic_cc, ref="S2")
        ligne = pilotage.seuils_budgetaires()[0]
        self.assertEqual((ligne["budget"], ligne["niveau"], ligne["taux_pct"]), (b.code, "depasse", "115.0"))
        pilotage.controler_seuils_budgetaires()
        n = Notification.objects.get(user=self.finance, subject__contains="110 %")
        self.assertIn("analyse d'écart est obligatoire", n.message)

    def test_tache_quotidienne_existante_controle_les_seuils(self):
        from analytics.tasks import alimenter_cubes

        self._budget("100000")
        self._post_charge("100000.00", analytic=self.analytic_cc, ref="S3")
        alimenter_cubes()
        self.assertTrue(Notification.objects.filter(user=self.pdg, subject__contains="seuil 100 %").exists())


class PublicationApresClotureTests(_Base):
    def setUp(self):
        super().setUp()
        self._post_produit("5000000.00", analytic=self.analytic_aff, ref="K1")
        cubes.alimenter_cube("2026-01")

    def test_consommateur_ne_voit_pas_un_mois_non_cloture(self):
        lu = cubes.lire_cube(None, ("periode",), user=self.pdg)
        self.assertEqual((lu["rows"], lu["periodes_non_publiees"]), ([], ["2026-01"]))
        self.assertEqual(len(cubes.lire_cube(None, ("periode",), user=self.finance)["rows"]), 1)  # producteur
        ClotureGestion.objects.create(period=Period.objects.get(number=1, fiscal_year=self._fy), statut="realisee")
        self.assertEqual(len(cubes.lire_cube(None, ("periode",), user=self.pdg)["rows"]), 1)

    def test_blocage_parametrable(self):
        _param("BLOCAGE_AVANT_CLOTURE", "0")
        self.assertEqual(len(cubes.lire_cube(None, ("periode",), user=self.pdg)["rows"]), 1)
        self.client.force_authenticate(self.admin)
        rows = self.client.get(BASE + "cubes/parametres/").json()
        rows = rows["results"] if isinstance(rows, dict) else rows
        p = next(x for x in rows if x["code"] == "BLOCAGE_AVANT_CLOTURE")
        self.assertEqual(self.client.patch(f"{BASE}cubes/parametres/{p['id']}/", {"valeur": "2"}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(f"{BASE}cubes/parametres/{p['id']}/", {"valeur": "1"}, format="json").status_code, 200)


class RetentionEtScellementTests(_Base):
    def setUp(self):
        super().setUp()
        self._post_produit("5000000.00", analytic=self.analytic_aff, ref="R1")

    def test_archive_du_cube_deposee_en_ged_et_refusee_hors_montants(self):
        archive = cubes.archiver_cube("2026-01", self.finance, today=date(2026, 10, 18))
        doc = archive.document
        self.assertIsNotNone(doc)
        self.assertEqual((doc.type.retention_years, doc.status), (10, "archived"))
        self.assertIn(b"AFF-PIPE-001", doc.current_version.file.read())
        self.assertFalse(visible_documents(self.logistique).filter(pk=doc.pk).exists())
        self.assertTrue(visible_documents(self.finance).filter(pk=doc.pk).exists())

    def test_scellement_des_marts_par_version(self):
        r = pilotage.sceller_marts(self.finance, noms=["dm_couts_m10", "dm_pointages_m9"])
        self.assertEqual([x["mart"] for x in r], ["dm_couts_m10", "dm_pointages_m9"])
        s = ScelleMart.objects.get(mart="dm_couts_m10")
        self.assertTrue(pilotage.verifier_scelle(s))
        self.assertEqual(s.type_donnees, "financier")
        self.assertEqual(ScelleMart.objects.get(mart="dm_pointages_m9").type_donnees, "operationnel")
        pilotage.sceller_marts(noms=["dm_couts_m10"])  # contenu inchangé : pas de nouveau scellé
        self.assertEqual(ScelleMart.objects.filter(mart="dm_couts_m10").count(), 1)
        self._post_charge("10.00", analytic=self.analytic_aff, ref="R2")
        pilotage.sceller_marts(noms=["dm_couts_m10"])
        self.assertEqual(ScelleMart.objects.filter(mart="dm_couts_m10").count(), 2)
        with self.assertRaises(ValidationError):
            s.save()
        with self.assertRaises(ValidationError):
            s.delete()

    def test_duree_par_type_et_purge(self):
        today = date(2026, 10, 21)
        pilotage.sceller_marts(noms=["dm_couts_m10", "dm_pointages_m9"], today=today)
        dates = dict(ScelleMart.objects.values_list("mart", "conserve_jusqu_au"))
        self.assertEqual((dates["dm_couts_m10"], dates["dm_pointages_m9"]), (date(2036, 10, 21), date(2031, 10, 21)))
        cubes.archiver_cube("2026-01", self.finance, today=today)
        self.assertEqual(pilotage.purger_archives_expirees(today=date(2032, 1, 1)), {"cubes": [], "scelles": 1})
        self.assertEqual(pilotage.purger_archives_expirees(today=date(2037, 1, 1)), {"cubes": ["2026-01"], "scelles": 1})
        self.assertFalse(CubeArchive.objects.exists() or ScelleMart.objects.exists())

    def test_api_scellement(self):
        self.client.force_authenticate(self.finance)
        r = self.client.post(BASE + "marts/scelles/sceller/")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertFalse([x for x in r.json()["resultats"] if "erreur" in x])
        rows = self.client.get(BASE + "marts/scelles/").json()
        rows = rows["results"] if isinstance(rows, dict) else rows
        self.assertTrue(rows and all(x["integre"] for x in rows))
        self.client.force_authenticate(self.pdg)
        self.assertEqual(self.client.post(BASE + "marts/scelles/purger/").status_code, 200)
        self.client.force_authenticate(self.logistique)
        self.assertEqual(self.client.get(BASE + "marts/scelles/").status_code, 403)
