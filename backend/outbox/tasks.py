"""Tâches Celery outbox — livraison des événements + souscripteurs (incr.17)."""

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .models import OutboxEvent
from .subscribers import SUBSCRIBERS

MAX_ATTEMPTS = 3


# Abonné d'exemple `accounting.move.posted` retiré (écart E3 de ETSL-ERP-INT) : aucun module ne publiait ce sujet.
# Les abonnés réels sont déclarés dans les apps (`@subscriber`) ; les sujets publiés sans abonné interne sont
# listés dans `subscribers.SUJETS_SANS_ABONNE_INTERNE`.


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
    """Livraison des événements en attente (lot borné — appelé par beat).

    Chaque événement est RÉSERVÉ (`select_for_update(skip_locked=True)`) pendant son traitement : deux workers
    / deux déclenchements simultanés de beat ne livrent jamais le même événement deux fois (sinon doublons de
    notifications et de webhooks).
    """
    ids = list(
        OutboxEvent.objects.filter(status=OutboxEvent.Status.PENDING)
        .order_by("created_at")
        .values_list("id", flat=True)[:limit]
    )
    delivered = failed = processed = 0
    for event_id in ids:
        with transaction.atomic():
            event = (
                OutboxEvent.objects.select_for_update(skip_locked=True)
                .filter(pk=event_id, status=OutboxEvent.Status.PENDING)
                .first()
            )
            if event is None:  # déjà pris par un autre worker, ou déjà livré
                continue
            processed += 1
            handlers = SUBSCRIBERS.get(event.topic, []) + SUBSCRIBERS.get("*", [])
            if not handlers:
                # Pas de souscripteur : l'événement est consommé sans effet de bord.
                event.attempt_count += 1
                _mark(event, OutboxEvent.Status.DELIVERED)
                delivered += 1
                continue
            try:
                with transaction.atomic():  # point de sauvegarde : un handler en erreur SQL n'abîme pas la réservation
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
    return {"processed": processed, "delivered": delivered, "failed": failed}
