"""Écarts M9-B : comptes de paie par organisme, ventilation analytique par affaire, provision des congés payés,
coût de main-d'œuvre chargé retourné à M3, heures de nuit / d'astreinte valorisées."""

from datetime import date
from decimal import Decimal

from django.core.management import call_command

from commercial.models import Affaire
from operations.cloture import transferer_paie
from operations.models import OrdreFabrication, PointageChantier
from referentiels.models import Account

from .models import (
    BaremeCotisation, BaremeImpot, BulletinPaie, ComptePaie, ContratTravail, ParametrePaie, ProvisionConges,
    SaisieTemps,
)
from .paie_m9a import preparer_bulletin
from .services import comptabiliser_bulletin
from .tests import BASE, BaseRHTest, _auth

MOIS = date(2026, 3, 1)


def _compte(code, cls=4, atype=Account.AccountType.LIABILITY, label=""):
    return Account.objects.get_or_create(code=code, defaults=dict(label=label or code, account_class=cls, account_type=atype))[0]


class M9bBase(BaseRHTest):
    def setUp(self):
        super().setUp()
        call_command("seed_accounting", year=2026)
        _compte("661000", 6, Account.AccountType.EXPENSE)
        _compte("664000", 6, Account.AccountType.EXPENSE)
        _compte("421000")
        _compte("431000")
        self.contrat = ContratTravail.objects.create(
            employe=self.employe, type=ContratTravail.Type.CDI, date_debut=date(2025, 1, 1), salaire_base=Decimal("400000"),
        )
        self.employe.user = self.ouvrier
        self.employe.save()
        BaremeCotisation.objects.create(code="CNSS-S", label="CNSS", organisme="CNSS", nature="salariale", taux=Decimal("5"), date_effet=date(2020, 1, 1))
        BaremeCotisation.objects.create(code="CNSS-P", label="CNSS", organisme="CNSS", nature="patronale", taux=Decimal("10"), date_effet=date(2020, 1, 1))
        BaremeCotisation.objects.create(code="CNAMGS-P", label="CNAMGS", organisme="CNAMGS", nature="patronale", taux=Decimal("5"), date_effet=date(2020, 1, 1))
        BaremeImpot.objects.create(code="IRPP", label="IRPP", tranches=[{"plafond": None, "taux": 10}], date_effet=date(2020, 1, 1))

    def param(self, code, valeur):
        ParametrePaie.objects.create(code=code, label=code, valeur=Decimal(valeur), date_effet=date(2020, 1, 1))

    def bulletin_valide(self):
        b = BulletinPaie.objects.create(employe=self.employe, periode=MOIS)
        preparer_bulletin(b)
        BulletinPaie.objects.filter(pk=b.pk).update(statut="valide")
        return BulletinPaie.objects.get(pk=b.pk)

    def pointer(self, of, jour, heures, type_="normal"):
        p = PointageChantier.objects.create(ordre=of, worker=self.ouvrier, date=jour, hours=Decimal(heures), hours_type=type_, status="valide")
        return transferer_paie(p)


class EcriturePaieTests(M9bBase):
    def test_comptes_par_organisme_et_impot(self):
        cnss, cnamgs, etat = _compte("431100"), _compte("431200"), _compte("447000")
        ComptePaie.objects.create(role="organismes", organisme="CNSS", compte=cnss)
        ComptePaie.objects.create(role="organismes", organisme="CNAMGS", compte=cnamgs)
        ComptePaie.objects.create(role="impot", compte=etat)
        move = comptabiliser_bulletin(self.bulletin_valide(), user=self.admin)
        solde = {}
        for l in move.lines.select_related("account"):
            solde[l.account.code] = solde.get(l.account.code, 0) + l.debit - l.credit
        # brut 400 000 ; CNSS 5 % + 10 % = 60 000 ; CNAMGS 5 % = 20 000 ; IRPP 10 % de 380 000 = 38 000
        self.assertEqual(solde["431100"], Decimal("-60000"))
        self.assertEqual(solde["431200"], Decimal("-20000"))
        self.assertEqual(solde["447000"], Decimal("-38000"))
        self.assertEqual(solde["421000"], Decimal("-342000"))
        self.assertNotIn("431000", solde)
        self.assertEqual(move.total_debit, move.total_credit)

    def test_ventilation_analytique_par_affaire_au_prorata_des_heures(self):
        a1, a2 = Affaire.objects.create(title="Pipeline A"), Affaire.objects.create(title="Pipeline B")
        of1 = OrdreFabrication.objects.create(label="OF A", affaire=a1)
        of2 = OrdreFabrication.objects.create(label="OF B", affaire=a2)
        self.pointer(of1, date(2026, 3, 2), "30")
        self.pointer(of2, date(2026, 3, 3), "10")
        SaisieTemps.objects.create(employe=self.employe, date=date(2026, 3, 4), heures=Decimal("40"))  # hors affaire
        move = comptabiliser_bulletin(self.bulletin_valide(), user=self.admin)
        brut = {(l.analytic_account.code if l.analytic_account_id else None): l.debit
                for l in move.lines.filter(account__code="661000").select_related("analytic_account")}
        self.assertEqual(brut, {a1.code: Decimal("150000"), a2.code: Decimal("50000"), None: Decimal("200000")})
        self.assertEqual(move.total_debit, move.total_credit)


