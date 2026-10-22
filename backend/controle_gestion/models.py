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
    pv_document = models.ForeignKey(
        "documents.Document", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        verbose_name="PV de validation archivé (GED)",
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
    pv_document = models.ForeignKey(
        "documents.Document", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        verbose_name="PV de validation archivé (GED)",
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
    date_publication = models.DateField(null=True, blank=True, verbose_name="Date de publication à la Direction")
    publie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", verbose_name="Publié par",
    )
    alerte_j6_le = models.DateField(null=True, blank=True, verbose_name="Relance J+6 envoyée le")
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
        from .services import get_param_gestion

        return self.jours_ecoulement <= int(get_param_gestion("REPORTING_JOUR_J4"))

    @property
    def echeance_j4(self):
        from .services import get_param_gestion

        return self.period.end_date + timedelta(days=int(get_param_gestion("REPORTING_JOUR_J4")))

    @property
    def echeance_j6(self):
        from .services import get_param_gestion

        return self.period.end_date + timedelta(days=int(get_param_gestion("REPORTING_JOUR_J6")))

    @property
    def reporting_statut(self):
        """a_temps (≤ J+4) · j6 (≤ J+6) · hors_delai · en_attente (publication pas encore due ou en cours)."""
        ref = self.date_publication or timezone.localdate()
        if ref <= self.echeance_j4:
            return "a_temps" if self.date_publication else "en_attente"
        if ref <= self.echeance_j6:
            return "j6" if self.date_publication else "en_attente"
        return "hors_delai"


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
    table = models.CharField(
        max_length=40, blank=True, db_index=True, verbose_name="Table de paramétrage (RGM_*, KPI_CIBLES)"
    )
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


# ==================================================================================================
# Écarts M11 (2026-10-21) : révision par ligne mensuelle, plan d'action de sous-activité, reporting
# archivé par horizon, revue de performance P-M11.10, validation de la marge d'affaire, provisions 408.
# ==================================================================================================
class BudgetRevisionLigne(models.Model):
    """Révision d'une ligne mensuelle (R1-R4) : appliquée à la `BudgetLigne` de la période au second visa."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    revision = models.ForeignKey(BudgetRevision, on_delete=models.CASCADE, related_name="lignes", verbose_name="Révision")
    period = models.ForeignKey("accounting_kernel.Period", on_delete=models.PROTECT, related_name="+", verbose_name="Période")
    ancien_montant = models.DecimalField(max_digits=16, decimal_places=2, default=0, verbose_name="Montant avant révision")
    nouveau_montant = models.DecimalField(max_digits=16, decimal_places=2, verbose_name="Montant révisé")

    class Meta:
        ordering = ["revision", "period"]
        verbose_name = "Ligne de révision budgétaire"
        verbose_name_plural = "Lignes de révision budgétaire"
        constraints = [models.UniqueConstraint(fields=["revision", "period"], name="uniq_revision_ligne_period")]

    def __str__(self):
        return f"{self.revision.code} · {self.period} → {self.nouveau_montant}"


class PlanActionSousActivite(models.Model):
    """Plan d'action rattaché à un budget en sous-activité (centre 99) : actions, responsable, échéance, suivi."""

    class Statut(models.TextChoices):
        OUVERT = "ouvert", "Ouvert"
        EN_COURS = "en_cours", "En cours"
        CLOS = "clos", "Clos"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name="plans_sous_activite", verbose_name="Budget")
    alerte = models.ForeignKey(
        AlerteSousActivite, null=True, blank=True, on_delete=models.SET_NULL, related_name="plans", verbose_name="Alerte"
    )
    centre = models.CharField(max_length=2, blank=True, verbose_name="Centre au lancement")
    taux = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, verbose_name="Taux de sous-activité")
    actions = models.TextField(verbose_name="Actions prévues")
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="Responsable"
    )
    echeance = models.DateField(null=True, blank=True, verbose_name="Échéance")
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.OUVERT, verbose_name="Statut")
    suivi = models.TextField(blank=True, verbose_name="Suivi / résultat")
    clos_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="Clos par"
    )
    clos_le = models.DateTimeField(null=True, blank=True, verbose_name="Clos le")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="Créé par"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["statut", "echeance"]
        verbose_name = "Plan d'action de sous-activité"
        verbose_name_plural = "Plans d'action de sous-activité"

    def __str__(self):
        return f"{self.code} — {self.budget.code}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = ControleGestionSequence.next_for("PAS", "PAS")
        return super().save(*args, **kwargs)

    @property
    def en_retard(self):
        return self.statut != self.Statut.CLOS and self.echeance is not None and timezone.localdate() > self.echeance


