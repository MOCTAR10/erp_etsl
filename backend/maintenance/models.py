"""Module M8 — Maintenance & GMAO : parc machines & équipements (RF-ERP-70…73).

Procédure MANUEL 5.9 (maintenance et inspection des équipements) : parc machines,
outils, engins, postes de soudage, appareils de levage, équipements d'atelier et
de chantier. RF-ERP-70 : parc interne ETSL · RF-ERP-71 : ordres de travail correctif /
préventif · RF-ERP-72 : inspections périodiques + compteurs GLOBAL RENTAL en
**lecture seule** (via logistique) · RF-ERP-73 : historique & cost tracking.
"""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone


class MaintenanceSequence(models.Model):
    """Numérotation séquentielle par type (EQ, OT, INS)."""

    kind = models.CharField(max_length=10, unique=True, verbose_name="Type")
    prefix = models.CharField(max_length=10, verbose_name="Préfixe")
    padding = models.PositiveSmallIntegerField(default=5, verbose_name="Zéro-padding")
    next_number = models.PositiveIntegerField(default=1, verbose_name="Prochain numéro")

    class Meta:
        verbose_name = "Séquence Maintenance"
        verbose_name_plural = "Séquences Maintenance"

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


class Actif(models.Model):
    """Parcc machines & équipements ETSL — machines, engins, levage, atelier (RF-ERP-70)."""

    class Categorie(models.TextChoices):
        MACHINE = "machine", "Machine / poste de soudage"
        ENGIN = "engin", "Engin / engin de chantier"
        LEVAGE = "levage", "Appareil de levage"
        ATELIER = "atelier", "Équipement d'atelier"
        CHANTIER = "chantier", "Équipement de chantier"
        OUTILLAGE = "outillage", "Outillage"

    class Statut(models.TextChoices):
        OPERATIONNEL = "operationnel", "Opérationnel"
        EN_MAINTENANCE = "en_maintenance", "En maintenance"
        EN_PANNE = "en_panne", "En panne"
        HORS_SERVICE = "hors_service", "Hors service"
        REFORME = "reforme", "Réformé"

    class Compteur(models.TextChoices):
        HEURES = "heures", "Heures moteur"
        KM = "km", "Kilomètres"
        AUCUN = "aucun", "Sans compteur"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    designation = models.CharField(max_length=200, verbose_name="Désignation")
    categorie = models.CharField(
        max_length=10, choices=Categorie.choices, default=Categorie.MACHINE,
        verbose_name="Catégorie",
    )
    fabricant = models.CharField(max_length=120, blank=True, verbose_name="Fabricant")
    modele = models.CharField(max_length=120, blank=True, verbose_name="Modèle")
    numero_serie = models.CharField(
        max_length=100, blank=True, verbose_name="N° de série"
    )
    site = models.CharField(max_length=120, blank=True, verbose_name="Site / dépôt")
    statut = models.CharField(
        max_length=14, choices=Statut.choices, default=Statut.OPERATIONNEL,
        verbose_name="Statut",
    )
    date_mise_en_service = models.DateField(
        null=True, blank=True, verbose_name="Mise en service"
    )
    garanti_jusqu = models.DateField(null=True, blank=True, verbose_name="Garantie jusqu'au")
    compteur_type = models.CharField(
        max_length=7, choices=Compteur.choices, default=Compteur.HEURES,
        verbose_name="Type de compteur",
    )
    compteur_value = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Valeur compteur"
    )
    is_global_rental = models.BooleanField(
        default=False, verbose_name="Équipement GLOBAL RENTAL (GR)"
    )
    equipement_gr = models.ForeignKey(
        "logistique.EquipementParc",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="maintenance_actifs",
        verbose_name="Équipement GLOBAL RENTAL lié",
        help_text="Compteur lu en lecture seule depuis la logistique (RF-ERP-72).",
    )
    signe_618 = models.BooleanField(
        default=False,
        verbose_name="Refacturation compte 618",
        help_text="Coût/Gain GR isolé au compte 618 (SYSCOHADA).",
    )
    notes = models.TextField(blank=True, verbose_name="Notes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "Actif (machine / équipement)"
        verbose_name_plural = "Actifs — parc machines & équipements"
        indexes = [models.Index(fields=["statut", "categorie"])]

    def __str__(self):
        return f"{self.code} — {self.designation} ({self.get_statut_display()})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = MaintenanceSequence.next_for("EQ", "EQ")
        return super().save(*args, **kwargs)

    def clean(self):
        if self.is_global_rental and not self.equipement_gr:
            raise ValidationError(
                {"equipement_gr": "Un actif GLOBAL RENTAL doit référencer l'équipement lié."}
            )
        if self.equipement_gr and not self.is_global_rental:
            self.is_global_rental = True

    @property
    def compteur_lecture(self):
        """Compteur lu : lecture seule depuis la logistique pour un équipement GR."""
        if self.is_global_rental and self.equipement_gr:
            return self.equipement_gr.compteur_value
        return self.compteur_value

    @property
    def en_arret(self):
        return self.statut in (
            self.Statut.EN_MAINTENANCE,
            self.Statut.EN_PANNE,
        )


class OrdreTravail(models.Model):
    """Ordre de travail de maintenance — correctif / préventif / inspection (RF-ERP-71)."""

    class TypeOT(models.TextChoices):
        CORRECTIF = "correctif", "Correctif"
        PREVENTIF = "preventif", "Préventif"
        URGENCE = "urgence", "Urgence / dépannage"
        INSPECTION = "inspection", "Inspection"

    class Priorite(models.TextChoices):
        BASSE = "basse", "Basse"
        MOYENNE = "moyenne", "Moyenne"
        HAUTE = "haute", "Haute"
        CRITIQUE = "critique", "Critique"

    class Statut(models.TextChoices):
        DEMANDE = "demande", "Demandé"
        PLANIFIE = "planifie", "Planifié"
        EN_COURS = "en_cours", "En cours"
        TERMINE = "termine", "Terminé"
        CLOTURE = "cloture", "Clôturé"
        ANNULE = "annule", "Annulé"

    class Decision(models.TextChoices):
        REPARATION = "reparation", "Réparation lourde"
        MISE_HORS_SERVICE = "mise_hors_service", "Mise hors service"
        REFORME = "reforme", "Réforme"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    actif = models.ForeignKey(
        Actif,
        on_delete=models.PROTECT,
        related_name="ordres_travail",
        verbose_name="Équipement",
    )
    type_ot = models.CharField(
        max_length=11, choices=TypeOT.choices, default=TypeOT.CORRECTIF,
        verbose_name="Type",
    )
    priorite = models.CharField(
        max_length=10, choices=Priorite.choices, default=Priorite.MOYENNE,
        verbose_name="Priorité",
    )
    description = models.TextField(verbose_name="Description de l'intervention")
    cause = models.TextField(blank=True, verbose_name="Cause / diagnostic")
    demandeur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="maintenance_ot_demandes",
        verbose_name="Demandeur",
    )
    technicien = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="maintenance_ot_interventions",
        verbose_name="Technicien",
    )
    date_demande = models.DateField(default=timezone.localdate, verbose_name="Date de demande")
    date_planifiee = models.DateField(null=True, blank=True, verbose_name="Date planifiée")
    date_debut = models.DateTimeField(null=True, blank=True, verbose_name="Début d'intervention")
    date_fin = models.DateTimeField(null=True, blank=True, verbose_name="Fin d'intervention")
    heures_mo = models.DecimalField(
        max_digits=8, decimal_places=2, default=0, verbose_name="Heures main-d'œuvre"
    )
    tarif_horaire = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, verbose_name="Tarif horaire (FCFA)"
    )
    cout_pieces = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Coût pièces (FCFA)"
    )
    decision = models.CharField(
        max_length=18, choices=Decision.choices, blank=True, verbose_name="Décision"
    )
    rapport = models.TextField(blank=True, verbose_name="Rapport d'intervention")
    statut = models.CharField(
        max_length=10, choices=Statut.choices, default=Statut.DEMANDE,
        verbose_name="Statut",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="maintenance_ot_crees",
        verbose_name="Créé par",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_demande", "-created_at"]
        verbose_name = "Ordre de travail (OT)"
        verbose_name_plural = "Ordres de travail — GMAO"
        indexes = [models.Index(fields=["type_ot", "statut"])]

    def __str__(self):
        return f"{self.code} — {self.actif.code} ({self.get_statut_display()})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = MaintenanceSequence.next_for("OT", "OT")
        return super().save(*args, **kwargs)

    @property
    def cout_main_oeuvre(self):
        return self.heures_mo * self.tarif_horaire

    @property
    def cout_total(self):
        return self.cout_main_oeuvre + self.cout_pieces


class Inspection(models.Model):
    """Inspection périodique des équipements — 5.9.5 (RF-ERP-72)."""

    class TypeInspection(models.TextChoices):
        VISUELLE = "visuelle", "Visuelle"
        FONCTIONNELLE = "fonctionnelle", "Fonctionnelle"
        SECURITE = "securite", "Sécurité"
        LEVAGE = "levage", "Appareil de levage"
        ATEX = "atex", "ATEX"
        METROLOGIE = "metrologie", "Métrologie / étalonnage"

    class Resultat(models.TextChoices):
        CONFORME = "conforme", "Conforme"
        SOUS_RESERVE = "sous_reserve", "Sous réserve"
        NON_CONFORME = "non_conforme", "Non conforme"

    class Statut(models.TextChoices):
        PLANIFIEE = "planifiee", "Planifiée"
        REALISEE = "realisee", "Réalisée"
        ANNULEE = "annulee", "Annulée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    actif = models.ForeignKey(
        Actif,
        on_delete=models.PROTECT,
        related_name="inspections",
        verbose_name="Équipement",
    )
    type_inspection = models.CharField(
        max_length=14, choices=TypeInspection.choices, default=TypeInspection.VISUELLE,
        verbose_name="Type",
    )
    date_inspection = models.DateField(verbose_name="Date d'inspection")
    prochaine_inspection = models.DateField(null=True, blank=True, verbose_name="Prochaine inspection")
    organisme = models.CharField(max_length=60, default="interne", verbose_name="Organisme")
    organisme_libelle = models.CharField(max_length=120, blank=True, verbose_name="Organisme (libellé)")
    resultat = models.CharField(
        max_length=14, choices=Resultat.choices, blank=True, verbose_name="Résultat"
    )
    constat = models.TextField(blank=True, verbose_name="Constat / observations")
    intervenant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="maintenance_inspections",
        verbose_name="Inspécteur",
    )
    statut = models.CharField(
        max_length=12, choices=Statut.choices, default=Statut.PLANIFIEE,
        verbose_name="Statut",
    )
    ot_genere = models.ForeignKey(
        OrdreTravail,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="inspections_source",
        verbose_name="OT généré",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_inspection"]
        verbose_name = "Inspection périodique"
        verbose_name_plural = "Inspections périodiques"
        indexes = [models.Index(fields=["type_inspection", "statut"])]

    def __str__(self):
        return f"{self.code} — {self.actif.code} ({self.get_statut_display()})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = MaintenanceSequence.next_for("INS", "INS")
        return super().save(*args, **kwargs)

    def clean(self):
        if self.prochaine_inspection and self.prochaine_inspection < self.date_inspection:
            raise ValidationError(
                {"prochaine_inspection": "La prochaine inspection doit être postérieure à l'inspection."}
            )