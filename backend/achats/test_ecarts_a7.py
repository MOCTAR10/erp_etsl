"""Recette du lot a7 (achats) : réception saisie hors ligne — horodatage `saisi_le` conservé, conflits 409 cohérents
avec /terrain (saisie trop ancienne, doublon, sur-réception survenue entre-temps), levés par `forcer`."""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APITestCase

from referentiels.models import Partner
from users.models import User

from .models import GoodsReceipt, GoodsReceiptLine, PurchaseOrder, PurchaseOrderLine

URL = "/api/achats/receipt-lines/"


class ReceptionHorsLigneTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="adm@etls.ga", password="x-Audit-2026", role=User.Role.ADMIN, is_staff=True)
        self.client.force_authenticate(self.user)
        self.bc = PurchaseOrder.objects.create(
            supplier=Partner.objects.create(code="F1", name="F", kind=Partner.Kind.FOURNISSEUR),
            status=PurchaseOrder.Status.CONFIRMEE,
        )
        self.ligne = PurchaseOrderLine.objects.create(purchase_order=self.bc, label="Tube", quantity=10, unit_price=Decimal("100"))
        self.bl = GoodsReceipt.objects.create(purchase_order=self.bc)

    def poster(self, quantite, saisi_le=None, forcer=False, **headers):
        corps = {"receipt": str(self.bl.pk), "purchase_order_line": str(self.ligne.pk), "quantity": str(quantite)}
        if saisi_le is not None:
            corps["saisi_le"] = saisi_le if isinstance(saisi_le, str) else saisi_le.isoformat()
        if forcer:
            corps["forcer"] = True
        return self.client.post(URL, corps, format="json", **headers)

    def test_horodatage_de_saisie_conserve(self):
        saisi = timezone.now().replace(microsecond=0) - timedelta(hours=3)
        r = self.poster(4, saisi)
        self.assertEqual(r.status_code, 201, r.content)
        ligne = GoodsReceiptLine.objects.get(pk=r.data["id"])
        self.assertEqual(ligne.saisi_le, saisi)
        self.assertIsNotNone(self.client.get(URL, {"receipt": str(self.bl.pk)}).data["results"][0]["saisi_le"])
        self.assertEqual(self.poster(1, timezone.now() + timedelta(days=1)).status_code, 400)  # horloge déréglée
        self.assertEqual(self.poster(1, "hier").status_code, 400)

    def test_saisie_trop_ancienne_conflit_puis_forcer(self):
        ancien = timezone.now() - timedelta(days=10)
        r = self.poster(4, ancien)
        self.assertEqual(r.status_code, 409)
        self.assertIn("Forcer", str(r.data))
        self.assertFalse(GoodsReceiptLine.objects.exists())
        self.assertEqual(self.poster(4, ancien, forcer=True).status_code, 201)

    def test_doublon_conflit_et_rejeu_idempotent_apres_forcer(self):
        self.assertEqual(self.poster(4).status_code, 201)  # saisie en ligne : aucun contrôle de synchronisation
        recent = timezone.now() - timedelta(hours=1)
        cle = {"HTTP_IDEMPOTENCY_KEY": "a7-reception-doublon"}
        self.assertEqual(self.poster(4, recent, **cle).status_code, 409)
        r = self.poster(4, recent, forcer=True, **cle)  # le 409 n'est pas mémorisé : « Forcer » passe
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(self.poster(4, recent, forcer=True, **cle).data["id"], r.data["id"])  # rejeu sans doublon
        self.assertEqual(GoodsReceiptLine.objects.count(), 2)

    def test_sur_reception_survenue_entre_temps(self):
        self.assertEqual(self.poster(8).status_code, 201)
        r = self.poster(4, timezone.now() - timedelta(minutes=30))
        self.assertEqual(r.status_code, 409)
        self.assertIn("déjà reçu", str(r.data))
        self.assertEqual(self.poster(4, timezone.now() - timedelta(minutes=30), forcer=True).status_code, 201)
        self.ligne.refresh_from_db()
        self.assertEqual(self.ligne.received_qty, Decimal("12"))


class FiltresMulticriteresA7Tests(APITestCase):
    """EX-G-09 branché sur les listes principales d achats et de comptabilité (lot a7)."""

    def setUp(self):
        self.client.force_authenticate(User.objects.create_user(
            email="adm2@etls.ga", password="x-Audit-2026", role=User.Role.ADMIN, is_staff=True))
        frs = Partner.objects.create(code="F2", name="F2", kind=Partner.Kind.FOURNISSEUR)
        PurchaseOrder.objects.create(supplier=frs, status=PurchaseOrder.Status.CONFIRMEE)
        PurchaseOrder.objects.create(supplier=frs, status=PurchaseOrder.Status.PARTIELLE, is_global_rental=False)

    def test_criteres_decrits_et_combines(self):
        for url in ("/api/achats/orders/", "/api/achats/invoices/", "/api/comptabilite/paiements/",
                    "/api/comptabilite/factures-clients/"):
            r = self.client.get(f"{url}filtres/")
            self.assertEqual(r.status_code, 200, url)
            self.assertTrue(r.data["results"], url)
        champs = {d["champ"] for d in self.client.get("/api/achats/orders/filtres/").data["results"]}
        self.assertIn("status", champs)
        r = self.client.get("/api/achats/orders/", {"status": "partielle"})
        self.assertEqual(r.data["count"], 1)
        self.assertEqual(self.client.get("/api/achats/orders/", {"status": "inconnu"}).status_code, 400)
