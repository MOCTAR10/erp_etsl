"""Audit métier GED (2026-10-16) — intégrité des documents archivés / en validation.

D6 : un document archivé (rétention légale) ne se supprime pas, ne reçoit ni nouvelle version
     ni rollback ; un document en validation n'a pas son contenu modifié sous les pieds des validateurs.
D7 : le rollback respecte le verrou check-out d'un autre utilisateur.
"""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from documents.models import Document, Version
from users.models import User


@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.InMemoryStorage"}})
class IntegriteDocumentTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@etls.ga", password="x-Audit-2026", role=User.Role.ADMIN, is_staff=True
        )
        self.other = User.objects.create_user(
            email="autre@etls.ga", password="x-Audit-2026", role=User.Role.SECRETAIRE_GENERAL
        )
        self.client.force_authenticate(self.admin)

    def doc(self, status):
        d = Document.objects.create(title=f"Doc {status}", status=status)
        v = Version.objects.create(
            document=d, number=1, file=SimpleUploadedFile("a.pdf", b"v1"), sha256="a" * 64,
            size=2, original_filename="a.pdf", created_by=self.admin,
        )
        d.current_version = v
        d.save(update_fields=["current_version"])
        return d

    def test_document_archive_non_supprimable(self):
        d = self.doc(Document.Status.ARCHIVED)
        r = self.client.delete(f"/api/documents/documents/{d.pk}/")
        self.assertEqual(r.status_code, 400, r.content)
        self.assertTrue(Document.objects.filter(pk=d.pk).exists())

    def test_document_en_validation_non_supprimable(self):
        d = self.doc(Document.Status.IN_VALIDATION)
        self.assertEqual(self.client.delete(f"/api/documents/documents/{d.pk}/").status_code, 400)

    def test_brouillon_supprimable(self):
        d = self.doc(Document.Status.DRAFT)
        self.assertEqual(self.client.delete(f"/api/documents/documents/{d.pk}/").status_code, 204)

    def test_nouvelle_version_refusee_sur_archive_et_en_validation(self):
        for st in (Document.Status.ARCHIVED, Document.Status.IN_VALIDATION):
            d = self.doc(st)
            r = self.client.post(
                f"/api/documents/documents/{d.pk}/new_version/",
                {"file": SimpleUploadedFile("b.pdf", b"v2")},
                format="multipart",
            )
            self.assertEqual(r.status_code, 400, (st, r.content))
            self.assertEqual(d.versions.count(), 1)

    def test_rollback_refuse_sur_archive(self):
        d = self.doc(Document.Status.ARCHIVED)
        r = self.client.post(
            f"/api/documents/documents/{d.pk}/rollback/",
            {"version_id": str(d.current_version_id)}, format="json",
        )
        self.assertEqual(r.status_code, 400, r.content)

    def test_rollback_respecte_le_checkout_d_un_autre(self):
        d = self.doc(Document.Status.DRAFT)
        v2 = Version.objects.create(
            document=d, number=2, file=SimpleUploadedFile("c.pdf", b"v2"), sha256="b" * 64,
            size=2, original_filename="c.pdf", created_by=self.admin,
        )
        d.current_version = v2
        d.checked_out_by = self.other
        d.save()
        r = self.client.post(
            f"/api/documents/documents/{d.pk}/rollback/",
            {"version_id": str(d.versions.get(number=1).pk)}, format="json",
        )
        self.assertEqual(r.status_code, 403, r.content)
        d.refresh_from_db()
        self.assertEqual(d.current_version_id, v2.pk)
