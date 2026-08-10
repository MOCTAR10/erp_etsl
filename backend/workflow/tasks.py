"""Tâches Celery du module workflow — relances / escalade (RF-35)."""

from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from users.models import User

from .models import Task
from .notifications import escalate_task, remind_assignee


@shared_task
def check_overdue_tasks():
    """Relance les tâches en retard et escalade N+1 si le délai d'étape est dépassé."""
    now = timezone.now()
    overdue = Task.objects.filter(
        status=Task.Status.PENDING, due_date__lt=now
    ).select_related("document", "step", "circuit", "assigned_to")

    reminded = 0
    escalated = 0
    for task in overdue:
        remind_assignee(task)
        reminded += 1
        # Escalade N+1 (RF-35) : délai d'étape dépassé → notification à l'administration.
        if now >= task.due_date + timedelta(days=task.step.max_days or 1):
            for admin in User.objects.filter(
                role=User.Role.ADMIN, is_active=True
            ):
                escalate_task(task, admin)
                escalated += 1
    return {"reminded": reminded, "escalated": escalated}
