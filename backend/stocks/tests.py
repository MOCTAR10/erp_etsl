"""Tests M5 — Stocks & Traçabilité matière (RF-ERP-40…43)."""

from datetime import date

from rest_framework import status
from rest_framework.test import APITestCase

from referentiels.models import Article, Currency, Partner, UnitOfMeasure
from stocks.models import (
    ArticleStock,
    CertificatMatiere,
    Depot,
    Inventaire,
    InventaireLigne,
    LotMatiere,
    MouvementStock,
    StockQuant,
)
from stocks.services import apply_move, cloturer_inventaire
from users.models import User


def make_references():
    unit, _ = UnitOfMeasure.objects.get_or_create(code="U", defaults={"label": "Unité"})
    article = Article.objects.create(
        code="ART-TUBE",
        label="Tube acier",
        article_type=Article.ArticleType.MATIERE,
        unit=unit,
    )
    currency = Currency.objects.create(code="XAF", label="Franc CFA", symbol="XAF")
    return article, currency, unit


def make_user(role=User.Role.LOGISTIQUE):
    return User.objects.create_user(
        email=f"{role.lower()}@etls.ga",
        password="test1234",
        first_name=role,
        last_name="Test",
        role=role,
    )


class M5BaseTest(APITestCase):
    def setUp(self):
        self.article, self.currency, self.unit = make_references()
        self.user = make_user()
        self.admin = make_user(User.Role.ADMIN)
        self.depot_a = Depot.objects.create(code="DEP-A", label="Dépôt A")
        self.depot_b = Depot.objects.create(code="DEP-B", label="Dépôt B")

    def auth(self, user=None):
        self.client.force_authenticate(user or self.user)


