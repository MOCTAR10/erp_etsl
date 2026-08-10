"""Notifications (RF-34/35) — enregistrement + envoi email."""

from django.conf import settings
from django.core.mail import send_mail

from .models import Notification, Task


def notify(user, subject, message, task=None, kind="info"):
    """Crée une notification en base (RF-37) et envoie un email (RF-34)."""
    notification = Notification.objects.create(
        user=user, subject=subject, message=message, task=task, kind=kind
    )
    if user.email:
        try:
            send_mail(
                subject=f"[ETSL Archivage] {subject}",
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=True,
            )
        except Exception:
            # L'email ne doit jamais faire échouer le reste du traitement.
            pass
    return notification


def remind_assignee(task):
    """Relance de l'assigné (RF-35, RF-34)."""
    subject = f"Tâche en retard : {task.step.name} — {task.document.title}"
    message = (
        f"Le document « {task.document.title} » (étape {task.step.name}, circuit "
        f"{task.circuit.label}) devait être traité avant le {task.due_date:%d/%m/%Y}.\n"
        f"Merci de traiter ou déléguer cette tâche."
    )
    return notify(task.assigned_to, subject, message, task=task, kind="reminder")


def escalate_task(task, admin):
    """Escalade N+1 vers l'administration (RF-35)."""
    subject = f"Escalade : {task.step.name} en retard — {task.document.title}"
    message = (
        f"La tâche « {task.step.name} » du document « {task.document.title} » "
        f"(assignée à {task.assigned_to.email if task.assigned_to else '—'}) "
        f"est en retard depuis le {task.due_date:%d/%m/%Y}."
    )
    return notify(admin, subject, message, task=task, kind="escalation")
