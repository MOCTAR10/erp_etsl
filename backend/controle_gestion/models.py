"""Module M11 — Contrôle de gestion (RF-ERP-A0…A4).

Périmètre SPEC §2.1 (M11) / MANUEL proc. 4.4 (suivi budgétaire et reporting) :
référentiel analytique multi-axes (A0 — `referentiels`) · budget annuel &
révisions R1-R4 (A1) · marges & écarts / sous-activité (A2) · reporting
Direction, clôtures < J+4 (A3) · isolement du coût GLOBAL RENTAL (compte 618,
A4). Les réalisations sont agrégées depuis les écritures comptabilisées du
noyau `accounting_kernel` (AccountMove/AccountMoveLine) ; le budget se
distribue par période via `BudgetLigne`. App `controle_gestion` + reporting
`reports` (dashboard Direction).
"""

import uuid

from django.conf import settings
from django.db import models, transaction
from django.db.models import Sum


class ControleGestionSequence(models.Model):
    """Numérotation séquentielle par type (BUD budget, REV révision, etc.)."""

    kind = models.CharField(max_length=10, unique=True, verbose_name="Type")
    prefix = models.CharField(max_length=10, verbose_name="Préfixe")
    padding = models.PositiveSmallIntegerField(default=5, verbose_name="Zéro-padding")
    next_number = models.PositiveIntegerField(default=1, verbose_name="Prochain numéro")

    class Meta:
        verbose_name = "Séquence Contrôle de gestion"
        verbose_name_plural = "Séquences Contrôle de gestion"

    def __str__(self):
        return f"{self.kind} → {self.prefix}{self.next_number:0{self.padding}d}"

    @classmethod
    def next_for(cls, kind, prefix):
        seq, _ = cls.objects.get_or_create(
            kind=kind, defaults={"prefix": prefix, "padding": 5}
        )
        with transaction.atomic():
            seq = cls.objects.select_for_update().get(pk=seq.pk)
            number = f"{seq.prefix}{str(seq.next_number).zfill(seq.padding)}"
            seq.next_number += 1
            seq.save(update_fields=["next_number"])
        return number


