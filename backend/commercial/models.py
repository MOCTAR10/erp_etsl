"""Module M1 — Commercial / CRM / CLM (RF-ERP-01…05).

CRM & mémoire client (scoring, alertes) · chiffrage multi-options & revue
d'appel d'offres · affaires (jalons, OF/BS, revue de commande) · pilotage
(pipeline, taux de conversion, marge par profil) · profils contractuels
MARCHE_TRAVAUX / MAINTENANCE · soumission & suivi client. Procédures MANUEL 6.3-6.9.
"""

import uuid
from decimal import Decimal

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


# Profils contractuels (pipe, profils CLM) et natures de coût du chiffrage (écarts M1).
PROFILS_PIPE = [
    ("marche_travaux", "Marché de travaux"),
    ("maintenance", "Contrat de maintenance"),
    ("global_rental", "GLOBAL RENTAL"),
    ("autre", "Autre"),
]
NATURES_COUT = [
    ("fourniture", "Fournitures / matières"),
    ("main_oeuvre", "Main-d'œuvre"),
    ("sous_traitance", "Sous-traitance"),
    ("equipement", "Équipements / location"),
    ("frais_directs", "Autres frais directs"),
]


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
    profil_contractuel = models.CharField(
        max_length=16, blank=True, default="", choices=PROFILS_PIPE, verbose_name="Profil contractuel visé"
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
        REMPLACEE = "remplacee", "Remplacée par une révision"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    # Versioning des offres (clôture M1, CDC §3.5) : une révision crée une nouvelle version, l'ancienne est scellée.
    version = models.PositiveSmallIntegerField(default=1, editable=False, verbose_name="Version")
    version_precedente = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="revisions",
        editable=False, verbose_name="Version précédente",
    )
    soumise_le = models.DateTimeField(null=True, blank=True, editable=False, verbose_name="Soumise le")
    decision_le = models.DateTimeField(null=True, blank=True, editable=False, verbose_name="Décision le")
    motif_perte = models.CharField(max_length=250, blank=True, editable=False, verbose_name="Motif de perte")
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
    # Structure de chiffrage (écarts M1) : à défaut, paramètres provisoires `CHIFFRAGE_*`.
    taux_frais_indirects = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="Frais indirects (%)"
    )
    taux_aleas = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="Aléas (%)")
    taux_marge_cible = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="Marge cible (%)"
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

    @property
    def montant_offre(self):
        """Montant chiffré : option retenue, sinon meilleure option, sinon somme des lignes, sinon total saisi."""
        options = list(self.options.all())
        retenue = next((o for o in options if o.is_selected), None)
        if retenue:
            return retenue.amount
        if options:
            return max(o.amount for o in options)
        lignes = sum((ligne.price_total for ligne in self.lines.all()), Decimal("0"))
        return lignes or self.total

    @transaction.atomic
    def reviser(self, user):
        """Nouvelle version en brouillon (options et lignes copiées) ; la version courante est remplacée."""
        options, lignes = list(self.options.all()), list(self.lines.all())
        ancienne = self.pk
        nouvelle = Estimate.objects.get(pk=ancienne)
        nouvelle.pk, nouvelle.id, nouvelle.code = None, uuid.uuid4(), ""
        nouvelle._state.adding = True
        nouvelle.version = self.version + 1
        nouvelle.version_precedente_id = ancienne
        nouvelle.status = self.Status.BROUILLON
        nouvelle.soumise_le = nouvelle.decision_le = None
        nouvelle.created_by = user
        nouvelle.save()
        for objet in options + lignes:
            objet.pk, objet.id, objet.estimate = None, uuid.uuid4(), nouvelle
            objet._state.adding = True
            objet.save()
        Estimate.objects.filter(pk=ancienne).update(status=self.Status.REMPLACEE, decision_le=timezone.now())
        return nouvelle


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
    lot = models.CharField(max_length=80, blank=True, verbose_name="Lot / poste de nomenclature")
    nature = models.CharField(max_length=16, choices=NATURES_COUT, default="fourniture", verbose_name="Nature de coût")
    cout_unitaire = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Déboursé unitaire (coût)"
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
    # RAO (CDC M1 §3.4/§3.8) : critères [{libelle, poids, note 0-100}] → note pondérée → Go / Go sous réserve / No-Go.
    criteres = models.JSONField(default=list, blank=True, verbose_name="Critères notés (RAO)")
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="Note pondérée (%)")
    decision_rao = models.CharField(
        max_length=12, blank=True, verbose_name="Décision RAO",
        choices=[("go", "Go"), ("go_reserve", "Go sous réserve"), ("no_go", "No-Go")],
    )
    document = models.ForeignKey(
        "documents.Document", null=True, blank=True, on_delete=models.PROTECT, related_name="revues_ao",
        editable=False, verbose_name="Formulaire RAO archivé (GED)",
    )
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

    def calculer_rao(self):
        """Note pondérée = Σ(poids × note) / Σ poids ; seuils paramétrables (défaut CDC : ≥ 75 % Go, 50-75 % Go sous
        réserve, < 50 % No-Go — `RAO_SEUIL_GO` / `RAO_SEUIL_RESERVE`, provisoires)."""
        from .ecarts_m1 import get_param

        criteres = self.criteres or []
        total = sum(Decimal(str(c.get("poids", 0))) for c in criteres)
        if not criteres or total <= 0:
            self.score, self.decision_rao = None, ""
            return
        self.score = (sum(Decimal(str(c["poids"])) * Decimal(str(c["note"])) for c in criteres) / total).quantize(Decimal("0.01"))
        go, reserve = get_param("RAO_SEUIL_GO"), get_param("RAO_SEUIL_RESERVE")
        self.decision_rao = "go" if self.score >= go else ("go_reserve" if self.score >= reserve else "no_go")

    def save(self, *args, **kwargs):
        self.calculer_rao()
        super().save(*args, **kwargs)



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
    # Pilotage (clôture M1, CDC §3.4 « marge par responsable d'affaire ») et lien analytique vers M10 / M11.
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="affaires_responsable", verbose_name="Responsable d'affaire",
    )
    analytic = models.ForeignKey(
        "referentiels.AnalyticAccount", null=True, blank=True, on_delete=models.PROTECT,
        related_name="affaires", editable=False, verbose_name="Compte analytique (axe projet)",
    )
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
        if self.responsable_id is None and self.opportunity_id and self.opportunity.owner_id:
            self.responsable_id = self.opportunity.owner_id
        return super().save(*args, **kwargs)

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "La date de fin doit être postérieure au début."})

    def assurer_compte_analytique(self):
        """Compte analytique de l'affaire sur l'axe « projet » (créé à la confirmation) : clé des coûts et marges."""
        from referentiels.models import AnalyticAccount, AnalyticAxis

        if self.analytic_id:
            return self.analytic
        axe = AnalyticAxis.objects.filter(axis_type=AnalyticAxis.AxisType.PROJET).order_by("code").first()
        if axe is None:
            axe = AnalyticAxis.objects.create(code="AFFAIRES", label="Affaires", axis_type=AnalyticAxis.AxisType.PROJET)
        self.analytic, _ = AnalyticAccount.objects.get_or_create(axis=axe, code=self.code, defaults={"label": self.title[:200]})
        self.save(update_fields=["analytic", "updated_at"])
        return self.analytic



