"""Couche D — cubes OLAP à 6 axes (CDC Couche D §2.4 / §2.5 / §2.11).

Axes référentiels du CDC : affaire · chantier · site · activité · centre · période. Le grand livre porte UN compte
analytique par ligne (affaire, chantier, site ou centre de coût) ; l'activité (chantier / atelier / maintenance /
fourniture, ou GLOBAL RENTAL) est dérivée de l'affaire. `CubeFait` est la table de faits reconstruite
idempotemment ; `CubeArchive` est la copie figée, scellée (SHA-256) et immuable, conservée 10 ans.
"""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class ParametreCube(models.Model):
    """Paramètre du cube modifiable par ETSL sans développeur (durée de conservation de l'archive).

    Tant que `statut_valeur` = « provisoire », l'écran avertit. Le défaut est créé à la volée par
    `cubes.get_param_cube` (donnée, jamais figée en code).
    """

    class StatutValeur(models.TextChoices):
        PROVISOIRE = "provisoire", "Provisoire"
        CONFIRME = "confirme", "Confirmé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=40, unique=True, verbose_name="Identifiant")
    label = models.CharField(max_length=200, verbose_name="Libellé")
    valeur = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Valeur")
    unite = models.CharField(max_length=20, blank=True, verbose_name="Unité")
    statut_valeur = models.CharField(
        max_length=10, choices=StatutValeur.choices, default=StatutValeur.PROVISOIRE,
        verbose_name="Statut de la valeur",
    )
    confirme_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", verbose_name="Confirmé par",
    )
    confirme_le = models.DateTimeField(null=True, blank=True, verbose_name="Confirmé le")

    class Meta:
        ordering = ["code"]
        verbose_name = "Paramètre cube"
        verbose_name_plural = "Paramètres cube"

    def __str__(self):
        return f"{self.code} = {self.valeur} {self.unite}"

    @property
    def est_provisoire(self):
        return self.statut_valeur != self.StatutValeur.CONFIRME


class CubeFait(models.Model):
    """Fait du cube : mesures d'un mois pour une combinaison d'axes (clé vide = axe non renseigné)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    periode = models.CharField(max_length=7, verbose_name="Période (AAAA-MM)", db_index=True)
    affaire = models.CharField(max_length=30, blank=True, default="", verbose_name="Affaire")
    chantier = models.CharField(max_length=30, blank=True, default="", verbose_name="Chantier")
    site = models.CharField(max_length=30, blank=True, default="", verbose_name="Site")
    activite = models.CharField(max_length=20, blank=True, default="", verbose_name="Activité")
    centre = models.CharField(max_length=30, blank=True, default="", verbose_name="Centre de coût")
    produits = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    charges = models.DecimalField(max_digits=18, decimal_places=2, default=0, help_text="Hors 618.")
    cout_gr = models.DecimalField(max_digits=18, decimal_places=2, default=0, help_text="Compte 618 isolé.")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-periode", "affaire", "chantier", "site", "centre"]
        verbose_name = "Fait du cube"
        verbose_name_plural = "Faits du cube"
        constraints = [
            models.UniqueConstraint(
                fields=["periode", "affaire", "chantier", "site", "activite", "centre"], name="analytics_cubefait_unique"
            )
        ]


class CubeArchive(models.Model):
    """Cube d'un mois figé, scellé et conservé N ans (10 ans Oil & Gas) — immuable, non supprimable."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    periode = models.CharField(max_length=7, unique=True, verbose_name="Période (AAAA-MM)")
    faits = models.JSONField(default=list, verbose_name="Faits figés")
    nb_faits = models.PositiveIntegerField(default=0)
    produits = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    charges = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    cout_gr = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    sha256 = models.CharField(max_length=64, verbose_name="Empreinte SHA-256")
    conserve_jusqu_au = models.DateField(verbose_name="Conservé jusqu'au")
    retention_provisoire = models.BooleanField(
        default=True, verbose_name="Durée de conservation provisoire au moment du scellement"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", verbose_name="Figé par",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-periode"]
        verbose_name = "Archive du cube"
        verbose_name_plural = "Archives du cube"

    def __str__(self):
        return f"Cube {self.periode}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Une archive de cube est immuable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Une archive de cube ne peut pas être supprimée (conservation légale).")
