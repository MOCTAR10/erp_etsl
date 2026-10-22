"""Écarts M5 (lot m5m8) — tests de recette : plan d'inventaire annuel, comptage à l'écran, écarts valorisés,
régularisation « MAD » soumise à validation au-delà du seuil (paramètre provisoire), état des écarts exportable."""

from datetime import date
from decimal import Decimal

from rest_framework import status

from referentiels.models import Article, UnitOfMeasure
from stocks.models import Inventaire, MouvementStock, ParametreStock, PlanInventaireTournant, StockQuant
from stocks.services import apply_move, get_param_stock
from users.models import User

from .test_audit import mouvement
from .tests import M5BaseTest, make_user


class _Base(M5BaseTest):
    def setUp(self):
        super().setUp()
        unit = UnitOfMeasure.objects.get(code="U")
        self.articles = [self.article] + [
            Article.objects.create(code=f"ART-{i}", label=f"Article {i}", article_type=Article.ArticleType.MATIERE, unit=unit)
            for i in range(1, 4)
        ]
        for art in self.articles:
            apply_move(mouvement(art, "100", "1000", destination=self.depot_a))  # CUMP 1 000 FCFA
        self.plan = PlanInventaireTournant.objects.create(
            depot=self.depot_a, periodicite_jours=91, articles_par_passage=1, prochaine_date=date(2026, 1, 15)
        )
        self.auth(self.admin)

    def passage(self):
        r = self.client.post(f"/api/stocks/plans-inventaire/{self.plan.id}/generer/")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.content)
        return r.data


class PlanAnnuelTests(_Base):
    def test_plan_annuel_capacite_cycles_et_tranche_conseillee(self):
        r = self.client.get(f"/api/stocks/plans-inventaire/{self.plan.id}/plan-annuel/?annee=2026")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["articles"], 4)
        self.assertEqual(len(r.data["passages_prevus"]), 4)  # 15/01, 16/04, 16/07, 15/10
        self.assertEqual(r.data["capacite"], 4)
        self.assertEqual(r.data["cycles_prevus"], "1.00")
        self.assertTrue(r.data["conforme"])
        get_param_stock("INVENTAIRE_CYCLES_AN")
        ParametreStock.objects.filter(code="INVENTAIRE_CYCLES_AN").update(valeur=Decimal("2"))
        r = self.client.get(f"/api/stocks/plans-inventaire/{self.plan.id}/plan-annuel/?annee=2026").data
        self.assertFalse(r["conforme"])
        self.assertEqual(r["articles_par_passage_conseille"], 2)

    def test_annee_invalide_400(self):
        r = self.client.get(f"/api/stocks/plans-inventaire/{self.plan.id}/plan-annuel/?annee=abc")
        self.assertEqual(r.status_code, 400)

    def test_couverture_apres_passage_compte_et_cloture(self):
        inv = self.passage()
        ligne = inv["lignes"][0]
        r = self.client.post(f"/api/stocks/inventaires/{inv['id']}/compter/",
                             {"lignes": [{"id": ligne["id"], "quantite_reelle": "100"}]}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.client.post(f"/api/stocks/inventaires/{inv['id']}/cloturer/").status_code, 200)
        annee = date.today().year
        r = self.client.get(f"/api/stocks/plans-inventaire/{self.plan.id}/plan-annuel/?annee={annee}").data
        self.assertEqual(r["articles_comptes"], 1)
        self.assertEqual(r["couverture_pct"], "25.00")
        self.assertEqual(r["realises"][0]["statut"], "cloture")


