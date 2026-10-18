"""Lot B M2 (2026-10-18) — la validation d'une réception met la marchandise en stock (CDC §5.10 aval M5).

Avant : aucune référence à `GoodsReceipt` dans `stocks/` ; les entrées de stock se créaient à la main. Après : à la
validation (contrôle qualité M6 validé), chaque ligne d'article géré en stock crée une entrée au dépôt de réception,
au prix du BC (CUMP), une seule fois, et la réception validée est scellée.
"""

from decimal import Decimal

from rest_framework.test import APITestCase

from qualite.models import ControleQualite
from referentiels.models import Article, Partner, UnitOfMeasure
from stocks.models import Depot, MouvementStock, StockQuant
from users.models import User

from .models import GoodsReceipt, GoodsReceiptLine, PurchaseOrder, PurchaseOrderLine


class ReceptionStockTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="fin@etls.ga", password="x-Audit-2026", role=User.Role.FINANCE)
        self.client.force_authenticate(self.user)
        unite, _ = UnitOfMeasure.objects.get_or_create(code="U", defaults={"label": "Unité"})
        self.tube = Article.objects.create(code="TUBE", label="Tube", unit=unite, is_stockable=True)
        self.service = Article.objects.create(code="SRV", label="Prestation", unit=unite, is_stockable=False)
        self.depot = Depot.objects.create(label="Magasin central")
        self.bc = PurchaseOrder.objects.create(
            supplier=Partner.objects.create(code="F1", name="F", kind=Partner.Kind.FOURNISSEUR),
            status=PurchaseOrder.Status.CONFIRMEE,
        )
        self.l_tube = PurchaseOrderLine.objects.create(
            purchase_order=self.bc, article=self.tube, label="Tube", quantity=10, unit_price=Decimal("100")
        )
        self.l_srv = PurchaseOrderLine.objects.create(
            purchase_order=self.bc, article=self.service, label="Presta", quantity=1, unit_price=Decimal("500")
        )
        self.l_libre = PurchaseOrderLine.objects.create(
            purchase_order=self.bc, article=None, label="Divers", quantity=1, unit_price=Decimal("50")
        )

    def _reception(self, qty_tube=4, prix=None):
        br = GoodsReceipt.objects.create(purchase_order=self.bc)
        GoodsReceiptLine.objects.create(receipt=br, purchase_order_line=self.l_tube, quantity=qty_tube)
        GoodsReceiptLine.objects.create(receipt=br, purchase_order_line=self.l_srv, quantity=1)
        GoodsReceiptLine.objects.create(receipt=br, purchase_order_line=self.l_libre, quantity=1)
        ctrl = ControleQualite.objects.get(reception=br)
        ControleQualite.objects.filter(pk=ctrl.pk).update(statut="valide", resultat="conforme")
        return br

    def _valider(self, br, **data):
        return self.client.post(f"/api/achats/receipts/{br.pk}/valider/", data, format="json")

    def test_validation_cree_l_entree_de_stock_des_seuls_articles_stockables(self):
        br = self._reception(4)
        r = self._valider(br)
        self.assertEqual(r.status_code, 200, r.content)
        mvts = MouvementStock.objects.filter(document_reference=br.code)
        self.assertEqual(mvts.count(), 1)
        mvt = mvts.get()
        self.assertEqual((mvt.type_mouvement, mvt.article_id, mvt.destination_id), ("reception", self.tube.id, self.depot.id))
        self.assertEqual((mvt.quantite, mvt.prix_unitaire, mvt.executed), (Decimal("4.00"), Decimal("100.00"), True))
        quant = StockQuant.objects.get(depot=self.depot, article=self.tube)
        self.assertEqual((quant.quantity, quant.stock_value), (Decimal("4.00"), Decimal("400.00")))

    def test_receptions_partielles_cumulent_au_cump(self):
        self._valider(self._reception(4))
        PurchaseOrderLine.objects.filter(pk=self.l_tube.pk).update(unit_price=Decimal("130"))
        self._valider(self._reception(6))
        quant = StockQuant.objects.get(depot=self.depot, article=self.tube)
        self.assertEqual(quant.quantity, Decimal("10.00"))
        self.assertEqual(quant.stock_value, Decimal("1180.00"))

    def test_une_seule_entree_par_reception(self):
        br = self._reception(4)
        self.assertEqual(self._valider(br).status_code, 200)
        self.assertEqual(self._valider(br).status_code, 400)
        self.assertEqual(MouvementStock.objects.filter(document_reference=br.code).count(), 1)

    def test_plusieurs_depots_exigent_un_choix(self):
        autre = Depot.objects.create(label="Chantier Port-Gentil")
        br = self._reception(4)
        r = self._valider(br)
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("dépôt", str(r.data).lower())
        br.refresh_from_db()
        self.assertEqual(br.status, GoodsReceipt.Status.EN_ATTENTE)
        self.assertFalse(MouvementStock.objects.exists())
        self.assertEqual(self._valider(br, depot=str(autre.pk)).status_code, 200)
        self.assertTrue(StockQuant.objects.filter(depot=autre, article=self.tube).exists())

    def test_sans_depot_et_avec_article_stockable_refuse(self):
        Depot.objects.all().delete()
        r = self._valider(self._reception(4))
        self.assertEqual(r.status_code, 400, r.content)

    def test_sans_article_stockable_aucun_depot_requis(self):
        Article.objects.filter(pk=self.tube.pk).update(is_stockable=False)
        Depot.objects.all().delete()
        self.assertEqual(self._valider(self._reception(4)).status_code, 200)
        self.assertFalse(MouvementStock.objects.exists())

    def test_reception_validee_scellee(self):
        br = self._reception(4)
        self._valider(br)
        ligne = br.lines.first()
        r = self.client.patch(f"/api/achats/receipt-lines/{ligne.pk}/", {"quantity": "9"}, format="json")
        self.assertEqual(r.status_code, 400, r.content)
        self.assertEqual(self.client.delete(f"/api/achats/receipt-lines/{ligne.pk}/").status_code, 400)
        self.assertEqual(self.client.delete(f"/api/achats/receipts/{br.pk}/").status_code, 400)
