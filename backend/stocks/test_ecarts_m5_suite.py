"""Écarts M5, suite (2026-10-19) — tests de recette (§7.3, §7.5, §7.8, §7.10 M10).

- Valorisation FIFO / PEPS et prix standard réellement appliqués, méthode par dépôt prioritaire sur l'article ;
  audit rétrospectif (rejeu des sorties, écarts de coût).
- Sites GLOBAL RENTAL consultables en lecture seule ; fonctions autorisées par dépôt.
- Variation de stock passée en écriture (journal STK, classes 3 / 603) au figé mensuel ; non bloquante si le
  noyau comptable n'est pas paramétré.
"""

from datetime import date
from decimal import Decimal

from django.core.management import call_command
from rest_framework.test import APITestCase

from referentiels.models import Article, UnitOfMeasure
from users.models import User

from .cloture import figer_valorisation_mensuelle
from .models import ArticleStock, Depot, MouvementStock, StockQuant
from .services import apply_move


class _Base(APITestCase):
    def setUp(self):
        unit, _ = UnitOfMeasure.objects.get_or_create(code="U", defaults={"label": "Unité"})
        self.article = Article.objects.create(code="ART-BRIDE", label="Bride DN100", article_type=Article.ArticleType.MATIERE, unit=unit)
        self.mag = User.objects.create_user(email="mag@etls.ga", password="x-Audit-2026", role=User.Role.LOGISTIQUE)
        self.fin = User.objects.create_user(email="fin@etls.ga", password="x-Audit-2026", role=User.Role.FINANCE)
        self.depot = Depot.objects.create(code="DEP-A", label="Magasin")
        self.client.force_authenticate(self.mag)

    def mouvement(self, type_mouvement, quantite, prix=0, source=None, destination=None, jour=None):
        return apply_move(MouvementStock.objects.create(
            type_mouvement=type_mouvement, article=self.article, quantite=Decimal(str(quantite)), prix_unitaire=Decimal(str(prix)),
            source=source, destination=destination, date=jour or date.today(), created_by=self.mag,
        ))

    def deux_receptions_puis_sortie(self):
        self.mouvement("reception", 10, 100, destination=self.depot)
        self.mouvement("reception", 10, 200, destination=self.depot)
        return self.mouvement("consommation", 15, source=self.depot)


class MethodesValorisationTests(_Base):
    def test_cump_par_defaut(self):
        self.assertEqual(self.deux_receptions_puis_sortie().cout_unitaire, Decimal("150"))

    def test_fifo_consomme_les_couches_les_plus_anciennes(self):
        ArticleStock.objects.create(article=self.article, methode="fifo")
        sortie = self.deux_receptions_puis_sortie()
        self.assertEqual(sortie.cout_unitaire.quantize(Decimal("0.01")), Decimal("133.33"))
        quant = StockQuant.objects.get(depot=self.depot, article=self.article)
        self.assertEqual(quant.stock_value.quantize(Decimal("1")), Decimal("1000"))  # 5 restants à 200

    def test_methode_du_depot_prioritaire_et_prix_standard(self):
        ArticleStock.objects.create(article=self.article, methode="cump", prix_standard=Decimal("120"))
        Depot.objects.filter(pk=self.depot.pk).update(methode_valorisation="peps")
        self.depot.refresh_from_db()
        self.assertEqual(self.deux_receptions_puis_sortie().cout_unitaire.quantize(Decimal("0.01")), Decimal("133.33"))
        autre = Depot.objects.create(code="DEP-PP", label="Standard", methode_valorisation="pp")
        self.mouvement("reception", 4, 300, destination=autre)
        sortie = self.mouvement("consommation", 2, source=autre)
        self.assertEqual(sortie.cout_unitaire, Decimal("120"))

    def test_audit_retrospectif_signale_les_ecarts_de_methode(self):
        self.deux_receptions_puis_sortie()  # valorisée au CUMP (150)
        ArticleStock.objects.create(article=self.article, methode="fifo")
        self.client.force_authenticate(self.fin)
        r = self.client.get(f"/api/stocks/quants/audit-valorisation/?depot={self.depot.pk}&article={self.article.pk}")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.data["methode"], r.data["ecarts"]), ("fifo", 1))
        self.assertEqual(Decimal(r.data["lignes"][0]["cout_recalcule"]).quantize(Decimal("0.01")), Decimal("133.33"))
        self.client.force_authenticate(self.mag)  # hors cercle des montants : coûts masqués
        r = self.client.get(f"/api/stocks/quants/audit-valorisation/?depot={self.depot.pk}&article={self.article.pk}")
        self.assertIsNone(r.data["lignes"][0]["cout_enregistre"])
        self.assertEqual(self.client.get("/api/stocks/quants/audit-valorisation/").status_code, 400)


class DepotsTests(_Base):
    def poster(self, destination):
        return self.client.post("/api/stocks/mouvements/", {
            "type_mouvement": "reception", "article": str(self.article.pk), "quantite": "1", "prix_unitaire": "10",
            "destination": str(destination.pk), "date": str(date.today()),
        }, format="json")

    def test_site_global_rental_en_lecture_seule(self):
        gr = Depot.objects.create(code="DEP-GR", label="Parc GR Owendo", is_global_rental=True)
        r = self.poster(gr)
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("lecture seule", str(r.data))
        self.assertEqual(self.client.get(f"/api/stocks/depots/{gr.pk}/").status_code, 200)

    def test_fonctions_autorisees_par_depot(self):
        Depot.objects.filter(pk=self.depot.pk).update(roles_autorises=["chef_atelier"])
        r = self.poster(self.depot)
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("pas autorisée", str(r.data))
        chef = User.objects.create_user(email="chef@etls.ga", password="x-Audit-2026", role=User.Role.CHEF_ATELIER)
        self.client.force_authenticate(chef)
        self.assertEqual(self.poster(self.depot).status_code, 201)


class VariationStockTests(_Base):
    def test_variation_passee_au_journal_stk(self):
        call_command("seed_referentiels", verbosity=0)
        call_command("seed_accounting", verbosity=0)
        self.mouvement("reception", 10, 100, destination=self.depot, jour=date.today().replace(day=1))
        periode = f"{date.today():%Y-%m}"
        val = next(v for v in figer_valorisation_mensuelle(periode, self.fin) if v.depot_id == self.depot.pk)
        self.assertEqual(val.motif_ecriture, "")
        lignes = {(l.account.code, l.debit, l.credit) for l in val.move.lines.select_related("account")}
        self.assertEqual(lignes, {("320000", Decimal("1000.00"), Decimal("0.00")), ("603200", Decimal("0.00"), Decimal("1000.00"))})
        self.assertEqual(val.move.journal.code, "STK")

    def test_sans_noyau_comptable_le_fige_reste_valable(self):
        self.mouvement("reception", 3, 50, destination=self.depot, jour=date.today().replace(day=1))
        val = next(v for v in figer_valorisation_mensuelle(f"{date.today():%Y-%m}", self.fin) if v.depot_id == self.depot.pk)
        self.assertIsNone(val.move)
        self.assertIn("Écriture non passée", val.motif_ecriture)
        self.assertEqual(val.valeur_par_compte, {"320000": "150.00"})
