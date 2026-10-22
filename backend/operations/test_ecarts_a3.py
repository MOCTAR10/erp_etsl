"""Lot a3 : saisie terrain hors ligne (horodatage, conflits de synchronisation) et consommation OF → stock (M3 → M5)."""

from datetime import date, timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from referentiels.models import Article, UnitOfMeasure
from stocks.models import Depot, LotMatiere, MouvementStock
from stocks.services import apply_move
from users.models import User

from .models import OrdreFabrication, ParametreOperations, PointageChantier


def _user(email, role):
    return User.objects.create_user(email=email, password="x-Terrain-2026", role=role)


class TerrainHorsLigneTests(APITestCase):
    def setUp(self):
        self.admin = _user("admin-a3@etls.ga", User.Role.ADMIN)
        self.client.force_authenticate(self.admin)
        self.of = OrdreFabrication.objects.create(label="Spool A3", scope="atelier", status="lance")

    def pointer(self, cle=None, **kw):
        corps = {"ordre": str(self.of.pk), "worker_name": "Moussa", "date": timezone.localdate().isoformat(),
                 "hours": "4", **kw}
        entetes = {"HTTP_IDEMPOTENCY_KEY": cle} if cle else {}
        return self.client.post("/api/operations/pointages/", corps, format="json", **entetes)

    def test_horodatage_de_saisie_conserve(self):
        saisi = timezone.now() - timedelta(hours=3)
        r = self.pointer(saisi_le=saisi.isoformat())
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(PointageChantier.objects.get(pk=r.data["id"]).saisi_le, saisi)

    def test_horodatage_dans_le_futur_refuse(self):
        r = self.pointer(saisi_le=(timezone.now() + timedelta(days=1)).isoformat())
        self.assertEqual(r.status_code, 400)
        self.assertIn("saisi_le", r.data)

    def test_doublon_hors_ligne_en_conflit_puis_force(self):
        saisi = (timezone.now() - timedelta(hours=1)).isoformat()
        self.assertEqual(self.pointer(saisi_le=saisi).status_code, 201)
        r = self.pointer(saisi_le=saisi)
        self.assertEqual(r.status_code, 409, r.content)
        self.assertIn("doublon", str(r.data["detail"]))
        self.assertEqual(self.pointer(saisi_le=saisi, forcer=True).status_code, 201)
        self.assertEqual(PointageChantier.objects.filter(ordre=self.of).count(), 2)

    def test_saisie_au_bureau_sans_conflit(self):
        self.assertEqual(self.pointer().status_code, 201)
        self.assertEqual(self.pointer().status_code, 201)

    def test_saisie_trop_ancienne_en_conflit_selon_le_parametre(self):
        vieux = (timezone.now() - timedelta(days=10)).isoformat()
        r = self.pointer(saisi_le=vieux, date=(timezone.localdate() - timedelta(days=10)).isoformat())
        self.assertEqual(r.status_code, 409)
        ParametreOperations.objects.filter(code="TERRAIN_DELAI_SYNCHRO_JOURS").update(valeur=0)
        r = self.pointer(saisi_le=vieux, date=(timezone.localdate() - timedelta(days=10)).isoformat())
        self.assertEqual(r.status_code, 201, r.content)

    def test_rejeu_de_la_meme_saisie_sans_doublon_ni_conflit(self):
        saisi = timezone.now().isoformat()
        self.assertEqual(self.pointer("cle-a3-1", saisi_le=saisi).status_code, 201)
        r = self.pointer("cle-a3-1", saisi_le=saisi)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r["Idempotent-Replay"], "true")
        self.assertEqual(PointageChantier.objects.filter(ordre=self.of).count(), 1)


class ConsommationOfTests(APITestCase):
    def setUp(self):
        unit, _ = UnitOfMeasure.objects.get_or_create(code="U", defaults={"label": "Unité"})
        self.article = Article.objects.create(code="ART-A3", label="Tube API 5L X52", article_type=Article.ArticleType.MATIERE,
                                              unit=unit)
        self.mag = _user("mag-a3@etls.ga", User.Role.LOGISTIQUE)
        self.depot = Depot.objects.create(code="DEP-A3", label="Magasin")
        self.lot = LotMatiere.objects.create(article=self.article, numero_lot="L-1", numero_coulee="HEAT-77",
                                             date_reception=date.today(), quantite_initiale=100, quantite_restante=0)
        apply_move(MouvementStock.objects.create(
            type_mouvement=MouvementStock.Type.RECEPTION, article=self.article, quantite=100, prix_unitaire=1500,
            destination=self.depot, lot=self.lot, date=date.today(), created_by=self.mag,
        ))
        self.of = OrdreFabrication.objects.create(label="Spool B", scope="atelier", status="lance")
        self.url = f"/api/operations/ordres/{self.of.pk}/consommations/"
        self.client.force_authenticate(self.mag)

    def consommer(self, quantite="10", **kw):
        return self.client.post(self.url, {"article": str(self.article.pk), "depot": str(self.depot.pk),
                                           "lot": str(self.lot.pk), "quantite": quantite, **kw}, format="json")

    def test_consommation_depuis_l_of_sort_le_lot_du_stock(self):
        r = self.consommer()
        self.assertEqual(r.status_code, 201, r.content)
        ligne = r.data["lignes"][0]
        self.assertEqual((ligne["quantite"], ligne["numero_coulee"], ligne["lot_code"]), ("10.00", "HEAT-77", self.lot.code))
        self.lot.refresh_from_db()
        self.assertEqual(self.lot.quantite_restante, 90)
        mvts = self.client.get(f"/api/stocks/mouvements/?ordre={self.of.pk}").data["results"]
        self.assertEqual([m["type_mouvement"] for m in mvts], ["consommation"])
        self.client.force_authenticate(_user("admin-a3c@etls.ga", User.Role.ADMIN))
        self.assertEqual(len(self.client.get(self.url).data["lignes"]), 1)

    def test_of_non_lance_refuse(self):
        OrdreFabrication.objects.filter(pk=self.of.pk).update(status="prevu")
        self.assertEqual(self.consommer().status_code, 400)

    def test_stock_insuffisant_sans_mouvement_residuel(self):
        r = self.consommer("1000")
        self.assertEqual(r.status_code, 400)
        self.assertIn("insuffisant", str(r.data["detail"]))
        self.assertFalse(MouvementStock.objects.filter(ordre=self.of).exists())

    def test_quantite_nulle_refusee(self):
        self.assertEqual(self.consommer("0").status_code, 400)

    def test_consommation_reservee_au_magasin(self):
        self.client.force_authenticate(_user("rh-a3@etls.ga", User.Role.RH))
        self.assertEqual(self.consommer().status_code, 403)
