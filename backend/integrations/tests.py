from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase

from accounting_kernel.models import AccountMove, Journal
from referentiels.models import Account, Currency, Partner

from .importers import run_import
from .models import BatchRow, ImportBatch

User = get_user_model()


PARTNERS_CSV = (
    "code,name,kind,tax_id\n"
    "CLI-001,Client A,client,123456\n"
    "FOU-001,Fournisseur B,fournisseur,789\n"
)


class PartnerImportTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@etls.local", password="MotDePasse#2026",
            role=User.Role.ADMIN, is_staff=True,
        )
        Currency.objects.create(code="XAF", label="Franc CFA", symbol="FCFA")

    def _import(self, content=PARTNERS_CSV, connector="partners", force=False):
        return run_import(
            connector, "partners.csv", content.encode("utf-8"), user=self.admin, force=force
        )

    def test_import_creates_partners(self):
        batch, replayed = self._import()
        self.assertFalse(replayed)
        self.assertEqual(batch.status, ImportBatch.Status.SUCCESS)
        self.assertEqual(batch.created_rows, 2)
        self.assertEqual(Partner.objects.count(), 2)
        self.assertEqual(Partner.objects.get(code="CLI-001").kind, Partner.Kind.CLIENT)

    def test_same_file_is_replayed_not_reimported(self):
        batch, _ = self._import()
        replay, replayed = self._import()
        self.assertTrue(replayed)
        self.assertEqual(replay.id, batch.id)
        self.assertEqual(Partner.objects.count(), 2)

    def test_forced_reimport_updates_not_duplicates(self):
        self._import()
        batch, replayed = self._import(force=True)
        self.assertFalse(replayed)
        self.assertEqual(batch.status, ImportBatch.Status.SUCCESS)
        self.assertEqual(batch.updated_rows, 2)
        self.assertEqual(batch.created_rows, 0)
        self.assertEqual(Partner.objects.count(), 2)

    def test_bad_row_is_logged_batch_partial(self):
        content = (
            "code,name,kind\n"
            "OK-001,Correct,client\n"
            "BAD-001,Pas ok,inexistant\n"
        )
        batch, _ = self._import(content=content)
        self.assertEqual(batch.status, ImportBatch.Status.PARTIAL)
        self.assertEqual(batch.created_rows, 1)
        self.assertEqual(batch.error_rows, 1)
        error = batch.rows.get(status=BatchRow.Status.ERROR)
        self.assertIn("kind invalide", error.error_message)


class GLImportSuites(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@etls.local", password="MotDePasse#2026",
            role=User.Role.ADMIN, is_staff=True,
        )
        call_command("seed_accounting", year=2026)
        Account.objects.create(
            code="411000", label="Clients", account_class=4,
            account_type=Account.AccountType.ASSET,
        )
        Account.objects.create(
            code="701000", label="Ventes", account_class=7,
            account_type=Account.AccountType.INCOME,
        )

    GL_CSV = (
        "date,journal,account_debit,account_credit,amount,reference,label\n"
        "2026-01-15,VTE,411000,701000,1000.00,FAC-001,Facture test\n"
    )

    def test_gl_import_posts_move(self):
        # Données issues de l'import SAGE → écritures comptabilisées.
        batch = run_import(
            "gl", "reprise.csv", self.GL_CSV.encode("utf-8"), user=self.admin
        )[0]
        self.assertEqual(batch.status, ImportBatch.Status.SUCCESS)
        self.assertEqual(batch.created_rows, 1)
        move = AccountMove.objects.get(reference="FAC-001")
        self.assertEqual(move.number, "VTE00001")
        self.assertEqual(move.status, AccountMove.Status.POSTED)
        self.assertEqual(move.source, "integrations")

    def test_gl_forced_reimport_skips_duplicates(self):
        run_import("gl", "reprise.csv", self.GL_CSV.encode("utf-8"), user=self.admin)
        batch = run_import(
            "gl", "reprise.csv", self.GL_CSV.encode("utf-8"), user=self.admin, force=True
        )[0]
        self.assertEqual(batch.status, ImportBatch.Status.SUCCESS)
        self.assertEqual(batch.created_rows, 0)
        self.assertEqual(
            batch.rows.filter(status=BatchRow.Status.DUPLICATE).count(), 1
        )
        self.assertEqual(AccountMove.objects.filter(reference="FAC-001").count(), 1)

    def test_gl_bad_account_logs_error_partial(self):
        content = (
            "date,journal,account_debit,account_credit,amount,reference,label\n"
            "2026-01-15,VTE,999999,701000,1000.00,FAC-002,Test\n"
        )
        batch = run_import(
            "gl", "reprise.csv", content.encode("utf-8"), user=self.admin
        )[0]
        self.assertEqual(batch.status, ImportBatch.Status.PARTIAL)
        self.assertEqual(batch.error_rows, 1)
        self.assertIn("compte débit inconnu", batch.rows.get(status=BatchRow.Status.ERROR).error_message)


class ImportAPITests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@etls.local", password="MotDePasse#2026",
            role=User.Role.ADMIN, is_staff=True,
        )
        Currency.objects.create(code="XAF", label="Franc CFA", symbol="FCFA")

    def _upload(self, content=PARTNERS_CSV, connector="partners", force=""):
        file = SimpleUploadedFile(
            "partners.csv", content.encode("utf-8"), content_type="text/csv"
        )
        data = {"connector": connector, "file": file}
        if force:
            data["force"] = force
        return self.client.post(
            "/api/integrations/import/", data, format="multipart"
        )

    def test_upload_requires_auth(self):
        resp = self._upload()
        self.assertIn(
            resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        )

    def test_upload_creates_batch(self):
        self.client.force_authenticate(self.admin)
        resp = self._upload()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data["created_rows"], 2)
        self.assertEqual(resp.data["status"], "success")

    def test_upload_replays_identical_file(self):
        self.client.force_authenticate(self.admin)
        first = self._upload()
        second = self._upload()
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(second.data["id"], first.data["id"])

    def test_upload_rejects_unknown_connector(self):
        self.client.force_authenticate(self.admin)
        resp = self._upload(connector="inconnu")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_batches_list_requires_auth(self):
        resp = self.client.get("/api/integrations/batches/")
        self.assertIn(
            resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        )