"""Recette du lot de suivi inter-modules côté M10 : unicité de la charge 618 des locations GR (liens M2 / M4),
contrôle interne (référence de procédure), retenue de garantie M1 → M10 (écriture, report, libération)."""

from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils import timezone

from accounting_kernel.models import AccountMove
from commercial.models import Affaire, ClientProfile, Contract
from referentiels.models import Account, Partner

from . import gr
from .models import ControleInterne, FactureClient, LigneFactureClient
from .test_ecarts_m10 import EcartsBase
from .tests import BASE, BaseComptaTest, _auth


class Double618Tests(EcartsBase):
    def setUp(self):
        super().setUp()
        from logistique.models import EquipementParc, LocationGR

        self.gr = Partner.objects.create(code="GR-S", name="GLOBAL RENTAL", kind=Partner.Kind.BOTH, is_global_rental=True)
        eq = EquipementParc.objects.create(label="Nacelle")
        self.loc = LocationGR.objects.create(
            partenaire=self.gr, equipement=eq, periodicite="jour", tarif=Decimal("10000"), date_debut=date(2026, 3, 1),
            date_retour=date(2026, 3, 10), statut=LocationGR.Statut.TERMINEE,
        )

    def bc(self):
        from achats.models import PurchaseOrder

        return PurchaseOrder.objects.create(supplier=self.gr, is_global_rental=True)

    def a_comptabiliser(self):
        return [r["code"] for r in self.client.get(f"{BASE}locations-gr/").json()["a_comptabiliser"]]

    def test_lien_pose_par_m4_exclut_la_location_et_synchronise_le_bc(self):
        from logistique.services import lier_bc_achat

        self.assertEqual(self.a_comptabiliser(), [self.loc.code])
        bc = self.bc()
        lier_bc_achat(self.loc, bc)
        bc.refresh_from_db()
        self.assertEqual(bc.location_gr_id, self.loc.pk)  # un seul lien, lu des deux côtés
        self.assertEqual(self.a_comptabiliser(), [])
        self.assertEqual(self.client.post(f"{BASE}locations-gr/{self.loc.pk}/comptabiliser/").status_code, 400)
        self.assertFalse(AccountMove.objects.filter(source="M4", source_ref=self.loc.code).exists())

    def test_lien_pose_par_m2_synchronise_la_location(self):
        from achats.ecarts import bc_depuis_location_gr

        bc = bc_depuis_location_gr(self.loc, self.admin)
        self.loc.refresh_from_db()
        self.assertEqual(self.loc.bon_commande_achat_id, bc.pk)
        self.assertEqual(self.a_comptabiliser(), [])
        with self.assertRaises(ValidationError):
            bc_depuis_location_gr(self.loc, self.admin)  # pas de second BC GR

    def test_lien_historique_m4_seul_est_lu_par_m10(self):
        """Donnée antérieure : seul `LocationGR.bon_commande_achat` est posé (BC sans location) → exclue quand même."""
        from logistique.models import LocationGR

        LocationGR.objects.filter(pk=self.loc.pk).update(bon_commande_achat=self.bc())
        self.loc.refresh_from_db()
        self.assertTrue(gr.bc_lie(self.loc))
        self.assertEqual(self.a_comptabiliser(), [])

    def test_location_deja_passee_au_618_ne_peut_plus_etre_liee(self):
        from achats.ecarts import bc_depuis_location_gr
        from logistique.services import lier_bc_achat

        self.assertEqual(self.client.post(f"{BASE}locations-gr/{self.loc.pk}/comptabiliser/").status_code, 201)
        with self.assertRaises(ValidationError):
            lier_bc_achat(self.loc, self.bc())
        with self.assertRaises(ValidationError):
            bc_depuis_location_gr(self.loc, self.admin)
        self.assertEqual(AccountMove.objects.filter(source="M4", source_ref=self.loc.code).count(), 1)

    def test_bc_deja_rattache_a_une_autre_location_refuse(self):
        from logistique.models import LocationGR
        from logistique.services import lier_bc_achat

        bc = self.bc()
        autre = LocationGR.objects.create(partenaire=self.gr, equipement=self.loc.equipement, periodicite="jour",
                                          tarif=Decimal("1"), date_debut=date(2026, 3, 1))
        lier_bc_achat(autre, bc)
        with self.assertRaises(ValidationError):
            lier_bc_achat(self.loc, bc)


