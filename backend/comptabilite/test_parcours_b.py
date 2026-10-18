"""Recette « parcours démo » lot B : situations -> facture M10 -> encaissement -> lettrage ; achats M2 (GR / 618) ;
litiges fournisseurs ; inventaire tournant M5 — tout rejoué par l'API réelle depuis `seed_all_demo`."""

from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase

from accounting_kernel.models import AccountMove
from achats.models import LitigeFournisseur, PurchaseInvoice
from comptabilite.models import FactureClient, Lettrage, Paiement
from juridique.models import Contentieux
from operations.models import SituationTravaux
from stocks.models import Inventaire, MouvementStock


def _etat():
    return {
        "situations": SituationTravaux.objects.count(), "factures": FactureClient.objects.count(),
        "paiements": Paiement.objects.count(), "lettrages": Lettrage.objects.count(),
        "ecritures": AccountMove.objects.count(), "litiges": LitigeFournisseur.objects.count(),
        "inventaires": Inventaire.objects.count(), "mvts": MouvementStock.objects.count(),
    }


class ParcoursDemoLotBTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_all_demo", verbosity=0)

    def test_situations_dans_chaque_etat(self):
        statuts = set(SituationTravaux.objects.filter(label__contains="(demo)").values_list("status", flat=True))
        self.assertEqual(statuts, {"brouillon", "soumise", "validee", "facturee"})

    def test_situation_facturee_emet_une_facture_et_l_ecriture_de_vente(self):
        facture = FactureClient.objects.get(situation__status="facturee")
        self.assertEqual(facture.statut, FactureClient.Statut.EMISE)
        self.assertEqual(facture.move.journal.code, "VTE")
        self.assertEqual(facture.situation.facture_ref, facture.code)
        self.assertEqual(facture.montant_ttc, facture.montant_ht * Decimal("1.18"))

    def test_encaissement_comptabilise_et_lettre_a_la_facture(self):
        facture = FactureClient.objects.get(situation__status="facturee")
        paiement = Paiement.objects.get(sens="entree", reference=f"Encaissement {facture.code}")
        self.assertEqual((paiement.statut, paiement.montant), ("valide", facture.montant_ttc))
        lettrage = Lettrage.objects.get(compte__code="411000", statut="actif")
        self.assertEqual(lettrage.ecart, 0)
        self.assertEqual({l.ligne.move_id for l in lettrage.lignes.all()}, {facture.move_id, paiement.move_id})

    def test_achats_comptabilises_dont_global_rental_au_618(self):
        gr = PurchaseInvoice.objects.get(purchase_order__is_global_rental=True, invoice_ref__endswith="DEMO")
        self.assertEqual(gr.status, PurchaseInvoice.Status.COMPTABILISEE)
        codes = {l.account.code for l in gr.move.lines.select_related("account")}
        self.assertTrue({"618000", "401100"} <= codes)
        standard = PurchaseInvoice.objects.get(purchase_order__is_global_rental=False, invoice_ref__endswith="DEMO")
        self.assertTrue(standard.paiements.filter(statut="valide").exists())  # dette 401 soldée
        self.assertFalse(gr.paiements.exists())  # dette GR laissée ouverte

    def test_litiges_ouvert_escalade_et_resolu(self):
        self.assertEqual(set(LitigeFournisseur.objects.values_list("statut", flat=True)), {"relance", "escalade", "resolu"})
        escalade = LitigeFournisseur.objects.get(statut="escalade")
        self.assertEqual(escalade.contentieux.phase, Contentieux.Phase.PRE_CONTENTIEUX)

    def test_inventaire_tournant_cloture_avec_ecart_applique(self):
        inv = Inventaire.objects.get(type="tournant")
        self.assertEqual(inv.statut, Inventaire.Statut.CLOTURE)
        self.assertTrue(inv.lignes.filter(comptee=True).exists())
        self.assertTrue(MouvementStock.objects.filter(type_mouvement="inventaire", document_reference=inv.code).exists())

    def test_seed_rejouable_sans_doublon(self):
        avant = _etat()
        call_command("seed_all_demo", verbosity=0)
        self.assertEqual(_etat(), avant)
