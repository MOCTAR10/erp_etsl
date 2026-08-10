import hashlib

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Document, DocumentType, Version

User = get_user_model()


@override_settings(
    STORAGES={"default": {"BACKEND": "django.core.files.storage.InMemoryStorage"}}
)
class DocumentAPITests(APITestCase):
    def setUp(self):
        self.comptable = User.objects.create_user(
            email="compta@etls.local", password="MotDePasse#2026", role=User.Role.COMPTABLE
        )
        self.direction = User.objects.create_user(
            email="direction@etls.local", password="MotDePasse#2026", role=User.Role.DIRECTION
        )
        self.admin = User.objects.create_user(
            email="admin@etls.local", password="MotDePasse#2026", role=User.Role.ADMIN, is_staff=True
        )
        self.other = User.objects.create_user(
            email="autre@etls.local", password="MotDePasse#2026", role=User.Role.CHEF_SERVICE
        )
        self.facture_type = DocumentType.objects.create(
            code="factures_fournisseurs", label="Factures fournisseurs", retention_years=10
        )

    def _auth(self, user):
        tokens = self.client.post(
            "/api/users/token/",
            {"email": user.email, "password": "MotDePasse#2026"},
            format="json",
        ).data
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

    def _file(self, content=b"contenu facture", name="facture.pdf"):
        return SimpleUploadedFile(name, content, content_type="application/pdf")

    def _upload(self, user=None, **extra):
        user = user or self.comptable
        self._auth(user)
        data = {
            "title": "Facture fournisseur X",
            "type": self.facture_type.id,
            "counterparty": "Fournisseur X",
            "amount": "1500.50",
            "file": self._file(),
        }
        data.update(extra)
        return self.client.post("/api/documents/documents/", data, format="multipart")

    def test_upload_creates_document_with_hash(self):
        resp = self._upload()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        doc = Document.objects.get(id=resp.data["id"])
        self.assertEqual(doc.status, Document.Status.DRAFT)
        self.assertEqual(doc.created_by, self.comptable)
        self.assertEqual(doc.sha256, hashlib.sha256(b"contenu facture").hexdigest())
        self.assertEqual(doc.current_version.number, 1)
        self.assertEqual(doc.current_version.sha256, doc.sha256)

    def test_upload_too_large_rejected(self):
        big = SimpleUploadedFile("gros.pdf", b"x" * (11 * 1024 * 1024))
        resp = self._upload(file=big)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("file", resp.data)

    def test_direction_cannot_create(self):
        resp = self._upload(user=self.direction)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_cannot_list(self):
        resp = self.client.get("/api/documents/documents/")
        self.assertIn(resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_new_version_updates_current(self):
        doc_id = self._upload().data["id"]
        self._auth(self.comptable)
        resp = self.client.post(
            f"/api/documents/documents/{doc_id}/new_version/",
            {"file": self._file(b"contenu v2")},
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data["number"], 2)
        doc = Document.objects.get(id=doc_id)
        self.assertEqual(doc.current_version.number, 2)
        self.assertEqual(doc.sha256, hashlib.sha256(b"contenu v2").hexdigest())
        self.assertEqual(doc.versions.count(), 2)

    def test_rollback_restores_previous_version(self):
        doc_id = self._upload().data["id"]
        self._auth(self.comptable)
        self.client.post(
            f"/api/documents/documents/{doc_id}/new_version/",
            {"file": self._file(b"contenu v2")},
            format="multipart",
        )
        doc = Document.objects.get(id=doc_id)
        v1 = Version.objects.get(document=doc, number=1)
        resp = self.client.post(
            f"/api/documents/documents/{doc_id}/rollback/",
            {"version_id": str(v1.id)},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        doc.refresh_from_db()
        self.assertEqual(doc.current_version, v1)
        self.assertEqual(doc.sha256, v1.sha256)

    def test_checkout_blocks_other_user_version(self):
        doc_id = self._upload().data["id"]
        self._auth(self.comptable)
        self.client.post(f"/api/documents/documents/{doc_id}/checkout/")
        self._auth(self.other)
        resp = self.client.post(
            f"/api/documents/documents/{doc_id}/new_version/",
            {"file": self._file(b"contenu v2")},
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self._auth(self.comptable)
        resp = self.client.post(f"/api/documents/documents/{doc_id}/checkin/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        doc = Document.objects.get(id=doc_id)
        self.assertFalse(doc.is_checked_out)

    def test_versions_history(self):
        doc_id = self._upload().data["id"]
        self._auth(self.comptable)
        self.client.post(
            f"/api/documents/documents/{doc_id}/new_version/",
            {"file": self._file(b"contenu v2")},
            format="multipart",
        )
        resp = self.client.get(f"/api/documents/documents/{doc_id}/versions/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 2)
        self.assertEqual(resp.data[0]["number"], 2)

    def test_dossier_hierarchy(self):
        self._auth(self.comptable)
        resp = self.client.post(
            "/api/documents/dossiers/", {"name": "Client A"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        parent_id = resp.data["id"]
        resp = self.client.post(
            "/api/documents/dossiers/",
            {"name": "2026", "parent": parent_id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["path"], "Client A / 2026")
