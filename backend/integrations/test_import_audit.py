"""Audit des imports (2026-10-16) + reprise des balances d'ouverture SAGE (CL-OM-10).

I1 : l'import de fichiers (tiers, ÉCRITURES COMPTABLES) est réservé au cercle comptable ; l'historique des lots aussi.
I2 : une écriture importée sans référence n'écrase/ignore pas une autre écriture du même jour.
I3 : balance d'ouverture : équilibrée, comptes connus, exercice ouvert, une seule fois par exercice, total de contrôle SAGE.
"""

from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from rest_framework.test import APITestCase

from accounting_kernel.models import AccountMove, FiscalYear
from referentiels.models import Account
from users.models import User

from .importers import run_import
from .models import ImportBatch


def user(email, role):
    return User.objects.create_user(email=email, password="x-Audit-2026", role=role, first_name=email[:3])


class ImportAutorisationTests(APITestCase):
    def setUp(self):
        self.service = user("service@etls.ga", User.Role.CHEF_SERVICE)
        self.logi = user("logi@etls.ga", User.Role.LOGISTIQUE)
        self.compta = user("compta@etls.ga", User.Role.COMPTABLE)
        self.csv = SimpleUploadedFile("p.csv", b"code,name\nCLI-9,Client Neuf\n", content_type="text/csv")

    def post(self, who, connector="partners"):
        self.client.force_authenticate(who)
        self.csv.seek(0)
        return self.client.post("/api/integrations/import/", {"connector": connector, "file": self.csv}, format="multipart")

    def test_roles_hors_cercle_comptable_refuses(self):
        for who in (self.service, self.logi):
            for connector in ("partners", "gl"):
                self.assertEqual(self.post(who, connector).status_code, 403, (who.role, connector))
        self.assertEqual(ImportBatch.objects.count(), 0)

    def test_cercle_comptable_autorise(self):
        self.assertEqual(self.post(self.compta).status_code, 201)

    def test_historique_des_lots_reserve(self):
        self.client.force_authenticate(self.service)
        self.assertEqual(self.client.get("/api/integrations/batches/").status_code, 403)
        self.client.force_authenticate(self.compta)
        self.assertEqual(self.client.get("/api/integrations/batches/").status_code, 200)


class EcrituresSansReferenceTests(APITestCase):
    def setUp(self):
        call_command("seed_accounting", year=2026)
        for code, cls, t in (("512000", 5, "asset"), ("701000", 7, "income"), ("601000", 6, "expense")):
            Account.objects.get_or_create(code=code, defaults=dict(label=code, account_class=cls, account_type=t))
        self.admin = user("admin@etls.ga", User.Role.ADMIN)

    def test_deux_ecritures_du_meme_jour_sans_reference_sont_importees(self):
        csv = (
            "date,journal,account_debit,account_credit,label,amount,reference\n"
            "2026-02-10,OD,512000,701000,Vente A,1000,\n"
            "2026-02-10,OD,601000,512000,Achat B,400,\n"
        )
        batch, _ = run_import("gl", "gl.csv", csv.encode(), user=self.admin)
        self.assertEqual(batch.created_rows, 2, batch.rows.values_list("error_message", flat=True))
        self.assertEqual(AccountMove.objects.count(), 2)

    def test_rejeu_force_sans_reference_ne_duplique_pas(self):
        csv = "date,journal,account_debit,account_credit,label,amount,reference\n2026-02-10,OD,512000,701000,Vente A,1000,\n"
        run_import("gl", "gl.csv", csv.encode(), user=self.admin)
        batch, _ = run_import("gl", "gl.csv", csv.encode(), user=self.admin, force=True)
        self.assertEqual(batch.created_rows, 0)
        self.assertEqual(AccountMove.objects.count(), 1)


