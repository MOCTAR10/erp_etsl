"""Recette M10 (clôture) — PR 1/3 : paramètres modifiables + lettrage automatique.

Les valeurs de ParametreCompta chargées par défaut sont PROVISOIRES (à confirmer par ETSL).
Le lettrage ne touche jamais aux écritures comptabilisées (immuables) : il vit dans ses propres tables.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from accounting_kernel.models import AccountMove, AccountMoveLine, Journal
from accounting_kernel.services import period_for_date, post_move
from referentiels.models import Account, Partner

from .models import Lettrage, LigneLettree, ParametreCompta
from .services import get_param
from .tests import BASE, BaseComptaTest, _auth


class M10Base(BaseComptaTest):
    def setUp(self):
        super().setUp()
        self.client_acc = Account.objects.get(code="411000")
        self.banque = Account.objects.get(code="512000")
        self.produit = Account.objects.get_or_create(
            code="706000",
            defaults=dict(label="Ventes", account_class=7, account_type=Account.AccountType.INCOME),
        )[0]
        self.p1 = Partner.objects.create(code="C-001", name="CLIENT UN", kind=Partner.Kind.CLIENT)
        self.p2 = Partner.objects.create(code="C-002", name="CLIENT DEUX", kind=Partner.Kind.CLIENT)

    def move(self, d, debit_acc, credit_acc, montant, partner=None, reference="", on="debit", post=True):
        """Écriture à 2 lignes ; `partner` posé sur la ligne du compte client (411)."""
        j = Journal.objects.get(code="OD")
        m = AccountMove.objects.create(
            journal=j, period=period_for_date(d), date=d, reference=reference, label="t"
        )
        AccountMoveLine.objects.create(
            move=m, account=debit_acc, debit=Decimal(montant), order=0,
            partner=partner if debit_acc.code == "411000" else None,
        )
        AccountMoveLine.objects.create(
            move=m, account=credit_acc, credit=Decimal(montant), order=1,
            partner=partner if credit_acc.code == "411000" else None,
        )
        if post:
            post_move(m, self.admin)
        return m

    def facture(self, d, montant, partner, reference=""):
        m = self.move(d, self.client_acc, self.produit, montant, partner, reference)
        return m.lines.get(account=self.client_acc)

    def encaissement(self, d, montant, partner, reference=""):
        m = self.move(d, self.banque, self.client_acc, montant, partner, reference)
        return m.lines.get(account=self.client_acc)


class ParametresTests(M10Base):
    def test_defaut_provisoire_cree_a_la_volee(self):
        p = get_param("LETTRAGE_TOLERANCE")
        self.assertEqual(p, Decimal("0"))
        obj = ParametreCompta.objects.get(code="LETTRAGE_TOLERANCE")
        self.assertTrue(obj.est_provisoire)

    def test_modification_par_finance_et_confirmation(self):
        _auth(self.client, "finance@etls.local")
        get_param("LETTRAGE_TOLERANCE")
        pid = ParametreCompta.objects.get(code="LETTRAGE_TOLERANCE").id
        r = self.client.patch(f"{BASE}parametres/{pid}/", {"valeur": "5"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(get_param("LETTRAGE_TOLERANCE"), Decimal("5"))
        r = self.client.post(f"{BASE}parametres/{pid}/confirmer/")
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual(body["statut_valeur"], "confirme")
        self.assertTrue(body["confirme_par"])

    def test_liste_expose_avertissement_provisoire(self):
        _auth(self.client, "compta@etls.local")
        r = self.client.get(f"{BASE}parametres/")
        self.assertEqual(r.status_code, 200)
        rows = r.json()["results"] if isinstance(r.json(), dict) else r.json()
        self.assertTrue(rows and all(x["est_provisoire"] for x in rows))

    def test_logistique_ne_modifie_pas(self):
        get_param("LETTRAGE_TOLERANCE")
        pid = ParametreCompta.objects.get(code="LETTRAGE_TOLERANCE").id
        _auth(self.client, "logi@etls.local")
        r = self.client.patch(f"{BASE}parametres/{pid}/", {"valeur": "5"}, format="json")
        self.assertIn(r.status_code, (401, 403))


class LettrageManuelTests(M10Base):
    def setUp(self):
        super().setUp()
        _auth(self.client, "compta@etls.local")

    def post(self, ids):
        return self.client.post(f"{BASE}lettrages/", {"lignes": [str(i) for i in ids]}, format="json")

    def test_lettrage_equilibre(self):
        f = self.facture(date(2026, 2, 1), "1000", self.p1)
        e = self.encaissement(date(2026, 2, 10), "1000", self.p1)
        r = self.post([f.id, e.id])
        self.assertEqual(r.status_code, 201, r.content)
        body = r.json()
        self.assertTrue(body["code"].startswith("LET"))
        self.assertFalse(body["automatique"])
        self.assertEqual(Decimal(body["ecart"]), Decimal("0"))
        self.assertEqual(LigneLettree.objects.count(), 2)
        self.assertTrue(body["created_by"])

    def test_desequilibre_refuse(self):
        f = self.facture(date(2026, 2, 1), "1000", self.p1)
        e = self.encaissement(date(2026, 2, 10), "900", self.p1)
        r = self.post([f.id, e.id])
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Lettrage.objects.count(), 0)

    def test_tolerance_parametrable_accepte_petit_ecart(self):
        get_param("LETTRAGE_TOLERANCE")
        ParametreCompta.objects.filter(code="LETTRAGE_TOLERANCE").update(valeur=Decimal("10"))
        f = self.facture(date(2026, 2, 1), "1000", self.p1)
        e = self.encaissement(date(2026, 2, 10), "995", self.p1)
        r = self.post([f.id, e.id])
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Decimal(r.json()["ecart"]), Decimal("5"))

    def test_comptes_differents_refuse(self):
        f = self.facture(date(2026, 2, 1), "1000", self.p1)
        autre = self.move(date(2026, 2, 2), self.banque, self.produit, "1000").lines.get(account=self.banque)
        self.assertEqual(self.post([f.id, autre.id]).status_code, 400)

    def test_compte_non_lettrable_refuse(self):
        a = self.move(date(2026, 2, 2), Account.objects.get(code="601000"), self.banque, "500")
        ids = [x.id for x in a.lines.all()]
        self.assertEqual(self.post(ids).status_code, 400)

    def test_ligne_brouillon_refusee(self):
        f = self.facture(date(2026, 2, 1), "1000", self.p1)
        m = self.move(date(2026, 2, 10), self.banque, self.client_acc, "1000", self.p1, post=False)
        e = m.lines.get(account=self.client_acc)
        self.assertEqual(self.post([f.id, e.id]).status_code, 400)

    def test_ligne_deja_lettree_refusee(self):
        f = self.facture(date(2026, 2, 1), "1000", self.p1)
        e = self.encaissement(date(2026, 2, 10), "1000", self.p1)
        self.assertEqual(self.post([f.id, e.id]).status_code, 201)
        e2 = self.encaissement(date(2026, 2, 11), "1000", self.p1)
        self.assertEqual(self.post([f.id, e2.id]).status_code, 400)

    def test_tiers_differents_refuse(self):
        f = self.facture(date(2026, 2, 1), "1000", self.p1)
        e = self.encaissement(date(2026, 2, 10), "1000", self.p2)
        self.assertEqual(self.post([f.id, e.id]).status_code, 400)

    def test_delettrage_trace_et_ecritures_intactes(self):
        f = self.facture(date(2026, 2, 1), "1000", self.p1)
        e = self.encaissement(date(2026, 2, 10), "1000", self.p1)
        lid = self.post([f.id, e.id]).json()["id"]
        r = self.client.post(f"{BASE}lettrages/{lid}/delettrer/", {"motif": "erreur de tiers"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        lt = Lettrage.objects.get(pk=lid)
        self.assertEqual(lt.statut, "annule")
        self.assertEqual(lt.motif_annulation, "erreur de tiers")
        self.assertIsNotNone(lt.annule_par_id)
        self.assertEqual(LigneLettree.objects.count(), 0)
        # les lignes peuvent être relettrées, l'écriture comptabilisée n'a pas bougé
        self.assertEqual(self.post([f.id, e.id]).status_code, 201)
        f.refresh_from_db()
        self.assertEqual(f.move.status, AccountMove.Status.POSTED)

    def test_delettrage_exige_un_motif(self):
        f = self.facture(date(2026, 2, 1), "1000", self.p1)
        e = self.encaissement(date(2026, 2, 10), "1000", self.p1)
        lid = self.post([f.id, e.id]).json()["id"]
        r = self.client.post(f"{BASE}lettrages/{lid}/delettrer/", {}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_logistique_ne_lettre_pas(self):
        f = self.facture(date(2026, 2, 1), "1000", self.p1)
        e = self.encaissement(date(2026, 2, 10), "1000", self.p1)
        _auth(self.client, "logi@etls.local")
        self.assertIn(self.post([f.id, e.id]).status_code, (401, 403))


class LettrageAutoTests(M10Base):
    def setUp(self):
        super().setUp()
        _auth(self.client, "compta@etls.local")

    def auto(self, **kw):
        return self.client.post(f"{BASE}lettrages/lettrer-auto/", {"compte": str(self.client_acc.id), **kw}, format="json")

    def test_auto_par_reference_commune(self):
        self.facture(date(2026, 2, 1), "1000", self.p1, "FAC-1")
        self.encaissement(date(2026, 2, 10), "600", self.p1, "FAC-1")
        self.encaissement(date(2026, 2, 12), "400", self.p1, "FAC-1")
        r = self.auto()
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["lettrages"], 1)
        lt = Lettrage.objects.get()
        self.assertTrue(lt.automatique)
        self.assertEqual(lt.lignes.count(), 3)

    def test_auto_par_montant_unique_sans_reference(self):
        self.facture(date(2026, 2, 1), "2500", self.p1)
        self.encaissement(date(2026, 2, 20), "2500", self.p1)
        self.assertEqual(self.auto().json()["lettrages"], 1)

    def test_auto_ne_melange_pas_les_tiers_et_laisse_le_non_apparie(self):
        self.facture(date(2026, 2, 1), "1000", self.p1, "X")
        self.encaissement(date(2026, 2, 5), "1000", self.p2, "X")
        self.facture(date(2026, 2, 6), "777", self.p1)
        r = self.auto()
        self.assertEqual(r.json()["lettrages"], 0)
        self.assertEqual(r.json()["non_lettrees"], 3)

    def test_auto_idempotent(self):
        self.facture(date(2026, 2, 1), "1000", self.p1, "A")
        self.encaissement(date(2026, 2, 5), "1000", self.p1, "A")
        self.assertEqual(self.auto().json()["lettrages"], 1)
        self.assertEqual(self.auto().json()["lettrages"], 0)
        self.assertEqual(Lettrage.objects.count(), 1)

    def test_auto_ignore_brouillons_et_comptes_non_lettrables(self):
        self.move(date(2026, 2, 1), self.client_acc, self.produit, "1000", self.p1, post=False)
        self.assertEqual(self.auto().json()["lettrages"], 0)
        r = self.client.post(
            f"{BASE}lettrages/lettrer-auto/", {"compte": str(Account.objects.get(code='601000').id)}, format="json"
        )
        self.assertEqual(r.status_code, 400)

    def test_anomalies_lignes_anciennes_non_lettrees(self):
        vieille = timezone.localdate() - timedelta(days=120)
        recente = timezone.localdate() - timedelta(days=5)
        f_old = self.facture(vieille, "300", self.p1)
        self.facture(recente, "400", self.p1)
        sans_tiers = self.move(recente, self.client_acc, self.produit, "50").lines.get(account=self.client_acc)
        r = self.client.get(f"{BASE}lettrages/anomalies/?compte={self.client_acc.id}")
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        motifs = {a["ligne"]: a["motif"] for a in body["anomalies"]}
        self.assertEqual(motifs[str(f_old.id)], "ancienne")
        self.assertEqual(motifs[str(sans_tiers.id)], "sans_tiers")
        self.assertEqual(len(body["anomalies"]), 2)
        self.assertEqual(body["delai_jours"], 90)
        self.assertTrue(body["parametres_provisoires"])
