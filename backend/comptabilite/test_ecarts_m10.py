"""Recette des écarts M10 : états SYSCOHADA exportables, balance âgée, trésorerie 13 semaines, analytique et retenue
sur paiements, TVA sur écritures + autofacturation, liasse / état 2460, clôture (API directe bloquée, e-mail, journal
archivé), conservation, écriture 618 des locations GR."""

from datetime import date, timedelta
from decimal import Decimal

from django.core import mail
from django.utils import timezone

from accounting_kernel.models import AccountMove, AccountMoveLine, FiscalYear, Journal, Period
from accounting_kernel.services import post_move
from referentiels.models import Account, AnalyticAccount, AnalyticAxis, Partner
from users.models import User
from workflow.models import Notification

from .models import AutoFacture, ClotureMensuelle, DeclarationTva, GabaritEtat, Paiement, PrevisionTresorerie
from .services import build_paiement_move
from .tests import BASE, BaseComptaTest, _auth

ETATS = f"{BASE}etats/"


class EcartsBase(BaseComptaTest):
    def setUp(self):
        super().setUp()
        for code, cls, typ, label in (
            ("101000", 1, Account.AccountType.EQUITY, "Capital"),
            ("706000", 7, Account.AccountType.INCOME, "Prestations"),
            ("447000", 4, Account.AccountType.LIABILITY, "Etat"),
            ("632000", 6, Account.AccountType.EXPENSE, "Honoraires"),
        ):
            Account.objects.get_or_create(code=code, defaults=dict(label=label, account_class=cls, account_type=typ))
        self.client_p = Partner.objects.create(code="CLI-1", name="CLIENT UN", kind=Partner.Kind.CLIENT)
        _auth(self.client, "finance@etls.local")

    def a(self, code):
        return Account.objects.get(code=code)

    def ecriture(self, lignes, d=date(2026, 3, 10), journal="OD"):
        m = AccountMove.objects.create(
            journal=Journal.objects.get(code=journal), period=Period.objects.get(start_date__lte=d, end_date__gte=d),
            date=d, label="test",
        )
        for i, (compte, debit, credit, partner) in enumerate(lignes):
            AccountMoveLine.objects.create(
                move=m, account=self.a(compte), debit=Decimal(debit), credit=Decimal(credit), partner=partner, order=i
            )
        return post_move(m, self.admin)

    def jeu(self):
        self.ecriture([("512000", "1000000", "0", None), ("101000", "0", "1000000", None)], d=date(2026, 1, 5))
        self.ecriture([("411000", "590000", "0", self.client_p), ("706000", "0", "500000", None), ("443000", "0", "90000", None)])
        self.ecriture([("601000", "200000", "0", None), ("512000", "0", "200000", None)])