class ProvisionCongesTests(M9bBase):
    def test_provision_mensuelle_unique_et_compte_dette_exige(self):
        self.param("PROVISION_CP_TAUX", "8.333")
        self.bulletin_valide()
        _auth(self.client, "admin@etls.local")
        r = self.client.post(f"{BASE}provisions-conges/", {"periode": "2026-03-01"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("non paramétré", str(r.json()))
        ComptePaie.objects.create(role="provision_dette", compte=_compte("428200"))
        r = self.client.post(f"{BASE}provisions-conges/", {"periode": "2026-03-01"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Decimal(r.json()["montant"]), Decimal("33332.00"))
        self.assertTrue(r.json()["move_number"])
        self.assertEqual(self.client.post(f"{BASE}provisions-conges/", {"periode": "2026-03-01"}, format="json").status_code, 400)
        self.assertEqual(ProvisionConges.objects.count(), 1)
        _auth(self.client, "rh@etls.local")  # cercle paie sans droit d'écriture comptable
        self.assertEqual(self.client.post(f"{BASE}provisions-conges/", {"periode": "2026-04-01"}, format="json").status_code, 403)


class CoutMainOeuvreTests(M9bBase):
    def test_pointage_transfere_valorise_et_agrege_par_of(self):
        self.param("DUREE_LEGALE_HEBDO", "40")
        of = OrdreFabrication.objects.create(label="OF chantier", affaire=Affaire.objects.create(title="Gamba"))
        saisie = self.pointer(of, date(2026, 3, 2), "8")
        # 400 000 × 1,15 ÷ (40 × 52 ÷ 12 = 173,33 h) = 2 653,85 F/h ; 8 h = 21 230,80
        self.assertEqual(saisie.cout_charge, Decimal("21230.80"))
        _auth(self.client, "admin@etls.local")
        r = self.client.get(f"{BASE}cout-main-oeuvre/?debut=2026-03-01&fin=2026-03-31")
        self.assertEqual(r.status_code, 200)
        ligne = r.json()[0]
        self.assertEqual((ligne["ordre_code"], Decimal(ligne["cout"]), Decimal(ligne["heures"])), (of.code, Decimal("21230.80"), Decimal("8")))
        _auth(self.client, "ouvrier@etls.local")  # chef d'atelier : hors cercle des montants
        self.assertEqual(self.client.get(f"{BASE}cout-main-oeuvre/").status_code, 403)

    def test_sans_duree_legale_non_valorise(self):
        of = OrdreFabrication.objects.create(label="OF")
        self.assertIsNone(self.pointer(of, date(2026, 3, 2), "8").cout_charge)


class NuitAstreinteTests(M9bBase):
    def test_nuit_et_astreinte_valorisees_si_parametrees(self):
        for code, v in (("DUREE_LEGALE_HEBDO", "40"), ("HS_MAJ_1", "25"), ("HS_MAJ_2", "50"), ("HS_SEUIL_2", "48"), ("MAJ_NUIT", "30")):
            self.param(code, v)
        SaisieTemps.objects.create(employe=self.employe, date=date(2026, 3, 2), heures=Decimal("10"), type="nuit")
        SaisieTemps.objects.create(employe=self.employe, date=date(2026, 3, 3), heures=Decimal("5"), type="astreinte")
        b = BulletinPaie.objects.create(employe=self.employe, periode=MOIS)
        preparer_bulletin(b)
        codes = {l.rubrique.code: l.montant for l in b.lignes.select_related("rubrique")}
        self.assertEqual(codes["NUIT-TEMPS"], Decimal("6923.07"))  # 10 h × 2 307,69 × 30 %
        self.assertNotIn("ASTR-TEMPS", codes)  # taux d'astreinte non paramétré : ignorée
        self.assertIn("MAJ_NUIT", [s["code"] for s in BulletinPaie.objects.get(pk=b.pk).baremes_utilises])
