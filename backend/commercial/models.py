"""Module M1 — Commercial / CRM / CLM (RF-ERP-01…05).

CRM & mémoire client (scoring, alertes) · chiffrage multi-options & revue
d'appel d'offres · affaires (jalons, OF/BS, revue de commande) · pilotage
(pipeline, taux de conversion, marge par profil) · profils contractuels
MARCHE_TRAVAUX / MAINTENANCE · soumission & suivi client. Procédures MANUEL 6.3-6.9.
"""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone


class CommercialSequence(models.Model):
    """Numérotation séquentielle par type d'objet (concept `ir.sequence`)."""

    kind = models.CharField(max_length=10, unique=True, verbose_name="Type")
    prefix = models.CharField(max_length=10, verbose_name="Préfixe")
    padding = models.PositiveSmallIntegerField(default=5, verbose_name="Zéro-padding")
    next_number = models.PositiveIntegerField(default=1, verbose_name="Prochain numéro")

    class Meta:
        verbose_name = "Séquence Commercial"
        verbose_name_plural = "Séquences Commercial"

    def __str__(self):
        return f"{self.kind} → {self.prefix}{self.next_number:0{self.padding}d}"

    @classmethod
    def next_for(cls, kind, prefix):
        """Retourne le numéro suivant du type, en verrouillant la séquence."""
        seq, _ = cls.objects.get_or_create(
            kind=kind, defaults={"prefix": prefix, "padding": 5}
        )
        with transaction.atomic():
            seq = cls.objects.select_for_update().get(pk=seq.pk)
            number = f"{seq.prefix}{str(seq.next_number).zfill(seq.padding)}"
            seq.next_number += 1
            seq.save(update_fields=["next_number"])
        return number


class ClientProfile(models.Model):
    """Mémoire client — segment, scoring, contacts, historique (M1.1)."""

    class Segment(models.TextChoices):
        PETROLE_GAZ = "petrole_gaz", "Pétrole & Gaz"
        INDUSTRIE = "industrie", "Industrie"
        CONSTRUCTION = "construction", "BTP / Construction"
        MINES = "mines", "Mines"
        ADMIN_PUB = "admin_pub", "Administration publique"
        PARTICULIER = "particulier", "Particulier"
        AUTRE = "autre", "Autre"

    class Origin(models.TextChoices):
        APPEL_OFFRES = "appel_offres", "Appel d'offres"
        RELATION = "relation", "Relation commerciale"
        PROSPECTION = "prospection", "Prospection"
        MARCHE = "marche", "Marché existant"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    partner = models.OneToOneField(
        "referentiels.Partner",
        on_delete=models.CASCADE,
        related_name="commercial_profile",
        verbose_name="Tiers",
    )
    segment = models.CharField(
        max_length=20, choices=Segment.choices, default=Segment.AUTRE, verbose_name="Segment"
    )
    scoring = models.PositiveSmallIntegerField(
        default=0, verbose_name="Score client (0-100)"
    )
    origin = models.CharField(
        max_length=20, choices=Origin.choices, default=Origin.RELATION, verbose_name="Origine"
    )
    contacts = models.JSONField(default=dict, blank=True, verbose_name="Contacts")
    history = models.JSONField(default=list, blank=True, verbose_name="Historique / mémoire")
    last_contact = models.DateField(null=True, blank=True, verbose_name="Dernier contact")
    next_contact = models.DateField(null=True, blank=True, verbose_name="Prochain contact")
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-scoring", "partner__name"]
        verbose_name = "Client (mémoire CRM)"
        verbose_name_plural = "Clients (mémoire CRM)"
        indexes = [models.Index(fields=["segment", "is_active"])]

    def __str__(self):
        return f"{self.partner} — score {self.scoring}"

    @property
    def short_name(self):
        return self.partner.name