class EtatsTests(EcartsBase):
    def test_balance_grand_livre_bilan_resultat(self):
        self.jeu()
        r = self.client.get(f"{ETATS}balance/?date_from=2026-01-01&date_to=2026-12-31")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["equilibre"])
        total = r.json()["tableaux"][0]["lignes"][-1]
        self.assertEqual(total["mvt_d"], "1790000.00")
        r = self.client.get(f"{ETATS}grand-livre/?compte=512&date_from=2026-01-01&date_to=2026-12-31")
        lignes = r.json()["tableaux"][0]["lignes"]
        self.assertEqual([l["solde"] for l in lignes if l.get("total")][0], "800000.00")
        r = self.client.get(f"{ETATS}compte-resultat/?date_from=2026-01-01&date_to=2026-12-31")
        self.assertEqual(r.json()["resultat"], "300000.00")
        self.assertTrue(r.json()["provisoire"])
        r = self.client.get(f"{ETATS}bilan/?date_to=2026-12-31")
        self.assertTrue(r.json()["equilibre"], r.json())
        passif = {l["rubrique"]: l["montant"] for l in r.json()["tableaux"][1]["lignes"]}
        self.assertEqual(passif["CJ"], "300000.00")
        self.assertEqual(passif["DZ"], "1390000.00")

    def test_exports_xlsx_pdf_et_format_refuse(self):
        self.jeu()
        r = self.client.get(f"{ETATS}balance/?export=xlsx")
        self.assertEqual(r.status_code, 200)
        self.assertIn("spreadsheetml", r["Content-Type"])
        r = self.client.get(f"{ETATS}bilan/?export=pdf")
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertTrue(r.content.startswith(b"%PDF"))
        self.assertEqual(self.client.get(f"{ETATS}balance/?export=doc").status_code, 400)

    def test_montants_refuses_hors_cercle(self):
        User.objects.create_user(email="dp@etls.local", password="Etls#Demo2026", role=User.Role.DIRECTEUR_PROJETS)
        _auth(self.client, "dp@etls.local")
        self.assertEqual(self.client.get(f"{ETATS}balance/").status_code, 403)
        self.assertEqual(self.client.get(f"{ETATS}plan-comptable/").status_code, 200)

    def test_plan_multi_niveaux(self):
        r = self.client.get(f"{ETATS}plan-comptable/")
        lignes = r.json()["tableaux"][0]["lignes"]
        sous = [l for l in lignes if l["code"] == "401100"][0]
        self.assertEqual((sous["niveau"], sous["parent"]), (4, "401000"))
        self.assertTrue(any(l["niveau"] == 1 and l["code"] == "4" for l in lignes))
        self.assertTrue(any(l["niveau"] == 2 and l["code"] == "40" for l in lignes))

    def test_balance_agee_par_tranches(self):
        jour = timezone.localdate()
        self.ecriture([("411000", "100", "0", self.client_p), ("706000", "0", "100", None)], d=jour - timedelta(days=5))
        self.ecriture([("411000", "300", "0", self.client_p), ("706000", "0", "300", None)], d=jour - timedelta(days=100))
        r = self.client.get(f"{ETATS}balance-agee/?nature=clients")
        ligne = r.json()["tableaux"][0]["lignes"][0]
        self.assertEqual((ligne["t0"], ligne["t3"], ligne["total"]), ("100.00", "300.00", "400.00"))
        self.assertTrue(r.json()["provisoire"])

    def test_conservation_et_exercice_non_supprimable(self):
        self.jeu()
        r = self.client.get(f"{ETATS}conservation/")
        ligne = [l for l in r.json()["tableaux"][0]["lignes"] if l["exercice"] == 2026][0]
        self.assertEqual(ligne["ecritures"], 3)
        self.assertEqual(ligne["conserver_jusqu_au"], "2036-12-31")
        _auth(self.client, "admin@etls.local")
        fy = FiscalYear.objects.get(year=2026)
        self.assertEqual(self.client.delete(f"/api/accounting/fiscal-years/{fy.pk}/").status_code, 400)


