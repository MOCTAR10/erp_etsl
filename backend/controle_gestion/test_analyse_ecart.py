"""Lot 15 (2026-10-17) — écart budget / réalisé > 10 % → analyse obligatoire sous 5 jours (CDC M11 §4.4).

- Une période écoulée dont le réalisé s'écarte de plus de 10 % du budget (dépassement ou sous-réalisation)
  ouvre une analyse d'écart, échéance J+5, et prévient le contrôle de gestion (Finance / DGA).
- Détection idempotente (une analyse par budget et période), quotidienne (Celery) ou à la demande.
- L'analyse se rend par l'action `analyser` (explication obligatoire, auteur et date tracés) ; une analyse
  non rendue après l'échéance est signalée en retard.
"""

from datetime import date, timedelta
from decimal import Decimal

from accounting_kernel.models import Period
from workflow.models import Notification

from .models import AnalyseEcart, BudgetLigne
from .services import detecter_ecarts
from .tests import BASE, BaseGestionTest, _auth


class AnalyseEcartTests(BaseGestionTest):
    def setUp(self):
        super().setUp()
        self.budget = self._budget(montant=Decimal("1000000"), statut="approuve")
        self.janvier = Period.objects.get(number=1, fiscal_year__year=2026)
        BudgetLigne.objects.create(budget=self.budget, period=self.janvier, montant=Decimal("1000000"))

    def test_depassement_de_plus_de_10_pourcent_ouvre_une_analyse(self):
        self._post_charge(montant="1150000.00", analytic=self.analytic_cc)
        crees = detecter_ecarts()
        self.assertEqual(len(crees), 1)
        analyse = AnalyseEcart.objects.get(budget=self.budget, period=self.janvier)
        self.assertEqual(analyse.ecart_pct, Decimal("15.00"))
        self.assertEqual(analyse.echeance, analyse.detecte_le + timedelta(days=5))
        self.assertTrue(Notification.objects.filter(user=self.finance, subject__icontains=self.budget.code).exists())
        self.assertEqual(detecter_ecarts(), [])  # idempotent

    def test_ecart_de_10_pourcent_ou_moins_sans_analyse(self):
        self._post_charge(montant="1100000.00", analytic=self.analytic_cc)
        self.assertEqual(detecter_ecarts(), [])

    def test_sous_realisation_de_plus_de_10_pourcent(self):
        self._post_charge(montant="800000.00", analytic=self.analytic_cc)
        detecter_ecarts()
        self.assertEqual(AnalyseEcart.objects.get().ecart_pct, Decimal("-20.00"))

    def test_budget_brouillon_ignore(self):
        self.budget.statut = "brouillon"
        self.budget.save(update_fields=["statut"])
        self._post_charge(montant="1500000.00", analytic=self.analytic_cc)
        self.assertEqual(detecter_ecarts(), [])

    def test_analyse_rendue_et_retard(self):
        self._post_charge(montant="1500000.00", analytic=self.analytic_cc)
        analyse = detecter_ecarts()[0]
        AnalyseEcart.objects.filter(pk=analyse.pk).update(echeance=date.today() - timedelta(days=1))
        _auth(self.client, "finance@etls.local")
        r = self.client.get(f"{BASE}analyses-ecart/?en_retard=1")
        self.assertEqual([a["id"] for a in r.data["results"]], [str(analyse.pk)])
        url = f"{BASE}analyses-ecart/{analyse.pk}/analyser/"
        self.assertEqual(self.client.post(url, {}, format="json").status_code, 400)
        r = self.client.post(url, {"analyse": "Surcoût acier non budgété", "actions": "Révision R1"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.data["statut"], r.data["en_retard"]), ("analysee", False))
        analyse.refresh_from_db()
        self.assertEqual(analyse.analyse_par, self.finance)
        self.assertEqual(self.client.post(url, {"analyse": "bis"}, format="json").status_code, 400)

    def test_lecture_seule_hors_cercle_finance(self):
        self._post_charge(montant="1500000.00", analytic=self.analytic_cc)
        analyse = detecter_ecarts()[0]
        _auth(self.client, "logi@etls.local")
        r = self.client.post(f"{BASE}analyses-ecart/{analyse.pk}/analyser/", {"analyse": "x"}, format="json")
        self.assertEqual(r.status_code, 403)
