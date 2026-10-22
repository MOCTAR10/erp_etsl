"""Recette du lot de suivi : imputation analytique de l'import grand livre (CSV / XML idempotent) et gabarit SAGE
transitoire paramétrable (fichier d'export, aucune API — H-04)."""

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from rest_framework.test import APITestCase

from accounting_kernel.models import AccountMove, AccountMoveLine
from commercial.models import Affaire
from referentiels.models import Account, AnalyticAccount, AnalyticAxis

from .importers import run_import
from .models import GabaritImport, ImportBatch

User = get_user_model()


class _Base(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(email="admin@etls.local", password="MotDePasse#2026",
                                              role=User.Role.ADMIN, is_staff=True)
        call_command("seed_accounting", year=2026)
        for code, cls, typ in (("411000", 4, Account.AccountType.ASSET), ("706000", 7, Account.AccountType.INCOME),
                               ("601000", 6, Account.AccountType.EXPENSE), ("512000", 5, Account.AccountType.ASSET)):
            Account.objects.get_or_create(code=code, defaults=dict(label=code, account_class=cls, account_type=typ))
        self.axe = AnalyticAxis.objects.create(code="AX-CC", label="Centre de coût", axis_type=AnalyticAxis.AxisType.CENTRE_COUT)
        self.cc = AnalyticAccount.objects.create(axis=self.axe, code="CC-ATELIER", label="Atelier")
        self.client.force_authenticate(self.admin)


class GLAnalytiqueTests(_Base):
    def test_csv_impute_la_ligne_de_charge_ou_produit(self):
        affaire = Affaire.objects.create(title="Affaire import")
        csv = ("date,journal,account_debit,account_credit,amount,reference,analytic,affaire\n"
               "2026-02-01,OD,601000,512000,1000,R1,CC-ATELIER,\n"
               f"2026-02-02,OD,411000,706000,5000,R2,,{affaire.code}\n")
        batch, _ = run_import("gl", "gl.csv", csv.encode(), user=self.admin)
        self.assertEqual((batch.status, batch.created_rows), (ImportBatch.Status.SUCCESS, 2))
        l601 = AccountMoveLine.objects.get(move__reference="R1", account__code="601000")
        self.assertEqual(l601.analytic_account_id, self.cc.pk)
        self.assertIsNone(AccountMoveLine.objects.get(move__reference="R1", account__code="512000").analytic_account_id)
        affaire.refresh_from_db()
        l706 = AccountMoveLine.objects.get(move__reference="R2", account__code="706000")
        self.assertEqual(l706.analytic_account_id, affaire.analytic_id)
        # Rejeu forcé : idempotent (aucune écriture en double).
        batch, _ = run_import("gl", "gl.csv", csv.encode(), user=self.admin, force=True)
        self.assertEqual(AccountMove.objects.filter(source="integrations").count(), 2)

    def test_code_analytique_inconnu_ligne_en_erreur(self):
        csv = "date,journal,account_debit,account_credit,amount,reference,analytic\n2026-02-01,OD,601000,512000,10,R9,NOPE\n"
        batch, _ = run_import("gl", "gl2.csv", csv.encode(), user=self.admin)
        self.assertEqual(batch.error_rows, 1)
        self.assertIn("analytique inconnu", batch.rows.get().error_message)

    def test_xml_avec_analytique(self):
        xml = ('<?xml version="1.0"?><ecritures>'
               '<ecriture date="2026-03-01" journal="OD" account_debit="601000" account_credit="512000" amount="250" '
               'reference="X1" analytic="AX-CC:CC-ATELIER"/>'
               '<ecriture><date>2026-03-02</date><journal>OD</journal><account_debit>601000</account_debit>'
               '<account_credit>512000</account_credit><amount>75</amount><reference>X2</reference></ecriture>'
               '</ecritures>')
        batch, _ = run_import("gl", "gl.xml", xml.encode(), user=self.admin)
        self.assertEqual((batch.status, batch.created_rows), (ImportBatch.Status.SUCCESS, 2))
        self.assertEqual(AccountMoveLine.objects.get(move__reference="X1", account__code="601000").analytic_account_id, self.cc.pk)
        bombe = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><ecritures><e/></ecritures>'
        batch, _ = run_import("gl", "bombe.xml", bombe.encode(), user=self.admin)
        self.assertEqual(batch.status, ImportBatch.Status.FAILED)


SAGE = ("Code journal;Date;N° pièce;N° compte général;Libellé écriture;Débit;Crédit;Section analytique;N° compte tiers\n"
        "OD;15/02/2026;P001;601000;Achat fournitures;1 200,50;;CC-ATELIER;\n"
        "OD;15/02/2026;P001;512000;Achat fournitures;;1 200,50;;\n"
        "OD;16/02/2026;P002;601000;Déséquilibrée;10,00;;;\n"
        "OD;16/02/2026;P002;512000;Déséquilibrée;;9,00;;\n")


class GabaritSageTests(_Base):
    def test_import_sage_par_piece_avec_gabarit_provisoire(self):
        batch, _ = run_import("sage", "export.txt", SAGE.encode("cp1252"), user=self.admin)
        self.assertEqual((batch.total_rows, batch.created_rows, batch.error_rows), (2, 1, 1))
        move = AccountMove.objects.get(reference="P001")
        self.assertEqual(move.lines.count(), 2)
        self.assertEqual(str(move.total_debit), "1200.50")
        self.assertEqual(move.lines.get(account__code="601000").analytic_account_id, self.cc.pk)
        self.assertIn("déséquilibrée", batch.rows.get(status="error").error_message)
        replay, rejoue = run_import("sage", "export.txt", SAGE.encode("cp1252"), user=self.admin)
        self.assertTrue(rejoue)
        self.assertEqual(AccountMove.objects.filter(reference="P001").count(), 1)

    def test_gabarit_modifiable_confirmable_et_utilise(self):
        r = self.client.get("/api/integrations/gabarits/")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        rows = data["results"] if isinstance(data, dict) else data
        g = next(x for x in rows if x["code"] == "SAGE_GL")
        self.assertTrue(g["est_provisoire"])
        url = f"/api/integrations/gabarits/{g['id']}/"
        self.assertEqual(self.client.patch(url, {"encodage": "pas-un-encodage"}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(url, {"colonnes": {"inconnu": "X"}}, format="json").status_code, 400)
        r = self.client.patch(url, {"separateur": ",", "encodage": "utf-8", "separateur_decimal": ".",
                                    "colonnes": {"compte": "Compte", "date": "Date", "journal": "Journal",
                                                 "piece": "Piece", "debit": "Debit", "credit": "Credit"}}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        r = self.client.post(f"{url}confirmer/")
        self.assertEqual(r.json()["statut_valeur"], "confirme")
        csv = "Journal,Date,Piece,Compte,Debit,Credit\nOD,01/03/2026,Q1,601000,50.5,\nOD,01/03/2026,Q1,512000,,50.5\n"
        f = SimpleUploadedFile("sage.csv", csv.encode("utf-8"), content_type="text/csv")
        r = self.client.post("/api/integrations/import/", {"connector": "sage", "gabarit": "SAGE_GL", "file": f})
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(AccountMove.objects.filter(reference="Q1").exists())
        self.assertEqual(GabaritImport.objects.get(code="SAGE_GL").statut_valeur, "confirme")
