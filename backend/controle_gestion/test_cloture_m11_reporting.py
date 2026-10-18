"""Clôture M11 (2026-10-18) — reporting Direction J+4 / J+6, marges brute / opérationnelle / nette, atterrissage.

Les jours J+4 / J+6 sont des paramètres ETSL provisoires ; le coût GLOBAL RENTAL (618) reste isolé.
"""

from datetime import date, timedelta
from decimal import Decimal

from accounting_kernel.models import Period
from workflow.models import Notification

from .models import ClotureGestion, ParametreGestion
from .services import compute_atterrissage, compute_niveaux_marge, suivre_reporting
from .tests import BASE, BaseGestionTest, _auth

from users.models import User


class ReportingTests(BaseGestionTest):
    def setUp(self):
        super().setUp()
        self.janvier = Period.objects.get(number=1, fiscal_year__year=2026)
        self.pdg = User.objects.create_user(email="pdg@etls.local", password="Etls#Demo2026", role=User.Role.PDG)

    def _realisee(self, jours):
        c = ClotureGestion.objects.create(period=self.janvier)
        ClotureGestion.objects.filter(pk=c.pk).update(
            statut="realisee", date_cloture=self.janvier.end_date + timedelta(days=jours)
        )
        return ClotureGestion.objects.get(pk=c.pk)

    def test_echeances_issues_des_parametres(self):
        c = ClotureGestion.objects.create(period=self.janvier)
        self.assertEqual(c.echeance_j4, self.janvier.end_date + timedelta(days=4))
        self.assertEqual(c.echeance_j6, self.janvier.end_date + timedelta(days=6))
        ParametreGestion.objects.filter(code="REPORTING_JOUR_J4").update(valeur=Decimal("3"))
        self.assertEqual(ClotureGestion.objects.get(pk=c.pk).echeance_j4, self.janvier.end_date + timedelta(days=3))

    def test_publication_exige_cloture_realisee_et_previent_la_direction(self):
        c = ClotureGestion.objects.create(period=self.janvier)
        _auth(self.client, "finance@etls.local")
        self.assertEqual(self.client.post(f"{BASE}clotures/{c.pk}/publier/").status_code, 400)
        c = self._realisee(2)
        r = self.client.post(f"{BASE}clotures/{c.pk}/publier/")
        self.assertEqual(r.status_code, 200, r.data)
        c.refresh_from_db()
        self.assertEqual((c.publie_par, c.date_publication is not None), (self.finance, True))
        self.assertTrue(Notification.objects.filter(user=self.pdg, subject__icontains="publié").exists())
        self.assertEqual(self.client.post(f"{BASE}clotures/{c.pk}/publier/").status_code, 400)

    def test_attestation_non_falsifiable_et_role_non_autorise(self):
        c = self._realisee(1)
        _auth(self.client, "logi@etls.local")
        self.assertEqual(self.client.post(f"{BASE}clotures/{c.pk}/publier/").status_code, 403)
        _auth(self.client, "finance@etls.local")
        self.client.patch(f"{BASE}clotures/{c.pk}/", {"date_publication": "2026-01-02", "publie_par": str(self.admin.pk)}, format="json")
        c.refresh_from_db()
        self.assertIsNone(c.date_publication)

    def test_statut_reporting_j4_j6_hors_delai(self):
        fin = self.janvier.end_date
        for jour, attendu in ((4, "a_temps"), (6, "j6"), (7, "hors_delai")):
            c = self._realisee(1)
            ClotureGestion.objects.filter(pk=c.pk).update(date_publication=fin + timedelta(days=jour))
            self.assertEqual(ClotureGestion.objects.get(pk=c.pk).reporting_statut, attendu, jour)
            c.delete()

    def test_relance_j6_une_seule_fois_et_cloture_creee(self):
        today = self.janvier.end_date + timedelta(days=7)
        self.assertEqual(len(suivre_reporting(today)), 1)
        self.assertTrue(ClotureGestion.objects.filter(period=self.janvier).exists())
        self.assertTrue(Notification.objects.filter(user=self.finance, subject__icontains="en retard").exists())
        self.assertEqual(suivre_reporting(today), [])

    def test_pas_de_relance_si_publie_ni_avant_j6(self):
        self.assertEqual(suivre_reporting(self.janvier.end_date + timedelta(days=5)), [])
        c = self._realisee(2)
        ClotureGestion.objects.filter(pk=c.pk).update(date_publication=self.janvier.end_date + timedelta(days=3))
        self.assertEqual(suivre_reporting(self.janvier.end_date + timedelta(days=7)), [])

    def test_stats_exposent_les_clotures_et_api_liste_provisoire(self):
        self._realisee(2)
        _auth(self.client, "finance@etls.local")
        r = self.client.get(f"{BASE}clotures/?fiscal_year={self._fy.pk}")
        self.assertTrue(r.data["results"][0]["reporting_provisoire"])
        self.assertIn("echeance_j6", r.data["results"][0])


