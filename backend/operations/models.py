"""Module M3 — Opérations (Atelier + Chantier) (RF-ERP-20…23).

Ordre de fabrication & gamme opératoire · pointage main-d'œuvre chantier
(→ M9) · rattachements & situations travaux · plan de charge & capacité
atelier · études & préparation des travaux (plans, DED / DOE).
Procédures MANUEL 5.3-5.7.
"""

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction


class OperationsSequence(models.Model):
    """Numérotation séquentielle par type (OF, GAM, PTS, SIT)."""

    kind = models.CharField(max_length=10, unique=True, verbose_name="Type")
    prefix = models.CharField(max_length=10, verbose_name="Préfixe")
    padding = models.PositiveSmallIntegerField(default=5, verbose_name="Zéro-padding")
    next_number = models.PositiveIntegerField(default=1, verbose_name="Prochain numéro")

    class Meta:
        verbose_name = "Séquence Opérations"
        verbose_name_plural = "Séquences Opérations"

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


class GammeOperatoire(models.Model):
    """Gamme type — suite d'opérations pour produire un ouvrage (RF-ERP-20)."""

    class Status(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        ACTIVE = "active", "Active"
        ARCHIVEE = "archivee", "Archivée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    label = models.CharField(max_length=200, verbose_name="Intitulé")
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.BROUILLON, verbose_name="Statut"
    )
    is_global_rental = models.BooleanField(default=False, verbose_name="GLOBAL RENTAL")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Gamme opératoire"
        verbose_name_plural = "Gammes opératoires"

    def __str__(self):
        return f"{self.code} — {self.label}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = OperationsSequence.next_for("GAM", "GAM")
        return super().save(*args, **kwargs)

    @property
    def total_hours_decimal(self):
        return sum((op.planned_hours for op in self.operations.all()), Decimal("0")) if self.id else Decimal("0")

    @property
    def total_planned_hours(self):
        return sum((float(op.planned_hours) for op in self.operations.all()), 0) if self.id else 0


class GammeOperation(models.Model):
    """Opération d'une gamme type — ordre, poste, temps (RF-ERP-20)."""

    class Poste(models.TextChoices):
        DECOUPE = "decoupe", "Découpe"
        TUYAUTERIE = "tuyauterie", "Tuyauterie"
        SOUDURE = "soudure", "Soudure"
        CHAUDRONNERIE = "chaudronnerie", "Chaudronnerie"
        STRUCTURE = "structure", "Structures métalliques"
        MONTAGE = "montage", "Montage"
        CONTRÔLE = "controle", "Contrôle / essais"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    gamme = models.ForeignKey(
        GammeOperatoire, on_delete=models.CASCADE, related_name="operations", verbose_name="Gamme"
    )
    sequence = models.PositiveIntegerField(default=1, verbose_name="Ordre")
    label = models.CharField(max_length=200, verbose_name="Opération")
    poste = models.CharField(
        max_length=16, choices=Poste.choices, default=Poste.TUYAUTERIE, verbose_name="Poste"
    )
    planned_hours = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Heures prévues"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["gamme", "sequence"]
        verbose_name = "Opération de gamme"
        verbose_name_plural = "Opérations de gamme"
        indexes = [models.Index(fields=["gamme", "sequence"])]

    def __str__(self):
        return f"{self.gamme.code} / {self.sequence} — {self.label}"


