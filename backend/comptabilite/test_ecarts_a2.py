"""Recette du lot a2 : multi-devises (EX-G-04), reconnaissance du revenu à l'avancement (M10 → M11 / M1),
export des écritures vers SAGE (interface transitoire), raison sociale de l'en-tête de facture."""

import csv
import io
from datetime import date
from decimal import Decimal

from django.db.models import Sum

from accounting_kernel.models import AccountMove, AccountMoveLine
from commercial.models import Affaire, ClientProfile, Contract
from referentiels.models import Account, AnalyticAccount, AnalyticAxis, Currency, Partner, TauxChange

from .models import FactureClient, OperationDevise, ParametreCompta, ReconnaissanceRevenu
from .test_ecarts_m10 import EcartsBase
from .tests import BASE

TAUX = f"{BASE}taux-change/"
OPS = f"{BASE}operations-devise/"
RAV = f"{BASE}reconnaissances-revenu/"


def solde(code, partner=None):
    qs = AccountMoveLine.objects.filter(account__code=code, move__status__in=("posted", "reversed"))
    if partner is not None:
        qs = qs.filter(partner=partner)
    agg = qs.aggregate(d=Sum("debit"), c=Sum("credit"))
    return (agg["d"] or Decimal("0")) - (agg["c"] or Decimal("0"))


