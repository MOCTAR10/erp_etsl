"""Lot a9 (correctifs v0.4) : codes d'objet des gabarits a7 alignés sur le plan de migration (ETSL-ERP-MIG §2),
factures ouvertes en devise (contre-valeur XAF au cours de la date de bascule, rejet sans cours), contrôle C2 par tiers."""

from datetime import date
from decimal import Decimal

from referentiels.models import Currency, TauxChange

from .importers_migration import GABARITS
from . import test_ecarts_a7 as a7
from .test_ecarts_a7 import RepriseA7Base, solde
from .test_ecarts_import import URL


class CodesObjetTests(RepriseA7Base):
    def test_codes_du_plan_de_migration(self):
        attendus = {
            "habilitations_hse": "D14", "equipements_parc": "D15", "releves_compteurs": "D15",
            "actifs_maintenance": "D15", "commandes_ouvertes": "D07", "factures_clients_ouvertes": "D12",
            "factures_fournisseurs_ouvertes": "D12", "balance_ouverture": "D11", "salaries": "D09",
        }
        self.assertEqual({k: GABARITS[k].objet for k in attendus}, attendus)


class _Base(RepriseA7Base):
    setUp = a7.CommandesFacturesOuvertesTests.setUp  # jeu de données a7 : tiers, comptable, exercice 2026


class FacturesEnDeviseTests(_Base):
    def setUp(self):
        super().setUp()
        self.usd, _ = Currency.objects.get_or_create(code="USD", defaults={"label": "Dollar US", "decimals": 2})
        Currency.objects.get_or_create(code="XAF", defaults={"label": "Franc CFA"})

    def cours(self, taux, jour=date(2026, 1, 1)):
        TauxChange.objects.create(devise=self.usd, date=jour, taux=Decimal(taux))

    def test_devise_sans_cours_rejetee_clairement(self):
        r = self.charger("factures_clients_ouvertes", "numero,client,date,solde,devise\nFA-9,CLI-1,2025-12-10,1000,USD\n",
                         date="2026-01-01")
        self.assertEqual((r.data["creees"], r.data["erreurs"]), (0, 1), r.data)
        lignes = self.client.get(f"{URL}lots/{r.data['id']}/lignes/").content.decode()
        self.assertIn("USD sans cours", lignes)
        r = self.charger("factures_clients_ouvertes", "numero,client,date,solde,devise\nFA-9,CLI-1,2025-12-10,1000,ZZZ\n",
                         date="2026-01-01")
        self.assertEqual(r.data["erreurs"], 1)

    def test_facture_client_en_usd_contre_valeur_xaf_a_la_bascule(self):
        from comptabilite.models import FactureClient

        self.cours("600", date(2025, 12, 1))  # cours plus ancien : ignoré au profit du dernier connu
        self.cours("610.5")
        contenu = "numero,client,date,solde,devise\nFA-USD,CLI-1,2025-12-10,1000,USD\n"
        r = self.charger("factures_clients_ouvertes", contenu, date="2026-01-01")
        self.assertEqual((r.data["statut"], r.data["creees"]), ("succes", 1), r.data)
        fa = FactureClient.objects.get(code="FA-USD")
        self.assertEqual(fa.montant_ttc, Decimal("610500"))
        self.assertIn("1000 USD", fa.objet)
        self.assertEqual(solde("411000", self.cli), Decimal("610500"))
        ligne = fa.move.lines.get(partner=self.cli)
        self.assertEqual((ligne.currency.code, ligne.amount_currency, ligne.exchange_rate),
                         ("USD", Decimal("1000"), Decimal("610.5")))
        # Rejeu après correction du cours : reconnu comme doublon (comparaison en devise), aucune écriture de plus.
        TauxChange.objects.filter(devise=self.usd, date=date(2026, 1, 1)).update(taux=Decimal("612"))
        r = self.charger("factures_clients_ouvertes", contenu, date="2026-01-01", force="true")
        self.assertEqual((r.data["doublons"], r.data["creees"]), (1, 0), r.data)
        self.assertEqual(solde("411000", self.cli), Decimal("610500"))

    def test_facture_fournisseur_en_usd_montants_xaf(self):
        from achats.models import PurchaseInvoice

        self.cours("600")
        r = self.charger("factures_fournisseurs_ouvertes", "numero,fournisseur,date,solde,devise\nF-1,FRS-1,2025-12-01,250,USD\n",
                         nom="ff.csv", date="2026-01-01")
        self.assertEqual((r.data["statut"], r.data["creees"]), ("succes", 1), r.data)
        facture = PurchaseInvoice.objects.get(invoice_ref="F-1")
        self.assertEqual((facture.total_ttc, facture.currency.code), (Decimal("150000"), "XAF"))
        self.assertIn("250 USD", facture.purchase_order.notes)
        self.assertEqual(solde("401000", self.frs), Decimal("-150000"))


class ControleC2ParTiersTests(_Base):
    def a_nouveaux(self):
        """À-nouveaux (D11) sur les comptes collectifs sans tiers : 411 1000 au débit, 401 400 au crédit."""
        from accounting_kernel.models import AccountMove, AccountMoveLine, Journal
        from accounting_kernel.services import period_for_date, post_move
        from comptabilite.devises import compte

        jour = date(2026, 1, 1)
        move = AccountMove.objects.create(journal=Journal.objects.get(code="OD"), period=period_for_date(jour), date=jour,
                                          reference="AN-2026", label="A-nouveaux", source="integrations")
        for i, (cpt, d, c) in enumerate((("411000", 1000, 0), ("401000", 0, 400), ("512000", 0, 600))):
            AccountMoveLine.objects.create(move=move, account=compte(cpt), order=i, debit=Decimal(d), credit=Decimal(c))
        post_move(move)

    def test_c2_compare_le_solde_par_tiers(self):
        self.a_nouveaux()
        contenu = "numero,client,date,solde\nFA-1,CLI-1,2025-12-10,1000\n"
        self.assertEqual(self.charger("factures_clients_ouvertes", contenu, date="2026-01-01").data["statut"], "succes")
        self.charger("factures_fournisseurs_ouvertes", "numero,fournisseur,date,solde\nF-1,FRS-1,2025-12-01,400\n",
                     nom="ff.csv", date="2026-01-01")

        def c2(**params):
            r = self.client.get(URL + "rapprochements/", params)
            self.assertEqual(r.status_code, 200, r.content)
            return next(c for c in r.data["controles"] if c["code"] == "C2")

        sans_source = c2()
        self.assertEqual({t["code"]: t["erp"] for t in sans_source["tiers"]}, {"CLI-1": "1000.00", "FRS-1": "-400.00"})
        self.assertEqual(sans_source["statut"], "a_saisir")
        # Total juste (600) mais tiers inversés : écart par tiers détecté.
        faux = c2(source_c2="600", source_c2_tiers="CLI-1;1100\nFRS-1;-500")
        self.assertEqual((faux["ecart"], faux["statut"]), ("0.00", "ecart"))
        self.assertEqual({t["code"]: t["ecart"] for t in faux["tiers"]}, {"CLI-1": "-100.00", "FRS-1": "100.00"})
        juste = c2(source_c2_tiers="CLI-1;1000\nFRS-1=-400")
        self.assertEqual((juste["valeur_source"], juste["statut"]), ("600", "conforme"))
        export = self.client.get(URL + "rapprochements/", {"source_c2_tiers": "CLI-1;1000", "export": "csv"})
        self.assertIn("C2 / CLI-1", export.content.decode("utf-8"))
