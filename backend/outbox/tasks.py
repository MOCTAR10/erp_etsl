"""Tâches Celery outbox — livraison des événements + souscripteurs (incr.17)."""

from celery import shared_task
from django.utils import timezone

from users.models import User
from workflow.models import Notification

from .models import OutboxEvent
from .subscribers import SUBSCRIBERS, subscriber

MAX_ATTEMPTS = 3


@subscriber("accounting.move.posted")
def notify_admins_move_posted(event):
    """Exemple de souscripteur : alerte aux admins après une écriture importée."""
    number = (event.payload or {}).get("number")
    for admin in User.objects.filter(role=User.Role.ADMIN, is_active=True):
        Notification.objects.create(
            user=admin,
            subject="Écriture comptabilisée",
            message=f"L'écriture {number} a été comptabilisée (import).",
            kind="info",
        )


def _mark(event, status, **extra):
    for field, value in extra.items():
        setattr(event, field, value)
    event.status = status
    if status == OutboxEvent.Status.DELIVERED:
        event.delivered_at = timezone.now()
    event.save(
        update_fields=["status", "attempt_count", "error_message", "delivered_at"]
    )


@shared_task
def dispatch_outbox(limit=50):
    """Livraison des événements en attente (lot borné — appelé par beat)."""
    events = list(
        OutboxEvent.objects.filter(status=OutboxEvent.Status.PENDING)
        .order_by("created_at")[:limit]
    )
    delivered = failed = 0
    for event in events:
        handlers = SUBSCRIBERS.get(event.topic, [])
        if not handlers:
            # Pas de souscripteur : l'événement est consommé sans effet de bord.
            event.attempt_count += 1
            _mark(event, OutboxEvent.Status.DELIVERED)
            delivered += 1
            continue
        try:
            for handler in handlers:
                handler(event)
            event.attempt_count += 1
            _mark(event, OutboxEvent.Status.DELIVERED)
            delivered += 1
        except Exception as exc:  # noqa: BLE001 — retry borné puis abandon
            event.attempt_count += 1
            event.error_message = repr(exc)
            if event.attempt_count >= MAX_ATTEMPTS:
                _mark(event, OutboxEvent.Status.FAILED)
                failed += 1
            else:
                event.save(update_fields=["attempt_count", "error_message"])
    return {"processed": len(events), "delivered": delivered, "failed": failed}