class A2Base(EcartsBase):
    def setUp(self):
        super().setUp()
        for code, label, sym, dec in (("XAF", "Franc CFA", "FCFA", 0), ("EUR", "Euro", "€", 2), ("USD", "Dollar", "$", 2)):
            Currency.objects.get_or_create(code=code, defaults=dict(label=label, symbol=sym, decimals=dec))
        self.fournisseur = Partner.objects.create(code="FRS-US", name="SUPPLIER INC", kind=Partner.Kind.FOURNISSEUR)

    def taux(self, devise, jour, taux):
        r = self.client.post(TAUX, {"devise": devise, "date": jour, "taux": taux}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()


class TauxChangeTests(A2Base):
    def test_saisie_maj_provisoire_confirmation_puis_verrou(self):
        self.taux("EUR", "2026-03-01", "655,957")
        self.taux("EUR", "2026-03-01", "655.957")  # provisoire : mis à jour, pas de doublon
        self.assertEqual(TauxChange.objects.count(), 1)
        t = TauxChange.objects.get()
        self.assertTrue(t.est_provisoire)
        self.assertEqual(self.client.post(f"{TAUX}{t.pk}/confirmer/").status_code, 200)
        r = self.client.post(TAUX, {"devise": "EUR", "date": "2026-03-01", "taux": "700"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.post(TAUX, {"devise": "XAF", "date": "2026-03-01", "taux": "1"}, format="json").status_code, 400)
        self.assertEqual(self.client.post(TAUX, {"devise": "EUR", "date": "2026-03-02", "taux": "-1"}, format="json").status_code, 400)

    def test_import_csv_idempotent_et_erreurs_par_ligne(self):
        contenu = "date;devise;taux\n2026-03-01;USD;600\n2026-03-02;USD;602,5\n2026-03-03;GBP;800\nmauvaise\n"
        r = self.client.post(f"{TAUX}importer/", {"contenu": contenu}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.json()["crees"], len(r.json()["erreurs"])), (2, 2))
        r = self.client.post(f"{TAUX}importer/", {"contenu": contenu}, format="json")
        self.assertEqual((r.json()["crees"], r.json()["mis_a_jour"]), (0, 2))
        self.assertEqual(TauxChange.objects.get(devise__code="USD", date=date(2026, 3, 2)).taux, Decimal("602.5"))
        sit = self.client.get(f"{TAUX}situation/").json()
        self.assertTrue(sit["provisoire"])
        self.assertIn("USD", [d["devise"] for d in sit["devises"]])

    def test_conversion_cours_du_jour_et_cours_trop_ancien(self):
        self.taux("USD", "2026-03-01", "600")
        r = self.client.get(f"{TAUX}convertir/?devise=USD&montant=12.50&date=2026-03-10")
        self.assertEqual(r.json()["contre_valeur"], "7500")
        r = self.client.get(f"{TAUX}convertir/?devise=USD&montant=1&date=2026-05-10")  # > 31 jours
        self.assertEqual(r.status_code, 400)
        ParametreCompta.objects.filter(code="DEVISE_ANCIENNETE_MAX_JOURS").update(valeur=0)
        self.assertEqual(self.client.get(f"{TAUX}convertir/?devise=USD&montant=1&date=2026-05-10").status_code, 200)


class OperationDeviseTests(A2Base):
    def creer(self, sens, partner, devise, montant, compte, jour="2026-03-05"):
        r = self.client.post(OPS, {
            "sens": sens, "partner": partner.pk, "devise": Currency.objects.get(code=devise).pk, "date": jour,
            "libelle": "Prestation export", "montant_devise": montant, "compte_contrepartie": self.a(compte).pk,
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()

    def test_creance_eur_comptabilisee_puis_reglee_gain_de_change_766(self):
        self.taux("EUR", "2026-03-01", "655.957")
        op = self.creer("creance", self.client_p, "EUR", "1000", "706000")
        self.assertEqual(op["contre_valeur"], "655957.00")
        self.assertTrue(op["taux_provisoire"])
        r = self.client.post(f"{OPS}{op['id']}/comptabiliser/")
        self.assertEqual(r.status_code, 200, r.content)
        ligne = AccountMoveLine.objects.get(move__number=r.json()["move_number"], account__code="411000")
        self.assertEqual((ligne.currency.code, ligne.amount_currency, ligne.debit), ("EUR", Decimal("1000"), Decimal("655957")))
        self.taux("EUR", "2026-03-20", "660")
        r = self.client.post(f"{OPS}{op['id']}/regler/", {"date": "2026-03-25"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["ecart_change"], "4043.00")
        self.assertEqual(solde("411000", self.client_p), 0)
        self.assertEqual(solde("766000"), Decimal("-4043"))
        self.assertEqual(self.client.post(f"{OPS}{op['id']}/regler/", {"date": "2026-03-26"}, format="json").status_code, 400)
        self.assertEqual(self.client.delete(f"{OPS}{op['id']}/").status_code, 400)

    def test_dette_usd_reevaluation_478_479_extournee_puis_perte_666(self):
        self.taux("USD", "2026-03-01", "600")
        op = self.creer("dette", self.fournisseur, "USD", "1000", "601000")
        self.client.post(f"{OPS}{op['id']}/comptabiliser/")
        self.assertEqual(solde("401000", self.fournisseur), Decimal("-600000"))
        self.taux("USD", "2026-03-31", "610")
        r = self.client.post(f"{OPS}{op['id']}/reevaluer/", {"date": "2026-03-31"}, format="json")
        self.assertEqual(r.json()["ecart_latent"], "-10000.00")
        self.assertEqual((solde("478000"), solde("401000", self.fournisseur)), (Decimal("10000"), Decimal("-610000")))
        self.taux("USD", "2026-04-15", "590")
        self.client.post(f"{OPS}{op['id']}/reevaluer/", {"date": "2026-04-15"}, format="json")
        self.assertEqual((solde("478000"), solde("479000")), (Decimal("0"), Decimal("-10000")))
        self.taux("USD", "2026-04-20", "605")
        r = self.client.post(f"{OPS}{op['id']}/regler/", {"date": "2026-04-20"}, format="json")
        self.assertEqual(r.json()["ecart_change"], "-5000.00")
        self.assertEqual((solde("401000", self.fournisseur), solde("479000"), solde("666000")), (0, 0, Decimal("5000")))

    def test_sans_cours_refus_et_compte_incoherent(self):
        r = self.client.post(OPS, {
            "sens": "creance", "partner": self.client_p.pk, "devise": Currency.objects.get(code="USD").pk,
            "date": "2026-03-05", "libelle": "x", "montant_devise": "10", "compte_contrepartie": self.a("706000").pk,
        }, format="json")
        self.assertEqual(r.status_code, 400)
        self.taux("USD", "2026-03-01", "600")
        r = self.client.post(OPS, {
            "sens": "creance", "partner": self.client_p.pk, "devise": Currency.objects.get(code="USD").pk,
            "date": "2026-03-05", "libelle": "x", "montant_devise": "10", "compte_contrepartie": self.a("601000").pk,
        }, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("compte_contrepartie", r.json())

    def test_montants_masques_hors_cercle(self):
        from users.models import User

        self.taux("USD", "2026-03-01", "600")
        self.creer("creance", self.client_p, "USD", "10", "706000")
        User.objects.create_user(email="dp@etls.local", password="Etls#Demo2026", role=User.Role.DIRECTEUR_PROJETS)
        from .tests import _auth

        _auth(self.client, "dp@etls.local")
        row = self.client.get(OPS).json()["results"][0]
        self.assertIsNone(row["contre_valeur"])
        self.assertEqual(self.client.post(TAUX, {"devise": "USD", "date": "2026-03-02", "taux": "1"}, format="json").status_code, 403)


class ReconnaissanceRevenuTests(A2Base):
    def setUp(self):
        super().setUp()
        profil = ClientProfile.objects.create(partner=self.client_p)
        axe = AnalyticAxis.objects.create(code="PRJ-A2", label="Projets", axis_type=AnalyticAxis.AxisType.PROJET)
        self.analytic = AnalyticAccount.objects.create(axis=axe, code="AFF-A2", label="Affaire A2")
        self.affaire = Affaire.objects.create(code="AFF-A2", client=profil, title="EPC A2", status=Affaire.Status.EN_COURS,
                                              contract_amount=Decimal("8000000"))
        Affaire.objects.filter(pk=self.affaire.pk).update(analytic=self.analytic)
        self.affaire.refresh_from_db()
        Contract.objects.create(code="CTR-A2", client=profil, affaire=self.affaire, profile="marche_travaux",
                                start_date=date(2026, 1, 1), amount_initial=Decimal("10000000"), status=Contract.Status.ACTIF)

    def situation(self, pct, fin):
        from operations.models import SituationTravaux

        return SituationTravaux.objects.create(affaire=self.affaire, label=f"S {pct}", period_start=date(2026, 1, 1),
                                               period_end=fin, progress=pct, status=SituationTravaux.Status.VALIDEE)

    def facture(self, ht, jour):
        return FactureClient.objects.create(client=self.client_p, affaire=self.affaire, date=jour, montant_ht=Decimal(ht),
                                            statut=FactureClient.Statut.EMISE)

    def test_produits_a_recevoir_puis_constates_d_avance_avec_extourne(self):
        self.situation(40, date(2026, 3, 31))
        self.facture("3000000", date(2026, 3, 15))
        ap = self.client.get(f"{RAV}apercu/?date=2026-03-31").json()
        row = next(r for r in ap["rows"] if r["affaire_code"] == "AFF-A2")
        self.assertEqual((row["revenu_cumule"], row["ecart"], row["nature"]), ("4000000", "1000000.00", "produits_a_recevoir"))
        self.assertTrue(ap["provisoire"])
        r = self.client.post(RAV, {"affaire": str(self.affaire.pk), "date_arrete": "2026-03-31"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual((solde("418100"), solde("706000")), (Decimal("1000000"), Decimal("-1000000")))
        self.assertEqual(AccountMoveLine.objects.get(account__code="706000").analytic_account, self.analytic)
        # Avril : 50 % mais 6 M facturés → PCA 1 M, la PAR de mars est extournée.
        self.situation(50, date(2026, 4, 30))
        self.facture("3000000", date(2026, 4, 10))
        r = self.client.post(RAV, {"affaire": str(self.affaire.pk), "date_arrete": "2026-04-30"}, format="json")
        self.assertEqual(r.json()["ecart"], "-1000000.00")
        self.assertEqual((solde("418100"), solde("477000"), solde("706000")), (0, Decimal("-1000000"), Decimal("1000000")))
        self.assertEqual(ReconnaissanceRevenu.objects.filter(statut="en_vigueur").count(), 1)
        # Une date antérieure à la position en vigueur est refusée.
        r = self.client.post(RAV, {"affaire": str(self.affaire.pk), "date_arrete": "2026-03-31"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_methode_couts_engages_sur_budget_m11(self):
        from accounting_kernel.models import FiscalYear
        from controle_gestion.models import Budget

        ParametreCompta.objects.update_or_create(code="REVENU_METHODE", defaults={"label": "m", "valeur": 1})
        self.assertEqual(self.client.post(RAV, {"affaire": str(self.affaire.pk), "date_arrete": "2026-03-31"},
                                          format="json").status_code, 400)  # sans budget
        Budget.objects.create(code="BUD-A2", label="Budget A2", type_budget="charge", fiscal_year=FiscalYear.objects.get(year=2026),
                              analytic=self.analytic, montant=Decimal("5000000"), statut="approuve")
        m = self.ecriture([("601000", "1500000", "0", None), ("512000", "0", "1500000", None)])
        AccountMoveLine.objects.filter(move=m, account__code="601000").update(analytic_account=self.analytic)
        r = self.client.post(RAV, {"affaire": str(self.affaire.pk), "date_arrete": "2026-03-31"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual((r.json()["pct_avancement"], r.json()["revenu_cumule"]), ("30.00", "3000000.00"))


class ExportSageTests(A2Base):
    URL = "/api/integrations/exports-sage/"

    def test_export_des_ecritures_au_gabarit_puis_pas_de_reexport(self):
        self.jeu()
        r = self.client.post(self.URL, {"date_from": "2026-01-01", "date_to": "2026-12-31"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        exp = r.json()
        self.assertEqual((exp["nb_ecritures"], exp["nb_lignes"]), (3, 7))
        self.assertEqual(exp["total_debit"], exp["total_credit"])
        self.assertTrue(exp["gabarit_provisoire"])
        fichier = self.client.get(f"{self.URL}{exp['id']}/telecharger/")
        self.assertEqual(fichier.status_code, 200)
        rows = list(csv.reader(io.StringIO(fichier.content.decode("cp1252")), delimiter=";"))
        self.assertEqual(rows[0][:4], ["Code journal", "Date", "N° pièce", "N° compte général"])
        vente = next(r for r in rows[1:] if r[3] == "411000")
        self.assertEqual((vente[1], vente[5], vente[8]), ("10/03/2026", "590000,00", "CLI-1"))
        r = self.client.post(self.URL, {"date_from": "2026-01-01", "date_to": "2026-12-31"}, format="json")
        self.assertEqual(r.status_code, 400)  # tout est déjà exporté
        r = self.client.post(self.URL, {"date_from": "2026-01-01", "date_to": "2026-12-31", "journal": "OD",
                                        "seulement_nouvelles": "false"}, format="json")
        self.assertEqual(r.json()["nb_ecritures"], 3)
        codes = [g["code"] for g in self.client.get("/api/integrations/gabarits/").json()["results"]]
        self.assertIn("SAGE_EXPORT", codes)

    def test_reservee_au_cercle_comptable(self):
        from .tests import _auth

        _auth(self.client, "logi@etls.local")
        self.assertEqual(self.client.post(self.URL, {"date_from": "2026-01-01"}, format="json").status_code, 403)


class EnteteFactureTests(A2Base):
    def test_raison_sociale_etsl_dans_le_modele_par_defaut(self):
        from .facturation import get_modele

        entete = get_modele().entete
        self.assertIn("Entreprise de Tuyauterie, Soudure et Location", entete)
        self.assertNotIn("Services Logistiques", entete)
        self.assertTrue(Account.objects.filter(code="706000").exists())
        self.assertFalse(AccountMove.objects.exists())
