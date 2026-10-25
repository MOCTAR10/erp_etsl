"""Écarts M11 (2026-10-21) — recette des lignes A du tri (paramètres provisoires pour les valeurs ETSL).

Révision par ligne mensuelle, PV de validation archivé 10 ans, tables RGM_*, axes activité / profil, pipe pondéré →
budget de produits, imputation des charges de structure, KPI KP-M11-01 à 12, plan d'action de sous-activité,
reporting J+4 / J+6 par horizon (PDF archivé), revue P-M11.10, validation de la marge d'affaire, coût MO par affaire,
provision 408 des réceptions non facturées.
"""

from datetime import date
from decimal import Decimal

from accounting_kernel.models import AccountMove, AccountMoveLine, FiscalYear, Journal, Period
from accounting_kernel.services import post_move
from commercial.models import Affaire, Opportunity
from referentiels.models import Account, AnalyticAxis, Partner

from .models import (
    Budget,
    BudgetLigne,
    BudgetRevision,
    ClotureGestion,
    ParametreGestion,
    PlanActionSousActivite,
    ProvisionFnp,
    RevuePerformance,
)
from .services import compute_variance
from .tests import BASE, BaseGestionTest
from users.models import User


class EcartsM11Base(BaseGestionTest):
    def setUp(self):
        super().setUp()
        self.fy = FiscalYear.objects.get(year=2026)
        self.dga = User.objects.create_user(email="dga@etls.local", password="Etls#Demo2026", role=User.Role.DGA)
        self.client.force_authenticate(self.finance)

    def period(self, n):
        return Period.objects.get(fiscal_year=self.fy, number=n)

    def ecriture(self, compte, montant, analytic=None, jour=date(2026, 1, 15), sens="credit"):
        move = AccountMove.objects.create(journal=Journal.objects.get(code="OD"), period=self.period(jour.month), date=jour,
                                          reference="T", label="T", status=AccountMove.Status.DRAFT)
        autre = {"credit": "debit", "debit": "credit"}[sens]
        AccountMoveLine.objects.create(move=move, account=Account.objects.get(code=compte), analytic_account=analytic,
                                       order=1, **{sens: Decimal(montant)})
        AccountMoveLine.objects.create(move=move, account=Account.objects.get(code="512000"), order=2,
                                       **{autre: Decimal(montant)})
        post_move(move)

    def viser(self, url):
        for who, visa in ((self.finance, "daf"), (self.dga, "cg")):
            self.client.force_authenticate(who)
            r = self.client.post(url, {"visa": visa}, format="json")
            self.assertEqual(r.status_code, 200, r.content)
        self.client.force_authenticate(self.finance)
        return r

    def budget_approuve(self, **kw):
        b = Budget.objects.create(label="Atelier", type_budget=kw.pop("type_budget", "charge"), fiscal_year=self.fy,
                                  montant=Decimal("200"), **kw)
        BudgetLigne.objects.create(budget=b, period=self.period(1), montant=Decimal("100"))
        BudgetLigne.objects.create(budget=b, period=self.period(2), montant=Decimal("100"))
        self.viser(f"{BASE}budgets/{b.pk}/approuver/")
        b.refresh_from_db()
        return b


