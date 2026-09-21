import uuid

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone


def current_year():
    return timezone.now().year


class Registre(models.Model):
    """Registre / tableau de suivi (9 modules) — source MANUEL ch.10 + proposition §6.5."""

    class Kind(models.TextChoices):
        CAISSE_APPRO = "caisse_appro", "Caisse & approvisionnements"
        FACTURES_PAIEMENTS = "factures_paiements", "Factures & paiements"
        CONTRATS_ECHEANCES = "contrats_echeances", "Contrats & échéances"
        COURRIER = "courrier", "Courrier (bureau d'ordre)"
        INCIDENTS_HSE = "incidents_hse", "Incidents & accidents HSE"
        STOCK_MAGASIN = "stock_magasin", "Stock & magasin"
        CONGES_ROTATIONS = "conges_rotations", "Congés & rotations"
        FORMATIONS = "formations", "Formations & sensibilisations"
        NON_CONFORMITES = "non_conformites", "Non-conformités qualité"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(
        max_length=30, choices=Kind.choices, verbose_name="Type", db_index=True
    )
    label = models.CharField(max_length=200, verbose_name="Libellé")
    year = models.PositiveSmallIntegerField(default=current_year, verbose_name="Exercice")
    annexe = models.ForeignKey(
        "referentiels.Annexe",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="registres",
        verbose_name="Annexe du MANUEL",
    )
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["kind", "-year"]
        verbose_name = "Registre"
        verbose_name_plural = "Registres"
        constraints = [
            models.UniqueConstraint(
                fields=["kind", "year"], name="uniq_registre_kind_year"
            )
        ]

    def __str__(self):
        return f"{self.get_kind_display()} ({self.year})"


class RegistreEntry(models.Model):
    """Ligne d'un registre — numérotation continue, données libres (JSON)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    registre = models.ForeignKey(
        Registre, on_delete=models.CASCADE, related_name="entries", verbose_name="Registre"
    )
    number = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="Numéro", db_index=True
    )
    entry_date = models.DateField(default=timezone.localdate, verbose_name="Date")
    data = models.JSONField(default=dict, blank=True, verbose_name="Données")
    document = models.ForeignKey(
        "documents.Document",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="registre_entries",
        verbose_name="Document lié",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="registre_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["registre", "-number"]
        verbose_name = "Ligne de registre"
        verbose_name_plural = "Lignes de registre"
        constraints = [
            models.UniqueConstraint(
                fields=["registre", "number"], name="uniq_registre_entry_number"
            )
        ]

    def __str__(self):
        return f"{self.registre_id} n°{self.number}"

    def save(self, *args, **kwargs):
        if self.number is None:
            with transaction.atomic():
                # Verrouille le registre pour garantir une numérotation continue.
                Registre.objects.select_for_update().get(pk=self.registre_id)
                last = (
                    RegistreEntry.objects.filter(registre_id=self.registre_id)
                    .aggregate(models.Max("number"))["number__max"]
                    or 0
                )
                self.number = last + 1
                return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)
