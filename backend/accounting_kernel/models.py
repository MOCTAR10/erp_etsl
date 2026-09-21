"""Noyau comptable en partie double — écritures immuables + extournes (incr.15).

Utilisé par M10 (comptabilité générale/analytique), M5 (valorisation stock)
et M9 (écritures de paie). Cf. ARCHITECTURE_ERP_ETSL.md §7.1/§7.2, SPEC §2.2.
"""

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction


class FiscalYear(models.Model):
    """Exercice comptable."""

    class Status(models.TextChoices):
        OPEN = "open", "Ouvert"
        CLOSED = "closed", "Clôturé"

    year = models.PositiveSmallIntegerField(unique=True, verbose_name="Exercice")
    start_date = models.DateField(verbose_name="Début")
    end_date = models.DateField(verbose_name="Fin")
    status = models.CharField(
        max_length=8, choices=Status.choices, default=Status.OPEN, verbose_name="Statut"
    )

    class Meta:
        ordering = ["-year"]
        verbose_name = "Exercice"
        verbose_name_plural = "Exercices"

    def __str__(self):
        return str(self.year)


class Period(models.Model):
    """Période (mois) d'un exercice — verrouillage à la clôture."""

    class Status(models.TextChoices):
        OPEN = "open", "Ouverte"
        CLOSED = "closed", "Clôturée"

    fiscal_year = models.ForeignKey(
        FiscalYear, on_delete=models.CASCADE, related_name="periods", verbose_name="Exercice"
    )
    number = models.PositiveSmallIntegerField(verbose_name="N° (1-12)")
    start_date = models.DateField(verbose_name="Début")
    end_date = models.DateField(verbose_name="Fin")
    status = models.CharField(
        max_length=8, choices=Status.choices, default=Status.OPEN, verbose_name="Statut"
    )

    class Meta:
        ordering = ["fiscal_year", "number"]
        verbose_name = "Période"
        verbose_name_plural = "Périodes"
        constraints = [
            models.UniqueConstraint(
                fields=["fiscal_year", "number"], name="uniq_period_year_number"
            )
        ]

    def __str__(self):
        return f"{self.fiscal_year}-{self.number:02d}"

    @property
    def is_open(self):
        return self.status == self.Status.OPEN


class Journal(models.Model):
    """Journal comptable (achat, vente, trésorerie, paie, stock, OD)."""

    class JournalType(models.TextChoices):
        VENTE = "vente", "Ventes"
        ACHAT = "achat", "Achats"
        TRESORERIE = "tresorerie", "Trésorerie"
        PAIE = "paie", "Paie"
        STOCK = "stock", "Stock"
        OD = "od", "Opérations diverses"

    code = models.CharField(max_length=10, unique=True, verbose_name="Code")
    label = models.CharField(max_length=120, verbose_name="Libellé")
    journal_type = models.CharField(
        max_length=12, choices=JournalType.choices, verbose_name="Type", db_index=True
    )
    is_active = models.BooleanField(default=True, verbose_name="Actif")

    class Meta:
        ordering = ["code"]
        verbose_name = "Journal"
        verbose_name_plural = "Journaux"

    def __str__(self):
        return f"{self.code} — {self.label}"


class Sequence(models.Model):
    """Séquence de numérotation par journal (concept `ir.sequence`, sans code Odoo)."""

    journal = models.OneToOneField(
        Journal, on_delete=models.CASCADE, related_name="sequence", verbose_name="Journal"
    )
    prefix = models.CharField(max_length=10, verbose_name="Préfixe")
    padding = models.PositiveSmallIntegerField(default=5, verbose_name="Zéro-padding")
    next_number = models.PositiveIntegerField(default=1, verbose_name="Prochain numéro")

    class Meta:
        verbose_name = "Séquence"
        verbose_name_plural = "Séquences"

    def __str__(self):
        return f"{self.journal.code} → {self.prefix}{self.next_number:0{self.padding}d}"

    @classmethod
    def next_for(cls, journal):
        """Retourne le numéro suivant du journal, en verrouillant la séquence."""
        seq, _ = cls.objects.get_or_create(
            journal=journal, defaults={"prefix": journal.code, "padding": 5}
        )
        with transaction.atomic():
            seq = cls.objects.select_for_update().get(pk=seq.pk)
            number = f"{seq.prefix}{str(seq.next_number).zfill(seq.padding)}"
            seq.next_number += 1
            seq.save(update_fields=["next_number"])
        return number


