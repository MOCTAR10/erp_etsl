"""Recette M9 (clôture) — barèmes de paie paramétrables, taux provisoires, historique inaltérable.

PR 1/3 : barèmes + taux. Les taux de test sont arbitraires ; les valeurs Gabon 2026 chargées par
`seed_baremes_legaux_provisoires` sont PROVISOIRES (à confirmer par ETSL / le cabinet de paie).
"""

from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.management import call_command
from rest_framework import status

from users.models import User

from .models import BaremeCotisation, BaremeImpot, BulletinLigne, BulletinPaie, HistoriqueBareme, ParametrePaie, RubriquePaie
from .services import calculer_bulletin
from .tests import BASE, BaseRHTest, _auth


class M9Base(BaseRHTest):
    def setUp(self):
        super().setUp()
        self.sal = RubriquePaie.objects.create(code="SAL", label="Salaire", nature=RubriquePaie.Nature.GAIN)
        self.finance = User.objects.create_user(
            email="finance@etls.local", password="Etls#Demo2026", role=User.Role.FINANCE
        )
        self.logistique = User.objects.create_user(
            email="logistique@etls.local", password="Etls#Demo2026", role=User.Role.LOGISTIQUE
        )

    def bulletin(self, periode=date(2026, 3, 1)):
        b = BulletinPaie.objects.create(employe=self.employe, periode=periode, salaire_base=Decimal("1000000"))
        BulletinLigne.objects.create(bulletin=b, rubrique=self.sal, libelle="Salaire", montant=Decimal("1000000"))
        return b

    def bareme(self, taux="5", **kw):
        return BaremeCotisation.objects.create(
            code="T-S", label="Test", nature="salariale", taux=Decimal(taux), date_effet=kw.pop("date_effet", date(2026, 1, 1)), **kw
        )


class TauxProvisoiresTests(M9Base):
    def test_seed_charge_valeurs_provisoires_idempotent(self):
        call_command("seed_baremes_legaux_provisoires")
        call_command("seed_baremes_legaux_provisoires")
        n = BaremeCotisation.objects.count()
        self.assertGreaterEqual(n, 6)
        self.assertFalse(BaremeCotisation.objects.exclude(statut_valeur="provisoire").exists())
        self.assertFalse(BaremeCotisation.objects.filter(source="").exists())  # chaque valeur est sourcée
        cnss = BaremeCotisation.objects.get(code="CNSS-VIEIL-P")
        self.assertEqual((cnss.taux, cnss.plafond), (Decimal("11"), Decimal("1500000")))
        self.assertTrue(BaremeImpot.objects.get(code="IRPP").est_provisoire)
        self.assertEqual(ParametrePaie.objects.get(code="DUREE_LEGALE_HEBDO").valeur, Decimal("40"))

    def test_seed_ne_remplace_pas_une_valeur_confirmee(self):
        call_command("seed_baremes_legaux_provisoires")
        BaremeCotisation.objects.filter(code="CNSS-VIEIL-P").update(taux=Decimal("12"), statut_valeur="confirme")
        call_command("seed_baremes_legaux_provisoires")
        self.assertEqual(BaremeCotisation.objects.get(code="CNSS-VIEIL-P").taux, Decimal("12"))

    def test_bulletin_avertit_tant_qu_un_bareme_est_provisoire(self):
        self.bareme()
        b = calculer_bulletin(self.bulletin())
        _auth(self.client, "finance@etls.local")
        data = self.client.get(f"{BASE}bulletins/{b.pk}/").json()
        self.assertEqual(data["baremes_provisoires"], ["T-S"])
        self.assertIn("provisoires", data["avertissement"])
        self.assertIn("T-S", data["avertissement"])

    def test_avertissement_disparait_apres_confirmation_et_recalcul(self):
        bar = self.bareme()
        b = self.bulletin()
        _auth(self.client, "finance@etls.local")
        r = self.client.post(f"{BASE}baremes/{bar.pk}/confirmer/")
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.content)
        self.client.post(f"{BASE}bulletins/{b.pk}/calculer/")
        data = self.client.get(f"{BASE}bulletins/{b.pk}/").json()
        self.assertEqual(data["baremes_provisoires"], [])
        self.assertEqual(data["avertissement"], "")

    def test_le_salarie_voit_aussi_l_avertissement(self):
        self.bareme()
        b = calculer_bulletin(self.bulletin())
        BulletinPaie.objects.filter(pk=b.pk).update(statut="valide")
        _auth(self.client, "admin@etls.local")
        self.client.post(f"{BASE}bulletins/{b.pk}/diffuser/")
        from .models import Employe

        Employe.objects.filter(pk=self.employe.pk).update(user=self.ouvrier)
        _auth(self.client, self.ouvrier.email)
        data = self.client.get(f"{BASE}mon-espace/bulletins/{b.pk}/").json()
        self.assertIn("provisoires", data["avertissement"])