class NiveauxMargeTests(BaseGestionTest):
    def test_trois_niveaux_et_gr_isole(self):
        self._post_produit(montant="10000000.00", analytic=self.analytic_aff)
        self._post_charge(montant="4000000.00", analytic=self.analytic_aff, ref="DIR1")  # direct (affaire)
        self._post_charge(montant="1000000.00", analytic=self.analytic_cc, ref="STR1")  # structure (centre de coût)
        self._post_charge_gr(montant="500000.00", analytic=self.analytic_aff)
        m = compute_niveaux_marge(self._fy.pk)
        self.assertEqual(m["marge_brute"], Decimal("6000000"))
        self.assertEqual(m["marge_operationnelle"], Decimal("5000000"))
        self.assertEqual(m["cout_gr"], Decimal("500000"))
        self.assertEqual(m["marge_nette"], Decimal("4500000"))
        self.assertEqual(m["taux_brute"], Decimal("60.00"))
        # Le coût GR n'est jamais mêlé aux charges directes ni de structure.
        self.assertEqual((m["charges_directes"], m["charges_structure"]), (Decimal("4000000"), Decimal("1000000")))

    def test_api_exercice_requis_et_montants_masques(self):
        _auth(self.client, "finance@etls.local")
        self.assertEqual(self.client.get(f"{BASE}niveaux-marge/").status_code, 400)
        r = self.client.get(f"{BASE}niveaux-marge/?fiscal_year={self._fy.pk}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("marge_nette", r.data)


class AtterrissageTests(BaseGestionTest):
    def test_atterrissage_et_marge_a_terminaison(self):
        from .models import BudgetLigne

        today = date(2026, 3, 1)  # janvier et février écoulés
        prod = self._budget(type_budget="produit", montant=Decimal("3000000"), statut="approuve")
        chg = self._budget(montant=Decimal("1800000"), statut="approuve")
        for b, mensuel in ((prod, "1000000"), (chg, "600000")):
            for n in (1, 2, 3):
                BudgetLigne.objects.create(
                    budget=b, period=Period.objects.get(number=n, fiscal_year__year=2026), montant=Decimal(mensuel)
                )
        self._post_produit(montant="1500000.00", analytic=self.analytic_cc)  # janvier : +500 000 vs budget
        a = compute_atterrissage(self._fy.pk, today)
        ligne = {r["code"]: r for r in a["rows"]}[prod.code]
        self.assertEqual(ligne["realise"], Decimal("1500000"))
        self.assertEqual(ligne["reste_a_venir"], Decimal("1000000"))  # mars seul à venir
        self.assertEqual(ligne["atterrissage"], Decimal("2500000"))
        self.assertEqual(ligne["ecart_objectif"], Decimal("-500000"))
        # charges : rien de réalisé sur février/janvier, mars à venir
        self.assertEqual(a["totaux"]["charge"], Decimal("600000"))
        self.assertEqual(a["marge_a_terminaison"], Decimal("1900000"))

    def test_api(self):
        _auth(self.client, "finance@etls.local")
        r = self.client.get(f"{BASE}atterrissage/?fiscal_year={self._fy.pk}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("marge_a_terminaison", r.data)