class Opportunity(models.Model):
    """Opportunité commerciale du pipeline CRM (M1.1 / M1.4)."""

    class Stage(models.TextChoices):
        PROSPECTION = "prospection", "Prospection"
        QUALIFICATION = "qualification", "Qualification"
        OFFRE = "offre", "Offre soumise"
        NEGOCIATION = "negociation", "Négociation"
        GAGNE = "gagne", "Gagnée"
        PERDU = "perdu", "Perdue"

    class Origin(models.TextChoices):
        APPEL_OFFRES = "appel_offres", "Appel d'offres"
        RELATION = "relation", "Relation commerciale"
        PROSPECTION = "prospection", "Prospection"
        MARCHE = "marche", "Marché existant"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    client = models.ForeignKey(
        ClientProfile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="opportunities",
        verbose_name="Client",
    )
    subject = models.CharField(max_length=200, verbose_name="Objet")
    stage = models.CharField(
        max_length=14, choices=Stage.choices, default=Stage.PROSPECTION, db_index=True,
        verbose_name="Étape",
    )
    amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Montant estimé"
    )
    probability = models.PositiveSmallIntegerField(
        default=0, verbose_name="Probabilité (%)"
    )
    expected_close = models.DateField(null=True, blank=True, verbose_name="Clôture prévue")
    origin = models.CharField(
        max_length=20, choices=Origin.choices, default=Origin.RELATION, verbose_name="Origine"
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="commercial_opportunities",
        verbose_name="Responsable",
    )
    description = models.TextField(blank=True, verbose_name="Description")
    won_date = models.DateField(null=True, blank=True, verbose_name="Date de gain")
    lost_reason = models.CharField(max_length=200, blank=True, verbose_name="Motif de perte")
    is_active = models.BooleanField(default=True, verbose_name="Active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-created_at"]
        verbose_name = "Opportunité"
        verbose_name_plural = "Opportunités"
        indexes = [models.Index(fields=["stage", "is_active"])]

    def __str__(self):
        return f"{self.code} — {self.subject} ({self.get_stage_display()})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = CommercialSequence.next_for("OPP", "OPP")
        if self.stage == self.Stage.GAGNE and self.won_date is None:
            self.won_date = timezone.localdate()
            self.probability = 100
        if self.stage == self.Stage.PERDU:
            self.probability = 0
        return super().save(*args, **kwargs)


class Estimate(models.Model):
    """Chiffrage / offre commerciale — multi-options (M1.2)."""

    class Status(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        SOUMISE = "soumise", "Soumise"
        GAGNEE = "gagnee", "Gagnée"
        PERDUE = "perdue", "Perdue"
        ANNULEE = "annulee", "Annulée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    opportunity = models.ForeignKey(
        Opportunity,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="estimates",
        verbose_name="Opportunité",
    )
    client = models.ForeignKey(
        ClientProfile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="estimates",
        verbose_name="Client",
    )
    title = models.CharField(max_length=200, verbose_name="Intitulé")
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.BROUILLON, verbose_name="Statut"
    )
    currency = models.ForeignKey(
        "referentiels.Currency",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="commercial_estimates",
        verbose_name="Devise",
    )
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Total")
    margin = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Marge prévue"
    )
    valid_until = models.DateField(null=True, blank=True, verbose_name="Validité de l'offre")
    is_global_rental = models.BooleanField(
        default=False, verbose_name="Prestation GLOBAL RENTAL"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="commercial_estimates",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Chiffrage / Offre"
        verbose_name_plural = "Chiffrages / Offres"

    def __str__(self):
        return f"{self.code} — {self.title}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = CommercialSequence.next_for("EST", "EST")
        return super().save(*args, **kwargs)


class EstimateOption(models.Model):
    """Option d'un chiffrage multi-options (M1.2)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    estimate = models.ForeignKey(
        Estimate, on_delete=models.CASCADE, related_name="options", verbose_name="Chiffrage"
    )
    label = models.CharField(max_length=200, verbose_name="Libellé de l'option")
    amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Montant de l'option"
    )
    duration_months = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="Durée (mois)"
    )
    notes = models.TextField(blank=True, verbose_name="Notes")
    is_selected = models.BooleanField(default=False, verbose_name="Option retenue")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Option de chiffrage"
        verbose_name_plural = "Options de chiffrage"

    def __str__(self):
        return f"{self.label} — {self.amount}"


class EstimateLine(models.Model):
    """Ligne d'un chiffrage (article / prestation)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    estimate = models.ForeignKey(
        Estimate, on_delete=models.CASCADE, related_name="lines", verbose_name="Chiffrage"
    )
    article = models.ForeignKey(
        "referentiels.Article",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="commercial_lines",
        verbose_name="Article",
    )
    label = models.CharField(max_length=200, verbose_name="Désignation")
    quantity = models.DecimalField(max_digits=14, decimal_places=2, default=1, verbose_name="Qté")
    unit = models.ForeignKey(
        "referentiels.UnitOfMeasure",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Unité",
    )
    unit_price = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Prix unitaire"
    )
    price_total = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Total ligne"
    )

    class Meta:
        ordering = ["estimate", "id"]
        verbose_name = "Ligne de chiffrage"
        verbose_name_plural = "Lignes de chiffrage"

    def __str__(self):
        return f"{self.label} × {self.quantity}"

    def save(self, *args, **kwargs):
        self.price_total = self.quantity * self.unit_price
        return super().save(*args, **kwargs)