class TresorerieTests(EcartsBase):
    def test_plan_13_semaines_et_alerte(self):
        jour = timezone.localdate()
        self.ecriture([("512000", "1000", "0", None), ("101000", "0", "1000", None)], d=jour - timedelta(days=jour.weekday() + 1))
        r = self.client.post(f"{BASE}previsions-tresorerie/", {
            "date_prevue": str(jour + timedelta(days=21)), "sens": "sortie", "categorie": "salaires",
            "libelle": "Paie", "montant": "5000",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        r = self.client.get(f"{ETATS}tresorerie/")
        plan = r.json()
        self.assertEqual(plan["semaines"], 13)
        self.assertEqual(plan["solde_initial"], "1000.00")
        self.assertTrue(plan["alertes"])
        self.assertTrue(plan["provisoire"])
        self.assertIsNotNone(plan["rows"][0]["realise_encaissements"])
        from .tresorerie import alerter_tresorerie

        self.assertIn("finance@etls.local", alerter_tresorerie())
        self.assertEqual(alerter_tresorerie(), [])  # une seule alerte par jour
        self.assertTrue(Notification.objects.filter(user=self.finance, subject__contains="Trésorerie").exists())
        self.assertEqual(self.client.get(f"{ETATS}tresorerie/?export=xlsx").status_code, 200)


class PaiementAnalytiqueRetenueTests(EcartsBase):
    def test_retenue_447_et_analytique(self):
        axe = AnalyticAxis.objects.create(code="AX-T", label="Affaires", axis_type=AnalyticAxis.AxisType.PROJET)
        ana = AnalyticAccount.objects.create(axis=axe, code="AFF-1", label="Affaire 1")
        p = self._paiement(montant="100000.00", tiers=self._fournisseur(), analytic_account=ana, retenue_source=True)
        move = build_paiement_move(p, self.finance)
        p.refresh_from_db()
        self.assertEqual(p.montant_retenue, Decimal("10000.00"))
        lignes = {l.account.code: l for l in move.lines.all()}
        self.assertEqual(lignes["447000"].credit, Decimal("10000.00"))
        self.assertEqual(lignes["512000"].credit, Decimal("90000.00"))
        self.assertEqual(lignes["401000"].analytic_account, ana)


class TvaAutofactureTests(EcartsBase):
    def test_autofacture_tva_sur_ecritures_et_depot_archive(self):
        taux = self._taux_tva()
        fournisseur = self._fournisseur()
        r = self.client.post(f"{BASE}autofactures/", {
            "fournisseur": str(fournisseur.pk), "date": "2026-03-12", "objet": "Prestation non résident",
            "montant_ht": "100000", "taux_tva": taux.pk, "compte_charge": self.a("632000").pk,
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        r = self.client.post(f"{BASE}autofactures/{r.json()['id']}/emettre/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["montant_tva"], "18000.00")
        self.assertEqual(self.client.patch(f"{BASE}autofactures/{r.json()['id']}/", {"objet": "x"}, format="json").status_code, 400)
        self.ecriture([("411000", "590000", "0", self.client_p), ("706000", "0", "500000", None), ("443000", "0", "90000", None)])
        decl = DeclarationTva.objects.create(mois=date(2026, 3, 1), taux_tva=taux)
        r = self.client.post(f"{BASE}declarations-tva/{decl.pk}/calculer/")
        d = r.json()
        self.assertEqual(d["source_calcul"], "ecritures")
        self.assertEqual((d["tva_collectee"], d["tva_deductible"], d["tva_autoliquidee"]), ("108000.00", "18000.00", "18000.00"))
        self.assertEqual(d["net_a_payer"], "90000.00")
        r = self.client.post(f"{BASE}declarations-tva/{decl.pk}/deposer/")
        self.assertEqual(r.status_code, 200)
        decl.refresh_from_db()
        self.assertEqual(decl.document.type.retention_years, 10)


class FiscalTests(EcartsBase):
    def test_liasse_etat_2460_gabarit(self):
        self.jeu()
        honoraires = Partner.objects.create(code="AVOCAT", name="CABINET", kind=Partner.Kind.FOURNISSEUR, tax_id="NIF-9")
        self.ecriture([("632000", "250000", "0", None), ("401000", "0", "250000", honoraires)])
        r = self.client.get(f"{ETATS}liasse/?exercice=2026")
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(len(r.json()["tableaux"]), 4)
        r = self.client.get(f"{ETATS}etat-2460/?exercice=2026")
        ligne = r.json()["tableaux"][0]["lignes"][0]
        self.assertEqual((ligne["tiers"], ligne["nif"], ligne["montant"]), ("CABINET", "NIF-9", "250000.00"))
        g = GabaritEtat.objects.get(code="ETAT_2460")
        r = self.client.post(f"{BASE}gabarits/{g.pk}/modifier/", {"parametres": '{"comptes": ["632"], "seuil": "300000"}'}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        r = self.client.get(f"{ETATS}etat-2460/?exercice=2026")
        self.assertEqual(len(r.json()["tableaux"][0]["lignes"]), 1)  # total seul : sous le seuil
        r = self.client.post(f"{BASE}gabarits/{g.pk}/confirmer/")
        self.assertEqual(r.json()["statut_valeur"], "confirme")
        r = self.client.post(f"{ETATS}archiver-liasse/", {"exercice": 2026}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(self.client.get(f"{ETATS}liasse/?exercice=abc").status_code, 400)


class ClotureTests(EcartsBase):
    def test_cloture_directe_bloquee_email_et_journal_archive(self):
        janvier = Period.objects.get(fiscal_year__year=2026, number=1)
        _auth(self.client, "admin@etls.local")
        self.assertEqual(self.client.post(f"/api/accounting/periods/{janvier.pk}/close/").status_code, 400)
        self.assertEqual(self.client.post(f"/api/accounting/periods/{janvier.pk}/reopen/").status_code, 400)
        User.objects.create_user(email="pdg@etls.local", password="Etls#Demo2026", role=User.Role.PDG)
        _auth(self.client, "finance@etls.local")
        r = self.client.post(f"{BASE}clotures-mensuelles/demarrer/", {"period": janvier.pk}, format="json")
        cid = r.json()["id"]
        r = self.client.post(f"{BASE}clotures-mensuelles/{cid}/cloturer/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIsNotNone(r.json()["document"])
        r = self.client.post(f"{BASE}clotures-mensuelles/{cid}/envoyer-direction/")
        self.assertEqual(r.json()["emails_envoyes"], 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("pdg@etls.local", mail.outbox[0].to)
        self.assertEqual(ClotureMensuelle.objects.get(pk=cid).period.status, Period.Status.CLOSED)


class LocationGrTests(EcartsBase):
    def location(self):
        from logistique.models import EquipementParc, LocationGR

        gr = Partner.objects.create(code="GR-T", name="GLOBAL RENTAL", kind=Partner.Kind.BOTH, is_global_rental=True)
        eq = EquipementParc.objects.create(label="Grue 50 t")
        return LocationGR.objects.create(
            partenaire=gr, equipement=eq, periodicite="jour", tarif=Decimal("10000"), date_debut=date(2026, 3, 1),
            date_retour=date(2026, 3, 10), statut=LocationGR.Statut.TERMINEE,
        )

    def test_ecriture_618_401100(self):
        loc = self.location()
        r = self.client.get(f"{BASE}locations-gr/")
        self.assertEqual(r.json()["a_comptabiliser"][0]["montant"], "100000.00")
        r = self.client.post(f"{BASE}locations-gr/{loc.pk}/comptabiliser/")
        self.assertEqual(r.status_code, 201, r.content)
        move = AccountMove.objects.get(source="M4", source_ref=loc.code)
        lignes = {l.account.code: l for l in move.lines.all()}
        self.assertEqual(lignes["618000"].debit, Decimal("100000.00"))
        self.assertEqual(lignes["401100"].credit, Decimal("100000.00"))
        self.assertEqual(self.client.post(f"{BASE}locations-gr/{loc.pk}/comptabiliser/").status_code, 400)
        self.assertEqual(self.client.get(f"{BASE}locations-gr/").json()["a_comptabiliser"], [])

    def test_tache_quotidienne_comptabilise_les_locations(self):
        loc = self.location()
        from .tasks import comptabiliser_locations_gr

        self.assertEqual(comptabiliser_locations_gr(), [loc.code])
        self.assertEqual(comptabiliser_locations_gr(), [])
        self.assertFalse(PrevisionTresorerie.objects.exists())
        self.assertFalse(Paiement.objects.exists())
        self.assertFalse(AutoFacture.objects.exists())

    def test_location_avec_bc_gr_une_seule_charge_618(self):
        """Location rattachée à un BC GLOBAL RENTAL (M2) : la charge 618 passe par sa facture d'achat, jamais ici."""
        from achats.ecarts import bc_depuis_location_gr

        loc = self.location()
        bc_depuis_location_gr(loc, self.admin)
        self.assertEqual(self.client.get(f"{BASE}locations-gr/").json()["a_comptabiliser"], [])
        self.assertEqual(self.client.post(f"{BASE}locations-gr/{loc.pk}/comptabiliser/").status_code, 400)
        from .tasks import comptabiliser_locations_gr

        self.assertEqual(comptabiliser_locations_gr(), [])
        self.assertFalse(AccountMove.objects.filter(source="M4", source_ref=loc.code).exists())
