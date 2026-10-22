"""Lot a7 : provision pour perte de change latente (SYSCOHADA 697 / 499), passée à la réévaluation de clôture."""

import uuid

from django.conf import settings
from django.db import models


class ProvisionChange(models.Model):
    """Provision pour perte de change latente nette, constatée à une date de clôture (Dr 697 / Cr 499) et
    contre-passée au calcul suivant (une seule provision active)."""

    class Statut(models.TextChoices):
        ACTIVE = "active", "Active"
        CONTRE_PASSEE = "contre_passee", "Contre-passée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    date_cloture = models.DateField(verbose_name="Date de clôture (réévaluation)")
    perte_latente = models.DecimalField(
        max_digits=16, decimal_places=2, default=0, verbose_name="Pertes latentes (écarts de conversion actif)"
    )
    gain_latent = models.DecimalField(
        max_digits=16, decimal_places=2, default=0, verbose_name="Gains latents (écarts de conversion passif)"
    )
    montant = models.DecimalField(max_digits=16, decimal_places=2, verbose_name="Provision (perte latente nette)")
    operations = models.PositiveIntegerField(default=0, verbose_name="Opérations réévaluées")
    statut = models.CharField(max_length=14, choices=Statut.choices, default=Statut.ACTIVE, db_index=True)
    move = models.ForeignKey(
        "accounting_kernel.AccountMove", on_delete=models.PROTECT, related_name="+", verbose_name="Écriture de dotation",
    )
    move_contre_passation = models.ForeignKey(
        "accounting_kernel.AccountMove", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        verbose_name="Écriture de contre-passation",
    )
    date_contre_passation = models.DateField(null=True, blank=True, verbose_name="Contre-passée le")
    cree_par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_cloture", "-created_at"]
        verbose_name = "Provision pour perte de change"
        verbose_name_plural = "Provisions pour perte de change"

    def __str__(self):
        return f"Provision perte de change {self.date_cloture} : {self.montant}"