class RevueCommande(models.Model):
    """Revue de commande (CDC M1 §3.4 / §3.8 / §3.11) : conformité de la commande à l'offre signée.

    Δ prix ≤ 5 % et Δ délai ≤ 7 jours → revue légère ; sinon revue complète (Direction). L'affaire ne se confirme pas
    tant que sa revue de commande n'est pas validée.
    """

    SEUIL_PRIX_PCT = Decimal("5")
    SEUIL_DELAI_JOURS = 7

    class Type(models.TextChoices):
        LEGERE = "legere", "Revue légère"
        COMPLETE = "complete", "Revue complète"

    class Statut(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente"
        VALIDEE = "validee", "Validée"
        REFUSEE = "refusee", "Refusée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    affaire = models.OneToOneField(Affaire, on_delete=models.CASCADE, related_name="revue_commande", verbose_name="Affaire")
    montant_offre = models.DecimalField(max_digits=16, decimal_places=2, verbose_name="Montant de l'offre signée")
    montant_commande = models.DecimalField(max_digits=16, decimal_places=2, verbose_name="Montant de la commande")
    delai_offre_jours = models.PositiveIntegerField(verbose_name="Délai de l'offre (jours)")
    delai_commande_jours = models.PositiveIntegerField(verbose_name="Délai de la commande (jours)")
    type_revue = models.CharField(max_length=10, choices=Type.choices, verbose_name="Type de revue")
    statut = models.CharField(max_length=12, choices=Statut.choices, default=Statut.EN_ATTENTE, verbose_name="Statut")
    commentaire = models.TextField(blank=True, verbose_name="Commentaire de revue")
    document = models.ForeignKey(
        "documents.Document", null=True, blank=True, on_delete=models.PROTECT, related_name="revues_commande",
        editable=False, verbose_name="Revue de commande archivée (GED)",
    )
    valide_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+", verbose_name="Validée par"
    )
    valide_le = models.DateTimeField(null=True, blank=True, verbose_name="Validée le")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Revue de commande"
        verbose_name_plural = "Revues de commande"

    def __str__(self):
        return f"RC {self.affaire.code} ({self.get_type_revue_display()})"

    @property
    def delta_prix_pct(self):
        if not self.montant_offre:
            return Decimal("0")
        return (abs(self.montant_commande - self.montant_offre) / self.montant_offre * 100).quantize(Decimal("0.01"))

    @property
    def delta_delai_jours(self):
        return abs(int(self.delai_commande_jours) - int(self.delai_offre_jours))

    def save(self, *args, **kwargs):
        legere = self.delta_prix_pct <= self.SEUIL_PRIX_PCT and self.delta_delai_jours <= self.SEUIL_DELAI_JOURS
        self.type_revue = self.Type.LEGERE if legere else self.Type.COMPLETE
        super().save(*args, **kwargs)

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
    # Échéancier contractuel (clôture M1 → M10) : un jalon réalisé devient « à facturer ».
    montant = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Montant facturable")
    facture_le = models.DateField(null=True, blank=True, editable=False, verbose_name="Facturé le")
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
    # Signature électronique + archivage GED 10 ans exigés à l'activation (clôture M1, CDC §3.5 / §3.11).
    document = models.ForeignKey(
        "documents.Document", null=True, blank=True, on_delete=models.PROTECT, related_name="contrats_commerciaux",
        editable=False, verbose_name="Contrat signé (GED)",
    )
    signe_le = models.DateTimeField(null=True, blank=True, editable=False, verbose_name="Activé (signé) le")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Champs figés une fois le contrat signé : toute modification passe par un avenant.
    CHAMPS_CONTRACTUELS = (
        "client", "affaire", "profile", "start_date", "end_date", "months", "amount_initial", "currency",
        "sla", "retenue_rate", "indexation", "penalty", "is_global_rental",
    )

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
    def montant_actuel(self):
        signes = self.avenants.filter(statut=Avenant.Statut.SIGNE).aggregate(t=models.Sum("delta_montant"))["t"]
        return self.amount_initial + (signes or 0)

    @property
    def days_to_expiry(self):
        if not self.end_date:
            return None
        return (self.end_date - timezone.localdate()).days

    @property
    def expiry_status(self):
        """Alerte contrat : EXPIRED / J0 / J15 / J30 / J60 / J90 / OK (alignée M12, EX-G-05)."""
        from config.echeances import bande

        return {"en_cours": "OK", "expiree": "EXPIRED"}.get(b := bande(self.days_to_expiry), b.upper())