class BalanceOuvertureTests(APITestCase):
    CSV = (
        "compte,libelle,debit,credit\n"
        "512000,Banques,5000000,0\n"
        "411000,Clients,2000000,0\n"
        "401000,Fournisseurs,0,3000000\n"
        "101000,Capital,0,4000000\n"
    )

    def setUp(self):
        call_command("seed_accounting", year=2026)
        for code, cls, t in (
            ("512000", 5, "asset"), ("411000", 4, "asset"), ("401000", 4, "liability"), ("101000", 1, "equity"),
        ):
            Account.objects.get_or_create(code=code, defaults=dict(label=code, account_class=cls, account_type=t))
        self.compta = user("compta@etls.ga", User.Role.COMPTABLE)
        self.service = user("service@etls.ga", User.Role.CHEF_SERVICE)
        self.client.force_authenticate(self.compta)

    def post(self, csv=None, **extra):
        data = {"file": SimpleUploadedFile("ouverture.csv", (csv or self.CSV).encode()), "date": "2026-01-01"}
        data.update(extra)
        return self.client.post("/api/integrations/opening-balances/", data, format="multipart")

    def test_balance_equilibree_importee_en_une_ecriture(self):
        r = self.post()
        self.assertEqual(r.status_code, 201, r.content)
        move = AccountMove.objects.get(reference="AN-2026")
        self.assertEqual(move.status, AccountMove.Status.POSTED)
        self.assertEqual(move.total_debit, Decimal("7000000"))
        self.assertEqual(move.total_credit, Decimal("7000000"))
        self.assertEqual(move.lines.count(), 4)

    def test_balance_desequilibree_refusee_avec_l_ecart(self):
        bad = self.CSV.replace("4000000", "3500000")
        r = self.post(bad)
        self.assertEqual(r.status_code, 400)
        self.assertIn("500000", str(r.data))
        self.assertEqual(AccountMove.objects.count(), 0)

    def test_compte_inconnu_refuse_et_liste(self):
        r = self.post(self.CSV + "999999,Inconnu,10,0\n")
        self.assertEqual(r.status_code, 400)
        self.assertIn("999999", str(r.data))

    def test_une_seule_balance_d_ouverture_par_exercice(self):
        self.assertEqual(self.post().status_code, 201)
        autre = self.CSV.replace("5000000", "5000001").replace("4000000", "4000001")
        self.assertEqual(self.post(autre).status_code, 409)
        self.assertEqual(AccountMove.objects.filter(reference="AN-2026").count(), 1)

    def test_rejeu_du_meme_fichier_idempotent(self):
        r1 = self.post()
        r2 = self.post()
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r1.data["move"], r2.data["move"])
        self.assertEqual(AccountMove.objects.filter(reference="AN-2026").count(), 1)

    def test_total_de_controle_sage(self):
        self.assertEqual(self.post(total_debit="9999999").status_code, 400)
        self.assertEqual(AccountMove.objects.count(), 0)
        self.assertEqual(self.post(total_debit="7000000").status_code, 201)

    def test_exercice_inexistant_ou_clos(self):
        self.assertEqual(self.post(date="2031-01-01").status_code, 400)
        FiscalYear.objects.filter(year=2026).update(status="closed")
        self.assertEqual(self.post().status_code, 400)

    def test_date_doit_etre_le_premier_jour_de_l_exercice(self):
        self.assertEqual(self.post(date="2026-03-15").status_code, 400)

    def test_reserve_au_cercle_comptable(self):
        self.client.force_authenticate(self.service)
        self.assertEqual(self.post().status_code, 403)

    def test_montants_negatifs_et_doubles_cotes_refuses(self):
        self.assertEqual(self.post(self.CSV.replace("5000000,0", "-5000000,0")).status_code, 400)
        self.assertEqual(self.post(self.CSV.replace("512000,Banques,5000000,0", "512000,Banques,5000000,100")).status_code, 400)

    def test_comptes_repetes_fusionnes_en_solde_net(self):
        csv = self.CSV + "512000,Banques (2),0,1000000\n401000,Fournisseurs (2),1000000,0\n"
        r = self.post(csv)
        self.assertEqual(r.status_code, 201, r.content)
        move = AccountMove.objects.get(reference="AN-2026")
        banque = sum((l.debit - l.credit for l in move.lines.filter(account__code="512000")), Decimal("0"))
        self.assertEqual(banque, Decimal("4000000"))