class ControleInterneCleanTests(BaseComptaTest):
    def test_reference_invalide_refusee_par_l_api_et_le_modele(self):
        _auth(self.client, "compta@etls.local")
        r = self.client.post(f"{BASE}controles/", {"libelle": "X", "reference_procedure": "proc. 9.1"}, format="json")
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("reference_procedure", r.json())
        with self.assertRaises(ValidationError):
            ControleInterne(code="CON9", libelle="X", reference_procedure="4.6").full_clean()
        r = self.client.post(f"{BASE}controles/", {"libelle": "X", "reference_procedure": "proc. 4.6"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)


class RetenueGarantieTests(BaseComptaTest):
    def setUp(self):
        super().setUp()
        self.tva = self._taux_tva()
        Account.objects.get_or_create(
            code="706000", defaults=dict(label="Prestations", account_class=7, account_type=Account.AccountType.INCOME)
        )
        self.partner = Partner.objects.create(code="C-RG", name="CLIENT RG", kind=Partner.Kind.CLIENT)
        profil = ClientProfile.objects.create(partner=self.partner)
        self.affaire = Affaire.objects.create(code="AFF-RG", client=profil, title="Marché RG")
        today = timezone.localdate()
        self.contrat = Contract.objects.create(
            code="CTR-RG", client=profil, affaire=self.affaire, profile="marche_travaux", start_date=today - timedelta(days=60),
            end_date=today + timedelta(days=300), retenue_rate=Decimal("5"), status=Contract.Status.ACTIF,
        )
        _auth(self.client, "finance@etls.local")

    def facture(self, ht="1000000", nature="facture", origine=None):
        f = FactureClient.objects.create(client=self.partner, affaire=self.affaire, taux_tva=self.tva, objet="Situation",
                                         nature=nature, facture_origine=origine)
        LigneFactureClient.objects.create(facture=f, designation="Travaux", quantite=1, prix_unitaire=Decimal(ht),
                                          compte_produit=Account.objects.get(code="706000"))
        f.recalculer()
        return f

    def emettre(self, f):
        r = self.client.post(f"{BASE}factures-clients/{f.pk}/emettre/")
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def test_ecriture_report_avoir_et_liberation(self):
        f = self.facture()
        brouillon = self.client.get(f"{BASE}factures-clients/{f.pk}/").json()
        self.assertEqual(Decimal(brouillon["montant_retenue"]), Decimal("50000"))  # report prévisionnel
        body = self.emettre(f)
        self.assertEqual((Decimal(body["montant_retenue"]), Decimal(body["net_a_payer"])),
                         (Decimal("50000.00"), Decimal("1130000.00")))
        move = AccountMove.objects.get(pk=body["move"])
        lignes = {l.account.code: l for l in move.lines.select_related("account")}
        self.assertEqual(lignes["411000"].debit, Decimal("1130000"))
        self.assertEqual(lignes["411700"].debit, Decimal("50000"))
        self.assertEqual(move.total_debit, move.total_credit)

        avoir = self.facture("200000", nature="avoir", origine=f)
        self.emettre(avoir)
        avoir.refresh_from_db()
        self.assertEqual(avoir.montant_retenue, Decimal("10000.00"))
        lignes = {l.account.code: l for l in avoir.move.lines.select_related("account")}
        self.assertEqual(lignes["411700"].credit, Decimal("10000"))

        r = self.client.get(f"{BASE}retenues-garantie/").json()
        row = r["rows"][0]
        self.assertEqual((row["affaire_code"], row["solde"], row["echue"]), ("AFF-RG", "40000.00", False))
        url = f"{BASE}retenues-garantie/{self.affaire.pk}/liberer/"
        self.assertEqual(self.client.post(url, {}, format="json").status_code, 400)  # non échue sans motif
        r = self.client.post(url, {"motif": "Caution bancaire de substitution"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        lib = AccountMove.objects.get(source_ref="RG/AFF-RG")
        lignes = {l.account.code: l for l in lib.lines.select_related("account")}
        self.assertEqual((lignes["411000"].debit, lignes["411700"].credit), (Decimal("40000"), Decimal("40000")))
        self.assertEqual(self.client.get(f"{BASE}retenues-garantie/").json()["rows"][0]["solde"], "0.00")
        self.assertEqual(self.client.post(url, {"motif": "x"}, format="json").status_code, 400)

    def test_parametre_inactif_ou_sans_contrat_pas_de_retenue(self):
        from .models import ParametreCompta
        from .services import get_param

        get_param("RETENUE_GARANTIE_ACTIVE")
        ParametreCompta.objects.filter(code="RETENUE_GARANTIE_ACTIVE").update(valeur=0)
        body = self.emettre(self.facture())
        self.assertEqual(Decimal(body["montant_retenue"]), Decimal("0"))
        self.assertEqual(Decimal(body["net_a_payer"]), Decimal(body["montant_ttc"]))

    def test_montants_masques_hors_cercle(self):
        self.emettre(self.facture())
        _auth(self.client, "logi@etls.local")
        r = self.client.get(f"{BASE}retenues-garantie/")
        if r.status_code == 200:
            self.assertIsNone(r.json()["rows"][0]["solde"])
        else:
            self.assertEqual(r.status_code, 403)
