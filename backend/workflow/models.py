import uuid

from django.conf import settings
from django.db import models

from users.models import User


class Circuit(models.Model):
    """Circuit de validation (RF-29 à 31) — 3 circuits figés, étapes séquentielles."""

    code = models.SlugField(max_length=60, unique=True)
    label = models.CharField(max_length=120, verbose_name="Libellé")
    max_days = models.PositiveSmallIntegerField(
        verbose_name="Délai max global (jours)", help_text="RF-35"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "Circuit"
        verbose_name_plural = "Circuits"

    def __str__(self):
        return self.label


class CircuitStep(models.Model):
    """Étape d'un circuit — un rôle acteur, un délai max (RF-29 à 31, RF-35)."""

    circuit = models.ForeignKey(Circuit, on_delete=models.CASCADE, related_name="steps")
    order = models.PositiveSmallIntegerField(verbose_name="Ordre")
    name = models.CharField(max_length=120, verbose_name="Nom de l'étape")
    actor_role = models.CharField(
        max_length=20,
        choices=User.Role.choices,
        verbose_name="Rôle acteur",
    )
    max_days = models.PositiveSmallIntegerField(
        default=1, verbose_name="Délai max (jours)"
    )

    class Meta:
        ordering = ["circuit", "order"]
        verbose_name = "Étape de circuit"
        verbose_name_plural = "Étapes de circuit"
        constraints = [
            models.UniqueConstraint(fields=["circuit", "order"], name="uniq_circuit_step_order")
        ]

    def __str__(self):
        return f"{self.circuit.code} · {self.order}. {self.name}"


class Task(models.Model):
    """Tâche de workflow — circuit, étape, assigné, échéance, statut (RF-29 à 37)."""

    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        DONE = "done", "Terminée"
        REJECTED = "rejected", "Rejeté"
        DELEGATED = "delegated", "Déléguée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        "documents.Document", on_delete=models.CASCADE, related_name="tasks"
    )
    circuit = models.ForeignKey(Circuit, on_delete=models.PROTECT, related_name="tasks")
    step = models.ForeignKey(
        CircuitStep, on_delete=models.PROTECT, related_name="tasks"
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="workflow_tasks",
        verbose_name="Assigné à",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Assigné par",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    due_date = models.DateTimeField(verbose_name="Échéance (RF-35)")
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Tâche de workflow"
        verbose_name_plural = "Tâches de workflow"

    def __str__(self):
        return f"{self.document_id} · {self.step.name} ({self.status})"


class TaskComment(models.Model):
    """Commentaire / annotation dans le circuit (RF-38)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )
    text = models.TextField(verbose_name="Texte")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Commentaire"
        verbose_name_plural = "Commentaires"

    def __str__(self):
        return f"Commentaire {self.task_id}"


class Notification(models.Model):
    """Notification utilisateur — relances, escalades, échéances (RF-34/35/37)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    task = models.ForeignKey(
        Task, null=True, blank=True, on_delete=models.SET_NULL, related_name="notifications"
    )
    subject = models.CharField(max_length=255, verbose_name="Objet")
    message = models.TextField(verbose_name="Message")
    kind = models.CharField(
        max_length=20,
        choices=[("reminder", "Relance"), ("escalation", "Escalade"), ("info", "Information")],
        default="info",
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"

    def __str__(self):
        return f"[{self.kind}] {self.subject} → {self.user_id}"
