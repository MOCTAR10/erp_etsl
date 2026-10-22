"""Lot a3 : M5 → M6 (lot / coulée / certificat 3.1 jusqu'au joint), M6 → M10 (coût de non-qualité comptabilisé),
contrôle saisi hors ligne (horodatage, conflit)."""

from datetime import date, timedelta
from decimal import Decimal

from django.core.management import call_command
from django.utils import timezone

from accounting_kernel.models import AccountMove
from operations.terrain_a3 import consommer_sur_of
from referentiels.models import Account, Article, UnitOfMeasure
from stocks.models import CertificatMatiere, Depot, LotMatiere, MouvementStock
from stocks.services import apply_move
from users.models import User

from .models import ControleQualite, CoutNonQualite, DiffusionWps, NonConformite, ParametreQualite
from .test_ecarts_m6 import Base, user


class LotJointBase(Base):
    def setUp(self):
        super().setUp()
        DiffusionWps.objects.create(wps=self.wps, ordre=self.of)
        self.of.status = "lance"
        self.of.save(update_fields=["status"])
        unit, _ = UnitOfMeasure.objects.get_or_create(code="U", defaults={"label": "Unité"})
        self.article = Article.objects.create(code="ART-A3Q", label="Tube X52", article_type=Article.ArticleType.MATIERE,
                                              unit=unit)
        self.depot = Depot.objects.create(code="DEP-A3Q", label="Magasin")
        self.mag = user("mag-a3q@etls.ga", User.Role.LOGISTIQUE)
        self.lot = self.creer_lot("L-77", "HEAT-77")
        CertificatMatiere.objects.create(lot=self.lot, type="mtc", numero_certificat="MTC-77", date_validation=date.today())

    def creer_lot(self, numero, coulee):
        lot = LotMatiere.objects.create(article=self.article, numero_lot=numero, numero_coulee=coulee,
                                        date_reception=date.today(), quantite_initiale=50, quantite_restante=0)
        apply_move(MouvementStock.objects.create(
            type_mouvement=MouvementStock.Type.RECEPTION, article=self.article, quantite=50, prix_unitaire=2000,
            destination=self.depot, lot=lot, date=date.today(), created_by=self.mag, document_reference="BC-0001",
        ))
        lot.refresh_from_db()
        return lot

    def consommer(self, lot=None):
        consommer_sur_of(self.of, self.mag, article=self.article, depot=self.depot, quantite=Decimal("5"),
                         lot=lot or self.lot)

    def joint_lot(self, repere="J1", **kw):
        return self.client.post("/api/qualite/joints/", {
            "ordre": str(self.of.pk), "repere": repere, "soudeur": str(self.soudeur.pk), "wps": str(self.wps.pk), **kw,
        }, format="json")


class LotJointTests(LotJointBase):
    def test_lot_obligatoire_des_que_l_of_a_consomme_un_lot(self):
        self.assertEqual(self.joint_lot("J0").status_code, 201)  # OF sans consommation tracée : facultatif
        self.consommer()
        r = self.joint_lot()
        self.assertEqual(r.status_code, 400)
        self.assertIn("lot", r.data)
        ParametreQualite.objects.filter(code="JOINT_LOT_OBLIGATOIRE").update(valeur=0)
        self.assertEqual(self.joint_lot().status_code, 201)

    def test_coulee_et_certificat_31_repris_du_lot(self):
        self.consommer()
        r = self.joint_lot(lot=str(self.lot.pk))
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["numero_coulee"], "HEAT-77")
        self.assertEqual(r.data["certificats"][0]["type_label"], "3.1 (MTC EN 10204)")
        self.assertTrue(r.data["certificats"][0]["valide"])
        trace = self.client.get(f"/api/qualite/joints/{r.data['id']}/tracabilite/").data
        self.assertEqual([m["type"] for m in trace["mouvements"]], ["reception", "consommation"])
        self.assertEqual(trace["mouvements"][0]["reference"], "BC-0001")
        choix = self.client.get(f"/api/qualite/joints/lots-consommes/?ordre={self.of.pk}").data  # QA/QC sans lecture M5
        self.assertEqual([(c["code"], c["numero_coulee"]) for c in choix], [(self.lot.code, "HEAT-77")])
        self.client.force_authenticate(self.mag)
        aval = self.client.get(f"/api/stocks/lots/{self.lot.pk}/joints/").data
        self.assertEqual([j["repere"] for j in aval], ["J1"])

    def test_coulee_differente_refusee(self):
        self.consommer()
        r = self.joint_lot(lot=str(self.lot.pk), numero_coulee="HEAT-99")
        self.assertEqual(r.status_code, 400)
        self.assertIn("numero_coulee", r.data)

    def test_lot_non_sorti_pour_l_of_refuse(self):
        self.consommer()
        autre = self.creer_lot("L-88", "HEAT-88")
        r = self.joint_lot(lot=str(autre.pk))
        self.assertEqual(r.status_code, 400)
        self.assertIn("non sorti", str(r.data["lot"]))

    def test_lot_en_quarantaine_refuse(self):
        self.consommer()
        LotMatiere.objects.filter(pk=self.lot.pk).update(statut=LotMatiere.Statut.BLOQUE)
        self.assertEqual(self.joint_lot(lot=str(self.lot.pk)).status_code, 400)


