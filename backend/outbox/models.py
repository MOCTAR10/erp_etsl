"""Outbox pattern — événements inter-modules consommés par Celery (incr.17).

Toute action transverse écrite dans l'outbox est livrée de manière **asynchrone
et garantie** au(x) souscripteur(s) (aucune règle métier couplée par signaux).
"""

import uuid

from django.db import models


class OutboxEvent(models.Model):
    """Événement à livrer (transactionnel à la publication, consommé par beat)."""

    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        DELIVERED = "delivered", "Livrée"
        FAILED = "failed", "Échouée (abandonnée)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    topic = models.CharField(max_length=60, verbose_name="Sujet", db_index=True)
    payload = models.JSONField(default=dict, blank=True, verbose_name="Données")
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="Statut",
        db_index=True,
    )
    attempt_count = models.PositiveSmallIntegerField(default=0, verbose_name="Tentatives")
    error_message = models.TextField(blank=True, verbose_name="Dernière erreur")
    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True, verbose_name="Livrée le")

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Événement outbox"
        verbose_name_plural = "Événements outbox"
        indexes = [models.Index(fields=["status", "created_at"])]

    def __str__(self):
        return f"{self.topic} [{self.status}]"


def publish(topic, payload=None):
    """Publie un événement (appelé dans la même transaction que l'action source)."""
    return OutboxEvent.objects.create(topic=topic, payload=payload or {})