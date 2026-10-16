"""Audit métier workflow (2026-10-16).

W1 : une tâche sans assigné (aucun utilisateur du rôle de l'étape) ne peut être traitée que par
     un utilisateur du rôle requis (ou un admin) — pas par n'importe quel authentifié.
W2 : la transition d'une tâche est atomique (pas de tâche suivante orpheline si l'archivage échoue).
"""

from django.core.exceptions import PermissionDenied
from django.test import TestCase

from documents.models import Document
from users.models import User
from workflow.models import Circuit, CircuitStep, Task
from workflow.services import complete_task, reject_task, start_circuit


class TacheSansAssigneTests(TestCase):
    def setUp(self):
        self.circuit = Circuit.objects.create(code="c-audit", label="Audit", max_days=5)
        self.step = CircuitStep.objects.create(
            circuit=self.circuit, order=1, name="Visa PDG", actor_role=User.Role.PDG, max_days=2
        )
        self.auteur = User.objects.create_user(
            email="auteur@etls.ga", password="x-Audit-2026", role=User.Role.CHEF_SERVICE
        )
        self.intrus = User.objects.create_user(
            email="intrus@etls.ga", password="x-Audit-2026", role=User.Role.LOGISTIQUE
        )
        self.doc = Document.objects.create(title="Contrat", status=Document.Status.DRAFT)
        # AUCUN utilisateur PDG : la tâche est créée sans assigné
        self.task = start_circuit(self.doc, self.auteur)
        self.assertIsNone(self.task.assigned_to)

    def test_intrus_ne_peut_pas_valider_une_etape_pdg(self):
        with self.assertRaises(PermissionDenied):
            complete_task(self.task, self.intrus)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.PENDING)

    def test_intrus_ne_peut_pas_rejeter(self):
        with self.assertRaises(PermissionDenied):
            reject_task(self.task, self.intrus, "non")
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.PENDING)

    def test_utilisateur_du_role_requis_peut_valider(self):
        pdg = User.objects.create_user(
            email="pdg@etls.ga", password="x-Audit-2026", role=User.Role.PDG
        )
        self.assertIsNone(complete_task(self.task, pdg))
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, Document.Status.ARCHIVED)

    def test_admin_peut_toujours_valider(self):
        admin = User.objects.create_user(
            email="adm@etls.ga", password="x-Audit-2026", role=User.Role.ADMIN, is_staff=True
        )
        self.assertIsNone(complete_task(self.task, admin))
