"""Clôture M11 (2026-10-18) — contrôle de gestion : paramètres ETSL, sous-activité 90/91/99, doctrine Mix A/B/C.

Critères du CDC : centres 90 (≤ 5 %) / 91 (5-15 %) / 99 (> 15 %) avec alertes ; doctrine d'imputation
Mix A 55 % / B 40 % / C ≤ 5 %. Les valeurs sont des paramètres PROVISOIRES modifiables par ETSL (rien en dur).
"""

from datetime import date
from decimal import Decimal

from accounting_kernel.models import Period
from users.models import User
from workflow.models import Notification

from .models import AlerteSousActivite, Budget, BudgetLigne, ParametreGestion
from .services import alerter_sous_activite, compute_doctrine, compute_sous_activite
from .tests import BASE, BaseGestionTest, _auth

APRES_JANVIER = date(2026, 2, 15)


class SousActiviteTests(BaseGestionTest):
    def setUp(self):
        super().setUp()
        self.budget = self._budget(montant=Decimal("1000000"), statut="approuve")
        BudgetLigne.objects.create(
            budget=self.budget, period=Period.objects.get(number=1, fiscal_year__year=2026), montant=Decimal("1000000")
        )

    def _centre(self, realise):
        self._post_charge(montant=realise, analytic=self.analytic_cc)
        rows = compute_sous_activite(self._fy.pk, APRES_JANVIER)["rows"]
        return rows[0]

    def test_centre_90_jusqua_5_pourcent(self):
        r = self._centre("950000.00")
        self.assertEqual((r["taux_sous_activite"], r["centre"]), (Decimal("5.00"), "90"))

    def test_centre_91_entre_5_et_15_pourcent(self):
        self.assertEqual(self._centre("900000.00")["centre"], "91")

    def test_centre_99_au_dela_de_15_pourcent(self):
        r = self._centre("700000.00")
        self.assertEqual((r["taux_sous_activite"], r["centre"]), (Decimal("30.00"), "99"))

    def test_periode_non_ecoulee_ignoree(self):
        self._post_charge(montant="100000.00", analytic=self.analytic_cc)
        self.assertEqual(compute_sous_activite(self._fy.pk, date(2026, 1, 20))["rows"], [])

    def test_seuils_modifiables_sans_developpeur(self):
        self.assertTrue(compute_sous_activite(self._fy.pk, APRES_JANVIER)["provisoire"])
        self._post_charge(montant="900000.00", analytic=self.analytic_cc)  # 10 % de sous-activité
        ParametreGestion.objects.filter(code="SOUS_ACTIVITE_SEUIL_90").update(valeur=Decimal("12"))
        self.assertEqual(compute_sous_activite(self._fy.pk, APRES_JANVIER)["rows"][0]["centre"], "90")

    def test_alerte_centre_99_une_seule_fois(self):
        self._post_charge(montant="500000.00", analytic=self.analytic_cc)
        self.assertEqual(len(alerter_sous_activite(APRES_JANVIER)), 1)
        self.assertTrue(Notification.objects.filter(user=self.finance, subject__icontains="centre 99").exists())
        self.assertEqual(alerter_sous_activite(APRES_JANVIER), [])
        self.assertEqual(AlerteSousActivite.objects.count(), 1)

    def test_api_sous_activite_et_exercice_requis(self):
        _auth(self.client, "finance@etls.local")
        r = self.client.get(f"{BASE}sous-activite/?fiscal_year={self._fy.pk}")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["provisoire"])
        self.assertEqual(self.client.get(f"{BASE}sous-activite/").status_code, 400)


