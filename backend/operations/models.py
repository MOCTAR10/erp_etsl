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
    machine_hours = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Heures machine",
        help_text="Temps machine unitaire (capacité machine du plan de charge).",
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
    replanifie_le = models.DateTimeField(null=True, blank=True, verbose_name="Replanifié le")
    motif_replanification = models.CharField(max_length=255, blank=True, verbose_name="Motif de la dernière replanification")
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

    class NatureMo(models.TextChoices):
        DIRECTE = "directe", "Main-d'œuvre directe"
        INDIRECTE = "indirecte", "Main-d'œuvre indirecte"

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
    employe = models.ForeignKey(
        "rh_paie.Employe", null=True, blank=True, on_delete=models.PROTECT, related_name="pointages_chantier",
        verbose_name="Salarié (fiche RH)", help_text="Rattachement opérateur ↔ fiche RH : rend le pointage transférable en paie.",
    )
    nature_mo = models.CharField(
        max_length=10, choices=NatureMo.choices, default=NatureMo.DIRECTE, verbose_name="Nature de la main-d'œuvre"
    )
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
    saisi_le = models.DateTimeField(
        null=True, blank=True, verbose_name="Saisi sur l'appareil le",
        help_text="Horodatage de la saisie terrain (hors ligne) ; vide pour une saisie au bureau.",
    )
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
        if not self.worker_name and not self.worker and not self.employe_id:
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
    recue_le = models.DateTimeField(null=True, blank=True, verbose_name="Reçu client le")
    recue_signataire = models.CharField(max_length=150, blank=True, verbose_name="Signataire du reçu client")
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


# ----------------------------------------------------------------------------------------------------------------
# Écarts M3 (lot 2) : paramètres provisoires, préparation atelier, besoins matière, rapports, transferts,
# attachements / métrés, fiches de contrôle chantier, escalades de surcharge.
# ----------------------------------------------------------------------------------------------------------------
class ParametreOperations(models.Model):
    """Paramètres M3 modifiables par ETSL : valeurs provisoires tant qu'ETSL ne les confirme pas."""

    class StatutValeur(models.TextChoices):
        PROVISOIRE = "provisoire", "Provisoire"
        CONFIRME = "confirme", "Confirmé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=40, unique=True, verbose_name="Identifiant")
    label = models.CharField(max_length=255, verbose_name="Libellé")
    valeur = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Valeur")
    unite = models.CharField(max_length=30, blank=True, verbose_name="Unité")
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
        verbose_name = "Paramètre opérations"
        verbose_name_plural = "Paramètres opérations"

    def __str__(self):
        return f"{self.code} = {self.valeur} {self.unite}"

    @property
    def est_provisoire(self):
        return self.statut_valeur == self.StatutValeur.PROVISOIRE


class FichePreparation(models.Model):
    """Fiche de préparation atelier d'un OF (CDC M3-03) : outillage réservé, consignes, besoins matière."""

    class Statut(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        VALIDEE = "validee", "Validée (prête)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    ordre = models.OneToOneField(OrdreFabrication, on_delete=models.CASCADE, related_name="fiche_preparation", verbose_name="OF")
    outillage = models.TextField(blank=True, verbose_name="Outillage / équipements réservés")
    consignes = models.TextField(blank=True, verbose_name="Consignes de préparation")
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.BROUILLON, verbose_name="Statut")
    valide_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="Validée par",
    )
    valide_le = models.DateTimeField(null=True, blank=True, verbose_name="Validée le")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="Créée par",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Fiche de préparation"
        verbose_name_plural = "Fiches de préparation"

    def __str__(self):
        return f"{self.code} — {self.ordre.code}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = OperationsSequence.next_for("FPR", "FPR")
        return super().save(*args, **kwargs)


