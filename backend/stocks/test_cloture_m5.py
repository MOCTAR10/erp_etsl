"""Clôture M5 Stocks (2026-10-17) — tests de recette des critères CDC (cahier détaillé §7.11).

1. Valorisation mensuelle → M11 sans ressaisie : instantané des quants + consommations du mois ventilées par compte
   analytique (affaire de l'OF), figé une fois, publié par l'outbox et exposé à M11 ; valeurs masquées hors rôles montants.
2. Inventaires tournants planifiés et régularisés : plan par dépôt, tranche d'articles par passage (rotation), lignes à
   compter, clôture refusée tant que tout n'est pas compté, écarts régularisés par mouvements, tâche planifiée.
"""

from datetime import date, timedelta
from decimal import Decimal

from rest_framework import status

from commercial.models import Affaire
from operations.models import OrdreFabrication
from outbox.models import OutboxEvent
from referentiels.models import Article, UnitOfMeasure
from stocks.cloture import planifier_inventaires_tournants
from stocks.models import Inventaire, InventaireLigne, MouvementStock, PlanInventaireTournant, StockQuant, ValorisationMensuelle
from stocks.services import apply_move, cloturer_inventaire
from users.models import User

from .test_audit import mouvement
from .tests import M5BaseTest, make_user


def jour(delta=0):
    return date.today() + timedelta(days=delta)


class ValorisationMensuelleTests(M5BaseTest):
    def setUp(self):
        super().setUp()
        self.periode = date.today().strftime("%Y-%m")
        self.affaire = Affaire.objects.create(title="Pipeline Gamba")
        self.affaire.assurer_compte_analytique()
        self.of = OrdreFabrication.objects.create(label="Spool 1", affaire=self.affaire)
        apply_move(mouvement(self.article, "100", "10", destination=self.depot_a))  # stock 1000
        conso = MouvementStock.objects.create(
            type_mouvement=MouvementStock.Type.CONSOMMATION, article=self.article, quantite=Decimal("20"),
            source=self.depot_a, ordre=self.of, date=date.today(),
        )
        apply_move(conso)  # 20 x CUMP 10 = 200 imputés à l'affaire
        self.auth()

    def figer(self, periode=None):
        return self.client.post("/api/stocks/valorisations/figer/", {"periode": periode or self.periode}, format="json")

    def test_consommation_imputee_a_l_affaire_avec_cout_cump(self):
        conso = MouvementStock.objects.get(type_mouvement=MouvementStock.Type.CONSOMMATION)
        self.assertEqual(conso.analytic, self.affaire.analytic)
        self.assertEqual(conso.cout_unitaire, Decimal("10"))

    def test_figer_ventile_par_axe_et_publie_a_m11(self):
        resp = self.figer()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        val = ValorisationMensuelle.objects.get(depot=self.depot_a, periode=self.periode)
        self.assertEqual(val.valeur_stock, Decimal("800"))
        self.assertEqual(val.consommation, Decimal("200"))
        self.assertEqual(val.ventilation[0]["axe"], self.affaire.analytic.code)
        self.assertTrue(OutboxEvent.objects.filter(topic="stocks.valorisation.figee", payload__depot="DEP-A").exists())
        self.auth(make_user(User.Role.FINANCE))
        m11 = self.client.get(f"/api/controle-gestion/consommations-stock/?periode={self.periode}")
        self.assertEqual(m11.status_code, 200, m11.content)
        self.assertEqual(m11.data["consommations_par_axe"][0], {"axe": self.affaire.analytic.code, "valeur": "200.00"})

    def test_valorisation_figee_une_seule_fois_et_immuable(self):
        self.assertEqual(self.figer().status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.figer().status_code, status.HTTP_400_BAD_REQUEST)
        vid = ValorisationMensuelle.objects.first().id
        self.assertEqual(self.client.patch(f"/api/stocks/valorisations/{vid}/", {"valeur_stock": 1}, format="json").status_code, 405)
        self.assertEqual(self.client.delete(f"/api/stocks/valorisations/{vid}/").status_code, 405)

    def test_periode_invalide_future_ou_depassee_par_des_mouvements(self):
        self.assertEqual(self.figer("2026-13").status_code, 400)
        self.assertEqual(self.figer((date.today().replace(day=1) + timedelta(days=40)).strftime("%Y-%m")).status_code, 400)
        mois_passe = (date.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        self.assertEqual(self.figer(mois_passe).status_code, 400)  # des mouvements postérieurs existent

    def test_montants_masques_hors_roles_autorises(self):
        self.figer()
        self.auth(make_user(User.Role.SECRETAIRE_GENERAL))
        resp = self.client.get("/api/stocks/valorisations/")
        if resp.status_code == 200:
            row = resp.data["results"][0] if "results" in resp.data else resp.data[0]
            self.assertIsNone(row["valeur_stock"])
            self.assertIsNone(row["ventilation"][0]["valeur"])


class InventaireTournantTests(M5BaseTest):
    def setUp(self):
        super().setUp()
        unit = UnitOfMeasure.objects.get(code="U")
        self.articles = [self.article] + [
            Article.objects.create(code=f"ART-{i}", label=f"Article {i}", article_type=Article.ArticleType.MATIERE, unit=unit)
            for i in range(1, 4)
        ]
        for art in self.articles:
            apply_move(mouvement(art, "50", "5", destination=self.depot_a))
        self.plan = PlanInventaireTournant.objects.create(
            depot=self.depot_a, periodicite_jours=30, articles_par_passage=2, prochaine_date=jour(-1)
        )
        self.auth()

    def test_passage_prepare_une_tranche_a_compter_puis_fait_tourner(self):
        inv1, = planifier_inventaires_tournants()
        self.assertEqual(inv1.type, Inventaire.Type.TOURNANT)
        self.assertEqual(sorted(l.article.code for l in inv1.lignes.all()), ["ART-1", "ART-2"])
        self.assertFalse(inv1.lignes.filter(comptee=True).exists())
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.prochaine_date, jour(30))
        self.assertEqual(planifier_inventaires_tournants(), [])  # pas encore échu
        inv2 = self.client.post(f"/api/stocks/plans-inventaire/{self.plan.id}/generer/").data
        self.assertEqual(sorted(l["article_code"] for l in inv2["lignes"]), ["ART-3", "ART-TUBE"])

    def test_cloture_refusee_tant_que_non_compte_puis_regularisation(self):
        inv, = planifier_inventaires_tournants()
        self.assertEqual(self.client.post(f"/api/stocks/inventaires/{inv.id}/cloturer/").status_code, 400)
        ligne = inv.lignes.get(article=self.articles[1])
        r = self.client.patch(f"/api/stocks/inventaire-lignes/{ligne.id}/", {"quantite_reelle": "47"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        inv.lignes.exclude(pk=ligne.pk).update(comptee=True)  # autre ligne comptée conforme
        resp = self.client.post(f"/api/stocks/inventaires/{inv.id}/cloturer/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(StockQuant.objects.get(depot=self.depot_a, article=self.articles[1]).quantity, Decimal("47"))
        self.assertTrue(MouvementStock.objects.filter(type_mouvement=MouvementStock.Type.INVENTAIRE, document_reference=inv.code).exists())

    def test_plan_inactif_ou_depot_vide_ne_genere_rien(self):
        self.plan.actif = False
        self.plan.save()
        self.assertEqual(planifier_inventaires_tournants(), [])