class DepotAndLotTests(M5BaseTest):
    def test_depot_creation_with_sequence(self):
        auth = self.auth()
        resp = self.client.post(
            "/api/stocks/depots/",
            {"label": "Magasin Port-Gentil", "site": "Port-Gentil", "is_active": True},
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.assertTrue(resp.data["code"].startswith("DEP"))
        self.assertEqual(Depot.objects.count(), 3)

    def test_lot_created_with_mtc_certificate(self):
        lot = LotMatiere.objects.create(
            article=self.article,
            numero_lot="MTC-1",
            date_reception=date.today(),
            quantite_initiale=100,
            quantite_restante=100,
        )
        cert = CertificatMatiere.objects.create(
            lot=lot,
            type=CertificatMatiere.Type.MTC,
            numero_certificat="MTC-2026-001",
            conforme=True,
        )
        self.assertTrue(lot.code.startswith("LOT"))
        self.assertTrue(cert.code.startswith("CERT"))
        self.assertEqual(cert.get_type_display(), "MTC (Mill Test Certificate)")

    def test_invalid_certificate_rejected(self):
        self.auth()
        lot = LotMatiere.objects.create(
            article=self.article,
            numero_lot="MTC-2",
            date_reception=date.today(),
            quantite_initiale=10,
            quantite_restante=10,
        )
        resp = self.client.post(
            "/api/stocks/certificats/",
            {"lot": str(lot.pk), "type": "coc", "numero_certificat": ""},
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class MoveDoubleEntryTests(M5BaseTest):
    def test_reception_and_consumption_update_quants(self):
        move = MouvementStock.objects.create(
            type_mouvement=MouvementStock.Type.RECEPTION,
            article=self.article,
            quantite=100,
            prix_unitaire=500,
            devise=self.currency,
            destination=self.depot_a,
            document_reference="BL-001",
            date=date.today(),
            created_by=self.user,
        )
        apply_move(move)
        quant = StockQuant.objects.get(depot=self.depot_a, article=self.article)
        self.assertEqual(float(quant.quantity), 100)
        self.assertEqual(float(quant.stock_value), 50_000)

        out = MouvementStock.objects.create(
            type_mouvement=MouvementStock.Type.CONSOMMATION,
            article=self.article,
            quantite=40,
            prix_unitaire=0,
            source=self.depot_a,
            document_reference="OF-0001",
            date=date.today(),
            created_by=self.user,
        )
        apply_move(out)
        quant.refresh_from_db()
        self.assertEqual(float(quant.quantity), 60)
        self.assertEqual(float(quant.stock_value), 30_000)

    def test_transfer_debits_source_credits_destination(self):
        move = MouvementStock.objects.create(
            type_mouvement=MouvementStock.Type.RECEPTION,
            article=self.article,
            quantite=80,
            prix_unitaire=1000,
            devise=self.currency,
            destination=self.depot_a,
            document_reference="BL-002",
            date=date.today(),
        )
        apply_move(move)
        transfer = MouvementStock.objects.create(
            type_mouvement=MouvementStock.Type.TRANSFERT,
            article=self.article,
            quantite=30,
            prix_unitaire=1000,
            devise=self.currency,
            source=self.depot_a,
            destination=self.depot_b,
            document_reference="TRF-1",
            date=date.today(),
        )
        apply_move(transfer)
        self.assertEqual(
            float(StockQuant.objects.get(depot=self.depot_a, article=self.article).quantity), 50
        )
        self.assertEqual(
            float(StockQuant.objects.get(depot=self.depot_b, article=self.article).quantity), 30
        )

    def test_insufficient_stock_raises(self):
        out = MouvementStock.objects.create(
            type_mouvement=MouvementStock.Type.RETOUR,
            article=self.article,
            quantite=10,
            source=self.depot_a,
            date=date.today(),
        )
        with self.assertRaises(ValueError):
            apply_move(out)

    def test_move_requires_source_or_destination(self):
        self.auth()
        resp = self.client.post(
            "/api/stocks/mouvements/",
            {
                "type_mouvement": "reception",
                "article": str(self.article.pk),
                "quantite": "5",
                "prix_unitaire": "10",
                "date": str(date.today()),
            },
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("source ou destination", str(resp.data))


class ValorisationTests(M5BaseTest):
    def test_cump_valuation(self):
        mv1 = MouvementStock.objects.create(
            type_mouvement=MouvementStock.Type.RECEPTION,
            article=self.article,
            quantite=100,
            prix_unitaire=500,
            devise=self.currency,
            destination=self.depot_a,
            date=date.today(),
        )
        apply_move(mv1)
        mv2 = MouvementStock.objects.create(
            type_mouvement=MouvementStock.Type.RECEPTION,
            article=self.article,
            quantite=50,
            prix_unitaire=600,
            devise=self.currency,
            destination=self.depot_a,
            date=date.today(),
        )
        apply_move(mv2)
        quant = StockQuant.objects.get(depot=self.depot_a, article=self.article)
        # (100*500 + 50*600) / 150 = 80000 / 150 ≈ 533.33
        self.assertEqual(float(quant.quantity), 150)
        self.assertEqual(float(quant.stock_value), 80_000)
        self.assertAlmostEqual(float(quant.stock_value) / float(quant.quantity), 533.33, places=2)

    def test_valuation_endpoint(self):
        mv = MouvementStock.objects.create(
            type_mouvement=MouvementStock.Type.RECEPTION,
            article=self.article,
            quantite=10,
            prix_unitaire=100,
            devise=self.currency,
            destination=self.depot_a,
            date=date.today(),
        )
        apply_move(mv)
        self.auth(self.admin)
        resp = self.client.get("/api/stocks/quants/valorisation/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(len(resp.data) >= 1)
        row = next(r for r in resp.data if r["article"] == "ART-TUBE")
        self.assertEqual(row["method"], "cump")
        self.assertEqual(row["quantity"], 10.0)
        self.assertEqual(row["value"], 1000.0)

    def test_pypp_standard_method(self):
        ArticleStock.objects.create(
            article=self.article,
            methode=ArticleStock.Methode.PP,
            prix_standard=900,
        )
        mv = MouvementStock.objects.create(
            type_mouvement=MouvementStock.Type.RECEPTION,
            article=self.article,
            quantite=10,
            prix_unitaire=100,
            devise=self.currency,
            destination=self.depot_a,
            date=date.today(),
        )
        apply_move(mv)
        self.auth(self.admin)
        resp = self.client.get("/api/stocks/quants/valorisation/")
        rows = [r for r in resp.data if r["article"] == "ART-TUBE"]
        self.assertEqual(rows[0]["method"], "pp")
        self.assertEqual(rows[0]["value"], 9000.0)


class InventaireTests(M5BaseTest):
    def test_inventaire_cloture_creates_adjustment_move(self):
        mv = MouvementStock.objects.create(
            type_mouvement=MouvementStock.Type.RECEPTION,
            article=self.article,
            quantite=50,
            prix_unitaire=100,
            devise=self.currency,
            destination=self.depot_a,
            date=date.today(),
        )
        apply_move(mv)
        inv = Inventaire.objects.create(
            depot=self.depot_a,
            date=date.today(),
            statut=Inventaire.Statut.BROUILLON,
            created_by=self.user,
        )
        InventaireLigne.objects.create(
            inventaire=inv,
            article=self.article,
            quantite_systeme=50,
            quantite_reelle=48,
        )
        cloturer_inventaire(inv, self.user)
        inv.refresh_from_db()
        self.assertEqual(inv.statut, Inventaire.Statut.CLOTURE)
        adj = MouvementStock.objects.filter(
            type_mouvement=MouvementStock.Type.INVENTAIRE
        ).first()
        self.assertTrue(adj.code.startswith("MVT"))
        self.assertEqual(adj.document_reference, inv.code)
        quant = StockQuant.objects.get(depot=self.depot_a, article=self.article)
        self.assertEqual(float(quant.quantity), 48)
        self.assertEqual(float(quant.stock_value), 4800)

    def test_inventaire_api_cloture(self):
        mv = MouvementStock.objects.create(
            type_mouvement=MouvementStock.Type.RECEPTION,
            article=self.article,
            quantite=20,
            prix_unitaire=100,
            devise=self.currency,
            destination=self.depot_b,
            document_reference="BL-003",
            date=date.today(),
        )
        apply_move(mv)
        self.auth()
        resp = self.client.post(
            "/api/stocks/inventaires/",
            {"depot": str(self.depot_b.pk), "date": str(date.today())},
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        inv_id = resp.data["id"]
        resp = self.client.post(
            f"/api/stocks/inventaire-lignes/",
            {
                "inventaire": inv_id,
                "article": str(self.article.pk),
                "quantite_systeme": "20",
                "quantite_reelle": "19",
            },
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        resp = self.client.post(f"/api/stocks/inventaires/{inv_id}/cloturer/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        self.assertEqual(resp.data["statut"], "cloture")
        resp = self.client.get(f"/api/stocks/inventaires/{inv_id}/")
        self.assertEqual(float(resp.data["lignes"][0]["ecart"]), -1.0)


class PermissionsTests(M5BaseTest):
    def test_write_denied_for_human_resources(self):
        user = make_user(User.Role.RH)
        self.auth(user)
        resp = self.client.post(
            "/api/stocks/depots/", {"label": "Dépôt interdit"}
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_amount_masked_for_logistique(self):
        mv = MouvementStock.objects.create(
            type_mouvement=MouvementStock.Type.RECEPTION,
            article=self.article,
            quantite=100,
            prix_unitaire=500,
            devise=self.currency,
            destination=self.depot_a,
            date=date.today(),
        )
        apply_move(mv)
        self.auth()  # logistique
        resp = self.client.get("/api/stocks/mouvements/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        row = next(r for r in resp.data["results"] if r["code"] == mv.code)
        self.assertIsNone(row["prix_unitaire"])
        self.assertIsNone(row["montant_total"])
        self.auth(self.admin)
        resp = self.client.get("/api/stocks/mouvements/")
        row = next(r for r in resp.data["results"] if r["code"] == mv.code)
        self.assertEqual(float(row["prix_unitaire"]), 500.0)

    def test_quants_value_masked_for_logistique(self):
        mv = MouvementStock.objects.create(
            type_mouvement=MouvementStock.Type.RECEPTION,
            article=self.article,
            quantite=100,
            prix_unitaire=500,
            devise=self.currency,
            destination=self.depot_a,
            date=date.today(),
        )
        apply_move(mv)
        self.auth()
        resp = self.client.get("/api/stocks/quants/")
        row = next(r for r in resp.data["results"] if r["article_code"] == "ART-TUBE")
        self.assertIsNone(row["stock_value"])

    def test_traceability_endpoint(self):
        lot = LotMatiere.objects.create(
            article=self.article,
            numero_lot="MTC-TRACE",
            date_reception=date.today(),
            quantite_initiale=50,
            quantite_restante=50,
        )
        mv = MouvementStock.objects.create(
            type_mouvement=MouvementStock.Type.RECEPTION,
            article=self.article,
            quantite=50,
            prix_unitaire=100,
            devise=self.currency,
            destination=self.depot_a,
            lot=lot,
            document_reference="BL-TRACE",
            date=date.today(),
        )
        apply_move(mv)
        self.auth()
        resp = self.client.get(f"/api/stocks/mouvements/tracabilite/?lot={lot.pk}")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["reference"], "BL-TRACE")
        resp = self.client.get(f"/api/stocks/mouvements/tracabilite/?article={self.article.pk}")
        self.assertEqual(len(resp.data), 1)