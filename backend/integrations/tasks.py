"""Tâches Celery d'intégration."""

from celery import shared_task

from .gr import retry_due_deliveries


@shared_task
def retry_webhook_deliveries(limit=50):
    """Relance les webhooks en attente dont l'échéance est atteinte (appelé par beat toutes les minutes)."""
    return {"retried": retry_due_deliveries(limit)}