class CoutNonQualiteTests(LotJointBase):
    def setUp(self):
        super().setUp()
        call_command("seed_accounting", year=timezone.localdate().year)
        for code in ("624000", "603200", "661000"):
            Account.objects.get_or_create(code=code, defaults={"label": code, "account_class": 6,
                                                               "account_type": Account.AccountType.EXPENSE})
        controle = ControleQualite.objects.create(type_controle="visuel", ordre=self.of, lot=self.lot,
                                                  resultat="non_conforme")
        self.nc = NonConformite.objects.create(controle=controle, source="interne", description="Fissure en racine")
        self.finance = user("fin-a3@etls.ga", User.Role.FINANCE)

    def saisir(self, **kw):
        return self.client.post("/api/qualite/couts-non-qualite/", {"non_conformite": str(self.nc.pk), **kw}, format="json")

    def test_valorisation_reprise_et_rebut(self):
        r = self.saisir(nature="reprise", heures="3")
        self.assertEqual(r.status_code, 201, r.content)
        r2 = self.saisir(nature="rebut", quantite="2")
        self.assertEqual(r2.status_code, 201, r2.content)
        self.assertEqual(CoutNonQualite.objects.get(pk=r.data["id"]).montant, Decimal("18000"))  # 3 h × 6 000
        self.assertEqual(CoutNonQualite.objects.get(pk=r2.data["id"]).montant, Decimal("4000"))  # 2 × coût du lot
        self.assertIsNone(r.data["montant"])  # QA/QC hors cercle des montants : masqué
        self.client.force_authenticate(self.finance)
        self.assertEqual(self.client.get("/api/qualite/couts-non-qualite/synthese/").data["total"], "22000.00")

    def test_saisie_incomplete_refusee(self):
        self.assertEqual(self.saisir(nature="reprise").status_code, 400)
        self.assertEqual(self.saisir(nature="rebut").status_code, 400)

    def test_comptabilisation_par_la_finance_seulement(self):
        cnq = self.saisir(nature="reprise", heures="2", frais_externes="5000").data
        url = f"/api/qualite/couts-non-qualite/{cnq['id']}/comptabiliser/"
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.force_authenticate(self.finance)
        r = self.client.post(url)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["statut"], "comptabilise")
        move = AccountMove.objects.get(source="M6", source_ref=cnq["id"])
        self.assertEqual(move.status, AccountMove.Status.POSTED)
        lignes = {(l.account.code, l.debit, l.credit) for l in move.lines.all()}
        self.assertEqual(lignes, {
            ("624000", Decimal("17000.00"), Decimal("0.00")),
            ("603200", Decimal("0.00"), Decimal("5000.00")),
            ("661000", Decimal("0.00"), Decimal("12000.00")),
        })
        self.assertEqual(self.client.post(url).status_code, 400)  # une seule écriture par coût

    def test_compte_absent_du_plan_bloque_sans_ecriture_partielle(self):
        from .ecarts import get_param_qualite

        get_param_qualite("CNQ_COMPTE_CHARGE")
        ParametreQualite.objects.filter(code="CNQ_COMPTE_CHARGE").update(valeur=999999)
        cnq = self.saisir(nature="reprise", heures="1").data
        self.client.force_authenticate(self.finance)
        r = self.client.post(f"/api/qualite/couts-non-qualite/{cnq['id']}/comptabiliser/")
        self.assertEqual(r.status_code, 400)
        self.assertIn("999999", str(r.data["detail"]))
        self.assertFalse(AccountMove.objects.filter(source="M6").exists())


class ControleHorsLigneTests(Base):
    def test_controle_saisi_hors_ligne_horodate_et_conflit_de_delai(self):
        corps = {"type_controle": "cnd", "point_controle": "J1", "resultat": "conforme", "statut": "en_cours"}
        saisi = timezone.now() - timedelta(minutes=30)
        r = self.client.post("/api/qualite/controles/", {**corps, "saisi_le": saisi.isoformat()}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(ControleQualite.objects.get(pk=r.data["id"]).saisi_le, saisi)
        vieux = (timezone.now() - timedelta(days=30)).isoformat()
        self.assertEqual(self.client.post("/api/qualite/controles/", {**corps, "saisi_le": vieux}, format="json").status_code, 409)
        r = self.client.post("/api/qualite/controles/", {**corps, "saisi_le": vieux, "forcer": True}, format="json")
        self.assertEqual(r.status_code, 201)