class ReportingArchive(models.Model):
    """Reporting de gestion d'un mois, par horizon (12 mois à J+4, 3 mois à J+6) : PDF archivé en GED."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cloture = models.ForeignKey(ClotureGestion, on_delete=models.CASCADE, related_name="reportings", verbose_name="Clôture")
    type_reporting = models.CharField(
        max_length=2, choices=[("j4", "Publié à J+4"), ("j6", "Publié à J+6")], verbose_name="Type de reporting"
    )
    horizon = models.PositiveSmallIntegerField(verbose_name="Horizon (mois)")
    echeance = models.DateField(verbose_name="Échéance de publication")
    archive_le = models.DateField(default=timezone.localdate, verbose_name="Archivé le")
    a_temps = models.BooleanField(default=False, verbose_name="Publié dans le délai")
    document = models.ForeignKey(
        "documents.Document", null=True, blank=True, on_delete=models.PROTECT, related_name="+", verbose_name="PDF archivé"
    )
    archive_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="Archivé par"
    )

    class Meta:
        ordering = ["-archive_le"]
        verbose_name = "Reporting de gestion archivé"
        verbose_name_plural = "Reportings de gestion archivés"
        constraints = [models.UniqueConstraint(fields=["cloture", "type_reporting"], name="uniq_reporting_cloture_type")]


class RevuePerformance(models.Model):
    """Revue de performance périodique (procédure P-M11.10) : ordre du jour, KPI figés, décisions, PV archivé."""

    class Statut(models.TextChoices):
        PLANIFIEE = "planifiee", "Planifiée"
        TENUE = "tenue", "Tenue (PV archivé)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    period = models.ForeignKey(
        "accounting_kernel.Period", on_delete=models.PROTECT, related_name="+", verbose_name="Période revue"
    )
    date_revue = models.DateField(verbose_name="Date de la revue")
    ordre_du_jour = models.TextField(blank=True, verbose_name="Ordre du jour")
    participants = models.TextField(blank=True, verbose_name="Participants")
    decisions = models.TextField(blank=True, verbose_name="Décisions et actions")
    kpis = models.JSONField(default=list, blank=True, verbose_name="KPI figés à la revue")
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.PLANIFIEE, verbose_name="Statut")
    pv_document = models.ForeignKey(
        "documents.Document", null=True, blank=True, on_delete=models.PROTECT, related_name="+", verbose_name="PV archivé"
    )
    tenue_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="PV établi par"
    )
    tenue_le = models.DateTimeField(null=True, blank=True, verbose_name="PV établi le")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="Créée par"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_revue"]
        verbose_name = "Revue de performance (P-M11.10)"
        verbose_name_plural = "Revues de performance (P-M11.10)"

    def __str__(self):
        return f"{self.code} — {self.period}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = ControleGestionSequence.next_for("RPF", "RPF")
        return super().save(*args, **kwargs)


class ValidationMarge(models.Model):
    """Validation de la marge prévisionnelle d'une affaire par le contrôle de gestion (CA et marge figés)."""

    class Statut(models.TextChoices):
        VALIDEE = "validee", "Validée"
        REJETEE = "rejetee", "Rejetée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    affaire = models.ForeignKey("commercial.Affaire", on_delete=models.CASCADE, related_name="validations_marge")
    ca = models.DecimalField(max_digits=16, decimal_places=2, verbose_name="CA contractuel figé")
    marge = models.DecimalField(max_digits=16, decimal_places=2, verbose_name="Marge prévue figée")
    statut = models.CharField(max_length=10, choices=Statut.choices, verbose_name="Décision")
    commentaire = models.CharField(max_length=250, blank=True, verbose_name="Commentaire")
    par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", verbose_name="Décidée par")
    le = models.DateTimeField(auto_now_add=True, verbose_name="Décidée le")

    class Meta:
        ordering = ["-le"]
        verbose_name = "Validation de marge d'affaire"
        verbose_name_plural = "Validations de marge d'affaire"