class BesoinMatiere(models.Model):
    """Besoin matière d'un OF : réservation logique sur le stock disponible, rupture ⇒ alerte + DA (M2)."""

    class Statut(models.TextChoices):
        A_VERIFIER = "a_verifier", "À vérifier"
        RESERVE = "reserve", "Réservé"
        RUPTURE = "rupture", "Rupture"
        SERVI = "servi", "Servi (sorti du stock)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ordre = models.ForeignKey(OrdreFabrication, on_delete=models.CASCADE, related_name="besoins_matiere", verbose_name="OF")
    article = models.ForeignKey("referentiels.Article", on_delete=models.PROTECT, related_name="+", verbose_name="Article")
    quantite = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Quantité nécessaire")
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.A_VERIFIER, verbose_name="Statut")
    disponible = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True, verbose_name="Disponible au dernier contrôle"
    )
    verifie_le = models.DateTimeField(null=True, blank=True, verbose_name="Contrôlé le")
    demande_achat = models.ForeignKey(
        "achats.PurchaseRequest", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="DA de réapprovisionnement",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["ordre", "created_at"]
        verbose_name = "Besoin matière"
        verbose_name_plural = "Besoins matière"
        indexes = [models.Index(fields=["article", "statut"])]

    def __str__(self):
        return f"{self.ordre.code} — {self.article} × {self.quantite}"


class RapportExecution(models.Model):
    """Rapport d'exécution atelier (M3-04) ou rapport d'avancement chantier (M3-06) : quantités réalisées, rebut, %."""

    class Type(models.TextChoices):
        EXECUTION = "execution", "Rapport d'exécution atelier"
        AVANCEMENT = "avancement", "Rapport d'avancement chantier"

    class Statut(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        VALIDE = "valide", "Validé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    ordre = models.ForeignKey(OrdreFabrication, on_delete=models.CASCADE, related_name="rapports", verbose_name="OF")
    type = models.CharField(max_length=10, choices=Type.choices, default=Type.EXECUTION, verbose_name="Type")
    date = models.DateField(verbose_name="Date")
    quantite_realisee = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Quantité réalisée")
    quantite_rebut = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Quantité rebutée")
    avancement = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Avancement déclaré (%)")
    observations = models.TextField(blank=True, verbose_name="Observations / aléas")
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.BROUILLON, verbose_name="Statut")
    valide_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="Validé par",
    )
    valide_le = models.DateTimeField(null=True, blank=True, verbose_name="Validé le")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="Établi par",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "Rapport d'exécution / d'avancement"
        verbose_name_plural = "Rapports d'exécution / d'avancement"
        indexes = [models.Index(fields=["ordre", "statut"])]

    def __str__(self):
        return f"{self.code} — {self.ordre.code}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = OperationsSequence.next_for("REX", "REX")
        return super().save(*args, **kwargs)


