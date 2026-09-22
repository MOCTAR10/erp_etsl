"""Tests M10 — Module Comptabilité & Trésorerie (RF-ERP-90…94)."""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APITestCase

from accounting_kernel.models import AccountMove, Journal, Period
from referentiels.models import Account, Partner
from users.models import User

from .models import (
    ComptabiliteSequence,
    CompteBancaire,
    ControleInterne,
    DeclarationTva,
    Engagement,
    LigneReleve,
    Paiement,
    RapprochementBancaire,
    ReleveBancaire,
    TauxTva,
)
from .services import build_paiement_move, compute_declaration_tva

User = get_user_model()

BASE = "/api/comptabilite/"


def _auth(client, email):
    r = client.post(
        "/api/users/token/", {"email": email, "password": "Etls#Demo2026"}, format="json"
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")


class BaseComptaTest(APITestCase):
    def setUp(self):
        call_command("seed_accounting", year=2026)
        self.admin = User.objects.create_user(
            email="admin@etls.local", password="Etls#Demo2026",
            role=User.Role.ADMIN, first_name="Admin", is_staff=True,
        )
        self.finance = User.objects.create_user(
            email="finance@etls.local", password="Etls#Demo2026",
            role=User.Role.FINANCE, first_name="Finance",
        )
        self.comptable = User.objects.create_user(
            email="compta@etls.local", password="Etls#Demo2026",
            role=User.Role.COMPTABLE, first_name="Compta",
        )
        self.logistique = User.objects.create_user(
            email="logi@etls.local", password="Etls#Demo2026",
            role=User.Role.LOGISTIQUE, first_name="Logi",
        )
        self._make_accounts()

    def _make_accounts(self):
        accounts = {
            "512000": (5, Account.AccountType.ASSET, "Banques", True),
            "401000": (4, Account.AccountType.LIABILITY, "Fournisseurs", True),
            "401100": (4, Account.AccountType.LIABILITY, "Fournisseurs GR", True),
            "411000": (4, Account.AccountType.ASSET, "Clients", True),
            "601000": (6, Account.AccountType.EXPENSE, "Achats", False),
            "618000": (6, Account.AccountType.EXPENSE, "Refacturations GR", False),
            "443000": (4, Account.AccountType.LIABILITY, "TVA collectee", True),
            "445000": (4, Account.AccountType.ASSET, "TVA deductible", True),
        }
        for code, (cls, atype, label, reconcile) in accounts.items():
            Account.objects.get_or_create(
                code=code,
                defaults=dict(
                    label=label, account_class=cls, account_type=atype, reconcile=reconcile
                ),
            )

    @property
    def banque_account(self):
        return Account.objects.get(code="512000")

    def _banque(self, label="BGFI"):
        return CompteBancaire.objects.create(
            label=label, banque="BGFI", compte_comptable=self.banque_account,
            solde_initial=Decimal("10000000"),
        )

    def _fournisseur(self, gr=False, code_suffix=""):
        return Partner.objects.create(
            code=f"F-SUP-{code_suffix or 'X'}", name="SUPPLIER",
            kind=Partner.Kind.FOURNISSEUR, is_global_rental=gr,
        )

    def _taux_tva(self):
        return TauxTva.objects.create(
            code="TVA18", label="TVA 18", taux=Decimal("18.00"),
            compte_collecte=Account.objects.get(code="443000"),
            compte_deductible=Account.objects.get(code="445000"),
            is_default=True,
        )

    def _engagement(self, statut=Engagement.Statut.BROUILLON):
        return Engagement.objects.create(
            objet="Dépense carburant", montant=Decimal("250000"),
            compte_depense=Account.objects.get(code="601000"),
            statut=statut, date_engagement=date(2026, 1, 10),
        )

    def _paiement(self, sens="sortie", montant="250000.00", mode="virement", **kw):
        return Paiement.objects.create(
            sens=sens, mode=mode, montant=Decimal(montant),
            date=kw.pop("date", date(2026, 1, 15)),
            compte_bancaire=kw.pop("compte_bancaire", self._banque()),
            **kw,
        )


class SequenceTests(BaseComptaTest):
    def test_sequences_next_for(self):
        n1 = ComptabiliteSequence.next_for("PAI", "PAI")
        self.assertTrue(n1.startswith("PAI"))
        n2 = ComptabiliteSequence.next_for("PAI", "PAI")
        self.assertNotEqual(n1, n2)


class ComptesBancairesTests(BaseComptaTest):
    def test_creation_auto_code(self):
        bq = self._banque()
        self.assertTrue(bq.code.startswith("BQ"))
        self.assertTrue(bq.compte_comptable.code, "512000")

    def test_lecture_authentifiee(self):
        self._banque()
        _auth(self.client, "logi@etls.local")
        r = self.client.get(f"{BASE}comptes-bancaires/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(r.data["results"]), 1)

    def test_non_authentifie_403(self):
        r = self.client.get(f"{BASE}comptes-bancaires/")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_ecriture_finance_ok(self):
        _auth(self.client, "finance@etls.local")
        r = self.client.post(
            f"{BASE}comptes-bancaires/",
            {
                "label": "UBA expl", "banque": "UBA", "numero": "UBA-1",
                "compte_comptable": self.banque_account.pk,
                "solde_initial": "500000",
            },
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertTrue(r.json()["code"].startswith("BQ"))

    def test_ecriture_logistique_interdite(self):
        _auth(self.client, "logi@etls.local")
        r = self.client.post(
            f"{BASE}comptes-bancaires/",
            {"label": "X", "banque": "B", "compte_comptable": self.banque_account.pk},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)


class TauxTvaTests(BaseComptaTest):
    def test_creation_par_finance_ok(self):
        _auth(self.client, "finance@etls.local")
        r = self.client.post(
            f"{BASE}taux-tva/",
            {"code": "TVA10", "label": "TVA 10", "taux": "10.00"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)

    def test_creation_par_admin_ok(self):
        _auth(self.client, "admin@etls.local")
        r = self.client.post(
            f"{BASE}taux-tva/", {"code": "TVA5", "label": "TVA 5", "taux": "5.00"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)

    def test_modification_taux_par_rh_interdite(self):
        taux = self._taux_tva()
        _auth(self.client, "logi@etls.local")
        r = self.client.post(
            f"{BASE}taux-tva/", {"code": "TVA18", "label": "X", "taux": "5.00"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)
        taux.refresh_from_db()
        self.assertEqual(taux.taux, Decimal("18.00"))


class ReleveBancaireTests(BaseComptaTest):
    def test_releve_avec_lignes(self):
        _auth(self.client, "compta@etls.local")
        bq = self._banque()
        r = self.client.post(
            f"{BASE}releves/",
            {
                "compte_bancaire": bq.pk, "date_debut": "2026-01-01",
                "date_fin": "2026-01-31", "solde_initial": "1000000",
                "solde_final": "950000", "source": "cfonb",
            },
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertTrue(r.json()["code"].startswith("REL"))
        releve_pk = r.json()["id"]

        r2 = self.client.post(
            f"{BASE}releves/{releve_pk}/lignes/",
            {
                "lignes": [
                    {"date": "2026-01-05", "libelle": "Virement client", "credit": "200000"},
                    {"date": "2026-01-20", "libelle": "Paiement fournisseur", "debit": "250000"},
                ]
            },
            format="json",
        )
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(r2.json()), 2)

        r3 = self.client.post(f"{BASE}releves/{releve_pk}/valider/")
        self.assertEqual(r3.status_code, status.HTTP_200_OK)
        self.assertEqual(r3.json()["statut"], "valide")

    def test_validation_sans_lignes_refusee(self):
        _auth(self.client, "compta@etls.local")
        bq = self._banque()
        releve = ReleveBancaire.objects.create(
            compte_bancaire=bq, date_debut=date(2026, 1, 1), date_fin=date(2026, 1, 31),
        )
        r = self.client.post(f"{BASE}releves/{releve.pk}/valider/")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


class RapprochementTests(BaseComptaTest):
    def test_rapprochement_lignes(self):
        _auth(self.client, "compta@etls.local")
        bq = self._banque()
        releve = ReleveBancaire.objects.create(
            compte_bancaire=bq, date_debut=date(2026, 1, 1), date_fin=date(2026, 1, 31),
        )
        ligne = LigneReleve.objects.create(
            releve=releve, date=date(2026, 1, 10), libelle="Virement", credit=Decimal("200000")
        )
        rapprochement = RapprochementBancaire.objects.create(compte_bancaire=bq)
        r = self.client.post(
            f"{BASE}rapprochements/{rapprochement.pk}/lignes/",
            {"lignes": [ligne.pk]}, format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        ligne.refresh_from_db()
        self.assertTrue(ligne.rapprochee)
        self.assertEqual(rapprochement.lignes.count(), 1)

    def test_rapprochement_different_compte_refuse(self):
        _auth(self.client, "compta@etls.local")
        bq = self._banque("BGFI")
        bq2 = self._banque("UBA")
        releve = ReleveBancaire.objects.create(
            compte_bancaire=bq2, date_debut=date(2026, 1, 1), date_fin=date(2026, 1, 31),
        )
        ligne = LigneReleve.objects.create(
            releve=releve, date=date(2026, 1, 10), libelle="Virement", credit=Decimal("200000")
        )
        rapprochement = RapprochementBancaire.objects.create(compte_bancaire=bq)
        r = self.client.post(
            f"{BASE}rapprochements/{rapprochement.pk}/lignes/",
            {"lignes": [ligne.pk]}, format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(rapprochement.lignes.count(), 0)


class EngagementTests(BaseComptaTest):
    def test_circuit_RF_ERP_W1(self):
        _auth(self.client, "compta@etls.local")
        engagement = self._engagement(statut=Engagement.Statut.BROUILLON)
        r = self.client.post(f"{BASE}engagements/{engagement.pk}/soumettre/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.json()["statut"], "soumis")
        r = self.client.post(f"{BASE}engagements/{engagement.pk}/approuver/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.json()["statut"], "approuve")

    def test_approuver_sans_soumission_refuse(self):
        _auth(self.client, "compta@etls.local")
        engagement = self._engagement(statut=Engagement.Statut.BROUILLON)
        r = self.client.post(f"{BASE}engagements/{engagement.pk}/approuver/")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_solde_engagement(self):
        engagement = self._engagement()
        self._paiement(engagement=engagement, sens="sortie", montant="100000.00")
        self._paiement(engagement=engagement, sens="sortie", montant="50000.00")
        self.assertEqual(engagement.total_paye, Decimal("150000.00"))
        self.assertEqual(engagement.solde, Decimal("100000.00"))


class PaiementTests(BaseComptaTest):
    def test_paiement_creation_code_auto(self):
        paiement = self._paiement()
        self.assertTrue(paiement.code.startswith("PAI"))

    def test_paiement_ecriture_finance_ok(self):
        _auth(self.client, "finance@etls.local")
        bq = self._banque()
        fournisseur = self._fournisseur(code_suffix="F")
        r = self.client.post(
            f"{BASE}paiements/",
            {
                "sens": "sortie", "mode": "virement", "montant": "250000",
                "date": "2026-01-15", "compte_bancaire": bq.pk,
                "tiers": fournisseur.pk,
            },
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertTrue(r.json()["has_amount_access"] is True)
        self.assertEqual(r.json()["montant"], "250000.00")
        self.assertTrue(r.json()["code"].startswith("PAI"))

    def test_comptabilisation_sortie_poste_ecriture(self):
        _auth(self.client, "compta@etls.local")
        bq = self._banque()
        fournisseur = self._fournisseur(code_suffix="F")
        paiement = self._paiement(
            compte_bancaire=bq, sens="sortie", montant="250000.00", tiers=fournisseur,
            mode="virement",
        )
        r = self.client.post(f"{BASE}paiements/{paiement.pk}/comptabiliser/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        paiement.refresh_from_db()
        self.assertIsNotNone(paiement.move)
        move = paiement.move
        self.assertEqual(move.status, AccountMove.Status.POSTED)
        self.assertTrue(move.number.startswith("BQ"))
        self.assertEqual(move.source, "M10")
        self.assertEqual(move.source_ref, paiement.code)
        # Débit 401 (fournisseur), crédit 512 (banque).
        self.assertEqual(move.total_debit, Decimal("250000.00"))
        self.assertEqual(move.total_credit, Decimal("250000.00"))

    def test_comptabilisation_entree_poste_ecriture(self):
        _auth(self.client, "compta@etls.local")
        bq = self._banque()
        client_partner = Partner.objects.create(
            code="C-X", name="CLIENT", kind=Partner.Kind.CLIENT,
        )
        paiement = self._paiement(
            compte_bancaire=bq, sens="entree", montant="500000.00", tiers=client_partner,
            mode="cheque",
        )
        r = self.client.post(f"{BASE}paiements/{paiement.pk}/comptabiliser/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        paiement.refresh_from_db()
        self.assertEqual(paiement.move.status, AccountMove.Status.POSTED)
        # Débit 512 (banque), crédit 411 (client).
        self.assertEqual(paiement.move.total_debit, Decimal("500000.00"))
        self.assertEqual(paiement.move.total_credit, Decimal("500000.00"))

    def test_comptabilisation_imputation_618(self):
        _auth(self.client, "compta@etls.local")
        bq = self._banque()
        gr = self._fournisseur(gr=True, code_suffix="GR")
        paiement = self._paiement(
            compte_bancaire=bq, sens="sortie", montant="120000.00", tiers=gr,
            imputation_618=True, mode="virement",
        )
        r = self.client.post(f"{BASE}paiements/{paiement.pk}/comptabiliser/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        paiement.refresh_from_db()
        line = paiement.move.lines.get(order=1)
        self.assertEqual(line.account.code, "618000")

    def test_double_comptabilisation_refusee(self):
        _auth(self.client, "compta@etls.local")
        paiement = self._paiement()
        build_paiement_move(paiement, user=self.comptable)
        r = self.client.post(f"{BASE}paiements/{paiement.pk}/comptabiliser/")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_validation_par_logistique_interdite(self):
        _auth(self.client, "logi@etls.local")
        paiement = self._paiement()
        r = self.client.post(f"{BASE}paiements/{paiement.pk}/comptabiliser/")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_annuler_paiement_valide_refuse(self):
        _auth(self.client, "compta@etls.local")
        paiement = self._paiement()
        build_paiement_move(paiement, user=self.comptable)
        r = self.client.post(f"{BASE}paiements/{paiement.pk}/annuler/")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_annuler_brouillon_ok(self):
        _auth(self.client, "compta@etls.local")
        paiement = self._paiement()
        r = self.client.post(f"{BASE}paiements/{paiement.pk}/annuler/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.json()["statut"], "annule")


class DeclarationTvaTests(BaseComptaTest):
    def test_calcul_tva(self):
        _auth(self.client, "compta@etls.local")
        taux = self._taux_tva()
        bq = self._banque()
        client_partner = Partner.objects.create(
            code="C-TV", name="CLIENT TVA", kind=Partner.Kind.CLIENT,
        )
        enc = self._paiement(
            compte_bancaire=bq, sens="entree", montant="50000.00",
            tiers=client_partner, mode="virement", date=date(2026, 1, 20),
        )
        dep = self._paiement(
            compte_bancaire=bq, sens="sortie", montant="20000.00",
            mode="virement", date=date(2026, 1, 25),
        )
        build_paiement_move(enc, user=self.comptable)
        build_paiement_move(dep, user=self.comptable)

        declaration = DeclarationTva.objects.create(
            mois=date(2026, 1, 1), taux_tva=taux,
        )
        compute_declaration_tva(declaration)
        # Base 50000, collectée 9000 ; déductible 18% * 20000 = 3600 ; net 5400.
        self.assertEqual(declaration.base_imposable, Decimal("50000.00"))
        self.assertEqual(declaration.tva_collectee, Decimal("9000.00"))
        self.assertEqual(declaration.tva_deductible, Decimal("3600.00"))
        self.assertEqual(declaration.net_a_payer, Decimal("5400.00"))

    def test_depot_sans_calcul_refuse(self):
        _auth(self.client, "compta@etls.local")
        taux = self._taux_tva()
        declaration = DeclarationTva.objects.create(mois=date(2026, 1, 1), taux_tva=taux)
        r = self.client.post(f"{BASE}declarations-tva/{declaration.pk}/deposer/")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_calcul_puis_depot_ok(self):
        _auth(self.client, "compta@etls.local")
        taux = self._taux_tva()
        bq = self._banque()
        client_partner = Partner.objects.create(
            code="C-TV2", name="CLIENT2", kind=Partner.Kind.CLIENT,
        )
        enc = self._paiement(
            compte_bancaire=bq, sens="entree", montant="10000.00",
            tiers=client_partner, mode="virement", date=date(2026, 1, 20),
        )
        build_paiement_move(enc, user=self.comptable)
        declaration = DeclarationTva.objects.create(mois=date(2026, 1, 1), taux_tva=taux)
        r = self.client.post(f"{BASE}declarations-tva/{declaration.pk}/calculer/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.json()["net_a_payer"], "1800.00")
        r = self.client.post(f"{BASE}declarations-tva/{declaration.pk}/deposer/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.json()["statut"], "deposee")

    def test_montants_masques_hors_roles(self):
        _auth(self.client, "logi@etls.local")
        taux = self._taux_tva()
        declaration = DeclarationTva.objects.create(mois=date(2026, 1, 1), taux_tva=taux)
        r = self.client.get(f"{BASE}declarations-tva/{declaration.pk}/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIsNone(r.json()["net_a_payer"])
        self.assertIs(r.json()["has_amount_access"], False)


class ControleInterneTests(BaseComptaTest):
    def test_creation_et_realisation(self):
        _auth(self.client, "compta@etls.local")
        controle = ControleInterne.objects.create(
            libelle="Contrôle rapprochement", reference_procedure="proc. 4.7",
        )
        self.assertTrue(controle.code.startswith("CON"))
        r = self.client.post(
            f"{BASE}controles/{controle.pk}/realiser/",
            {"constat": "RAS"}, format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.json()["statut"], "realise")
        self.assertEqual(r.json()["constat"], "RAS")

    def test_reference_procedure_validée(self):
        controle = ControleInterne(
            code="CON00001", libelle="X", reference_procedure="proc. 4.6",
        )
        controle.full_clean()
        self.assertTrue(controle.reference_procedure.startswith("proc. 4."))


class MixedFluxM10Test(BaseComptaTest):
    """Flux complet : engagement approuvé → paiement → TVA du mois."""

    def test_engagement_paiement_tva_chain(self):
        _auth(self.client, "compta@etls.local")
        bq = self._banque()
        fournisseur = self._fournisseur(code_suffix="C")

        # 1. Engagement approuvé.
        eng = self._engagement()
        r = self.client.post(f"{BASE}engagements/{eng.pk}/soumettre/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        r = self.client.post(f"{BASE}engagements/{eng.pk}/approuver/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)

        # 2. Paiement rattaché à l'engagement, comptabilisé.
        paiement = self._paiement(
            compte_bancaire=bq, sens="sortie", montant="250000.00",
            engagement=eng, tiers=fournisseur, mode="virement",
        )
        r = self.client.post(f"{BASE}paiements/{paiement.pk}/comptabiliser/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        eng.refresh_from_db()
        self.assertEqual(eng.statut, Engagement.Statut.APPROUVE)
        self.assertEqual(eng.total_paye, Decimal("250000.00"))
        self.assertEqual(eng.solde, Decimal("0.00"))

        # 3. La TVA déductible capte les décaissements validés.
        taux = self._taux_tva()
        declaration = DeclarationTva.objects.create(mois=date(2026, 1, 1), taux_tva=taux)
        compute_declaration_tva(declaration)
        self.assertEqual(declaration.tva_deductible, Decimal("45000.00"))


class JournalBelongsTest(BaseComptaTest):
    def test_periodes_2026_presentes(self):
        self.assertTrue(Period.objects.filter(fiscal_year__year=2026).exists())
        self.assertTrue(Journal.objects.filter(code="VTE").exists())
        self.assertTrue(Journal.objects.filter(code="BQ").exists())
        self.assertTrue(Journal.objects.filter(code="CAI").exists())