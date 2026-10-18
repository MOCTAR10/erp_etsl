"""Clôture M8 Maintenance — tests de recette (CDC M8).

Critères :
- MTBF / MTTR / disponibilité par machine calculés depuis les OT, période d'observation paramétrable, valeurs
  provisoires tant qu'ETSL ne les a pas confirmées (publiés à la Couche D : mart dbt `dm_maintenance_fiabilite`) ;
- coût de maintenance par machine et par mois exposé à M11 (sans écriture comptable ; GR isolé au compte 618) ;
- OT 5 états et seuils compteurs GR → OT auto : déjà couverts (tests.py, test_preventif.py).
"""

from datetime import date, datetime, timedelta, timezone as dt_tz
from decimal import Decimal
from pathlib import Path

from rest_framework.test import APITestCase

from accounting_kernel.models import AccountMove
from users.models import User

from .models import Actif, OrdreTravail, ParametreMaintenance
from .services import PARAMETRES_DEFAUT, fiabilite_actifs, get_param_maintenance

AUJOURDHUI = date(2026, 10, 18)


def _user(email, role):
    return User.objects.create_user(email=email, password="x-Audit-2026", role=role)


def _dt(jour, heure=8):
    return datetime(jour.year, jour.month, jour.day, heure, tzinfo=dt_tz.utc)


class _Base(APITestCase):
    def setUp(self):
        self.maint = _user("maint@etls.ga", User.Role.MAINTENANCE)
        self.dop = _user("dop@etls.ga", User.Role.DIRECTEUR_OPERATIONS)
        self.admin = _user("adm@etls.ga", User.Role.ADMIN)
        self.rh = _user("rh@etls.ga", User.Role.RH)
        self.actif = Actif.objects.create(designation="Groupe électrogène", categorie="machine")
        self.client.force_authenticate(self.maint)

    def ot(self, jour, heures, type_ot="correctif", statut="termine", actif=None, **kw):
        debut = _dt(jour)
        return OrdreTravail.objects.create(
            actif=actif or self.actif, description="Intervention", type_ot=type_ot, statut=statut,
            date_debut=debut, date_fin=debut + timedelta(hours=heures) if heures is not None else None, **kw,
        )

    def regler(self, code, valeur):
        get_param_maintenance(code)
        ParametreMaintenance.objects.filter(code=code).update(valeur=Decimal(str(valeur)))

    def ligne(self, actif=None):
        rows = fiabilite_actifs(AUJOURDHUI)["rows"]
        return next(r for r in rows if r["actif"] == (actif or self.actif).code)