class ComptageEtRegularisationTests(_Base):
    def test_comptage_ecran_puis_ecarts_valorises(self):
        inv = self.passage()
        ligne = inv["lignes"][0]
        r = self.client.post(f"/api/stocks/inventaires/{inv['id']}/compter/",
                             {"lignes": [{"id": ligne["id"], "quantite_reelle": "-1"}]}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.post(f"/api/stocks/inventaires/{inv['id']}/compter/",
                             {"lignes": [{"id": ligne["id"], "quantite_reelle": "97"}]}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["statut"], "en_cours")
        e = self.client.get(f"/api/stocks/inventaires/{inv['id']}/ecarts/").data
        self.assertEqual(e["lignes"][0]["ecart"], "-3.00")
        self.assertEqual(e["lignes"][0]["valeur_ecart"], "-3000.00")
        self.assertTrue(e["lignes"][0]["hors_tolerance"])  # 3 % > tolérance 2 %
        self.assertFalse(e["validation_requise"])  # 3 000 FCFA < seuil 500 000

    def test_au_dela_du_seuil_validation_mad_requise_avant_cloture(self):
        get_param_stock("SEUIL_VALIDATION_ECART")
        ParametreStock.objects.filter(code="SEUIL_VALIDATION_ECART").update(valeur=Decimal("1000"))
        inv = self.passage()
        ligne = inv["lignes"][0]
        self.client.post(f"/api/stocks/inventaires/{inv['id']}/compter/",
                         {"lignes": [{"id": ligne["id"], "quantite_reelle": "95"}]}, format="json")
        r = self.client.post(f"/api/stocks/inventaires/{inv['id']}/cloturer/")
        self.assertEqual(r.status_code, 400)
        self.assertIn("MAD", str(r.data))
        # Logistique ne valide pas ; la finance si.
        self.auth(self.user)
        self.assertEqual(self.client.post(f"/api/stocks/inventaires/{inv['id']}/valider-ecarts/").status_code, 403)
        self.auth(make_user(User.Role.FINANCE))
        r = self.client.post(f"/api/stocks/inventaires/{inv['id']}/valider-ecarts/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIsNotNone(r.data["ecarts_valides_le"])
        self.auth()
        r = self.client.post(f"/api/stocks/inventaires/{inv['id']}/cloturer/")
        self.assertEqual(r.status_code, 200, r.content)
        mvt = MouvementStock.objects.get(type_mouvement=MouvementStock.Type.INVENTAIRE)
        self.assertIn("Régularisation MAD", mvt.notes)
        art = Article.objects.get(pk=ligne["article"])
        self.assertEqual(StockQuant.objects.get(depot=self.depot_a, article=art).quantity, Decimal("95"))

    def test_comptage_refuse_sur_inventaire_cloture(self):
        inv = Inventaire.objects.create(depot=self.depot_a, date=date.today(), statut=Inventaire.Statut.CLOTURE)
        r = self.client.post(f"/api/stocks/inventaires/{inv.id}/compter/", {"lignes": [{"id": "x"}]}, format="json")
        self.assertEqual(r.status_code, 400)


class EtatEcartsTests(_Base):
    def setUp(self):
        super().setUp()
        inv = self.passage()
        self.client.post(f"/api/stocks/inventaires/{inv['id']}/compter/",
                         {"lignes": [{"id": inv["lignes"][0]["id"], "quantite_reelle": "98"}]}, format="json")
        self.client.post(f"/api/stocks/inventaires/{inv['id']}/cloturer/")
        self.url = f"/api/stocks/plans-inventaire/{self.plan.id}/etat-ecarts/?annee={date.today().year}"

    def test_etat_json_et_exports(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(len(r.data["rows"]), 1)
        self.assertEqual(r.data["valeur_nette"], "-2000.00")
        self.assertEqual(r.data["hors_tolerance"], 0)  # 2 % = tolérance
        x = self.client.get(self.url + "&export=xlsx")
        self.assertEqual(x.status_code, 200)
        self.assertTrue(x.content.startswith(b"PK"))
        p = self.client.get(self.url + "&export=pdf")
        self.assertEqual(p.status_code, 200)
        self.assertTrue(p.content.startswith(b"%PDF"))
        self.assertEqual(self.client.get(self.url + "&export=csv").status_code, 400)

    def test_valeurs_masquees_hors_roles_montants(self):
        self.auth(make_user(User.Role.CHEF_ATELIER))
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIsNone(r.data["valeur_nette"])
        self.assertIsNone(r.data["rows"][0]["valeur_ecart"])

    def test_parametres_provisoires_exposes(self):
        codes = {p["code"]: p for p in self.client.get("/api/stocks/parametres/").data["results"]} \
            if isinstance(self.client.get("/api/stocks/parametres/").data, dict) else \
            {p["code"]: p for p in self.client.get("/api/stocks/parametres/").data}
        for code in ("INVENTAIRE_CYCLES_AN", "ECART_TOLERANCE_PCT", "SEUIL_VALIDATION_ECART"):
            self.assertTrue(codes[code]["est_provisoire"])