class RevisionParLigneEtPvTests(EcartsM11Base):
    def test_pv_archive_au_second_visa(self):
        b = self.budget_approuve()
        self.assertEqual(b.statut, "approuve")
        self.assertIsNotNone(b.pv_document)
        self.assertEqual(b.pv_document.type.retention_years, 10)
        self.assertEqual(b.pv_document.status, "archived")

    def test_revision_d_une_ligne_mensuelle(self):
        b = self.budget_approuve()
        r = self.client.post(f"{BASE}revisions/", {"budget": str(b.pk), "date_revision": "2026-03-01"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        rev = r.data["id"]
        r = self.client.post(f"{BASE}revision-lignes/", {"revision": rev, "period": self.period(2).pk,
                                                        "nouveau_montant": "300"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(BudgetRevision.objects.get(pk=rev).nouveau_montant, Decimal("400"))
        # doublon de période normalisé en 400
        r = self.client.post(f"{BASE}revision-lignes/", {"revision": rev, "period": self.period(2).pk,
                                                        "nouveau_montant": "10"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.viser(f"{BASE}revisions/{rev}/appliquer/")
        b.refresh_from_db()
        self.assertEqual(b.montant, Decimal("400"))
        self.assertEqual(b.lignes.get(period=self.period(2)).montant, Decimal("300"))
        rev = BudgetRevision.objects.get(pk=rev)
        self.assertEqual((rev.statut, rev.pv_document is not None), ("appliquee", True))
        r = self.client.post(f"{BASE}revision-lignes/", {"revision": str(rev.pk), "period": self.period(3).pk,
                                                        "nouveau_montant": "10"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_edition_d_un_brouillon(self):
        b = Budget.objects.create(label="X", type_budget="charge", fiscal_year=self.fy, montant=Decimal("10"))
        r = self.client.patch(f"{BASE}budgets/{b.pk}/", {"label": "Atelier 2026", "montant": "20"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)


class ParametresEtAxesTests(EcartsM11Base):
    def test_tables_rgm_provisoires(self):
        r = self.client.get(f"{BASE}parametres/?table=RGM_POND_PROSPECT&page_size=50")
        rows = r.data["results"] if isinstance(r.data, dict) else r.data
        self.assertEqual({p["code"]: p["valeur"] for p in rows},
                         {"POND_SIGNE": "90.00", "POND_EN_COURS": "60.00", "POND_PROSPECT": "25.00"})
        self.assertTrue(all(p["est_provisoire"] for p in rows))
        for table in ("RGM_PARAM_STRUCTURE", "RGM_TAUX_STRUCTURE", "KPI_CIBLES"):
            self.assertTrue(ParametreGestion.objects.filter(table=table).exists(), table)
        r = self.client.get(f"{BASE}parametres/?page_size=100")
        rows = r.data["results"] if isinstance(r.data, dict) else r.data
        self.assertNotIn("POND_SIGNE", {p["code"] for p in rows})

    def test_axes_activite_profil(self):
        self.client.force_authenticate(self.logistique)
        self.assertEqual(self.client.post(f"{BASE}axes/initialiser/").status_code, 403)
        self.client.force_authenticate(self.finance)
        self.assertEqual(self.client.post(f"{BASE}axes/initialiser/").status_code, 200)
        self.assertTrue(AnalyticAxis.objects.filter(code="AX-ACT", nature_m11__nature="activite").exists())
        prof = AnalyticAxis.objects.get(code="AX-PROF", nature_m11__nature="profil")
        self.assertTrue(prof.values.filter(code="global_rental").exists())
        r = self.client.post(f"{BASE}valeurs-axes/", {"axis": prof.pk, "code": "regie", "label": "Régie"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        # Budget par profil : réalisé = écritures des affaires de ce profil.
        affaire = Affaire.objects.create(title="GR", is_global_rental=True, status="en_cours")
        affaire.assurer_compte_analytique()
        self.ecriture("701000", "700", analytic=affaire.analytic)
        b = Budget.objects.create(label="GR", type_budget="produit", fiscal_year=self.fy, axis=prof,
                                  analytic=prof.values.get(code="global_rental"), montant=Decimal("1000"))
        BudgetLigne.objects.create(budget=b, period=self.period(1), montant=Decimal("1000"))
        self.assertEqual(compute_variance(b)["totals"]["realise"], Decimal("700"))


class PipeKpiImputationTests(EcartsM11Base):
    def test_pipe_pondere_vers_budget_de_produits(self):
        Opportunity.objects.create(subject="A", stage="negociation", amount=Decimal("1000"),
                                   expected_close=date(2026, 3, 15))
        Opportunity.objects.create(subject="B", stage="prospection", amount=Decimal("1200"))
        r = self.client.get(f"{BASE}pipe-budget/?fiscal_year={self.fy.pk}")
        self.assertEqual(r.data["total"], "900.00")  # 600 + 300
        r = self.client.post(f"{BASE}pipe-budget/proposer/", {"fiscal_year": self.fy.pk}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        b = Budget.objects.get(pk=r.data["budget"])
        self.assertEqual((b.type_budget, b.statut, b.montant), ("produit", "brouillon", Decimal("900")))
        self.assertEqual(b.lignes.get(period=self.period(3)).montant, Decimal("625"))
        self.assertEqual(sum(l.montant for l in b.lignes.all()), Decimal("900"))

    def test_pipe_commercial_et_controle_gestion_meme_source(self):
        """B03 (audit premium) : mêmes pondérations (paramètres RGM_POND_PROSPECT) ; seul le périmètre diffère —
        le Pipeline montre tous les horizons et, en « dont clôtures », exactement le chiffre du contrôle de gestion."""
        from commercial.services import pipe_pondere

        Opportunity.objects.create(subject="A", stage="negociation", amount=Decimal("1000"), expected_close=date(2026, 3, 15))
        Opportunity.objects.create(subject="B", stage="prospection", amount=Decimal("1200"))
        Opportunity.objects.create(subject="C", stage="offre", amount=Decimal("5000"), expected_close=date(2027, 6, 1))
        self.client.get(f"{BASE}parametres/")
        ParametreGestion.objects.filter(code="POND_EN_COURS").update(valeur=50)  # modifié par ETSL à l'écran
        cg = self.client.get(f"{BASE}pipe-budget/?fiscal_year={self.fy.pk}").data["total"]
        self.assertEqual(cg, "800.00")  # 1000 × 50 % + 1200 × 25 %
        self.assertEqual(pipe_pondere(2026)["total"], 800.0)
        self.assertEqual(pipe_pondere()["total"], 3300.0)  # + 5000 × 50 % (clôture 2027)
        self.assertEqual(pipe_pondere()["ponderations"]["en_cours"], 0.5)

    def test_douze_kpi(self):
        self.ecriture("701000", "1000")
        r = self.client.get(f"{BASE}kpis/?fiscal_year={self.fy.pk}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual([k["code"] for k in r.data["kpis"]], [f"KP-M11-{n:02d}" for n in range(1, 13)])
        self.assertTrue(r.data["cibles_provisoires"])
        self.assertEqual(self.client.get(f"{BASE}kpis/").status_code, 400)

    def test_imputation_des_charges_de_structure_cle_ca(self):
        ParametreGestion.objects.filter(code="STRUCT_CLE_REPARTITION").delete()
        self.client.get(f"{BASE}parametres/")
        ParametreGestion.objects.filter(code="STRUCT_CLE_REPARTITION").update(valeur=2)
        a1 = Affaire.objects.create(title="A1", status="en_cours", contract_amount=Decimal("5000"))
        a1.assurer_compte_analytique()
        a2 = Affaire.objects.create(title="A2", status="en_cours")
        a2.assurer_compte_analytique()
        self.ecriture("701000", "3000", analytic=a1.analytic)
        self.ecriture("701000", "1000", analytic=a2.analytic)
        self.ecriture("601000", "800", sens="debit")  # sans axe = structure
        r = self.client.get(f"{BASE}imputation-structure/?fiscal_year={self.fy.pk}")
        self.assertEqual(r.status_code, 200, r.content)
        rows = {x["code"]: x for x in r.data["rows"]}
        self.assertEqual(rows[a1.code]["structure_imputee"], "600.00")
        self.assertEqual(rows[a2.code]["structure_imputee"], "200.00")
        self.assertEqual(rows[a1.code]["taux_structure_reel"], "20.00")
        self.assertTrue(r.data["provisoire"])

    def test_tableau_de_bord_par_profil_et_client(self):
        Affaire.objects.create(title="A1", status="en_cours", is_global_rental=True, contract_amount=Decimal("10"))
        for par in ("profil", "client", "affaire"):
            r = self.client.get(f"{BASE}tableau-bord/?par={par}")
            self.assertEqual(r.status_code, 200, r.content)
        self.assertIn("global_rental", [x["cle"] for x in self.client.get(f"{BASE}tableau-bord/?par=profil").data["lignes"]])
        self.assertEqual(self.client.get(f"{BASE}tableau-bord/?par=xx").status_code, 400)

    def test_marges_brute_op_nette_parametrees(self):
        self.ecriture("701000", "1000")
        self.ecriture("618000", "100", sens="debit")
        r = self.client.get(f"{BASE}niveaux-marge/?fiscal_year={self.fy.pk}").data
        self.assertEqual((r["marge_brute"], r["marge_nette"], r["provisoire"]), (Decimal("1000"), Decimal("900"), True))
        ParametreGestion.objects.filter(code="MARGE_NIVEAU_GR").update(valeur=1)
        r = self.client.get(f"{BASE}niveaux-marge/?fiscal_year={self.fy.pk}").data
        self.assertEqual(r["marge_brute"], Decimal("900"))


class PlanReportingRevueTests(EcartsM11Base):
    def test_plan_d_action_de_sous_activite(self):
        b = self.budget_approuve()
        r = self.client.post(f"{BASE}plans-sous-activite/", {"budget": str(b.pk), "actions": "Relancer l'atelier"},
                             format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(r.data["code"].startswith("PAS"))
        self.assertIsNotNone(r.data["echeance"])
        pid = r.data["id"]
        self.assertEqual(self.client.post(f"{BASE}plans-sous-activite/{pid}/demarrer/").status_code, 200)
        self.assertEqual(self.client.post(f"{BASE}plans-sous-activite/{pid}/clore/").status_code, 400)
        r = self.client.post(f"{BASE}plans-sous-activite/{pid}/clore/", {"suivi": "Charge rétablie"}, format="json")
        self.assertEqual(r.data["statut"], "clos")
        self.assertEqual(PlanActionSousActivite.objects.get(pk=pid).clos_par, self.finance)

    def test_reporting_par_horizon_et_archivage(self):
        self.ecriture("701000", "1000")
        c = ClotureGestion.objects.create(period=self.period(1))
        r = self.client.get(f"{BASE}reportings/donnees/?cloture={c.pk}&type=j4")
        self.assertEqual((r.status_code, r.data["horizon"]), (200, 12))
        self.assertEqual(r.data["rows"][-1]["produits"], "1000.00")
        r = self.client.get(f"{BASE}reportings/donnees/?cloture={c.pk}&type=j6")
        self.assertEqual(len(r.data["rows"]), 3)
        r = self.client.get(f"{BASE}reportings/donnees/?cloture={c.pk}&type=j4&export=pdf")
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertEqual(self.client.post(f"{BASE}reportings/archiver/", {"cloture": str(c.pk), "type": "j4"}).status_code, 400)
        ClotureGestion.objects.filter(pk=c.pk).update(statut="realisee", date_cloture=date(2026, 2, 2))
        r = self.client.post(f"{BASE}reportings/archiver/", {"cloture": str(c.pk), "type": "j4"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertIsNotNone(r.data["document"])
        r = self.client.post(f"{BASE}reportings/archiver/", {"cloture": str(c.pk), "type": "j4"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_revue_de_performance(self):
        r = self.client.post(f"{BASE}revues-performance/", {"period": self.period(1).pk, "date_revue": "2026-02-10",
                                                            "participants": "DG, DAF, CG"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertIn("KPI", r.data["ordre_du_jour"])
        rid = r.data["id"]
        self.assertEqual(self.client.post(f"{BASE}revues-performance/{rid}/tenir/").status_code, 400)
        r = self.client.post(f"{BASE}revues-performance/{rid}/tenir/", {"decisions": "Réduire le 618"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        revue = RevuePerformance.objects.get(pk=rid)
        self.assertEqual((revue.statut, len(revue.kpis), revue.pv_document is not None), ("tenue", 12, True))
        self.assertEqual(self.client.patch(f"{BASE}revues-performance/{rid}/", {"participants": "x"}, format="json").status_code, 400)


class MargeMoProvisionTests(EcartsM11Base):
    def test_validation_de_la_marge_d_affaire(self):
        a = Affaire.objects.create(title="A", status="confirmee", contract_amount=Decimal("1000"), margin=Decimal("200"))
        rows = {x["code"]: x for x in self.client.get(f"{BASE}marges-affaires/").data["rows"]}
        self.assertEqual(rows[a.code]["validation"], "a_valider")
        self.client.force_authenticate(self.logistique)
        self.assertEqual(self.client.post(f"{BASE}marges-affaires/{a.pk}/valider/").status_code, 403)
        self.client.force_authenticate(self.finance)
        self.assertEqual(self.client.post(f"{BASE}marges-affaires/{a.pk}/valider/").status_code, 200)
        rows = {x["code"]: x for x in self.client.get(f"{BASE}marges-affaires/").data["rows"]}
        self.assertEqual((rows[a.code]["validation"], rows[a.code]["taux"]), ("validee", "20.00"))
        Affaire.objects.filter(pk=a.pk).update(margin=Decimal("150"))
        rows = {x["code"]: x for x in self.client.get(f"{BASE}marges-affaires/").data["rows"]}
        self.assertEqual(rows[a.code]["validation"], "a_revalider")
        self.assertEqual(self.client.post(f"{BASE}marges-affaires/{a.pk}/rejeter/").status_code, 400)

    def test_cout_mo_par_affaire(self):
        r = self.client.get(f"{BASE}cout-mo-affaires/?debut=2026-01-01&fin=2026-12-31")
        self.assertEqual((r.status_code, r.data["rows"]), (200, []))
        self.assertEqual((r.data["heures"], r.data["pct_heures_valorisees"]), ("0.00", None))
        self.assertEqual(self.client.get(f"{BASE}cout-mo-affaires/?debut=xx").status_code, 400)

    def test_provision_408_et_extourne(self):
        from achats.models import GoodsReceipt, GoodsReceiptLine, PurchaseOrder, PurchaseOrderLine

        f = Partner.objects.create(code="F-X", name="Fournisseur", kind=Partner.Kind.FOURNISSEUR)
        bc = PurchaseOrder.objects.create(status=PurchaseOrder.Status.CONFIRMEE, supplier=f)
        ligne = PurchaseOrderLine.objects.create(purchase_order=bc, label="Tube", quantity=10, unit_price=Decimal("100"))
        br = GoodsReceipt.objects.create(purchase_order=bc, received_at=date(2026, 1, 20))
        GoodsReceiptLine.objects.create(receipt=br, purchase_order_line=ligne, quantity=4)
        GoodsReceipt.objects.filter(pk=br.pk).update(status=GoodsReceipt.Status.VALIDE)
        r = self.client.get(f"{BASE}provisions-fnp/apercu/?date=2026-01-31")
        self.assertEqual((r.data["total"], r.data["compte"]), ("400.00", "408100"))
        r = self.client.post(f"{BASE}provisions-fnp/provisionner/", {"date_arrete": "2026-01-31"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        p = ProvisionFnp.objects.get(pk=r.data["id"])
        lignes = {l.account.code: (l.debit, l.credit) for l in p.move.lines.select_related("account")}
        self.assertEqual(lignes, {"601000": (Decimal("400"), Decimal("0")), "408100": (Decimal("0"), Decimal("400"))})
        self.assertEqual(p.move.status, AccountMove.Status.POSTED)
        r = self.client.post(f"{BASE}provisions-fnp/provisionner/", {"date_arrete": "2026-02-28"}, format="json")
        self.assertEqual(r.status_code, 400)  # provision précédente non extournée
        r = self.client.post(f"{BASE}provisions-fnp/{p.pk}/extourner/")
        self.assertEqual(r.status_code, 200, r.content)
        p.refresh_from_db()
        self.assertEqual((p.statut, p.extourne.date), ("extournee", date(2026, 2, 1)))
        self.client.force_authenticate(self.logistique)
        self.assertEqual(self.client.post(f"{BASE}provisions-fnp/provisionner/", {"date_arrete": "2026-02-28"}).status_code, 403)