class Avenant(models.Model):
    """Avenant à un contrat actif (clôture M1, CDC §3.5 « versioning des avenants ») : seule voie de modification
    d'un contrat signé. Signé électroniquement et archivé 10 ans, il ajuste montant et échéance ; puis il est scellé."""

    class Statut(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        SIGNE = "signe", "Signé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contract = models.ForeignKey(Contract, on_delete=models.PROTECT, related_name="avenants", verbose_name="Contrat")
    numero = models.PositiveSmallIntegerField(editable=False, verbose_name="N° d'avenant")
    objet = models.CharField(max_length=250, verbose_name="Objet")
    delta_montant = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Variation de montant")
    nouvelle_date_fin = models.DateField(null=True, blank=True, verbose_name="Nouvelle date de fin")
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.BROUILLON, verbose_name="Statut")
    document = models.ForeignKey(
        "documents.Document", null=True, blank=True, on_delete=models.PROTECT, related_name="avenants",
        editable=False, verbose_name="Avenant signé (GED)",
    )
    signe_le = models.DateTimeField(null=True, blank=True, editable=False, verbose_name="Signé le")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="Créé par"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["contract", "numero"]
        verbose_name = "Avenant"
        verbose_name_plural = "Avenants"
        constraints = [models.UniqueConstraint(fields=["contract", "numero"], name="uniq_avenant_numero")]

    def __str__(self):
        return f"{self.contract.code} — avenant n° {self.numero}"

    def save(self, *args, **kwargs):
        if self._state.adding and not self.numero:
            dernier = Avenant.objects.filter(contract_id=self.contract_id).aggregate(m=models.Max("numero"))["m"]
            self.numero = (dernier or 0) + 1
        return super().save(*args, **kwargs)

    def clean(self):
        if self.contract_id and self.contract.status not in (Contract.Status.ACTIF, Contract.Status.SUSPENDU):
            raise ValidationError({"contract": "Un avenant porte sur un contrat signé (actif ou suspendu)."})
        if self.nouvelle_date_fin and self.contract_id and self.nouvelle_date_fin < self.contract.start_date:
            raise ValidationError({"nouvelle_date_fin": "La nouvelle échéance précède le début du contrat."})


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