class OrdreFabrication(models.Model):
    """Ordre de fabrication (OF) — production atelier ou chantier (RF-ERP-20)."""

    class Status(models.TextChoices):
        PREVU = "prevu", "Prévu"
        LANCE = "lance", "Lancé"
        EN_COURS = "en_cours", "En cours"
        TERMINE = "termine", "Terminé"
        CLOTURE = "cloture", "Clôturé"
        ANNULE = "annule", "Annulé"

    class Scope(models.TextChoices):
        ATELIER = "atelier", "Atelier"
        CHANTIER = "chantier", "Chantier"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    label = models.CharField(max_length=200, verbose_name="Désignation")
    affaire = models.ForeignKey(
        "commercial.Affaire",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ordres_fabrication",
        verbose_name="Affaire",
    )
    gamme = models.ForeignKey(
        GammeOperatoire,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ordres_fabrication",
        verbose_name="Gamme type",
    )
    scope = models.CharField(
        max_length=10, choices=Scope.choices, default=Scope.ATELIER, verbose_name="Périmètre"
    )
    article = models.ForeignKey(
        "referentiels.Article",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Ouvrage / article",
    )
    quantity = models.DecimalField(
        max_digits=14, decimal_places=2, default=1, verbose_name="Quantité"
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PREVU, verbose_name="Statut"
    )
    planned_start = models.DateField(null=True, blank=True, verbose_name="Début prévu")
    planned_end = models.DateField(null=True, blank=True, verbose_name="Fin prévue")
    calculated_hours = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Heures calculées (gamme)"
    )
    alerte_mo_le = models.DateTimeField(
        null=True, blank=True, verbose_name="Alerte de dépassement de main-d'œuvre émise le"
    )
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="operations_ordres",
        verbose_name="Responsable",
    )
    soudeurs = models.ManyToManyField(
        "qualite.Soudeur", blank=True, related_name="ordres_fabrication",
        verbose_name="Soudeurs affectés",
        help_text="Qualifications contrôlées au démarrage de l'OF (CDC M6 §8.11).",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="operations_created_ordres",
        verbose_name="Créé par",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Ordre de fabrication"
        verbose_name_plural = "Ordres de fabrication"
        indexes = [models.Index(fields=["status", "scope"])]

    def __str__(self):
        return f"{self.code} — {self.label}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = OperationsSequence.next_for("OF", "OF")
        if self.gamme_id and not self.calculated_hours:
            # Heures calculées = temps de la gamme × quantité (jusqu'ici saisies à la main, donc à 0 pour un OF auto).
            self.calculated_hours = self.gamme.total_hours_decimal * (self.quantity or 1)
        return super().save(*args, **kwargs)

    def clean(self):
        if self.planned_start and self.planned_end and self.planned_end < self.planned_start:
            raise ValidationError({"planned_end": "La fin prévue doit être postérieure au début."})

    @property
    def pointage_hours(self):
        return sum((float(p.hours) for p in self.pointages.all()), 0) if self.id else 0


class PointageChantier(models.Model):
    """Pointage main-d'œuvre (OF / chantier) → M9 (RF-ERP-21)."""

    class Status(models.TextChoices):
        SAISI = "saisi", "Saisi"
        VALIDE = "valide", "Validé"
        TRANSFERE = "transfere", "Transféré paie (M9)"

    class TypeTempe(models.TextChoices):
        NORMAL = "normal", "Heures normales"
        SUPPLEMENTAIRE = "supplementaire", "Heures supplémentaires"
        NUIT = "nuit", "Heures de nuit"
        ASTREINTE = "astreinte", "Astreinte"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    ordre = models.ForeignKey(
        OrdreFabrication,
        on_delete=models.CASCADE,
        related_name="pointages",
        verbose_name="Ordre de fabrication",
    )
    worker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="operations_pointages",
        verbose_name="Opérateur",
    )
    worker_name = models.CharField(max_length=150, blank=True, verbose_name="Nom opérateur")
    date = models.DateField(verbose_name="Date")
    hours = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Heures"
    )
    hours_type = models.CharField(
        max_length=14, choices=TypeTempe.choices, default=TypeTempe.NORMAL, verbose_name="Type d'heures"
    )
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.SAISI, verbose_name="Statut"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="operations_created_pointages",
        verbose_name="Saisi par",
    )
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="operations_validated_pointages", verbose_name="Validé par",
    )
    validated_at = models.DateTimeField(null=True, blank=True, verbose_name="Validé le")
    saisie_temps = models.OneToOneField(
        "rh_paie.SaisieTemps", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="pointage_chantier", verbose_name="Saisie temps M9",
        help_text="Saisie temps générée dans M9 au transfert (flux pointage → paie).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "Pointage main-d'œuvre"
        verbose_name_plural = "Pointages main-d'œuvre"
        indexes = [models.Index(fields=["date", "status"])]

    def __str__(self):
        return f"{self.code} — {self.worker_name or self.worker} — {self.date}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = OperationsSequence.next_for("PTS", "PTS")
        return super().save(*args, **kwargs)

    def clean(self):
        if self.hours <= 0:
            raise ValidationError({"hours": "Le nombre d'heures doit être strictement positif."})
        if not self.worker_name and not self.worker:
            raise ValidationError(
                {"worker": "Le pointage doit être rattaché à un opérateur ou un nom libre."}
            )


class SituationTravaux(models.Model):
    """Situation de travaux — rattachement d'OF à une affaire (RF-ERP-22)."""

    class Status(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        SOUMISE = "soumise", "Soumise"
        VALIDEE = "validee", "Validée"
        FACTUREE = "facturee", "Facturée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    affaire = models.ForeignKey(
        "commercial.Affaire",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="situations_travaux",
        verbose_name="Affaire",
    )
    label = models.CharField(max_length=200, verbose_name="Intitulé")
    period_start = models.DateField(verbose_name="Début période")
    period_end = models.DateField(verbose_name="Fin période")
    amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Montant"
    )
    progress = models.PositiveSmallIntegerField(
        default=0, verbose_name="Avancement (%)"
    )
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.BROUILLON, verbose_name="Statut"
    )
    ordres = models.ManyToManyField(
        OrdreFabrication,
        blank=True,
        related_name="situations",
        verbose_name="Ordres de fabrication rattachés",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="operations_created_situations",
        verbose_name="Créé par",
    )
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="operations_validated_situations",
        verbose_name="Validé par",
    )
    validated_at = models.DateTimeField(null=True, blank=True, verbose_name="Validé le")
    facture_ref = models.CharField(max_length=60, blank=True, verbose_name="Référence facture (M10)")
    facture_le = models.DateField(null=True, blank=True, verbose_name="Facturée le")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-period_end", "-created_at"]
        verbose_name = "Situation de travaux"
        verbose_name_plural = "Situations de travaux"
        indexes = [models.Index(fields=["status", "affaire"])]

    def __str__(self):
        return f"{self.code} — {self.label}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = OperationsSequence.next_for("SIT", "SIT")
        return super().save(*args, **kwargs)

    def clean(self):
        if self.period_end and self.period_start and self.period_end < self.period_start:
            raise ValidationError({"period_end": "La fin de période doit être postérieure au début."})
        if self.progress > 100:
            raise ValidationError({"progress": "L'avancement ne peut dépasser 100 %."})

    @property
    def ordered_hours(self):
        return sum((float(o.pointage_hours) for o in self.ordres.all()), 0) if self.pk else 0


