"""Moteur de workflow (RF-29 à 31) — state machine custom Django."""

from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from documents.models import AuditLog, Document
from users.models import User

from .models import Circuit, CircuitStep, Task, TaskComment


def _find_assignee(role):
    """Rôle → premier utilisateur actif du rôle (ajustable par délégation, RF-36)."""
    return (
        User.objects.filter(role=role, is_active=True)
        .order_by("created_at")
        .first()
    )


def _create_task(document, circuit, step, assigned_by):
    return Task.objects.create(
        document=document,
        circuit=circuit,
        step=step,
        assigned_to=_find_assignee(step.actor_role),
        assigned_by=assigned_by,
        status=Task.Status.PENDING,
        due_date=timezone.now() + timedelta(days=step.max_days),
    )


def start_circuit(document, user):
    """Soumission d'un brouillon : démarre le circuit (RF-29 à 31, RF-40)."""
    if document.status != Document.Status.DRAFT:
        raise ValidationError("Seul un document brouillon peut être soumis au circuit.")
    circuit = None
    if document.type_id and document.type.circuit_id:
        circuit = document.type.circuit
    if circuit is None:
        circuit = Circuit.objects.filter(is_active=True).order_by("code").first()
    if circuit is None:
        raise ValidationError("Aucun circuit de validation n'est configuré.")
    step = circuit.steps.order_by("order").first()
    if step is None:
        raise ValidationError(f"Le circuit {circuit.code} ne contient aucune étape.")

    task = _create_task(document, circuit, step, user)

    # RF-40 : action automatique au changement de statut.
    document.status = Document.Status.IN_VALIDATION
    document.submitted_at = timezone.now()
    document.save(update_fields=["status", "submitted_at"])

    return task


def complete_task(task, user):
    """Termine l'étape courante : avance au circuit suivant ou archive (RF-40)."""
    if task.status != Task.Status.PENDING:
        raise ValidationError("Cette tâche n'est pas en attente.")
    if task.assigned_to_id and task.assigned_to_id != user.id and not user.is_staff:
        raise PermissionDenied("Seul l'assigné peut terminer cette tâche.")

    task.status = Task.Status.DONE
    task.completed_at = timezone.now()
    task.save(update_fields=["status", "completed_at"])

    next_step = (
        task.circuit.steps.filter(order__gt=task.step.order).order_by("order").first()
    )
    if next_step is None:
        # Dernière étape → archivage automatique (RF-40, RF-41).
        document = task.document
        document.status = Document.Status.ARCHIVED
        document.archived_at = timezone.now()
        document.save(update_fields=["status", "archived_at"])
        return None
    return _create_task(task.document, task.circuit, next_step, user)


def reject_task(task, user, reason):
    """Rejet motivé : retour au statut rejeté, tâches en attente fermées (RF-39/41)."""
    if task.status != Task.Status.PENDING:
        raise ValidationError("Cette tâche n'est pas en attente.")
    if task.assigned_to_id and task.assigned_to_id != user.id and not user.is_staff:
        raise PermissionDenied("Seul l'assigné peut rejeter cette tâche.")
    if not reason:
        raise ValidationError("Le motif de rejet est obligatoire (RF-39).")

    task.status = Task.Status.REJECTED
    task.completed_at = timezone.now()
    task.save(update_fields=["status", "completed_at"])

    document = task.document
    document.tasks.filter(status=Task.Status.PENDING).exclude(id=task.id).update(
        status=Task.Status.REJECTED
    )
    document.status = Document.Status.REJECTED
    document.rejected_at = timezone.now()
    document.rejection_reason = reason
    document.save(update_fields=["status", "rejected_at", "rejection_reason"])
    return document


def delegate_task(task, user, to_user):
    """Délégation / transfert de tâche (RF-36)."""
    if task.status != Task.Status.PENDING:
        raise ValidationError("Seule une tâche en attente peut être déléguée.")
    if task.assigned_to_id and task.assigned_to_id != user.id and not user.is_staff:
        raise PermissionDenied("Seul l'assigné peut déléguer cette tâche.")
    if to_user is None:
        raise ValidationError("L'utilisateur destinataire est obligatoire.")

    previous = task.assigned_to
    task.assigned_to = to_user
    task.assigned_by = user
    task.status = Task.Status.PENDING
    task.save(update_fields=["assigned_to", "assigned_by", "status"])
    TaskComment.objects.create(
        task=task,
        author=user,
        text=(
            f"Délégation de {previous.email if previous else '—'} "
            f"à {to_user.email} (RF-36)."
        ),
    )
    return task


def add_comment(task, user, text):
    """Commentaire / annotation dans le circuit (RF-38)."""
    return TaskComment.objects.create(task=task, author=user, text=text)