class TenderReview(models.Model):
    """Revue d'appel d'offres avant soumission (proc. MANUEL 6.5)."""

    class Status(models.TextChoices):
        EN_COURS = "en_cours", "En cours de revue"
        PRET = "pret", "Prêt à soumettre"
        SOUMIS = "soumis", "Soumis"
        ARCHIVE = "archive", "Archivé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    estimate = models.ForeignKey(
        Estimate,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tender_reviews",
        verbose_name="Chiffrage",
    )
    client = models.ForeignKey(
        "referentiels.Partner",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tender_reviews",
        verbose_name="Client",
    )
    tender_ref = models.CharField(max_length=100, blank=True, verbose_name="Réf. appel d'offres")
    bid_deadline = models.DateField(null=True, blank=True, verbose_name="Date limite de dépôt")
    review_status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.EN_COURS, verbose_name="État de revue"
    )
    requirements = models.JSONField(default=list, blank=True, verbose_name="Exigences")
    decision = models.TextField(blank=True, verbose_name="Décision / suite")
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tender_reviews",
        verbose_name="Revu par",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="Revu le")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Revue d'appel d'offres"
        verbose_name_plural = "Revues d'appel d'offres"

    def __str__(self):
        return f"{self.tender_ref or 'AO'} — {self.get_review_status_display()}"


class Affaire(models.Model):
    """Affaire commercial exécutée — jalons, OF/BS, revue de commande (M1.3)."""

    class AffaireType(models.TextChoices):
        CHANTIER = "chantier", "Chantier"
        ATELIER = "atelier", "Atelier"
        MAINTENANCE = "maintenance", "Maintenance"
        FOURNITURE = "fourniture", "Fourniture"

    class Status(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        CONFIRMEE = "confirmee", "Confirmée"
        EN_COURS = "en_cours", "En cours"
        CLOTUREE = "cloturee", "Clôturée"
        ARCHIVEE = "archivee", "Archivée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    opportunity = models.ForeignKey(
        Opportunity,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="affaires",
        verbose_name="Opportunité",
    )
    client = models.ForeignKey(
        ClientProfile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="affaires",
        verbose_name="Client",
    )
    title = models.CharField(max_length=200, verbose_name="Intitulé")
    description = models.TextField(blank=True, verbose_name="Description")
    affaire_type = models.CharField(
        max_length=12, choices=AffaireType.choices, default=AffaireType.ATELIER,
        verbose_name="Type",
    )
    currency = models.ForeignKey(
        "referentiels.Currency",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Devise",
    )
    contract_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Montant contractuel"
    )
    margin = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Marge"
    )
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.BROUILLON, verbose_name="Statut"
    )
    start_date = models.DateField(null=True, blank=True, verbose_name="Début")
    end_date = models.DateField(null=True, blank=True, verbose_name="Fin")
    is_global_rental = models.BooleanField(default=False, verbose_name="GLOBAL RENTAL")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Affaire"
        verbose_name_plural = "Affaires"

    def __str__(self):
        return f"{self.code} — {self.title}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = CommercialSequence.next_for("AFF", "AFF")
        return super().save(*args, **kwargs)

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "La date de fin doit être postérieure au début."})