class ParametresGestionTests(BaseGestionTest):
    def test_defauts_provisoires_et_confirmation_tracee(self):
        _auth(self.client, "finance@etls.local")
        r = self.client.get(f"{BASE}parametres/")
        codes = {p["code"]: p for p in r.data["results"]}
        for code in ("RGM_MIX_A", "RGM_MIX_B", "RGM_MIX_C", "SOUS_ACTIVITE_SEUIL_90", "REPORTING_JOUR_J4"):
            self.assertTrue(codes[code]["est_provisoire"], code)
        pid = codes["RGM_MIX_A"]["id"]
        r = self.client.post(f"{BASE}parametres/{pid}/confirmer/")
        self.assertEqual(r.data["statut_valeur"], "confirme")
        self.assertEqual(ParametreGestion.objects.get(pk=pid).confirme_par, self.finance)
        # Modifier une valeur confirmée la repasse en provisoire.
        r = self.client.patch(f"{BASE}parametres/{pid}/", {"valeur": "60"}, format="json")
        self.assertEqual((r.data["statut_valeur"], r.data["est_provisoire"]), ("provisoire", True))

    def test_valeur_negative_refusee_creation_interdite_role_non_autorise(self):
        _auth(self.client, "finance@etls.local")
        pid = self.client.get(f"{BASE}parametres/").data["results"][0]["id"]
        self.assertEqual(self.client.patch(f"{BASE}parametres/{pid}/", {"valeur": "-1"}, format="json").status_code, 400)
        self.assertEqual(self.client.post(f"{BASE}parametres/", {"code": "X", "valeur": "1"}, format="json").status_code, 400)
        _auth(self.client, "logi@etls.local")
        self.assertEqual(self.client.patch(f"{BASE}parametres/{pid}/", {"valeur": "3"}, format="json").status_code, 403)


class DoctrineTests(BaseGestionTest):
    def _budget_mix(self, classe, montant):
        return self._budget(montant=Decimal(montant), statut="approuve", classe_mix=classe)

    def test_repartition_conforme_55_40_5(self):
        for classe, m in (("A", "5500000"), ("B", "4000000"), ("C", "500000")):
            self._budget_mix(classe, m)
        d = compute_doctrine(self._fy.pk)
        self.assertTrue(d["provisoire"])
        self.assertTrue(d["cible_coherente"])
        self.assertEqual([x["conforme"] for x in d["lignes"]], [True, True, True])

    def test_mix_c_au_dela_du_plafond_non_conforme(self):
        for classe, m in (("A", "5000000"), ("B", "3500000"), ("C", "1500000")):
            self._budget_mix(classe, m)
        d = compute_doctrine(self._fy.pk)
        self.assertFalse(d["lignes"][2]["conforme"])

    def test_cible_incoherente_signalee_apres_modification_etsl(self):
        ParametreGestion.objects.create(code="RGM_MIX_A", label="A", valeur=Decimal("70"), unite="%")
        self.assertFalse(compute_doctrine(self._fy.pk)["cible_coherente"])

    def test_budgets_non_classes_comptes_et_api(self):
        self._budget(montant=Decimal("1000000"), statut="approuve")
        _auth(self.client, "finance@etls.local")
        r = self.client.get(f"{BASE}doctrine/?fiscal_year={self._fy.pk}")
        self.assertEqual((r.status_code, r.data["non_classes"]), (200, 1))

    def test_classe_mix_modifiable_en_brouillon_seulement(self):
        b = self._budget(montant=Decimal("1000000"))
        _auth(self.client, "finance@etls.local")
        r = self.client.patch(f"{BASE}budgets/{b.pk}/", {"classe_mix": "B"}, format="json")
        self.assertEqual((r.status_code, r.data["classe_mix"]), (200, "B"))
        Budget.objects.filter(pk=b.pk).update(statut="approuve")
        self.assertEqual(self.client.patch(f"{BASE}budgets/{b.pk}/", {"classe_mix": "A"}, format="json").status_code, 400)

    def test_chef_service_ne_lit_pas_la_doctrine(self):
        User.objects.create_user(email="cs@etls.local", password="Etls#Demo2026", role=User.Role.CHEF_SERVICE)
        _auth(self.client, "cs@etls.local")
        self.assertEqual(self.client.get(f"{BASE}doctrine/?fiscal_year={self._fy.pk}").status_code, 403)
