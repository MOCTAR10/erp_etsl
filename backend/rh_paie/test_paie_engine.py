"""Moteur de paie (G-01) et écritures de paie (G-02) — barèmes versionnés, cotisations plafonnées,
comptabilisation dans le journal PAI via le noyau comptable.

Les taux utilisés ici sont des valeurs de test arbitraires, PAS les taux légaux gabonais.
"""

from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.management import call_command
from rest_framework import status

from accounting_kernel.models import AccountMove
from referentiels.models import Account

from .models import BaremeCotisation, BulletinLigne, BulletinPaie, RubriquePaie
from .services import calculer_bulletin, comptabiliser_bulletin
from .tests import BASE, BaseRHTest, _auth


class MoteurPaieBase(BaseRHTest):
    def setUp(self):
        super().setUp()
        self.salaire = RubriquePaie.objects.create(code="SAL", label="Salaire", nature=RubriquePaie.Nature.GAIN)
        self.prime = RubriquePaie.objects.create(code="PRI", label="Prime", nature=RubriquePaie.Nature.GAIN)
        self.avance = RubriquePaie.objects.create(code="AVA", label="Avance", nature=RubriquePaie.Nature.RETENUE)

    def bulletin(self, brut_lignes=(("SAL", "2000000"),), periode=date(2026, 3, 1)):
        b = BulletinPaie.objects.create(employe=self.employe, periode=periode, salaire_base=Decimal("2000000"))
        for code, montant in brut_lignes:
            BulletinLigne.objects.create(
                bulletin=b, rubrique=RubriquePaie.objects.get(code=code), libelle=code, montant=Decimal(montant)
            )
        return b

    def bareme(self, code, taux, nature=BaremeCotisation.Nature.SALARIALE, plafond=None, **kw):
        return BaremeCotisation.objects.create(
            code=code, label=code, nature=nature, taux=Decimal(taux), plafond=plafond,
            date_effet=kw.pop("date_effet", date(2026, 1, 1)), **kw,
        )


class CalculCotisationsTests(MoteurPaieBase):
    def test_cotisation_salariale_plafonnee_et_charge_patronale(self):
        self.bareme("SOC-S", "2.5", plafond=Decimal("1500000"))  # 2,5 % sur 1 500 000 = 37 500
        self.bareme("SOC-P", "10", nature=BaremeCotisation.Nature.PATRONALE)  # 10 % de 2 000 000
        b = calculer_bulletin(self.bulletin())
        self.assertEqual(b.brut, Decimal("2000000.00"))
        self.assertEqual(b.charges_patronales, Decimal("200000.00"))
        retenue = b.lignes.get(rubrique__code="COT-SOC-S")
        self.assertEqual(retenue.montant, Decimal("37500.00"))
        self.assertEqual(b.net, Decimal("1962500.00"))

    def test_recalcul_idempotent(self):
        self.bareme("SOC-S", "2.5")
        b = self.bulletin()
        calculer_bulletin(b)
        calculer_bulletin(b)
        b.refresh_from_db()
        self.assertEqual(b.lignes.filter(rubrique__code="COT-SOC-S").count(), 1)
        self.assertEqual(b.net, Decimal("1950000.00"))

    def test_retenues_manuelles_conservees(self):
        self.bareme("SOC-S", "2")
        b = calculer_bulletin(self.bulletin((("SAL", "1000000"), ("PRI", "100000"), ("AVA", "50000"))))
        # brut 1 100 000 ; cotisation 2 % = 22 000 ; avance 50 000
        self.assertEqual(b.brut, Decimal("1100000.00"))
        self.assertEqual(b.net, Decimal("1028000.00"))

    def test_bareme_versionne_par_date_d_effet(self):
        self.bareme("SOC-S", "2", date_effet=date(2026, 1, 1), date_fin=date(2026, 2, 28))
        self.bareme("SOC-S", "3", date_effet=date(2026, 3, 1))
        b = calculer_bulletin(self.bulletin(periode=date(2026, 3, 1)))
        self.assertEqual(b.lignes.get(rubrique__code="COT-SOC-S").montant, Decimal("60000.00"))
        b2 = calculer_bulletin(self.bulletin(periode=date(2026, 2, 1)))
        self.assertEqual(b2.lignes.get(rubrique__code="COT-SOC-S").montant, Decimal("40000.00"))

    def test_bareme_futur_ignore(self):
        self.bareme("SOC-S", "5", date_effet=date(2026, 6, 1))
        b = calculer_bulletin(self.bulletin(periode=date(2026, 3, 1)))
        self.assertFalse(b.lignes.filter(rubrique__code__startswith="COT-").exists())
        self.assertEqual(b.net, b.brut)

    def test_bulletin_valide_non_recalculable(self):
        b = self.bulletin()
        b.statut = BulletinPaie.Statut.VALIDE
        b.save()
        with self.assertRaises(ValidationError):
            calculer_bulletin(b)

    def test_action_calculer_api(self):
        self.bareme("SOC-S", "2.5", plafond=Decimal("1500000"))
        b = self.bulletin()
        _auth(self.client, "admin@etls.local")
        r = self.client.post(f"{BASE}bulletins/{b.pk}/calculer/")
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.content)
        self.assertEqual(Decimal(r.data["net"]), Decimal("1962500.00"))


