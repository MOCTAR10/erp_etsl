import hashlib

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from documents.models import Document, DocumentType
from workflow.models import Circuit, CircuitStep, Task, TaskComment

User = get_user_model()


@override_settings(
    STORAGES={"default": {"BACKEND": "django.core.files.storage.InMemoryStorage"}}
)
class WorkflowTests(APITestCase):
    def setUp(self):
        self.chef_service = User.objects.create_user(
            email="chef@etls.local", password="MotDePasse#2026", role=User.Role.CHEF_SERVICE
        )
        self.comptable = User.objects.create_user(
            email="compta@etls.local", password="MotDePasse#2026", role=User.Role.COMPTABLE
        )
        self.admin = User.objects.create_user(
            email="admin@etls.local", password="MotDePasse#2026", role=User.Role.ADMIN, is_staff=True
        )
        self.direction = User.objects.create_user(
            email="direction@etls.local", password="MotDePasse#2026", role=User.Role.DIRECTION
        )
        self.circuit = Circuit.objects.create(
            code="circuit_comptabilite", label="Comptabilité", max_days=5
        )
        self.step1 = CircuitStep.objects.create(
            circuit=self.circuit, order=1, name="Réception",
            actor_role=User.Role.CHEF_SERVICE, max_days=1,
        )
        self.step2 = CircuitStep.objects.create(
            circuit=self.circuit, order=2, name="Saisie",
            actor_role=User.Role.COMPTABLE, max_days=2,
        )
        self.step3 = CircuitStep.objects.create(
            circuit=self.circuit, order=3, name="Validation saisie",
            actor_role=User.Role.ADMIN, max_days=2,
        )
        self.facture_type = DocumentType.objects.create(
            code="factures_fournisseurs", label="Factures fournisseurs",
            retention_years=10, circuit=self.circuit,
        )

    def _auth(self, user):
        tokens = self.client.post(
            "/api/users/token/",
            {"email": user.email, "password": "MotDePasse#2026"},
            format="json",
        ).data
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

    def _upload(self, user, doc_type=None, title="Facture X"):
        self._auth(user)
        resp = self.client.post(
            "/api/documents/documents/",
            {
                "title": title,
                "type": (doc_type or self.facture_type).id,
                "file": SimpleUploadedFile(
                    "facture.pdf", b"contenu", content_type="application/pdf"
                ),
            },
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        return resp.data["id"]

    def _submit(self, user, doc_id):
        self._auth(user)
        return self.client.post(
            "/api/workflow/tasks/submit/", {"document": doc_id}, format="json"
        )

    def _complete(self, user, task_id):
        self._auth(user)
        return self.client.post(f"/api/workflow/tasks/{task_id}/complete/")

    def test_submit_starts_circuit(self):
        doc_id = self._upload(self.comptable)
        resp = self._submit(self.comptable, doc_id)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["step_order"], 1)
        self.assertEqual(resp.data["assigned_to_email"], self.chef_service.email)

        self._auth(self.comptable)
        doc = self.client.get(f"/api/documents/documents/{doc_id}/").data
        self.assertEqual(doc["status"], Document.Status.IN_VALIDATION)
        self.assertIsNotNone(doc["submitted_at"])

    def test_complete_advances_to_next_step(self):
        doc_id = self._upload(self.comptable)
        task_id = self._submit(self.comptable, doc_id).data["id"]

        resp = self._complete(self.chef_service, task_id)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["step_order"], 2)
        self.assertEqual(resp.data["assigned_to_email"], self.comptable.email)

    def test_complete_last_step_archives_document(self):
        doc_id = self._upload(self.comptable)
        task1 = self._submit(self.comptable, doc_id).data["id"]
        task2 = self._complete(self.chef_service, task1).data["id"]
        task3 = self._complete(self.comptable, task2).data["id"]

        resp = self._complete(self.admin, task3)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("archivé", resp.data["detail"])

        self._auth(self.comptable)
        doc = self.client.get(f"/api/documents/documents/{doc_id}/").data
        self.assertEqual(doc["status"], Document.Status.ARCHIVED)
        self.assertIsNotNone(doc["archived_at"])

    def test_reject_with_reason(self):
        doc_id = self._upload(self.comptable)
        task_id = self._submit(self.comptable, doc_id).data["id"]

        self._auth(self.chef_service)
        resp = self.client.post(
            f"/api/workflow/tasks/{task_id}/reject/",
            {"reason": "Facture erronée, à refaire."},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self._auth(self.comptable)
        doc = self.client.get(f"/api/documents/documents/{doc_id}/").data
        self.assertEqual(doc["status"], Document.Status.REJECTED)
        self.assertEqual(doc["rejection_reason"], "Facture erronée, à refaire.")

        task = Task.objects.get(id=task_id)
        self.assertEqual(task.status, Task.Status.REJECTED)

    def test_reject_requires_reason(self):
        doc_id = self._upload(self.comptable)
        task_id = self._submit(self.comptable, doc_id).data["id"]
        self._auth(self.chef_service)
        resp = self.client.post(
            f"/api/workflow/tasks/{task_id}/reject/", {}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delegate_transfers_task(self):
        doc_id = self._upload(self.comptable)
        task_id = self._submit(self.comptable, doc_id).data["id"]
        self._auth(self.chef_service)
        resp = self.client.post(
            f"/api/workflow/tasks/{task_id}/delegate/",
            {"user": self.comptable.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["assigned_to_email"], self.comptable.email)
        self.assertTrue(TaskComment.objects.filter(task_id=task_id).exists())

    def test_comments_in_circuit(self):
        doc_id = self._upload(self.comptable)
        task_id = self._submit(self.comptable, doc_id).data["id"]
        self._auth(self.chef_service)
        resp = self.client.post(
            f"/api/workflow/tasks/{task_id}/comments/",
            {"text": "Pièce à joindre."},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        resp = self.client.get(f"/api/workflow/tasks/{task_id}/comments/")
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["text"], "Pièce à joindre.")

    def test_task_list_shows_only_own_tasks(self):
        doc1 = self._upload(self.comptable)
        doc2 = self._upload(self.comptable)
        self._submit(self.comptable, doc1)
        self._submit(self.comptable, doc2)

        self._auth(self.comptable)
        resp = self.client.get("/api/workflow/tasks/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["results"]), 0)

        self._auth(self.chef_service)
        resp = self.client.get("/api/workflow/tasks/")
        self.assertEqual(len(resp.data["results"]), 2)
        self.assertTrue(all(t["assigned_to_email"] == self.chef_service.email for t in resp.data["results"]))

    def test_cannot_complete_other_task(self):
        doc_id = self._upload(self.comptable)
        task_id = self._submit(self.comptable, doc_id).data["id"]
        self._auth(self.comptable)
        resp = self.client.post(f"/api/workflow/tasks/{task_id}/complete/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_submit_requires_write_permission(self):
        doc_id = self._upload(self.comptable)
        self._auth(self.direction)
        resp = self._submit(self.direction, doc_id)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_restricted_document_task_hidden(self):
        paie_type = DocumentType.objects.create(
            code="bulletins_de_paie", label="Bulletins de paie",
            retention_years=3, is_restricted_rh=True,
        )
        doc_id = self._upload(self.admin, doc_type=paie_type, title="Bulletin paie")
        self._submit(self.admin, doc_id)

        self._auth(self.chef_service)
        resp = self.client.get("/api/workflow/tasks/")
        self.assertEqual(len(resp.data["results"]), 0)

    def test_circuits_listed(self):
        self._auth(self.comptable)
        resp = self.client.get("/api/workflow/circuits/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(len(resp.data["results"][0]["steps"]), 3)

    def test_summary_dashboard_admin_only(self):
        doc_id = self._upload(self.comptable)
        self._submit(self.comptable, doc_id)
        self._auth(self.comptable)
        self.assertEqual(
            self.client.get("/api/workflow/tasks/summary/").status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self._auth(self.admin)
        resp = self.client.get("/api/workflow/tasks/summary/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(resp.data["total_pending"], 1)