class ParametrageDroitsTests(M9Base):
    def test_confirmation_posee_cote_serveur_par_le_cercle_paie(self):
        bar = self.bareme()
        _auth(self.client, "finance@etls.local")
        r = self.client.post(f"{BASE}baremes/{bar.pk}/confirmer/", {"confirme_par": self.admin.pk}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        bar.refresh_from_db()
        self.assertEqual(bar.statut_valeur, "confirme")
        self.assertEqual(bar.confirme_par, self.finance)  # jamais le client
        self.assertIsNotNone(bar.confirme_le)

    def test_statut_non_modifiable_par_patch(self):
        bar = self.bareme()
        _auth(self.client, "finance@etls.local")
        self.client.patch(f"{BASE}baremes/{bar.pk}/", {"statut_valeur": "confirme"}, format="json")
        bar.refresh_from_db()
        self.assertEqual(bar.statut_valeur, "provisoire")

    def test_hors_cercle_paie_aucun_acces(self):
        bar = self.bareme()
        _auth(self.client, "logistique@etls.local")
        for url in ("baremes/", "baremes-impot/", "parametres-paie/", "historique-baremes/"):
            self.assertIn(self.client.get(f"{BASE}{url}").status_code, (401, 403), url)
        self.assertEqual(self.client.post(f"{BASE}baremes/{bar.pk}/confirmer/").status_code, 403)
        self.assertEqual(
            self.client.post(f"{BASE}parametres-paie/", {"code": "X", "label": "x", "valeur": "1", "date_effet": "2026-01-01"},
                             format="json").status_code, 403)

    def test_modifier_une_valeur_confirmee_la_repasse_en_provisoire(self):
        bar = self.bareme()
        _auth(self.client, "finance@etls.local")
        self.client.post(f"{BASE}baremes/{bar.pk}/confirmer/")
        r = self.client.patch(f"{BASE}baremes/{bar.pk}/", {"taux": "6"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        bar.refresh_from_db()
        self.assertEqual((bar.taux, bar.statut_valeur, bar.confirme_par), (Decimal("6"), "provisoire", None))

    def test_parametre_paie_cree_par_api(self):
        _auth(self.client, "rh@etls.local")
        r = self.client.post(
            f"{BASE}parametres-paie/",
            {"code": "SMIG", "label": "SMIG", "valeur": "80000", "unite": "FCFA", "date_effet": "2026-01-01",
             "source": "test"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["statut_valeur"], "provisoire")


class HistoriqueTests(M9Base):
    def test_creation_modification_confirmation_tracees(self):
        _auth(self.client, "finance@etls.local")
        r = self.client.post(
            f"{BASE}baremes/",
            {"code": "H1", "label": "H", "nature": "salariale", "base": "brut", "taux": "1", "date_effet": "2026-01-01"},
            format="json")
        pk = r.json()["id"]
        self.client.patch(f"{BASE}baremes/{pk}/", {"taux": "2"}, format="json")
        self.client.post(f"{BASE}baremes/{pk}/confirmer/")
        actions = list(HistoriqueBareme.objects.filter(code="H1").order_by("le").values_list("action", flat=True))
        self.assertEqual(actions, ["creation", "modification", "confirmation"])
        modif = HistoriqueBareme.objects.get(code="H1", action="modification")
        self.assertEqual(modif.avant["taux"], "1.000")
        self.assertEqual(modif.apres["taux"], "2.000")
        self.assertEqual(modif.par, self.finance)
        hist = self.client.get(f"{BASE}baremes/{pk}/historique/").json()
        self.assertEqual(len(hist), 3)

    def test_historique_inalterable(self):
        bar = self.bareme()
        from .services import tracer_changement

        h = tracer_changement(bar, "cotisation", "creation", self.admin)
        h.action = "autre"
        with self.assertRaises(ValidationError):
            h.save()
        with self.assertRaises(ValidationError):
            h.delete()
        _auth(self.client, "admin@etls.local")
        self.assertEqual(self.client.delete(f"{BASE}historique-baremes/{h.pk}/").status_code, 405)
        self.assertEqual(self.client.patch(f"{BASE}historique-baremes/{h.pk}/", {"code": "x"}, format="json").status_code, 405)


class VersionsEtRecalculTests(M9Base):
    def test_revision_conserve_l_ancien_bareme_pour_les_bulletins_passes(self):
        bar = self.bareme("5", plafond=None)
        _auth(self.client, "finance@etls.local")
        r = self.client.post(f"{BASE}baremes/{bar.pk}/reviser/", {"date_effet": "2026-07-01", "taux": "8"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["statut_valeur"], "provisoire")
        bar.refresh_from_db()
        self.assertEqual(bar.date_fin, date(2026, 6, 30))
        self.assertEqual(BaremeCotisation.objects.filter(code="T-S").count(), 2)
        mars = calculer_bulletin(self.bulletin(date(2026, 3, 1)))
        aout = calculer_bulletin(self.bulletin(date(2026, 8, 1)))
        self.assertEqual(mars.lignes.get(rubrique__code="COT-T-S").montant, Decimal("50000.00"))  # 5 %
        self.assertEqual(aout.lignes.get(rubrique__code="COT-T-S").montant, Decimal("80000.00"))  # 8 %
        self.assertEqual(mars.baremes_utilises[0]["taux"], "5.000")  # instantané rejouable

    def test_revision_date_anterieure_refusee(self):
        bar = self.bareme()
        _auth(self.client, "finance@etls.local")
        r = self.client.post(f"{BASE}baremes/{bar.pk}/reviser/", {"date_effet": "2025-01-01", "taux": "8"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_valeur_utilisee_par_un_bulletin_valide_ni_modifiable_ni_supprimable(self):
        bar = self.bareme()
        b = calculer_bulletin(self.bulletin())
        BulletinPaie.objects.filter(pk=b.pk).update(statut="valide")
        _auth(self.client, "finance@etls.local")
        self.assertEqual(self.client.patch(f"{BASE}baremes/{bar.pk}/", {"taux": "9"}, format="json").status_code, 400)
        self.assertEqual(self.client.delete(f"{BASE}baremes/{bar.pk}/").status_code, 400)
        bar.refresh_from_db()
        self.assertEqual(bar.taux, Decimal("5"))
        # une simple annotation (source) reste permise
        self.assertEqual(self.client.patch(f"{BASE}baremes/{bar.pk}/", {"source": "JO"}, format="json").status_code, 200)

    def test_bareme_impot_revisable(self):
        imp = BaremeImpot.objects.create(
            code="IR", label="IR", tranches=[{"plafond": 100000, "taux": 0}, {"plafond": None, "taux": 10}],
            date_effet=date(2026, 1, 1),
        )
        _auth(self.client, "finance@etls.local")
        r = self.client.post(
            f"{BASE}baremes-impot/{imp.pk}/reviser/",
            {"date_effet": "2027-01-01", "tranches": [{"plafond": None, "taux": 5}]}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(BaremeImpot.objects.filter(code="IR").count(), 2)
