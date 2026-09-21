import hashlib

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from workflow.models import Circuit

from .models import AuditLog, Document, DocumentType, Dossier, DossierAccess, Version
from .services import AMOUNT_ROLES, WRITE_ROLES, can_see_amount

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
        self.rh = User.objects.create_user(
            email="rh@etls.local", password="MotDePasse#2026", role=User.Role.RH
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


class AccessControlTests(APITestCase):
    """RF-33 (paie→RH), RF-57 (ACL document), RF-58 (ACL dossier), RF-59 (montant)."""

    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@etls.local", password="MotDePasse#2026", role=User.Role.ADMIN, is_staff=True
        )
        self.comptable = User.objects.create_user(
            email="compta@etls.local", password="MotDePasse#2026", role=User.Role.COMPTABLE
        )
        self.direction = User.objects.create_user(
            email="direction@etls.local", password="MotDePasse#2026", role=User.Role.DIRECTION
        )
        self.chef_service = User.objects.create_user(
            email="chef@etls.local", password="MotDePasse#2026", role=User.Role.CHEF_SERVICE
        )
        self.rh = User.objects.create_user(
            email="rh@etls.local", password="MotDePasse#2026", role=User.Role.RH
        )
        self.facture_type = DocumentType.objects.create(
            code="factures_fournisseurs", label="Factures fournisseurs", retention_years=10
        )
        self.paie_type = DocumentType.objects.create(
            code="bulletins_paie", label="Bulletins de paie", retention_years=3, is_restricted_rh=True
        )

    def _auth(self, user):
        tokens = self.client.post(
            "/api/users/token/",
            {"email": user.email, "password": "MotDePasse#2026"},
            format="json",
        ).data
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

    def _file(self, content=b"contenu paie", name="bulletin.pdf"):
        return SimpleUploadedFile(name, content, content_type="application/pdf")

    def _upload(self, user, title="Facture A", doc_type=None, dossier=None, **extra):
        self._auth(user)
        data = {
            "title": title,
            "type": (doc_type or self.facture_type).id,
            "file": self._file(),
            **extra,
        }
        if dossier:
            data["dossier"] = dossier.id
        return self.client.post("/api/documents/documents/", data, format="multipart")

    # ── RF-33 : paie → accès restreint RH ──
    def test_restricted_doc_visible_only_to_rh_and_admin(self):
        resp = self._upload(self.admin, title="Bulletin paie", doc_type=self.paie_type)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        doc_id = resp.data["id"]

        for user in (self.comptable, self.direction, self.chef_service):
            self._auth(user)
            self.assertEqual(
                self.client.get(f"/api/documents/documents/{doc_id}/").status_code,
                status.HTTP_404_NOT_FOUND,
            )
            self.assertNotIn(
                doc_id,
                [d["id"] for d in self.client.get("/api/documents/documents/").data["results"]],
            )

        for user in (self.rh, self.admin):
            self._auth(user)
            self.assertEqual(
                self.client.get(f"/api/documents/documents/{doc_id}/").status_code,
                status.HTTP_200_OK,
            )

    def test_non_admin_cannot_create_restricted_document(self):
        for user in (self.comptable, self.direction, self.chef_service, self.rh):
            resp = self._upload(user, title="Paie", doc_type=self.paie_type)
            self.assertEqual(
                resp.status_code, status.HTTP_403_FORBIDDEN, f"rôle {user.role}"
            )

    def test_restricted_document_not_writable_by_rh(self):
        resp = self._upload(self.admin, title="Paie", doc_type=self.paie_type)
        doc_id = resp.data["id"]
        self._auth(self.rh)
        resp = self.client.patch(
            f"/api/documents/documents/{doc_id}/", {"title": "modif"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    # ── RF-59 : montant masqué ──
    def test_amount_masked_for_non_authorized_roles(self):
        resp = self._upload(self.comptable, amount="1234.56")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        doc_id = resp.data["id"]
        self.assertEqual(resp.data["amount"], "1234.56")

        self._auth(self.chef_service)
        self.assertEqual(
            self.client.get(f"/api/documents/documents/{doc_id}/").data["amount"], None
        )
        self.assertEqual(
            self.client.get("/api/documents/documents/").data["results"][0]["amount"], None
        )

        for user in (self.direction, self.admin):
            self._auth(user)
            self.assertEqual(
                self.client.get(f"/api/documents/documents/{doc_id}/").data["amount"],
                "1234.56",
            )

    def test_non_authorized_role_cannot_set_amount(self):
        resp = self._upload(self.chef_service, amount="9999")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        doc = Document.objects.get(id=resp.data["id"])
        self.assertIsNone(doc.amount)

    # ── RF-57 : ACL document ──
    def test_document_acl_deny_hides_document(self):
        resp = self._upload(self.comptable, title="Facture sensible")
        doc_id = resp.data["id"]

        self._auth(self.admin)
        resp = self.client.post(
            f"/api/documents/documents/{doc_id}/acl/",
            {"user": self.chef_service.id, "permission": "deny"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self._auth(self.chef_service)
        self.assertEqual(
            self.client.get(f"/api/documents/documents/{doc_id}/").status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self._auth(self.comptable)
        self.assertEqual(
            self.client.get(f"/api/documents/documents/{doc_id}/").status_code,
            status.HTTP_200_OK,
        )

    def test_document_acl_write_grant_allows_direction(self):
        resp = self._upload(self.comptable, title="Facture")
        doc_id = resp.data["id"]

        self._auth(self.admin)
        self.client.post(
            f"/api/documents/documents/{doc_id}/acl/",
            {"user": self.direction.id, "permission": "write"},
            format="json",
        )

        self._auth(self.direction)
        resp = self.client.patch(
            f"/api/documents/documents/{doc_id}/", {"title": "Modifié"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["title"], "Modifié")

        self._auth(self.direction)
        resp = self.client.post(
            f"/api/documents/documents/{doc_id}/new_version/",
            {"file": self._file(b"contenu v2")},
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_direction_cannot_write_without_grant(self):
        resp = self._upload(self.comptable, title="Facture")
        doc_id = resp.data["id"]
        self._auth(self.direction)
        resp = self.client.patch(
            f"/api/documents/documents/{doc_id}/", {"title": "Hack"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_only_manager_can_edit_acl(self):
        resp = self._upload(self.comptable, title="Facture")
        doc_id = resp.data["id"]
        self._auth(self.chef_service)
        resp = self.client.post(
            f"/api/documents/documents/{doc_id}/acl/",
            {"user": self.rh.id, "permission": "deny"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    # ── RF-58 : ACL dossier avec héritage ──
    def test_dossier_acl_deny_hides_subtree(self):
        self._auth(self.admin)
        parent = self.client.post(
            "/api/documents/dossiers/", {"name": "Client X"}, format="json"
        ).data
        child = self.client.post(
            "/api/documents/dossiers/",
            {"name": "2026", "parent": parent["id"]},
            format="json",
        ).data
        resp = self._upload(
            self.admin,
            title="Doc du client X",
            dossier=Dossier.objects.get(id=child["id"]),
        )
        doc_id = resp.data["id"]

        self._auth(self.admin)
        self.client.post(
            f"/api/documents/dossiers/{parent['id']}/acl/",
            {"user": self.chef_service.id, "permission": "deny"},
            format="json",
        )

        self._auth(self.chef_service)
        self.assertNotIn(
            parent["id"],
            [d["id"] for d in self.client.get("/api/documents/dossiers/").data["results"]],
        )
        self.assertNotIn(
            child["id"],
            [d["id"] for d in self.client.get("/api/documents/dossiers/").data["results"]],
        )
        self.assertEqual(
            self.client.get(f"/api/documents/documents/{doc_id}/").status_code,
            status.HTTP_404_NOT_FOUND,
        )

        self._auth(self.comptable)
        self.assertEqual(
            self.client.get(f"/api/documents/documents/{doc_id}/").status_code,
            status.HTTP_200_OK,
        )

    def test_dossier_acl_write_grant_allows_creation_in_subtree(self):
        self._auth(self.admin)
        parent = self.client.post(
            "/api/documents/dossiers/", {"name": "Client Y"}, format="json"
        ).data
        child = self.client.post(
            "/api/documents/dossiers/",
            {"name": "2027", "parent": parent["id"]},
            format="json",
        ).data
        self.client.post(
            f"/api/documents/dossiers/{parent['id']}/acl/",
            {"user": self.direction.id, "permission": "write"},
            format="json",
        )

        resp = self._upload(
            self.direction,
            title="Créé par la direction",
            dossier=Dossier.objects.get(id=child["id"]),
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_direction_cannot_create_document_without_grant(self):
        self._auth(self.direction)
        resp = self._upload(self.direction, title="Interdit")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


@override_settings(
    STORAGES={"default": {"BACKEND": "django.core.files.storage.InMemoryStorage"}}
)
class AuditTrailTests(APITestCase):
    """RF-63/64/65 : traçabilité création / modif / suppression / téléchargement."""

    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@etls.local", password="MotDePasse#2026", role=User.Role.ADMIN, is_staff=True
        )
        self.comptable = User.objects.create_user(
            email="compta@etls.local", password="MotDePasse#2026", role=User.Role.COMPTABLE
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

    def _upload(self, user):
        self._auth(user)
        return self.client.post(
            "/api/documents/documents/",
            {
                "title": "Facture auditable",
                "type": self.facture_type.id,
                "file": SimpleUploadedFile("facture.pdf", b"contenu", content_type="application/pdf"),
            },
            format="multipart",
        )

    def _log(self, **filters):
        return AuditLog.objects.filter(**filters).first()

    def test_create_is_traced(self):
        resp = self._upload(self.comptable)
        entry = self._log(object_type="document", object_id=resp.data["id"], action=AuditLog.Action.CREATE)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.user, self.comptable)
        self.assertEqual(entry.detail["title"], "Facture auditable")

    def test_new_version_is_traced(self):
        doc_id = self._upload(self.comptable).data["id"]
        self._auth(self.comptable)
        self.client.post(
            f"/api/documents/documents/{doc_id}/new_version/",
            {"file": SimpleUploadedFile("facture.pdf", b"contenu v2", content_type="application/pdf")},
            format="multipart",
        )
        entry = self._log(object_type="document", object_id=doc_id, action=AuditLog.Action.UPDATE)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.detail["new_version"], 2)

    def test_download_is_traced(self):
        doc_id = self._upload(self.comptable).data["id"]
        self._auth(self.comptable)
        resp = self.client.get(f"/api/documents/documents/{doc_id}/download/")
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        entry = self._log(object_type="document", object_id=doc_id, action=AuditLog.Action.DOWNLOAD)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.detail["version"], 1)

    def test_acl_grant_is_traced(self):
        doc_id = self._upload(self.admin).data["id"]
        self._auth(self.admin)
        self.client.post(
            f"/api/documents/documents/{doc_id}/acl/",
            {"user": self.comptable.id, "permission": "write"},
            format="json",
        )
        entry = self._log(object_type="document", object_id=doc_id, action=AuditLog.Action.ACL_GRANT)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.detail["permission"], "write")

    def test_delete_is_traced(self):
        doc_id = self._upload(self.comptable).data["id"]
        self._auth(self.comptable)
        self.assertEqual(
            self.client.delete(f"/api/documents/documents/{doc_id}/").status_code,
            status.HTTP_204_NO_CONTENT,
        )
        entry = self._log(object_type="document", object_id=doc_id, action=AuditLog.Action.DELETE)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.detail["title"], "Facture auditable")

    def test_audit_endpoint_admin_only(self):
        self._upload(self.comptable)
        self._auth(self.comptable)
        self.assertEqual(
            self.client.get("/api/documents/audit/").status_code, status.HTTP_403_FORBIDDEN
        )
        self._auth(self.admin)
        resp = self.client.get("/api/documents/audit/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(resp.data["results"]), 1)

    def test_audit_endpoint_filters_by_object(self):
        doc_id = self._upload(self.comptable).data["id"]
        self._auth(self.admin)
        resp = self.client.get(f"/api/documents/audit/?object_id={doc_id}")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(all(d["object_id"] == doc_id for d in resp.data["results"]))


@override_settings(
    STORAGES={"default": {"BACKEND": "django.core.files.storage.InMemoryStorage"}}
)
class SearchAndFacetsTests(APITestCase):
    """RF-23/26/27 : recherche full-text et facettes."""

    def setUp(self):
        self.comptable = User.objects.create_user(
            email="compta@etls.local", password="MotDePasse#2026", role=User.Role.COMPTABLE
        )
        self.admin = User.objects.create_user(
            email="admin@etls.local", password="MotDePasse#2026", role=User.Role.ADMIN, is_staff=True
        )
        self.facture_type = DocumentType.objects.create(
            code="factures_fournisseurs", label="Factures fournisseurs", retention_years=10
        )
        self.devis_type = DocumentType.objects.create(
            code="devis", label="Devis", retention_years=5
        )
        self.circuit = Circuit.objects.create(code="c1", label="Circuit", max_days=5)

    def _upload(self, title, counterparty="", extracted_text="", status=Document.Status.IN_VALIDATION):
        self._auth(self.comptable)
        resp = self.client.post(
            "/api/documents/documents/",
            {
                "title": title,
                "type": self.facture_type.id if "Facture" in title else self.devis_type.id,
                "counterparty": counterparty,
                "file": SimpleUploadedFile("f.pdf", b"contenu", content_type="application/pdf"),
            },
            format="multipart",
        )
        doc = Document.objects.get(id=resp.data["id"])
        if extracted_text:
            doc.extracted_text = extracted_text
        if status:
            doc.status = status
        if extracted_text or status:
            doc.save()
        return doc.id

    def _auth(self, user):
        tokens = self.client.post(
            "/api/users/token/",
            {"email": user.email, "password": "MotDePasse#2026"},
            format="json",
        ).data
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

    def test_search_matches_title_and_counterparty(self):
        self._upload("Facture electricite", counterparty="EDF SA")
        self._upload("Facture telephone", counterparty="Orange")
        self._upload("Devis travaux", counterparty="Macon")
        self._auth(self.comptable)
        resp = self.client.get("/api/documents/documents/?search=EDF")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["results"]), 1)
        self.assertEqual(resp.data["results"][0]["title"], "Facture electricite")

    def test_search_matches_ocr_invisible_text(self):
        self._upload("Facture electricite", extracted_text="montant electricite fournisseur")
        self._upload("Devis travaux")
        self._auth(self.comptable)
        resp = self.client.get("/api/documents/documents/?search=electricite")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["results"]), 1)

    def test_search_respects_visibility(self):
        # Document placé dans un dossier refusé à la compta via ACL (RF-58).
        dossier = Dossier.objects.create(name="Dossier secret", created_by=self.admin)
        DossierAccess.objects.create(
            dossier=dossier, user=self.comptable,
            permission=DossierAccess.Permission.DENY, granted_by=self.admin,
        )
        doc = Document.objects.create(
            title="Facture confidentielle",
            type=self.facture_type,
            dossier=dossier,
            created_by=self.admin,
        )
        Version.objects.create(
            document=doc, number=1,
            file=SimpleUploadedFile("f.pdf", b"c", content_type="application/pdf"),
            sha256="abc", size=1, original_filename="f.pdf", created_by=self.admin,
        )
        doc.current_version = doc.versions.first()
        doc.save(update_fields=["current_version"])
        self._auth(self.comptable)
        resp = self.client.get("/api/documents/documents/?search=confidentielle")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["results"]), 0)
        self._auth(self.admin)
        resp = self.client.get("/api/documents/documents/?search=confidentielle")
        self.assertEqual(len(resp.data["results"]), 1)

    def test_facets_counts(self):
        self._upload("Facture electricite")
        self._upload("Facture telephone")
        self._upload("Devis travaux")
        self._auth(self.comptable)
        resp = self.client.get("/api/documents/documents/facets/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["total"], 3)
        self.assertEqual(resp.data["by_status"]["in_validation"], 3)
        by_type = {t["type__label"]: t["count"] for t in resp.data["by_type"]}
        self.assertEqual(by_type["Factures fournisseurs"], 2)
        self.assertEqual(by_type["Devis"], 1)

    def test_facets_respects_search_filter(self):
        self._upload("Facture electricite")
        self._upload("Facture telephone")
        self._upload("Devis travaux")
        self._auth(self.comptable)
        resp = self.client.get("/api/documents/documents/facets/?search=telephone")
        self.assertEqual(resp.data["total"], 1)


class RoleMatrixUnitTests(TestCase):
    """Incrément 12 : la matrice RBAC couvre les 12 fonctions ETSL (sans I/O)."""

    def _user(self, role):
        return User(role=role)

    def test_amount_roles(self):
        for role in (
            User.Role.ADMIN,
            User.Role.COMPTABLE,
            User.Role.FINANCE,
            User.Role.DIRECTION,
            User.Role.PDG,
            User.Role.DGA,
        ):
            self.assertIn(role, AMOUNT_ROLES)
            self.assertTrue(can_see_amount(self._user(role)))
        for role in (User.Role.CHEF_SERVICE, User.Role.SECRETAIRE_GENERAL, User.Role.HSE):
            self.assertNotIn(role, AMOUNT_ROLES)
            self.assertFalse(can_see_amount(self._user(role)))

    def test_write_roles_exclude_rh_and_direction(self):
        for role in (
            User.Role.SECRETAIRE_GENERAL,
            User.Role.FINANCE,
            User.Role.QAQC,
            User.Role.HSE,
            User.Role.LOGISTIQUE,
            User.Role.MAINTENANCE,
            User.Role.CHEF_ATELIER,
        ):
            self.assertIn(role, WRITE_ROLES)
        self.assertNotIn(User.Role.RH, WRITE_ROLES)
        self.assertNotIn(User.Role.DIRECTION, WRITE_ROLES)
