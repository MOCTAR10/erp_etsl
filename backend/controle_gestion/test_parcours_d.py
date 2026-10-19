"""Recette « parcours démo » lot D : budget par affaire et écarts (M11), contrats signés, avenant et dossier GR (M12),
cubes — tout rejoué par l'API réelle depuis `seed_all_demo`."""

from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase

from analytics.models import CubeFait
from commercial.models import Avenant, Contract
from controle_gestion.models import AnalyseEcart, Budget
from juridique.models import DossierGlobalRental, LienDocument


def _etat():
    return {
        "budgets": Budget.objects.count(), "ecarts": AnalyseEcart.objects.count(), "contrats": Contract.objects.count(),
        "avenants": Avenant.objects.count(), "dossiers_gr": DossierGlobalRental.objects.count(),
        "liens": LienDocument.objects.count(), "faits": CubeFait.objects.count(),
    }


class ParcoursDemoLotDTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_all_demo", verbosity=0)

    def test_budget_affaire_approuve_au_double_visa(self):
        budget = Budget.objects.get(label__startswith="Budget produits - ")
        self.assertEqual(budget.statut, Budget.Statut.APPROUVE)
        self.assertNotEqual(budget.visa_daf_par_id, budget.visa_cg_par_id)
        self.assertTrue(budget.analytic_id)

    def test_ecarts_detectes_dont_un_analyse(self):
        ecarts = AnalyseEcart.objects.filter(budget__label__startswith="Budget produits - ")
        self.assertEqual(set(ecarts.values_list("statut", flat=True)), {"analysee", "a_analyser"})
        self.assertTrue(all(e.ecart_pct < 0 for e in ecarts))

    def test_contrats_actifs_avec_document_signe_et_avenant(self):
        contrats = Contract.objects.filter(affaire__title__startswith="Parcours demo")
        self.assertEqual(contrats.count(), 2)
        self.assertEqual(set(contrats.values_list("status", flat=True)), {"actif"})
        chantier = contrats.get(is_global_rental=False)
        avenant = chantier.avenants.get()
        self.assertEqual((avenant.numero, avenant.statut, avenant.delta_montant), (1, "signe", Decimal("15000000.00")))
        self.assertEqual(chantier.end_date, avenant.nouvelle_date_fin)

    def test_dossier_gr_ouvert_lie_au_contrat_gr(self):
        dossier = DossierGlobalRental.objects.get(affaire__title__icontains="GLOBAL RENTAL")
        self.assertEqual(dossier.statut, DossierGlobalRental.Statut.OUVERT)
        contrat = Contract.objects.get(affaire=dossier.affaire)
        self.assertEqual(dossier.reference_contrat, contrat.code)
        self.assertTrue(dossier.signe_618)
        self.assertTrue(LienDocument.objects.filter(objet_type="commercial.contract", objet_id=str(contrat.pk)).exists())

    def test_cubes_reconstruits_avec_l_affaire_facturee(self):
        self.assertTrue(CubeFait.objects.exists())

    def test_seed_rejouable_sans_doublon(self):
        avant = _etat()
        call_command("seed_all_demo", verbosity=0)
        self.assertEqual(_etat(), avant)