class Milestone(models.Model):
    """Jalon d'affaire — rattachements, situations travaux (M1.3)."""

    class Status(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente"
        FAIT = "fait", "Réalisé"
        RETARD = "retard", "En retard"
        SKIP = "skip", "Sauté"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    affaire = models.ForeignKey(
        Affaire, on_delete=models.CASCADE, related_name="milestones", verbose_name="Affaire"
    )
    code = models.CharField(max_length=20, blank=True, verbose_name="Code")
    label = models.CharField(max_length=200, verbose_name="Intitulé")
    planned_date = models.DateField(verbose_name="Date prévue")
    actual_date = models.DateField(null=True, blank=True, verbose_name="Date réelle")
    progress = models.PositiveSmallIntegerField(
        default=0, verbose_name="Avancement (%)"
    )
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.EN_ATTENTE, verbose_name="Statut"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["affaire", "planned_date"]
        verbose_name = "Jalon"
        verbose_name_plural = "Jalons"

    def __str__(self):
        return f"{self.affaire.code} / {self.label}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = CommercialSequence.next_for("MIL", "J")
        today = timezone.localdate()
        if self.actual_date:
            self.status = (
                self.Status.FAIT
                if self.actual_date <= self.planned_date
                else self.Status.RETARD
            )
        else:
            self.status = self.Status.RETARD if self.planned_date < today else self.Status.EN_ATTENTE
        return super().save(*args, **kwargs)


class Contract(models.Model):
    """Contrat commercial CLM — profils MARCHE_TRAVAUX / MAINTENANCE (M1.3)."""

    class Profile(models.TextChoices):
        MARCHE_TRAVAUX = "marche_travaux", "Marché de travaux"
        MAINTENANCE = "maintenance", "Contrat de maintenance"

    class Status(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        ACTIF = "actif", "Actif"
        SUSPENDU = "suspendu", "Suspendu"
        CLOTURE = "cloture", "Clôturé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    affaire = models.ForeignKey(
        Affaire,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="contracts",
        verbose_name="Affaire",
    )
    client = models.ForeignKey(
        ClientProfile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="contracts",
        verbose_name="Client",
    )
    profile = models.CharField(
        max_length=14, choices=Profile.choices, verbose_name="Profil contractuel"
    )
    start_date = models.DateField(verbose_name="Début")
    end_date = models.DateField(null=True, blank=True, verbose_name="Fin")
    months = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Durée (mois)")
    amount_initial = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Montant initial"
    )
    currency = models.ForeignKey(
        "referentiels.Currency",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Devise",
    )
    sla = models.CharField(max_length=200, blank=True, verbose_name="SLA (maintenance)")
    retenue_rate = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        verbose_name="Taux de retenue (%)",
    )
    indexation = models.BooleanField(default=False, verbose_name="Clause d'indexation")
    penalty = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True, verbose_name="Pénalités"
    )
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.BROUILLON, verbose_name="Statut"
    )
    is_global_rental = models.BooleanField(default=False, verbose_name="GLOBAL RENTAL")
    notes = models.TextField(blank=True, verbose_name="Notes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Contrat (CLM)"
        verbose_name_plural = "Contrats (CLM)"

    def __str__(self):
        return f"{self.code} — {self.get_profile_display()}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = CommercialSequence.next_for("CTT", "CTT")
        today = timezone.localdate()
        if self.status == self.Status.ACTIF and self.end_date and today > self.end_date:
            self.status = self.Status.CLOTURE
        return super().save(*args, **kwargs)

    def clean(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "La date de fin doit être postérieure au début."})

    @property
    def days_to_expiry(self):
        if not self.end_date:
            return None
        return (self.end_date - timezone.localdate()).days

    @property
    def expiry_status(self):
        """Alerte contrat : EXPIRED / J-90 / J-60 / J-30 / OK (alignée M12)."""
        days = self.days_to_expiry
        if days is None:
            return "OK"
        if days < 0:
            return "EXPIRED"
        if days <= 30:
            return "J30"
        if days <= 60:
            return "J60"
        if days <= 90:
            return "J90"
        return "OK"


class ContractService(models.Model):
    """Prestation liée à un contrat de maintenance (forfait + variable, SLA)."""

    class Kind(models.TextChoices):
        FORFAIT = "forfait", "Forfait"
        VARIABLE = "variable", "Variable"
        SLA = "sla", "SLA / réactif"

    class Frequency(models.TextChoices):
        MENSUEL = "mensuel", "Mensuel"
        TRIMESTRIEL = "trimestriel", "Trimestriel"
        ANNUEL = "annuel", "Annuel"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contract = models.ForeignKey(
        Contract, on_delete=models.CASCADE, related_name="services", verbose_name="Contrat"
    )
    label = models.CharField(max_length=200, verbose_name="Prestation")
    kind = models.CharField(
        max_length=10, choices=Kind.choices, default=Kind.FORFAIT, verbose_name="Type"
    )
    sla_hours = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="SLA (heures)"
    )
    price = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Prix")
    frequency = models.CharField(
        max_length=12, choices=Frequency.choices, default=Frequency.MENSUEL,
        verbose_name="Facturation",
    )
    is_global_rental = models.BooleanField(default=False, verbose_name="GLOBAL RENTAL")

    class Meta:
        ordering = ["contract", "label"]
        verbose_name = "Prestation de contrat"
        verbose_name_plural = "Prestations de contrat"

    def __str__(self):
        return f"{self.contract.code} / {self.label}"


class SoumissionEvent(models.Model):
    """Soumission & suivi client — clarifications, négociations, retour (proc. 6.6)."""

    class Kind(models.TextChoices):
        CLARIFICATION = "clarification", "Clarification"
        NEGOCIATION = "negociation", "Négociation"
        RETOUR = "retour", "Retour client"
        LIVRAISON_DOC = "livraison_doc", "Livraison document"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(
        ClientProfile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="soumission_events",
        verbose_name="Client",
    )
    opportunity = models.ForeignKey(
        Opportunity,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="soumission_events",
        verbose_name="Opportunité",
    )
    estimate = models.ForeignKey(
        Estimate,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="soumission_events",
        verbose_name="Chiffrage",
    )
    kind = models.CharField(
        max_length=14, choices=Kind.choices, verbose_name="Type d'échange"
    )
    happened_at = models.DateField(default=timezone.localdate, verbose_name="Date")
    content = models.TextField(verbose_name="Contenu")
    document = models.ForeignKey(
        "documents.Document",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="commercial_soumissions",
        verbose_name="Document lié",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="commercial_soumissions",
        verbose_name="Auteur",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-happened_at", "-created_at"]
        verbose_name = "Échange soumission client"
        verbose_name_plural = "Échanges soumission client"

    def __str__(self):
        return f"{self.get_kind_display()} — {self.happened_at}"