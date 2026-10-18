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
from datetime import timedelta

from django.conf import settings
from django.db import models, transaction
from django.db.models import Sum
from django.utils import timezone


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
    classe_mix = models.CharField(
        max_length=1, blank=True, choices=[("A", "Mix A"), ("B", "Mix B"), ("C", "Mix C")],
        verbose_name="Classe de la doctrine d'imputation (Mix A/B/C)",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="budgets_cg",
        verbose_name="Créé par",
    )
    # Double visa DAF + Contrôle de gestion (CDC M11 §4.4) : deux personnes distinctes.
    visa_daf_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+", verbose_name="Visa DAF"
    )
    visa_daf_le = models.DateTimeField(null=True, blank=True, verbose_name="Date du visa DAF")
    visa_cg_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        verbose_name="Visa Contrôle de gestion",
    )
    visa_cg_le = models.DateTimeField(null=True, blank=True, verbose_name="Date du visa CG")
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
        # `.all()` exploite le prefetch_related de la vue (sinon 1 requête) : pas d'aggregate par budget.
        return sum((l.montant for l in self.lignes.all()), 0)

    @property
    def nb_revisions(self):
        return len(self.revisions.all())


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
    # Double visa DAF + Contrôle de gestion (CDC M11 §4.4) : deux personnes distinctes.
    visa_daf_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+", verbose_name="Visa DAF"
    )
    visa_daf_le = models.DateTimeField(null=True, blank=True, verbose_name="Date du visa DAF")
    visa_cg_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        verbose_name="Visa Contrôle de gestion",
    )
    visa_cg_le = models.DateTimeField(null=True, blank=True, verbose_name="Date du visa CG")
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


class AnalyseEcart(models.Model):
    """Analyse d'écart budget / réalisé > 10 % — à rendre sous 5 jours (lot 15, CDC M11 §4.4).

    Ouverte automatiquement par `controle_gestion.services.detecter_ecarts` (une par budget et période) ;
    rendue par l'action `analyser` (explication + actions, auteur et date tracés).
    """

    SEUIL_PCT = 10
    DELAI_JOURS = 5

    class Statut(models.TextChoices):
        A_ANALYSER = "a_analyser", "À analyser"
        ANALYSEE = "analysee", "Analysée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name="analyses_ecart", verbose_name="Budget")
    period = models.ForeignKey(
        "accounting_kernel.Period", on_delete=models.PROTECT, related_name="analyses_ecart", verbose_name="Période"
    )
    montant_budget = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="Budget de la période")
    realise = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="Réalisé")
    ecart_pct = models.DecimalField(max_digits=8, decimal_places=2, verbose_name="Écart (%)")
    detecte_le = models.DateField(default=timezone.localdate, verbose_name="Détecté le")
    echeance = models.DateField(verbose_name="Analyse attendue avant le")
    analyse = models.TextField(blank=True, verbose_name="Analyse de l'écart")
    actions = models.TextField(blank=True, verbose_name="Actions correctives")
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.A_ANALYSER, verbose_name="Statut")
    analyse_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="analyses_ecart", verbose_name="Analysée par",
    )
    analyse_le = models.DateTimeField(null=True, blank=True, verbose_name="Analysée le")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["statut", "echeance"]
        verbose_name = "Analyse d'écart budgétaire"
        verbose_name_plural = "Analyses d'écart budgétaire"
        constraints = [models.UniqueConstraint(fields=["budget", "period"], name="uniq_analyse_ecart_budget_periode")]

    def __str__(self):
        return f"{self.code} — {self.budget.code} P{self.period.number} ({self.ecart_pct} %)"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = ControleGestionSequence.next_for("AEC", "AEC")
        if not self.echeance:
            self.echeance = self.detecte_le + timedelta(days=self.DELAI_JOURS)
        return super().save(*args, **kwargs)

    @property
    def en_retard(self):
        return self.statut == self.Statut.A_ANALYSER and timezone.localdate() > self.echeance


class ParametreGestion(models.Model):
    """Paramètre de contrôle de gestion modifiable par ETSL sans développeur (seuils de sous-activité,
    doctrine d'imputation Mix A/B/C, jours de reporting J+4/J+6).

    Tant que `statut_valeur` = « provisoire », les écrans et états qui l'utilisent avertissent. Le défaut est
    créé à la volée par `services.get_param_gestion` (la valeur est une DONNÉE, jamais figée dans le code).
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
        verbose_name = "Paramètre de gestion"
        verbose_name_plural = "Paramètres de gestion"

    def __str__(self):
        return f"{self.code} = {self.valeur} {self.unite}"

    @property
    def est_provisoire(self):
        return self.statut_valeur != self.StatutValeur.CONFIRME


class AlerteSousActivite(models.Model):
    """Alerte d'entrée d'un budget en centre 99 (sous-activité > seuil haut) : une seule fois par budget."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name="alertes_sous_activite")
    centre = models.CharField(max_length=2)
    taux = models.DecimalField(max_digits=6, decimal_places=2)
    detecte_le = models.DateField()

    class Meta:
        ordering = ["-detecte_le"]
        constraints = [models.UniqueConstraint(fields=["budget", "centre"], name="uniq_alerte_sous_activite")]