class CapaciteAtelier(models.Model):
    """Capacité finie hebdomadaire par périmètre (heures/semaine) — alertes de surcharge (CDC M3 §6.5)."""

    class Resource(models.TextChoices):
        RH = "rh", "Main-d'œuvre"
        MACHINE = "machine", "Machines"

    scope = models.CharField(max_length=10, choices=OrdreFabrication.Scope.choices, verbose_name="Périmètre")
    resource = models.CharField(max_length=8, choices=Resource.choices, default=Resource.RH, verbose_name="Ressource")
    hours_per_week = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Heures / semaine")

    class Meta:
        unique_together = [("scope", "resource")]
        verbose_name = "Capacité hebdomadaire"
        verbose_name_plural = "Capacités hebdomadaires"

    def __str__(self):
        return f"{self.get_scope_display()} / {self.get_resource_display()} : {self.hours_per_week} h"


class DossierOperationnel(models.Model):
    """Dossier opérationnel figé à la libération de l'OF : OF, pointages, contrôles, NC, consommations (CDC M3 §6.11).

    Immuable ; l'empreinte SHA-256 garantit l'intégrité (archivage 10 ans)."""

    ordre = models.OneToOneField(OrdreFabrication, on_delete=models.PROTECT, related_name="dossier")
    contenu = models.JSONField(default=dict)
    sha256 = models.CharField(max_length=64)
    retention_years = models.PositiveSmallIntegerField(default=10)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Dossier opérationnel"
        verbose_name_plural = "Dossiers opérationnels"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Dossier opérationnel scellé : non modifiable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Dossier opérationnel scellé : suppression interdite.")


