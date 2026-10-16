"""Audit métier M5 (2026-10-16) — régressions des écarts trouvés.

S2 : un transfert conserve la valeur du stock (le dépôt de destination reçoit au coût de la source).
S8 : un mouvement exécuté est immuable (ni PATCH ni DELETE) : on corrige par mouvement inverse.
"""

from decimal import Decimal

from rest_framework import status

from stocks.models import MouvementStock, StockQuant
from stocks.services import apply_move

from .tests import M5BaseTest


def mouvement(article, quantite, prix=0, source=None, destination=None, type_=None):
    return MouvementStock.objects.create(
        type_mouvement=type_ or (
            MouvementStock.Type.TRANSFERT if source and destination
            else MouvementStock.Type.RECEPTION if destination else MouvementStock.Type.CONSOMMATION
        ),
        article=article, quantite=Decimal(quantite), prix_unitaire=Decimal(prix),
        source=source, destination=destination, date="2026-01-10",
    )


class TransfertValeurTests(M5BaseTest):
    def valeur_totale(self):
        return sum((q.stock_value for q in StockQuant.objects.all()), Decimal("0"))

    def test_transfert_conserve_la_valeur_du_stock(self):
        apply_move(mouvement(self.article, "100", "10", destination=self.depot_a))  # 1000
        self.assertEqual(self.valeur_totale(), Decimal("1000"))
        apply_move(mouvement(self.article, "30", source=self.depot_a, destination=self.depot_b))
        self.assertEqual(self.valeur_totale(), Decimal("1000"))
        b = StockQuant.objects.get(depot=self.depot_b, article=self.article)
        self.assertEqual(b.stock_value, Decimal("300"))  # 30 x CUMP 10

    def test_transfert_apres_plusieurs_receptions_au_cump(self):
        apply_move(mouvement(self.article, "100", "10", destination=self.depot_a))
        apply_move(mouvement(self.article, "100", "20", destination=self.depot_a))  # CUMP 15
        apply_move(mouvement(self.article, "40", source=self.depot_a, destination=self.depot_b))
        b = StockQuant.objects.get(depot=self.depot_b, article=self.article)
        self.assertEqual(b.stock_value, Decimal("600"))  # 40 x 15
        self.assertEqual(self.valeur_totale(), Decimal("3000"))


class MouvementImmuableTests(M5BaseTest):
    def setUp(self):
        super().setUp()
        self.mvt = mouvement(self.article, "50", "10", destination=self.depot_a)
        apply_move(self.mvt)
        self.auth()

    def test_mouvement_execute_non_modifiable(self):
        r = self.client.patch(f"/api/stocks/mouvements/{self.mvt.pk}/", {"quantite": "500"}, format="json")
        self.assertGreaterEqual(r.status_code, 400, r.content)
        self.mvt.refresh_from_db()
        self.assertEqual(self.mvt.quantite, Decimal("50.00"))

    def test_mouvement_execute_non_supprimable(self):
        r = self.client.delete(f"/api/stocks/mouvements/{self.mvt.pk}/")
        self.assertGreaterEqual(r.status_code, 400, r.content)
        self.assertTrue(MouvementStock.objects.filter(pk=self.mvt.pk).exists())
