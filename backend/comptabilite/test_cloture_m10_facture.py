"""Recette M10 (clôture) — PR 3a : facturation client (facture, avoir, jalons et situations « à facturer »).

Le modèle d'impression (en-tête, mentions légales) est une donnée ETSL : PROVISOIRE tant qu'il n'est pas confirmé.
"""

from datetime import date, timedelta
from decimal import Decimal

from accounting_kernel.models import AccountMove
from commercial.models import Affaire, ClientProfile, Milestone
from operations.models import SituationTravaux
from referentiels.models import Account, Partner

from .facturation import facture_pdf
from .models import FactureClient, ModeleFacture
from .tests import BASE, BaseComptaTest, _auth


class M10FactureBase(BaseComptaTest):
    def setUp(self):
        super().setUp()
        self.tva = self._taux_tva()
        Account.objects.get_or_create(
            code="706000",
            defaults=dict(label="Prestations", account_class=7, account_type=Account.AccountType.INCOME),
        )
        self.partner = Partner.objects.create(code="C-100", name="CLIENT FACTURE", kind=Partner.Kind.CLIENT)
        self.profil = ClientProfile.objects.create(partner=self.partner)
        self.affaire = Affaire.objects.create(code="AFF-T1", client=self.profil, title="Affaire test")
        _auth(self.client, "compta@etls.local")

    def brouillon(self, ht="1000000", **kw):
        r = self.client.post(
            f"{BASE}factures-clients/",
            {"client": str(self.partner.id), "objet": "Prestation", "lignes": [
                {"designation": "Travaux", "quantite": "1", "prix_unitaire": ht}], **kw},
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()

    def emettre(self, fid):
        return self.client.post(f"{BASE}factures-clients/{fid}/emettre/")


class FactureEmissionTests(M10FactureBase):
    def test_brouillon_calcule_ht_tva_ttc_et_numero(self):
        f = self.brouillon("1000000")
        self.assertTrue(f["code"].startswith("FAC"))
        self.assertEqual(
            (Decimal(f["montant_ht"]), Decimal(f["montant_tva"]), Decimal(f["montant_ttc"])),
            (Decimal("1000000"), Decimal("180000"), Decimal("1180000")),
        )
        self.assertEqual((f["statut"], f["nature"]), ("brouillon", "facture"))

    def test_emission_ecrit_411_706_443_equilibre(self):
        f = self.brouillon("1000000")
        r = self.emettre(f["id"])
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual(body["statut"], "emise")
        self.assertTrue(body["emise_par"] and body["emise_le"])
        move = AccountMove.objects.get(pk=body["move"])
        self.assertEqual((move.journal.code, move.status, move.source), ("VTE", "posted", "M10"))
        lignes = {l.account.code: l for l in move.lines.select_related("account")}
        self.assertEqual(lignes["411000"].debit, Decimal("1180000"))
        self.assertEqual(lignes["411000"].partner_id, self.partner.id)
        self.assertEqual(lignes["706000"].credit, Decimal("1000000"))
        self.assertEqual(lignes["443000"].credit, Decimal("180000"))
        self.assertEqual(move.total_debit, move.total_credit)

    def test_facture_emise_scellee(self):
        fid = self.brouillon()["id"]
        self.emettre(fid)
        self.assertEqual(self.client.patch(f"{BASE}factures-clients/{fid}/", {"objet": "x"}, format="json").status_code, 400)
        self.assertEqual(self.client.delete(f"{BASE}factures-clients/{fid}/").status_code, 400)
        self.assertEqual(self.emettre(fid).status_code, 400)

    def test_brouillon_modifiable_puis_supprimable(self):
        fid = self.brouillon("100")["id"]
        r = self.client.patch(
            f"{BASE}factures-clients/{fid}/",
            {"lignes": [{"designation": "Nouveau", "quantite": "2", "prix_unitaire": "500"}]}, format="json",
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(Decimal(r.json()["montant_ht"]), Decimal("1000"))
        self.assertEqual(self.client.delete(f"{BASE}factures-clients/{fid}/").status_code, 204)

    def test_sans_ligne_ou_client_non_client_refuse(self):
        r = self.client.post(f"{BASE}factures-clients/", {"client": str(self.partner.id)}, format="json")
        self.assertEqual(self.emettre(r.json()["id"]).status_code, 400)
        fournisseur = Partner.objects.create(code="F-100", name="FOURNISSEUR", kind=Partner.Kind.FOURNISSEUR)
        f = self.brouillon(client=str(fournisseur.id))
        self.assertEqual(self.emettre(f["id"]).status_code, 400)

    def test_code_et_statut_en_lecture_seule(self):
        r = self.client.post(
            f"{BASE}factures-clients/",
            {"client": str(self.partner.id), "code": "HACK", "statut": "emise", "lignes": []}, format="json",
        )
        self.assertEqual(r.status_code, 201)
        self.assertNotEqual(r.json()["code"], "HACK")
        self.assertEqual(r.json()["statut"], "brouillon")

    def test_pdf_et_archivage_ged_10_ans(self):
        fid = self.brouillon()["id"]
        body = self.emettre(fid).json()
        facture = FactureClient.objects.get(pk=fid)
        self.assertIsNotNone(facture.document_id)
        self.assertGreaterEqual(facture.document.type.retention_years, 10)
        self.assertEqual(facture.document.status, "archived")
        r = self.client.get(f"{BASE}factures-clients/{fid}/pdf/")
        self.assertEqual((r.status_code, r["Content-Type"]), (200, "application/pdf"))
        self.assertTrue(r.content.startswith(b"%PDF"))
        self.assertTrue(body["avertissement_provisoire"])

    def test_droits(self):
        _auth(self.client, "logi@etls.local")
        r = self.client.post(f"{BASE}factures-clients/", {"client": str(self.partner.id)}, format="json")
        self.assertIn(r.status_code, (401, 403))

    def test_montants_masques_hors_cercle_montants(self):
        fid = self.brouillon()["id"]
        directeur = self.admin.__class__.objects.create_user(
            email="dp@etls.local", password="Etls#Demo2026", role="directeur_projets"
        )
        self.client.force_authenticate(directeur)
        r = self.client.get(f"{BASE}factures-clients/{fid}/")
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()["montant_ttc"])
        self.assertFalse(r.json()["has_amount_access"])


class AvoirTests(M10FactureBase):
    def emise(self, ht="1000000"):
        f = self.brouillon(ht)
        self.emettre(f["id"])
        return f["id"]

    def avoir(self, fid, **data):
        return self.client.post(f"{BASE}factures-clients/{fid}/avoir/", data, format="json")

    def test_avoir_total_inverse_l_ecriture(self):
        fid = self.emise()
        r = self.avoir(fid)
        self.assertEqual(r.status_code, 201, r.content)
        a = r.json()
        self.assertTrue(a["code"].startswith("AVO"))
        self.assertEqual((a["nature"], a["facture_origine"]), ("avoir", fid))
        self.assertEqual(Decimal(a["montant_ttc"]), Decimal("1180000"))
        out = self.emettre(a["id"]).json()
        lignes = {l.account.code: l for l in AccountMove.objects.get(pk=out["move"]).lines.select_related("account")}
        self.assertEqual(lignes["411000"].credit, Decimal("1180000"))
        self.assertEqual(lignes["706000"].debit, Decimal("1000000"))
        self.assertEqual(lignes["443000"].debit, Decimal("180000"))

    def test_avoirs_partiels_plafonnes_au_montant_de_la_facture(self):
        fid = self.emise("1000000")
        self.assertEqual(self.avoir(fid, montant_ht="400000").status_code, 201)
        self.assertEqual(self.avoir(fid, montant_ht="500000").status_code, 201)
        r = self.avoir(fid, montant_ht="200000")
        self.assertEqual(r.status_code, 400)

    def test_avoir_seulement_sur_facture_emise(self):
        f = self.brouillon()
        self.assertEqual(self.avoir(f["id"]).status_code, 400)

    def test_avoir_montant_negatif_refuse(self):
        fid = self.emise()
        self.assertEqual(self.avoir(fid, montant_ht="-5").status_code, 400)


class SourcesAFacturerTests(M10FactureBase):
    def jalon(self, realise=True, montant="30000000"):
        j = Milestone.objects.create(
            affaire=self.affaire, label="Préfabrication 50 %", planned_date=date.today(),
            actual_date=date.today() if realise else None, montant=Decimal(montant),
        )
        return j

    def depuis_jalon(self, j):
        return self.client.post(f"{BASE}factures-clients/depuis-jalon/", {"jalon": str(j.id)}, format="json")

    def test_jalon_realise_devient_facture_puis_scelle(self):
        j = self.jalon()
        r = self.depuis_jalon(j)
        self.assertEqual(r.status_code, 201, r.content)
        f = r.json()
        self.assertEqual((f["jalon"], f["affaire"], f["client"]), (str(j.id), str(self.affaire.pk), self.partner.pk))
        self.assertEqual(Decimal(f["montant_ht"]), Decimal("30000000"))
        self.emettre(f["id"])
        j.refresh_from_db()
        self.assertEqual(j.facture_le, date.today())
        self.assertEqual(self.depuis_jalon(j).status_code, 400)  # déjà facturé

    def test_jalon_non_realise_ou_sans_client_refuse(self):
        self.assertEqual(self.depuis_jalon(self.jalon(realise=False)).status_code, 400)
        self.affaire.client = None
        self.affaire.save()
        self.assertEqual(self.depuis_jalon(self.jalon()).status_code, 400)

    def test_double_facturation_en_preparation_refusee(self):
        j = self.jalon()
        self.assertEqual(self.depuis_jalon(j).status_code, 201)
        self.assertEqual(self.depuis_jalon(j).status_code, 400)

    def test_ecriture_portee_par_le_compte_analytique_de_l_affaire(self):
        self.affaire.assurer_compte_analytique()
        f = self.depuis_jalon(self.jalon()).json()
        move = AccountMove.objects.get(pk=self.emettre(f["id"]).json()["move"])
        produit = move.lines.get(account__code="706000")
        self.assertEqual(produit.analytic_account_id, self.affaire.analytic_id)

    def situation(self, statut=SituationTravaux.Status.VALIDEE):
        return SituationTravaux.objects.create(
            label="Situation 1", affaire=self.affaire, period_start=date.today() - timedelta(days=30),
            period_end=date.today(), amount=Decimal("1500000"), status=statut,
        )

    def test_situation_validee_facturee_et_scellee_avec_la_reference(self):
        s = self.situation()
        r = self.client.post(f"{BASE}factures-clients/depuis-situation/", {"situation": str(s.pk)}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        out = self.emettre(r.json()["id"]).json()
        s.refresh_from_db()
        self.assertEqual((s.status, s.facture_ref), (SituationTravaux.Status.FACTUREE, out["code"]))

    def test_situation_non_validee_refusee(self):
        s = self.situation(SituationTravaux.Status.BROUILLON)
        r = self.client.post(f"{BASE}factures-clients/depuis-situation/", {"situation": str(s.pk)}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_liste_a_facturer(self):
        j = self.jalon()
        self.jalon(realise=False)
        s = self.situation()
        body = self.client.get(f"{BASE}factures-clients/a-facturer/").json()
        self.assertEqual([x["id"] for x in body["jalons"]], [str(j.id)])
        self.assertEqual([x["id"] for x in body["situations"]], [str(s.pk)])
        self.depuis_jalon(j)
        self.assertEqual(self.client.get(f"{BASE}factures-clients/a-facturer/").json()["jalons"], [])

    def test_facture_emise_se_lettre_avec_l_encaissement(self):
        """Chaîne affaire → facture → encaissement : le 411 porte le tiers, donc il est lettrable (PR 1)."""
        from accounting_kernel.models import Journal
        from accounting_kernel.services import period_for_date, post_move
        from accounting_kernel.models import AccountMoveLine

        f = self.depuis_jalon(self.jalon(montant="1000")).json()
        move = AccountMove.objects.get(pk=self.emettre(f["id"]).json()["move"])
        ligne_facture = move.lines.get(account__code="411000")
        enc = AccountMove.objects.create(
            journal=Journal.objects.get(code="BQ"), period=period_for_date(date.today()), date=date.today(), reference=f["code"]
        )
        AccountMoveLine.objects.create(move=enc, account=Account.objects.get(code="512000"), debit=Decimal("1180"), order=0)
        ligne_enc = AccountMoveLine.objects.create(
            move=enc, account=Account.objects.get(code="411000"), partner=self.partner, credit=Decimal("1180"), order=1
        )
        post_move(enc, self.admin)
        r = self.client.post(f"{BASE}lettrages/lettrer-auto/", {"compte": str(ligne_facture.account_id)}, format="json")
        self.assertEqual(r.json()["lettrages"], 1, r.content)
        self.assertTrue(ligne_enc.lettrage_actif)


class ModeleFactureTests(M10FactureBase):
    def test_modele_provisoire_modifiable_puis_confirme(self):
        r = self.client.get(f"{BASE}modele-facture/")
        rows = r.json()["results"] if isinstance(r.json(), dict) else r.json()
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["est_provisoire"])
        mid = rows[0]["id"]
        r = self.client.patch(f"{BASE}modele-facture/{mid}/", {"entete": "ETSL SA — NIF 123456"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        _auth(self.client, "finance@etls.local")
        r = self.client.post(f"{BASE}modele-facture/{mid}/confirmer/")
        self.assertEqual((r.status_code, r.json()["statut_valeur"]), (200, "confirme"))
        self.assertFalse(ModeleFacture.objects.get().est_provisoire)
        # une modification le repasse en provisoire
        self.client.patch(f"{BASE}modele-facture/{mid}/", {"pied_page": "x"}, format="json")
        self.assertTrue(ModeleFacture.objects.get().est_provisoire)

    def test_facture_emise_avec_modele_confirme_sans_avertissement(self):
        self.client.get(f"{BASE}modele-facture/")
        ModeleFacture.objects.update(statut_valeur="confirme")
        body = self.emettre(self.brouillon()["id"]).json()
        self.assertFalse(body["avertissement_provisoire"])
        self.assertTrue(facture_pdf(FactureClient.objects.get(pk=body["id"])).startswith(b"%PDF"))

    def test_logistique_ne_modifie_pas_le_modele(self):
        self.client.get(f"{BASE}modele-facture/")
        mid = ModeleFacture.objects.get().pk
        _auth(self.client, "logi@etls.local")
        r = self.client.patch(f"{BASE}modele-facture/{mid}/", {"entete": "x"}, format="json")
        self.assertIn(r.status_code, (401, 403))