class ProvisionFnp(models.Model):
    """Provision des factures non parvenues (compte 408) : réceptions validées non facturées à la date d'arrêté.

    Écriture OD comptabilisée (Dr charge · Cr 408), extournée à l'ouverture de la période suivante.
    """

    class Statut(models.TextChoices):
        COMPTABILISEE = "comptabilisee", "Comptabilisée"
        EXTOURNEE = "extournee", "Extournée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    date_arrete = models.DateField(unique=True, verbose_name="Date d'arrêté")
    montant = models.DecimalField(max_digits=16, decimal_places=2, verbose_name="Montant provisionné (HT)")
    detail = models.JSONField(default=list, blank=True, verbose_name="Détail par ligne de commande")
    statut = models.CharField(max_length=14, choices=Statut.choices, default=Statut.COMPTABILISEE, verbose_name="Statut")
    move = models.ForeignKey(
        "accounting_kernel.AccountMove", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        verbose_name="Écriture de provision",
    )
    extourne = models.ForeignKey(
        "accounting_kernel.AccountMove", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        verbose_name="Écriture d'extourne",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="Passée par"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_arrete"]
        verbose_name = "Provision factures non parvenues (408)"
        verbose_name_plural = "Provisions factures non parvenues (408)"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = ControleGestionSequence.next_for("FNP", "FNP")
        return super().save(*args, **kwargs)


class AxeAnalytiqueM11(models.Model):
    """Nature M11 d'un axe analytique (activité / profil contractuel) : le réalisé d'un budget sur cet axe agrège
    les écritures des affaires de l'activité ou du profil correspondant."""

    class Nature(models.TextChoices):
        ACTIVITE = "activite", "Activité"
        PROFIL = "profil", "Profil contractuel"

    axis = models.OneToOneField("referentiels.AnalyticAxis", on_delete=models.CASCADE, related_name="nature_m11")
    nature = models.CharField(max_length=10, choices=Nature.choices, verbose_name="Nature")

    class Meta:
        verbose_name = "Axe analytique M11 (activité / profil)"
        verbose_name_plural = "Axes analytiques M11 (activité / profil)"


class MargeTerminaisonAffaire(models.Model):
    """Dernière marge à terminaison d'une affaire publiée par M3 (événement outbox `operations.marge_terminaison`)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    affaire = models.OneToOneField(
        "commercial.Affaire", on_delete=models.CASCADE, related_name="marge_terminaison_m3", verbose_name="Affaire"
    )
    avancement_pct = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True, verbose_name="Avancement (%)")
    chiffre_affaires = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True, verbose_name="Chiffre d'affaires")
    couts_engages = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True, verbose_name="Coûts engagés")
    cout_a_terminaison = models.DecimalField(
        max_digits=16, decimal_places=2, null=True, blank=True, verbose_name="Coût à terminaison"
    )
    marge_a_terminaison = models.DecimalField(
        max_digits=16, decimal_places=2, null=True, blank=True, verbose_name="Marge à terminaison"
    )
    marge_pct = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True, verbose_name="Marge (%)")
    ordres = models.JSONField(default=list, blank=True, verbose_name="OF de l'affaire")
    publie_le = models.DateTimeField(null=True, blank=True, verbose_name="Publiée par M3 le")
    publie_par = models.CharField(max_length=254, blank=True, verbose_name="Publiée par")
    evenement = models.UUIDField(null=True, blank=True, verbose_name="Événement outbox")
    recu_le = models.DateTimeField(auto_now=True, verbose_name="Reçue le")

    class Meta:
        ordering = ["affaire__code"]
        verbose_name = "Marge à terminaison (M3)"
        verbose_name_plural = "Marges à terminaison (M3)"

    def __str__(self):
        return f"{self.affaire_id} — {self.marge_a_terminaison}"
