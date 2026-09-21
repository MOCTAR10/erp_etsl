"""Framework d'intégration par fichiers (H-04 : CSV/XML, sans API) — incr.16.

Couvre la reprise de données (SAGE/ALAN) et les flux CFONB/MT940, CNSSG/CNAMGS, GR.
L'idempotence repose sur l'empreinte SHA-256 du fichier + une clé métier par ligne.
"""

import uuid

from django.conf import settings
from django.db import models


class ImportBatch(models.Model):
    """Lot d'import — journal de bord : idempotence par empreinte + compteurs."""

    class Connector(models.TextChoices):
        PARTNERS = "partners", "Tiers (CSV)"
        GL = "gl", "Écritures générales (CSV — reprise SAGE)"
        CFONB = "cfonb", "Relevés bancaires CFONB"
        MT940 = "mt940", "Relevé bancaire SWIFT MT940"
        CNSSG = "cnssg", "Cotisations CNSSG"
        CNAMGS = "cnamgs", "Cotisations CNAMGS"
        GENERIC = "generic", "Table générique"

    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        RUNNING = "running", "En cours"
        SUCCESS = "success", "Succès"
        PARTIAL = "partial", "Partiel (erreurs)"
        FAILED = "failed", "Échoué"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    connector = models.CharField(
        max_length=12, choices=Connector.choices, verbose_name="Connecteur", db_index=True
    )
    status = models.CharField(
        max_length=8, choices=Status.choices, default=Status.PENDING, verbose_name="Statut"
    )
    filename = models.CharField(max_length=255, verbose_name="Fichier")
    file_hash = models.CharField(max_length=64, verbose_name="SHA-256", db_index=True)
    total_rows = models.PositiveIntegerField(default=0, verbose_name="Lignes")
    created_rows = models.PositiveIntegerField(default=0, verbose_name="Créées")
    updated_rows = models.PositiveIntegerField(default=0, verbose_name="Mises à jour")
    error_rows = models.PositiveIntegerField(default=0, verbose_name="En erreur")
    error_message = models.TextField(blank=True, verbose_name="Message d'erreur global")
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="import_batches",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Lot d'import"
        verbose_name_plural = "Lots d'import"

    def __str__(self):
        return f"{self.get_connector_display()} [{self.status}] {self.filename}"

    @property
    def has_errors(self):
        return self.error_rows > 0


class BatchRow(models.Model):
    """Résultat par ligne importée — journal d'erreurs (rapprochement / audit)."""

    class Status(models.TextChoices):
        SUCCESS = "success", "Traitée"
        DUPLICATE = "duplicate", "Déjà présente (écartée)"
        ERROR = "error", "En erreur"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(
        ImportBatch, on_delete=models.CASCADE, related_name="rows", verbose_name="Lot"
    )
    row_number = models.PositiveIntegerField(verbose_name="N° de ligne")
    status = models.CharField(
        max_length=10, choices=Status.choices, verbose_name="Statut"
    )
    data = models.JSONField(default=dict, blank=True, verbose_name="Données")
    error_message = models.TextField(blank=True, verbose_name="Erreur")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["batch", "row_number"]
        verbose_name = "Ligne d'import"
        verbose_name_plural = "Lignes d'import"
        constraints = [
            models.UniqueConstraint(
                fields=["batch", "row_number"], name="uniq_batchrow_number"
            )
        ]

    def __str__(self):
        return f"{self.batch} l.{self.row_number} [{self.status}]"