class ParametreCommercial(models.Model):
    """Paramètre M1 modifiable par ETSL sans développeur (scoring, alertes, chiffrage, profils, durées, RAO).

    Valeur provisoire tant qu'ETSL ne l'a pas confirmée ; défauts créés à la volée par `ecarts_m1.get_param`.
    """

    class StatutValeur(models.TextChoices):
        PROVISOIRE = "provisoire", "Provisoire"
        CONFIRME = "confirme", "Confirmé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=40, unique=True, verbose_name="Identifiant")
    label = models.CharField(max_length=200, verbose_name="Libellé")
    valeur = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Valeur")
    unite = models.CharField(max_length=20, blank=True, verbose_name="Unité")
    texte = models.TextField(
        blank=True, verbose_name="Valeur texte",
        help_text="Libellé d'un critère RAO, définition (BS, prix moyen) ou mention de modèle PDF.",
    )
    statut_valeur = models.CharField(
        max_length=10, choices=StatutValeur.choices, default=StatutValeur.PROVISOIRE, verbose_name="Statut de la valeur"
    )
    confirme_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Confirmé par",
    )
    confirme_le = models.DateTimeField(null=True, blank=True, verbose_name="Confirmé le")

    class Meta:
        ordering = ["code"]
        verbose_name = "Paramètre commercial"
        verbose_name_plural = "Paramètres commerciaux"

    def __str__(self):
        return f"{self.code} = {self.valeur} {self.unite}"

    @property
    def est_provisoire(self):
        return self.statut_valeur != self.StatutValeur.CONFIRME


class HabilitationRequise(models.Model):
    """Habilitation exigée du personnel affecté (aval M9) : par profil contractuel (défaut) ou par contrat."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contract = models.ForeignKey(
        Contract, null=True, blank=True, on_delete=models.CASCADE, related_name="habilitations_requises",
        verbose_name="Contrat",
    )
    profile = models.CharField(max_length=14, blank=True, choices=Contract.Profile.choices, verbose_name="Profil")
    mot_cle = models.CharField(max_length=80, verbose_name="Mot-clé de la qualification exigée")
    libelle = models.CharField(max_length=200, blank=True, verbose_name="Libellé")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["profile", "mot_cle"]
        verbose_name = "Habilitation requise"
        verbose_name_plural = "Habilitations requises"

    def __str__(self):
        return f"{self.contract or self.get_profile_display()} — {self.mot_cle}"

    def clean(self):
        if not self.contract_id and not self.profile:
            raise ValidationError({"profile": "Indiquez un contrat ou un profil contractuel."})