class FicheControleChantier(models.Model):
    """Fiche d'autocontrôle chantier (M3-06) : points vérifiés, résultat calculé, visa du contrôleur."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    ordre = models.ForeignKey(OrdreFabrication, on_delete=models.CASCADE, related_name="fiches_controle", verbose_name="OF")
    date = models.DateField(verbose_name="Date")
    objet = models.CharField(max_length=200, verbose_name="Objet du contrôle")
    points = models.JSONField(default=list, verbose_name="Points contrôlés [{libelle, conforme}]")
    conforme = models.BooleanField(default=True, verbose_name="Conforme")
    controle_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="Contrôlé par",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "Fiche de contrôle chantier"
        verbose_name_plural = "Fiches de contrôle chantier"

    def __str__(self):
        return f"{self.code} — {self.objet}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = OperationsSequence.next_for("FCC", "FCC")
        self.conforme = all(bool(p.get("conforme")) for p in (self.points or []))
        return super().save(*args, **kwargs)


class BonTransfert(models.Model):
    """Bon de livraison / fiche de transfert atelier → chantier (M3-05) : préparé, expédié, réceptionné."""

    class Type(models.TextChoices):
        BL = "bl", "Bon de livraison"
        TRANSFERT = "transfert", "Fiche de transfert"

    class Statut(models.TextChoices):
        PREPARE = "prepare", "Préparé"
        EXPEDIE = "expedie", "Expédié"
        RECEPTIONNE = "receptionne", "Réceptionné sur chantier"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    type = models.CharField(max_length=10, choices=Type.choices, default=Type.BL, verbose_name="Type")
    ordre = models.ForeignKey(OrdreFabrication, on_delete=models.PROTECT, related_name="transferts", verbose_name="OF")
    origine = models.CharField(max_length=120, default="Atelier ETSL", verbose_name="Origine")
    destination = models.CharField(max_length=120, verbose_name="Destination (chantier / site)")
    transporteur = models.CharField(max_length=120, blank=True, verbose_name="Transporteur / véhicule")
    lignes = models.JSONField(default=list, verbose_name="Lignes [{designation, quantite}]")
    statut = models.CharField(max_length=12, choices=Statut.choices, default=Statut.PREPARE, verbose_name="Statut")
    expedie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="Expédié par",
    )
    expedie_le = models.DateTimeField(null=True, blank=True, verbose_name="Expédié le")
    receptionne_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="Réceptionné par",
    )
    receptionne_le = models.DateTimeField(null=True, blank=True, verbose_name="Réceptionné le")
    reserves = models.CharField(max_length=255, blank=True, verbose_name="Réserves à la réception")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="Établi par",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Bon de livraison / transfert"
        verbose_name_plural = "Bons de livraison / transferts"

    def __str__(self):
        return f"{self.code} — {self.ordre.code} → {self.destination}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = OperationsSequence.next_for(
                "BL" if self.type == self.Type.BL else "FTR", "BL" if self.type == self.Type.BL else "FTR"
            )
        return super().save(*args, **kwargs)


class Attachement(models.Model):
    """Attachement / métré contradictoire (quantité réalisée constatée avec le client) : base de la situation."""

    class Statut(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        SIGNE = "signe", "Signé contradictoirement"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    ordre = models.ForeignKey(OrdreFabrication, on_delete=models.PROTECT, related_name="attachements", verbose_name="OF")
    situation = models.ForeignKey(
        SituationTravaux, null=True, blank=True, on_delete=models.SET_NULL, related_name="attachements",
        verbose_name="Situation de travaux",
    )
    date = models.DateField(verbose_name="Date du constat")
    designation = models.CharField(max_length=200, verbose_name="Ouvrage / poste")
    unite = models.CharField(max_length=20, default="u", verbose_name="Unité (ml, m², kg, u…)")
    quantite = models.DecimalField(max_digits=14, decimal_places=3, verbose_name="Quantité métrée")
    prix_unitaire = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Prix unitaire")
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.BROUILLON, verbose_name="Statut")
    signataire_client = models.CharField(max_length=150, blank=True, verbose_name="Signataire client")
    signe_le = models.DateTimeField(null=True, blank=True, verbose_name="Signé le")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="Établi par",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "Attachement / métré"
        verbose_name_plural = "Attachements / métrés"

    def __str__(self):
        return f"{self.code} — {self.designation}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = OperationsSequence.next_for("ATT", "ATT")
        return super().save(*args, **kwargs)

    @property
    def montant(self):
        return (self.quantite * self.prix_unitaire).quantize(Decimal("0.01"))


class RepartitionAffaireOF(models.Model):
    """Cas multi-affaires (interprétation provisoire) : un OF commun réparti entre plusieurs affaires (clé en %)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ordre = models.ForeignKey(OrdreFabrication, on_delete=models.CASCADE, related_name="repartitions", verbose_name="OF")
    affaire = models.ForeignKey("commercial.Affaire", on_delete=models.PROTECT, related_name="+", verbose_name="Affaire")
    part_pct = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="Part (%)")

    class Meta:
        unique_together = [("ordre", "affaire")]
        verbose_name = "Répartition multi-affaires"
        verbose_name_plural = "Répartitions multi-affaires"

    def __str__(self):
        return f"{self.ordre.code} → {self.affaire} ({self.part_pct} %)"


class EscaladeSurcharge(models.Model):
    """Escalade d'une surcharge de capacité vers la direction (sous-traitance / location GLOBAL RENTAL) — une par semaine."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scope = models.CharField(max_length=10, choices=OrdreFabrication.Scope.choices, verbose_name="Périmètre")
    resource = models.CharField(max_length=8, choices=CapaciteAtelier.Resource.choices, verbose_name="Ressource")
    semaine = models.DateField(verbose_name="Semaine du")
    surcharge_pct = models.DecimalField(max_digits=8, decimal_places=1, verbose_name="Surcharge (%)")
    escalade_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="Escaladée par",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-semaine"]
        unique_together = [("scope", "resource", "semaine")]
        verbose_name = "Escalade de surcharge"
        verbose_name_plural = "Escalades de surcharge"