class AccountMove(models.Model):
    """Écriture comptable (pièce) — immuable une fois comptabilisée."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Brouillon"
        POSTED = "posted", "Comptabilisée"
        REVERSED = "reversed", "Extournée"

    # Champs figés après comptabilisation (toute correction = extourne).
    IMMUTABLE_FIELDS = (
        "journal_id",
        "period_id",
        "date",
        "reference",
        "label",
        "source",
        "source_ref",
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    journal = models.ForeignKey(
        Journal, on_delete=models.PROTECT, related_name="moves", verbose_name="Journal"
    )
    period = models.ForeignKey(
        Period, on_delete=models.PROTECT, related_name="moves", verbose_name="Période"
    )
    date = models.DateField(verbose_name="Date comptable", db_index=True)
    number = models.CharField(
        max_length=30, null=True, blank=True, verbose_name="Numéro", db_index=True
    )
    reference = models.CharField(max_length=120, blank=True, verbose_name="Référence")
    label = models.CharField(max_length=200, blank=True, verbose_name="Libellé")
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name="Statut",
        db_index=True,
    )
    source = models.CharField(
        max_length=20, blank=True, verbose_name="Module source", help_text="Ex. M10, M9, M5."
    )
    source_ref = models.CharField(max_length=60, blank=True, verbose_name="Réf. source")
    reversed_by = models.OneToOneField(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reverses",
        verbose_name="Extournée par",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="account_moves",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    posted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "Écriture comptable"
        verbose_name_plural = "Écritures comptables"
        constraints = [
            models.UniqueConstraint(
                fields=["journal", "number"], name="uniq_move_journal_number"
            )
        ]

    def __str__(self):
        return self.number or f"brouillon {self.id}"

    @property
    def is_posted(self):
        return self.status in (self.Status.POSTED, self.Status.REVERSED)

    @property
    def total_debit(self):
        return sum((line.debit for line in self.lines.all()), Decimal("0"))

    @property
    def total_credit(self):
        return sum((line.credit for line in self.lines.all()), Decimal("0"))

    def save(self, *args, **kwargs):
        if not self._state.adding:
            old = AccountMove.objects.filter(pk=self.pk).values().first()
            if old and old["status"] == self.Status.POSTED:
                for field in self.IMMUTABLE_FIELDS:
                    if old[field] != getattr(self, field):
                        raise ValidationError(
                            "Écriture comptabilisée immuable — corrigez par extourne."
                        )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.is_posted:
            raise ValidationError("Écriture comptabilisée immuable — pas de suppression.")
        return super().delete(*args, **kwargs)


class AccountMoveLine(models.Model):
    """Ligne d'écriture (débit OU crédit) — immuable si l'écriture est comptabilisée."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    move = models.ForeignKey(
        AccountMove, on_delete=models.CASCADE, related_name="lines", verbose_name="Écriture"
    )
    account = models.ForeignKey(
        "referentiels.Account",
        on_delete=models.PROTECT,
        related_name="move_lines",
        verbose_name="Compte",
    )
    partner = models.ForeignKey(
        "referentiels.Partner",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="move_lines",
        verbose_name="Tiers",
    )
    analytic_account = models.ForeignKey(
        "referentiels.AnalyticAccount",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="move_lines",
        verbose_name="Axe analytique",
    )
    label = models.CharField(max_length=200, blank=True, verbose_name="Libellé")
    debit = models.DecimalField(
        max_digits=16, decimal_places=2, default=0, verbose_name="Débit"
    )
    credit = models.DecimalField(
        max_digits=16, decimal_places=2, default=0, verbose_name="Crédit"
    )
    order = models.PositiveSmallIntegerField(default=0, verbose_name="Ordre")

    class Meta:
        ordering = ["move", "order"]
        verbose_name = "Ligne d'écriture"
        verbose_name_plural = "Lignes d'écriture"

    def __str__(self):
        return f"{self.account_id} D{self.debit} C{self.credit}"

    def _move_is_posted(self):
        if not self.move_id:
            return False
        return (
            AccountMove.objects.filter(pk=self.move_id)
            .values_list("status", flat=True)
            .first()
            == AccountMove.Status.POSTED
        )

    def save(self, *args, **kwargs):
        if self._move_is_posted():
            raise ValidationError("Ligne d'écriture comptabilisée immuable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self._move_is_posted():
            raise ValidationError("Ligne d'écriture comptabilisée immuable.")
        return super().delete(*args, **kwargs)