class Equipe(models.Model):
    """Équipe de métier affectable aux OF / chantiers (CDC M3 §6.3 : affectation des équipes)."""

    class Metier(models.TextChoices):
        SOUDEUR = "soudeur", "Soudeurs"
        CHAUDRONNIER = "chaudronnier", "Chaudronniers"
        TUYAUTEUR = "tuyauteur", "Tuyauteurs"
        MONTEUR = "monteur", "Monteurs"
        PEINTRE = "peintre", "Peintres"
        GENIE_CIVIL = "genie_civil", "Génie civil"
        ELECTRICIEN = "electricien", "Électriciens"
        INSTRUMENTISTE = "instrumentiste", "Instrumentistes"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    label = models.CharField(max_length=150, verbose_name="Équipe")
    metier = models.CharField(max_length=16, choices=Metier.choices, verbose_name="Corps de métier")
    chef = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="operations_equipes_dirigees", verbose_name="Chef d'équipe",
    )
    membres = models.ManyToManyField(
        "rh_paie.Employe", blank=True, related_name="equipes_operations", verbose_name="Membres",
    )
    actif = models.BooleanField(default=True, verbose_name="Active")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["metier", "label"]
        verbose_name = "Équipe"
        verbose_name_plural = "Équipes"

    def __str__(self):
        return f"{self.code} — {self.label}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = OperationsSequence.next_for("EQP", "EQP")
        return super().save(*args, **kwargs)


class AffectationEquipe(models.Model):
    """Tableau d'affectation : une équipe sur un OF pour une période ; la mobilisation est attestée (fiche de mobilisation)."""

    class Statut(models.TextChoices):
        PLANIFIEE = "planifiee", "Planifiée"
        MOBILISEE = "mobilisee", "Mobilisée"
        TERMINEE = "terminee", "Terminée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    equipe = models.ForeignKey(Equipe, on_delete=models.PROTECT, related_name="affectations", verbose_name="Équipe")
    ordre = models.ForeignKey(
        OrdreFabrication, on_delete=models.CASCADE, related_name="affectations", verbose_name="Ordre de fabrication",
    )
    date_debut = models.DateField(verbose_name="Du")
    date_fin = models.DateField(verbose_name="Au")
    effectif = models.PositiveSmallIntegerField(default=1, verbose_name="Effectif mobilisé")
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.PLANIFIEE, verbose_name="Statut")
    mobilise_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="operations_mobilisations", verbose_name="Mobilisée par",
    )
    mobilise_le = models.DateTimeField(null=True, blank=True, verbose_name="Mobilisée le")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="operations_affectations_creees", verbose_name="Créée par",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_debut", "-created_at"]
        verbose_name = "Affectation d'équipe"
        verbose_name_plural = "Affectations d'équipes"
        indexes = [models.Index(fields=["ordre", "statut"]), models.Index(fields=["equipe", "date_debut"])]

    def __str__(self):
        return f"{self.code} — {self.equipe.label} / {self.ordre.code}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = OperationsSequence.next_for("AFE", "AFE")
        return super().save(*args, **kwargs)

    def clean(self):
        if self.date_debut and self.date_fin and self.date_fin < self.date_debut:
            raise ValidationError({"date_fin": "La fin doit être postérieure au début."})
        if self.effectif < 1:
            raise ValidationError({"effectif": "L'effectif doit être d'au moins 1."})


class PresenceChantier(models.Model):
    """Registre de présence : un salarié, un OF, un jour (une seule ligne par jour)."""

    class Statut(models.TextChoices):
        PRESENT = "present", "Présent"
        ABSENT = "absent", "Absent"
        RETARD = "retard", "En retard"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ordre = models.ForeignKey(OrdreFabrication, on_delete=models.CASCADE, related_name="presences", verbose_name="OF")
    employe = models.ForeignKey(
        "rh_paie.Employe", on_delete=models.PROTECT, related_name="presences_chantier", verbose_name="Salarié",
    )
    date = models.DateField(verbose_name="Date")
    statut = models.CharField(max_length=8, choices=Statut.choices, default=Statut.PRESENT, verbose_name="Présence")
    motif = models.CharField(max_length=200, blank=True, verbose_name="Motif (absence / retard)")
    releve_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="operations_presences_relevees", verbose_name="Relevé par",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "employe__nom"]
        unique_together = [("ordre", "employe", "date")]
        verbose_name = "Présence chantier"
        verbose_name_plural = "Registre de présence"

    def __str__(self):
        return f"{self.employe} — {self.ordre.code} — {self.date} ({self.get_statut_display()})"

    def clean(self):
        if self.statut != self.Statut.PRESENT and not self.motif:
            raise ValidationError({"motif": "Un motif est obligatoire pour une absence ou un retard."})