class FiabiliteTests(_Base):
    def setUp(self):
        super().setUp()
        self.regler("OBSERVATION_JOURS", 100)  # 100 j × 24 h = 2400 h requises
        self.regler("HEURES_PAR_JOUR", 24)

    def test_mtbf_mttr_disponibilite(self):
        self.ot(AUJOURDHUI - timedelta(days=50), 10)
        self.ot(AUJOURDHUI - timedelta(days=20), 20, type_ot="urgence")
        r = self.ligne()
        self.assertEqual(r["pannes"], 2)
        self.assertEqual(r["heures_arret"], Decimal("30.00"))
        self.assertEqual(r["mttr_h"], Decimal("15.00"))
        self.assertEqual(r["mtbf_h"], Decimal("1185.00"))  # (2400 - 30) / 2
        self.assertEqual(r["disponibilite_pct"], Decimal("98.75"))

    def test_preventif_baisse_la_disponibilite_sans_compter_comme_panne(self):
        self.ot(AUJOURDHUI - timedelta(days=30), 24, type_ot="preventif")
        r = self.ligne()
        self.assertEqual(r["pannes"], 0)
        self.assertIsNone(r["mtbf_h"])
        self.assertIsNone(r["mttr_h"])
        self.assertEqual(r["disponibilite_pct"], Decimal("99.00"))  # (2400 - 24) / 2400

    def test_sans_intervention_disponibilite_pleine(self):
        r = self.ligne()
        self.assertEqual((r["pannes"], r["disponibilite_pct"]), (0, Decimal("100.00")))

    def test_ot_hors_fenetre_annule_ou_non_termine_ignores(self):
        self.ot(AUJOURDHUI - timedelta(days=300), 10)                      # hors fenêtre
        self.ot(AUJOURDHUI - timedelta(days=10), 10, statut="annule")      # annulé
        self.ot(AUJOURDHUI - timedelta(days=5), None, statut="en_cours")   # sans fin
        self.assertEqual(self.ligne()["pannes"], 0)

    def test_fenetre_bornee_par_la_mise_en_service(self):
        self.actif.date_mise_en_service = AUJOURDHUI - timedelta(days=50)
        self.actif.save()
        self.ot(AUJOURDHUI - timedelta(days=10), 12)
        r = self.ligne()
        self.assertEqual(r["heures_requises"], Decimal("1200.00"))  # 50 j × 24 h
        self.assertEqual(r["disponibilite_pct"], Decimal("99.00"))

    def test_periode_observation_parametrable(self):
        self.ot(AUJOURDHUI - timedelta(days=50), 10)
        self.regler("OBSERVATION_JOURS", 30)  # la panne sort de la fenêtre
        self.assertEqual(self.ligne()["pannes"], 0)

    def test_valeurs_provisoires_jusqu_a_confirmation(self):
        self.assertTrue(fiabilite_actifs(AUJOURDHUI)["provisoire"])
        ParametreMaintenance.objects.update(statut_valeur="confirme")
        self.assertFalse(fiabilite_actifs(AUJOURDHUI)["provisoire"])

    def test_endpoint_fiabilite(self):
        r = self.client.get("/api/maintenance/actifs/fiabilite/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.data["provisoire"])
        self.assertEqual(r.data["observation_jours"], 100)
        self.assertEqual([x["actif"] for x in r.data["rows"]], [self.actif.code])


class ParametresMaintenanceTests(_Base):
    def test_defauts_provisoires_crees_a_la_volee(self):
        r = self.client.get("/api/maintenance/parametres/")
        self.assertEqual(r.status_code, 200, r.content)
        rows = r.data["results"] if isinstance(r.data, dict) else r.data
        self.assertEqual({p["code"] for p in rows}, set(PARAMETRES_DEFAUT))
        self.assertTrue(all(p["est_provisoire"] for p in rows))

    def test_modifier_repasse_en_provisoire_et_confirmer_est_reserve_a_la_direction(self):
        p = ParametreMaintenance.objects.get_or_create(
            code="OBSERVATION_JOURS", defaults={"label": "x", "valeur": Decimal("365")})[0]
        self.client.force_authenticate(self.dop)
        r = self.client.post(f"/api/maintenance/parametres/{p.pk}/confirmer/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["confirme_par"], self.dop.pk)
        self.client.force_authenticate(self.maint)
        r = self.client.patch(f"/api/maintenance/parametres/{p.pk}/", {"valeur": "180"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["statut_valeur"], "provisoire")
        r = self.client.post(f"/api/maintenance/parametres/{p.pk}/confirmer/")
        self.assertEqual(r.status_code, 403)

    def test_valeur_non_positive_refusee_et_creation_interdite(self):
        p = ParametreMaintenance.objects.get_or_create(
            code="HEURES_PAR_JOUR", defaults={"label": "x", "valeur": Decimal("24")})[0]
        r = self.client.patch(f"/api/maintenance/parametres/{p.pk}/", {"valeur": "0"}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/maintenance/parametres/", {"code": "X", "valeur": "1"}, format="json")
        self.assertEqual(r.status_code, 405)

    def test_rh_ne_peut_pas_modifier(self):
        p = ParametreMaintenance.objects.get_or_create(
            code="HEURES_PAR_JOUR", defaults={"label": "x", "valeur": Decimal("24")})[0]
        self.client.force_authenticate(self.rh)
        r = self.client.patch(f"/api/maintenance/parametres/{p.pk}/", {"valeur": "10"}, format="json")
        self.assertEqual(r.status_code, 403)


class CoutsM11Tests(_Base):
    def setUp(self):
        super().setUp()
        self.gr = Actif.objects.create(designation="Grue GR", categorie="levage", is_global_rental=True, signe_618=True)
        self.client.force_authenticate(self.admin)

    def terminer(self, actif, jour, heures_mo, tarif, pieces):
        return self.ot(jour, 4, actif=actif, heures_mo=Decimal(heures_mo), tarif_horaire=Decimal(tarif),
                       cout_pieces=Decimal(pieces))

    def test_cout_par_machine_et_par_mois(self):
        self.terminer(self.actif, date(2026, 9, 10), "5", "2000", "30000")   # 40 000
        self.terminer(self.actif, date(2026, 9, 25), "2", "2000", "0")       # 4 000
        self.terminer(self.actif, date(2026, 10, 2), "1", "2000", "0")       # autre mois
        r = self.client.get("/api/controle-gestion/maintenance-couts/?periode=2026-09")
        self.assertEqual(r.status_code, 200, r.content)
        ligne = next(x for x in r.data["rows"] if x["actif"] == self.actif.code)
        self.assertEqual(ligne["nb_ot"], 2)
        self.assertEqual(Decimal(ligne["main_oeuvre"]), Decimal("14000.00"))
        self.assertEqual(Decimal(ligne["pieces"]), Decimal("30000.00"))
        self.assertEqual(Decimal(ligne["total"]), Decimal("44000.00"))

    def test_gr_isole_au_compte_618_et_totaux_separes(self):
        self.terminer(self.actif, date(2026, 9, 10), "1", "1000", "0")
        self.terminer(self.gr, date(2026, 9, 11), "1", "5000", "0")
        r = self.client.get("/api/controle-gestion/maintenance-couts/?periode=2026-09")
        par_code = {x["actif"]: x for x in r.data["rows"]}
        self.assertEqual(par_code[self.gr.code]["compte"], "618000")
        self.assertEqual(par_code[self.actif.code]["compte"], "624000")
        self.assertEqual(Decimal(r.data["totaux"]["gr_618"]), Decimal("5000.00"))
        self.assertEqual(Decimal(r.data["totaux"]["hors_gr"]), Decimal("1000.00"))

    def test_ot_non_termine_ou_annule_non_compte(self):
        self.ot(date(2026, 9, 10), None, statut="en_cours", cout_pieces=Decimal("999"))
        self.ot(date(2026, 9, 12), 3, statut="annule", cout_pieces=Decimal("999"))
        r = self.client.get("/api/controle-gestion/maintenance-couts/?periode=2026-09")
        self.assertEqual(r.data["rows"], [])

    def test_aucune_ecriture_comptable(self):
        self.terminer(self.actif, date(2026, 9, 10), "1", "1000", "100")
        avant = AccountMove.objects.count()
        self.client.get("/api/controle-gestion/maintenance-couts/?periode=2026-09")
        self.assertEqual(AccountMove.objects.count(), avant)

    def test_periode_requise_et_valide(self):
        self.assertEqual(self.client.get("/api/controle-gestion/maintenance-couts/").status_code, 400)
        self.assertEqual(self.client.get("/api/controle-gestion/maintenance-couts/?periode=2026-13").status_code, 400)

    def test_rh_sans_acces_m11(self):
        self.client.force_authenticate(self.rh)
        r = self.client.get("/api/controle-gestion/maintenance-couts/?periode=2026-09")
        self.assertEqual(r.status_code, 403)


class CoucheDTests(APITestCase):
    def test_mart_dbt_publie_et_documente(self):
        dbt = Path(__file__).resolve().parents[2] / "dbt" / "models"
        sql = (dbt / "marts" / "dm_maintenance_fiabilite.sql").read_text(encoding="utf-8")
        for mot in ("mtbf_h", "mttr_h", "disponibilite_pct", "maintenance_parametremaintenance"):
            self.assertIn(mot, sql)
        self.assertIn("dm_maintenance_fiabilite", (dbt / "marts" / "schema.yml").read_text(encoding="utf-8"))
        self.assertIn("maintenance_parametremaintenance", (dbt / "sources.yml").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------------------------------
# PR 2 : pièces de rechange sorties du stock M5, liées à l'OT, valorisées au CUMP ; réappro sous seuil
# --------------------------------------------------------------------------------------------------
from achats.models import PurchaseRequest  # noqa: E402
from referentiels.models import Article, UnitOfMeasure  # noqa: E402
from stocks.models import ArticleStock, Depot, MouvementStock, StockQuant  # noqa: E402
from stocks.services import apply_move  # noqa: E402

from .models import PieceOT  # noqa: E402


class _PiecesBase(_Base):
    def setUp(self):
        super().setUp()
        unit, _ = UnitOfMeasure.objects.get_or_create(code="U", defaults={"label": "Unité"})
        self.filtre = Article.objects.create(
            code="PR-FILTRE", label="Filtre à huile", article_type="consommable", unit=unit, is_stockable=True)
        self.depot = Depot.objects.create(code="DEP-M8", label="Magasin pièces")
        self.entree(10, "1000")
        self.entree(10, "2000")  # CUMP = 1500
        self.ot_en_cours = self.ot_(statut="en_cours")

    def entree(self, qte, prix):
        mv = MouvementStock.objects.create(
            type_mouvement="reception", article=self.filtre, quantite=qte, prix_unitaire=Decimal(prix),
            destination=self.depot, date=AUJOURDHUI)
        apply_move(mv)

    def ot_(self, statut="en_cours"):
        return OrdreTravail.objects.create(actif=self.actif, description="Révision", statut=statut)

    def sortir(self, ot, qte="4", **kw):
        body = {"article": str(self.filtre.pk), "depot": str(self.depot.pk), "quantite": qte}
        body.update(kw)
        return self.client.post(f"/api/maintenance/ordres/{ot.pk}/sortir-piece/", body, format="json")

class PiecesStockTests(_PiecesBase):
    def test_sortie_decremente_le_stock_au_cump_et_alimente_le_cout_de_l_ot(self):
        r = self.sortir(self.ot_en_cours, "4")
        self.assertEqual(r.status_code, 200, r.content)
        quant = StockQuant.objects.get(depot=self.depot, article=self.filtre)
        self.assertEqual(quant.quantity, Decimal("16.00"))
        piece = PieceOT.objects.get(ot=self.ot_en_cours)
        self.assertEqual(piece.cout_unitaire, Decimal("1500.0000"))
        self.assertEqual(piece.mouvement.type_mouvement, "consommation")
        self.assertEqual(piece.mouvement.document_reference, self.ot_en_cours.code)
        self.assertEqual(piece.sorti_par, self.maint)
        self.ot_en_cours.refresh_from_db()
        self.assertEqual(self.ot_en_cours.cout_pieces, Decimal("6000.00"))

    def test_stock_insuffisant_refuse_sans_effet(self):
        r = self.sortir(self.ot_en_cours, "999")
        self.assertEqual(r.status_code, 400, r.content)
        self.assertEqual(PieceOT.objects.count(), 0)
        self.assertEqual(StockQuant.objects.get(depot=self.depot).quantity, Decimal("20.00"))

    def test_ot_non_ouvert_ou_scelle_refuse(self):
        for statut in ("demande", "termine", "cloture", "archive", "annule"):
            self.assertEqual(self.sortir(self.ot_(statut)).status_code, 400, statut)

    def test_quantite_invalide_refusee(self):
        for q in ("0", "-1", "abc"):
            self.assertEqual(self.sortir(self.ot_en_cours, q).status_code, 400, q)

    def test_cout_pieces_libre_interdit_des_qu_une_sortie_existe(self):
        self.sortir(self.ot_en_cours, "1")
        r = self.client.post(f"/api/maintenance/ordres/{self.ot_en_cours.pk}/terminer/", {"cout_pieces": "5"}, format="json")
        self.assertEqual(r.status_code, 400, r.content)
        r = self.client.patch(f"/api/maintenance/ordres/{self.ot_en_cours.pk}/", {"cout_pieces": "5"}, format="json")
        self.assertEqual(r.status_code, 400, r.content)

    def test_cout_piece_remonte_a_m11(self):
        self.sortir(self.ot_en_cours, "2")
        self.client.post(f"/api/maintenance/ordres/{self.ot_en_cours.pk}/terminer/", {}, format="json")
        self.client.force_authenticate(self.admin)
        mois = OrdreTravail.objects.get(pk=self.ot_en_cours.pk).date_fin.strftime("%Y-%m")
        r = self.client.get(f"/api/controle-gestion/maintenance-couts/?periode={mois}")
        ligne = next(x for x in r.data["rows"] if x["actif"] == self.actif.code)
        self.assertEqual(Decimal(ligne["pieces"]), Decimal("3000.00"))

    def test_montants_masques_pour_les_roles_sans_acces(self):
        self.sortir(self.ot_en_cours, "1")
        self.client.force_authenticate(self.rh)
        # rh lit rh_paie mais pas maintenance : 403 ; un lecteur sans montants (chef atelier) voit des None
        chef = _user("chef@etls.ga", User.Role.CHEF_ATELIER)
        self.client.force_authenticate(chef)
        r = self.client.get(f"/api/maintenance/ordres/{self.ot_en_cours.pk}/pieces/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIsNone(r.data[0]["cout_unitaire"])

    def test_liste_des_pieces_de_l_ot(self):
        self.sortir(self.ot_en_cours, "1")
        self.sortir(self.ot_en_cours, "2")
        r = self.client.get(f"/api/maintenance/ordres/{self.ot_en_cours.pk}/pieces/")
        self.assertEqual(len(r.data), 2)
        self.assertEqual(r.data[0]["article_code"], "PR-FILTRE")


class ReapproTests(_PiecesBase):
    def setUp(self):
        super().setUp()
        ArticleStock.objects.create(article=self.filtre, seuil_minimal=Decimal("25"))
        self.sortir(self.ot_en_cours, "1")  # 19 en stock < seuil 25

    def test_besoins_sous_seuil(self):
        r = self.client.get("/api/maintenance/pieces/reappro/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(len(r.data["rows"]), 1)
        b = r.data["rows"][0]
        self.assertEqual((b["article"], Decimal(b["stock"]), Decimal(b["seuil"]), Decimal(b["a_commander"])),
                         ("PR-FILTRE", Decimal("19"), Decimal("25"), Decimal("6")))

    def test_generation_da_brouillon_idempotente(self):
        r = self.client.post("/api/maintenance/pieces/reappro/", {}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        da = PurchaseRequest.objects.get(code=r.data["da"])
        self.assertEqual(da.status, "brouillon")
        self.assertEqual(da.lines.get().quantity, Decimal("6"))
        r2 = self.client.post("/api/maintenance/pieces/reappro/", {}, format="json")
        self.assertEqual(r2.data["lignes_ajoutees"], 0)
        self.assertEqual(PurchaseRequest.objects.count(), 1)

    def test_rien_sous_seuil_aucune_da(self):
        self.entree(50, "1000")
        r = self.client.post("/api/maintenance/pieces/reappro/", {}, format="json")
        self.assertIsNone(r.data["da"])
        self.assertEqual(PurchaseRequest.objects.count(), 0)