class Budget(models.Model):
    """Budget annuel (charges ou produits) — RF-ERP-A1.

    Rattachable à un axe analytique (A0) via `axis` + `analytic` pour un suivi
    par affaire / chantier / centre de coût. Le montant annuel se distribue par
    période comptable via `BudgetLigne`. Révisions budgétaires R1-R4 :
    `BudgetRevision` (au plus 4 révisions annuelles, SPEC RF-ERP-A1).
    """

    class TypeBudget(models.TextChoices):
        CHARGE = "charge", "Budget de charges"
        PRODUIT = "produit", "Budget de produits"

    class Statut(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        APPROUVE = "approuve", "Approuvé"
        CLOTURE = "cloture", "Clôturé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    label = models.CharField(max_length=250, verbose_name="Intitulé du budget")
    type_budget = models.CharField(
        max_length=10, choices=TypeBudget.choices, verbose_name="Type", db_index=True
    )
    fiscal_year = models.ForeignKey(
        "accounting_kernel.FiscalYear",
        on_delete=models.PROTECT,
        related_name="budgets",
        verbose_name="Exercice",
    )
    axis = models.ForeignKey(
        "referentiels.AnalyticAxis",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="budgets",
        verbose_name="Axe analytique",
    )
    analytic = models.ForeignKey(
        "referentiels.AnalyticAccount",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="budgets",
        verbose_name="Valeur d'axe (affaire / chantier / CC)",
    )
    montant = models.DecimalField(
        max_digits=16, decimal_places=2, default=0, verbose_name="Montant (FCFA)"
    )
    statut = models.CharField(
        max_length=10, choices=Statut.choices, default=Statut.BROUILLON, verbose_name="Statut"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="budgets_cg",
        verbose_name="Créé par",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fiscal_year", "-created_at"]
        verbose_name = "Budget"
        verbose_name_plural = "Budgets"

    def __str__(self):
        return f"{self.code} — {self.label} ({self.get_type_budget_display()})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = ControleGestionSequence.next_for("BUD", "BUD")
        return super().save(*args, **kwargs)

    @property
    def montant_lignes(self):
        return self.lignes.aggregate(total=Sum("montant"))["total"] or 0

    @property
    def nb_revisions(self):
        return self.revisions.count()


class BudgetLigne(models.Model):
    """Répartition mensuelle d'un budget (RF-ERP-A1) — une ligne par période."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    budget = models.ForeignKey(
        Budget, on_delete=models.CASCADE, related_name="lignes", verbose_name="Budget"
    )
    period = models.ForeignKey(
        "accounting_kernel.Period",
        on_delete=models.PROTECT,
        related_name="budget_lignes",
        verbose_name="Période comptable",
    )
    montant = models.DecimalField(
        max_digits=16, decimal_places=2, default=0, verbose_name="Montant (FCFA)"
    )

    class Meta:
        ordering = ["budget", "period"]
        verbose_name = "Ligne de budget"
        verbose_name_plural = "Lignes de budget"
        constraints = [
            models.UniqueConstraint(fields=["budget", "period"], name="uniq_budget_ligne_period")
        ]

    def __str__(self):
        return f"{self.budget.code} · {self.period} → {self.montant}"


class BudgetRevision(models.Model):
    """Révision budgétaire R1-R4 (RF-ERP-A1) — au plus 4 par budget et an.

    Chaque révision ajuste le montant du budget (à la hausse ou à la baisse) ;
    elle est horodatée et journalisée (audit trail). Les révisions 1 à 4 sont
    les révisions budgétaires annuelles types du processus ETSL.
    """

    class Statut(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        APPLIQUEE = "appliquee", "Appliquée"
        ANNULEE = "annulee", "Annulée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    budget = models.ForeignKey(
        Budget, on_delete=models.CASCADE, related_name="revisions", verbose_name="Budget"
    )
    numero = models.PositiveSmallIntegerField(verbose_name="N° de révision (1-4)")
    date_revision = models.DateField(verbose_name="Date de révision")
    ancien_montant = models.DecimalField(
        max_digits=16, decimal_places=2, default=0, verbose_name="Montant avant révision"
    )
    nouveau_montant = models.DecimalField(
        max_digits=16, decimal_places=2, verbose_name="Montant après révision"
    )
    commentaire = models.CharField(max_length=250, blank=True, verbose_name="Commentaire")
    statut = models.CharField(
        max_length=10, choices=Statut.choices, default=Statut.BROUILLON, verbose_name="Statut"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="revisions_cg",
        verbose_name="Créée par",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["budget", "numero"]
        verbose_name = "Révision budgétaire"
        verbose_name_plural = "Révisions budgétaires"
        constraints = [
            models.UniqueConstraint(
                fields=["budget", "numero"], name="uniq_budget_revision_numero"
            )
        ]

    def __str__(self):
        return f"{self.code} — R{self.numero} {self.budget.code}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = ControleGestionSequence.next_for("REV", "REV")
        return super().save(*args, **kwargs)


class ClotureGestion(models.Model):
    """Clôture mensuelle de gestion — reporting Direction < J+4 (RF-ERP-A3).

    Une clôture de gestion par période comptable : l'écart entre `date_cloture`
    et la fin de période déterminé `jours_ecoulement` ; la conformité
    `conforme_j4` vaut si la clôture est réalisée au plus 4 jours après la fin
    de période (proc. MANUEL 4.6 contrôle interne / reporting < J+4).
    """

    class Statut(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente"
        REALISEE = "realisee", "Réalisée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    period = models.ForeignKey(
        "accounting_kernel.Period",
        on_delete=models.PROTECT,
        related_name="clotures_gestion",
        verbose_name="Période comptable",
    )
    date_cloture = models.DateField(null=True, blank=True, verbose_name="Date de clôture")
    statut = models.CharField(
        max_length=12, choices=Statut.choices, default=Statut.EN_ATTENTE, verbose_name="Statut"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="clotures_cg",
        verbose_name="Créée par",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-period"]
        verbose_name = "Clôture de gestion"
        verbose_name_plural = "Clôtures de gestion"

    def __str__(self):
        return f"{self.code} — {self.period}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = ControleGestionSequence.next_for("CLO", "CLO")
        return super().save(*args, **kwargs)

    @property
    def jours_ecoulement(self):
        """Nombre de jours entre la fin de période et la clôture réalisée."""
        if not self.date_cloture:
            return None
        return (self.date_cloture - self.period.end_date).days

    @property
    def conforme_j4(self):
        """Conformité < J+4 : clôture réalisée au plus 4 jours après la période."""
        if self.statut != self.Statut.REALISEE or self.jours_ecoulement is None:
            return False
        return self.jours_ecoulement <= 4