class EcrituresPaieTests(MoteurPaieBase):
    def setUp(self):
        super().setUp()
        call_command("seed_accounting", year=2026)
        for code, cls, atype, label in (
            ("661000", 6, Account.AccountType.EXPENSE, "Charges de personnel"),
            ("664000", 6, Account.AccountType.EXPENSE, "Charges sociales"),
            ("421000", 4, Account.AccountType.LIABILITY, "Personnel"),
            ("431000", 4, Account.AccountType.LIABILITY, "Organismes sociaux"),
        ):
            Account.objects.get_or_create(
                code=code, defaults=dict(label=label, account_class=cls, account_type=atype)
            )
        self.bareme("SOC-S", "2.5", plafond=Decimal("1500000"))
        self.bareme("SOC-P", "10", nature=BaremeCotisation.Nature.PATRONALE)
        self.b = calculer_bulletin(self.bulletin())
        self.b.statut = BulletinPaie.Statut.VALIDE
        self.b.save()

    def test_ecriture_equilibree_dans_le_journal_de_paie(self):
        move = comptabiliser_bulletin(self.b, user=self.admin)
        self.assertEqual(move.journal.code, "PAI")
        self.assertEqual(move.status, AccountMove.Status.POSTED)
        self.assertEqual(move.total_debit, move.total_credit)
        by_acc = {}
        for ln in move.lines.select_related("account"):
            by_acc[ln.account.code] = ln.debit - ln.credit
        self.assertEqual(by_acc["661000"], Decimal("2000000"))      # brut
        self.assertEqual(by_acc["664000"], Decimal("200000"))       # charges patronales
        self.assertEqual(by_acc["421000"], Decimal("-1962500"))     # net à payer
        self.assertEqual(by_acc["431000"], Decimal("-237500"))      # 37 500 + 200 000
        self.b.refresh_from_db()
        self.assertEqual(self.b.move_id, move.pk)

    def test_double_comptabilisation_refusee(self):
        comptabiliser_bulletin(self.b, user=self.admin)
        with self.assertRaises(ValidationError):
            comptabiliser_bulletin(self.b, user=self.admin)
        self.assertEqual(AccountMove.objects.filter(source_ref=self.b.code).count(), 1)

    def test_bulletin_brouillon_non_comptabilisable(self):
        b = self.bulletin(periode=date(2026, 4, 1))
        with self.assertRaises(ValidationError):
            comptabiliser_bulletin(b, user=self.admin)

    def test_compte_absent_erreur_metier(self):
        Account.objects.filter(code="664000").delete()
        with self.assertRaises(ValidationError):
            comptabiliser_bulletin(self.b, user=self.admin)
        self.assertEqual(AccountMove.objects.count(), 0)

    def test_api_comptabiliser_reserve_au_cercle_comptable(self):
        _auth(self.client, "rh@etls.local")
        r = self.client.post(f"{BASE}bulletins/{self.b.pk}/comptabiliser/")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN, r.content)
        _auth(self.client, "admin@etls.local")
        r = self.client.post(f"{BASE}bulletins/{self.b.pk}/comptabiliser/")
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.content)
        self.assertTrue(r.data["move_number"])
