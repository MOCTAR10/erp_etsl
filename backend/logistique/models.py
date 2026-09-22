"""Module M4 — Logistique ETSL & GLOBAL RENTAL (RF-ERP-30…33).

Parc logistique interne ETSL · besoins opérationnels & affectations ·
prestations GLOBAL RENTAL (documents BC / GR / BL / GR) · compteurs de
location (lecture seule pour M8/M10) · refacturation intra-groupe
(compte 618 → M10/M11). Fil rouge GR sur M2/M4/M8/M10/M11/M12
(cf. `ARCHITECTURE_ERP_ETSL.md` §2.1).
"""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction


class LogistiqueSequence(models.Model):
    """Numérotation séquentielle par type (PAR, DEM, AFF, LOC, CPT)."""

    kind = models.CharField(max_length=10, unique=True, verbose_name="Type")
    prefix = models.CharField(max_length=10, verbose_name="Préfixe")
    padding = models.PositiveSmallIntegerField(default=5, verbose_name="Zéro-padding")
    next_number = models.PositiveIntegerField(default=1, verbose_name="Prochain numéro")

    class Meta:
        verbose_name = "Séquence Logistique"
        verbose_name_plural = "Séquences Logistique"

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


class EquipementParc(models.Model):
    """Équipement du parc logistique interne ETSL (RF-ERP-30)."""

    class Categorie(models.TextChoices):
        ENGIN = "engin", "Engin de chantier"
        LEVAGE = "levage", "Matériel de levage"
        TRANSPORT = "transport", "Transport / véhicule"
        ATELIER = "atelier", "Matériel d'atelier"
        MATERIEL = "materiel", "Matériel divers"

    class Statut(models.TextChoices):
        DISPONIBLE = "disponible", "Disponible"
        AFFECTE = "affecte", "Affecté"
        EN_LOCATION = "en_location", "En location (GR)"
        HORS_SERVICE = "hors_service", "Hors service"
        MAINTENANCE = "maintenance", "En maintenance"

    class Compteur(models.TextChoices):
        HEURES = "heures", "Heures moteur"
        KM = "km", "Kilomètres"
        FORFAIT = "forfait", "Forfait (sans compteur)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    label = models.CharField(max_length=200, verbose_name="Désignation")
    registration = models.CharField(
        max_length=40, blank=True, verbose_name="Immatriculation / n° série"
    )
    categorie = models.CharField(
        max_length=12, choices=Categorie.choices, default=Categorie.ENGIN, verbose_name="Catégorie"
    )
    statut = models.CharField(
        max_length=14, choices=Statut.choices, default=Statut.DISPONIBLE, verbose_name="Statut"
    )
    compteur_type = models.CharField(
        max_length=7, choices=Compteur.choices, default=Compteur.HEURES, verbose_name="Type de compteur"
    )
    compteur_value = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Valeur compteur"
    )
    site = models.CharField(max_length=120, blank=True, verbose_name="Site / dépôt")
    is_global_rental = models.BooleanField(default=False, verbose_name="GLOBAL RENTAL")
    proprietaire = models.ForeignKey(
        "referentiels.Partner",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="equipements_parc",
        verbose_name="Propriétaire",
    )
    signe_618 = models.BooleanField(
        default=False,
        verbose_name="Refacturation compte 618",
        help_text="Coût/Gain GR isolé au compte 618 (SYSCOHADA).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "Équipement du parc"
        verbose_name_plural = "Équipements du parc"
        indexes = [models.Index(fields=["statut", "categorie"])]

    def __str__(self):
        return f"{self.code} — {self.label}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = LogistiqueSequence.next_for("PAR", "PAR")
        return super().save(*args, **kwargs)

    @property
    def disponible(self):
        return self.statut in (
            self.Statut.DISPONIBLE, self.Statut.AFFECTE, self.Statut.MAINTENANCE,
        )


class DemandeMobilisation(models.Model):
    """Besoin opérationnel — mobilisation d'équipement (RF-ERP-31)."""

    class Statut(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        SOUMISE = "soumise", "Soumise"
        TRAITEE = "traitee", "Traitée"
        ANNULEE = "annulee", "Annulée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    label = models.CharField(max_length=200, verbose_name="Objet du besoin")
    affaire = models.ForeignKey(
        "commercial.Affaire",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="demandes_logistique",
        verbose_name="Affaire",
    )
    ordre = models.ForeignKey(
        "operations.OrdreFabrication",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="demandes_logistique",
        verbose_name="Ordre de fabrication",
    )
    departement = models.CharField(max_length=120, blank=True, verbose_name="Département demandeur")
    date_debut = models.DateField(null=True, blank=True, verbose_name="Début souhaité")
    date_fin = models.DateField(null=True, blank=True, verbose_name="Fin souhaitée")
    notes = models.TextField(blank=True, verbose_name="Notes / spécifications")
    statut = models.CharField(
        max_length=12, choices=Statut.choices, default=Statut.BROUILLON, verbose_name="Statut"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="logistique_created_demandes",
        verbose_name="Créé par",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Demande de mobilisation"
        verbose_name_plural = "Demandes de mobilisation"
        indexes = [models.Index(fields=["statut", "date_debut"])]

    def __str__(self):
        return f"{self.code} — {self.label}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = LogistiqueSequence.next_for("DEM", "DEM")
        return super().save(*args, **kwargs)

    def clean(self):
        if self.date_debut and self.date_fin and self.date_fin < self.date_debut:
            raise ValidationError({"date_fin": "La fin souhaitée doit être postérieure au début."})


class AffectationParc(models.Model):
    """Affectation d'un équipement à une affaire / un chantier (RF-ERP-31)."""

    class Statut(models.TextChoices):
        ACTIVE = "active", "Active"
        TERMINEE = "terminee", "Terminée"
        ANNULEE = "annulee", "Annulée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    equipement = models.ForeignKey(
        EquipementParc,
        on_delete=models.CASCADE,
        related_name="affectations",
        verbose_name="Équipement",
    )
    demande = models.ForeignKey(
        DemandeMobilisation,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="affectations",
        verbose_name="Demande liée",
    )
    affaire = models.ForeignKey(
        "commercial.Affaire",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="affectations_logistique",
        verbose_name="Affaire",
    )
    ordre = models.ForeignKey(
        "operations.OrdreFabrication",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="affectations_logistique",
        verbose_name="Ordre de fabrication",
    )
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="logistique_affectations",
        verbose_name="Responsable",
    )
    date_debut = models.DateField(verbose_name="Début")
    date_fin = models.DateField(null=True, blank=True, verbose_name="Fin")
    statut = models.CharField(
        max_length=12, choices=Statut.choices, default=Statut.ACTIVE, verbose_name="Statut"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="logistique_created_affectations",
        verbose_name="Créé par",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Affectation de parc"
        verbose_name_plural = "Affectations de parc"
        indexes = [models.Index(fields=["statut", "equipement"])]

    def __str__(self):
        return f"{self.code} — {self.equipement.label}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = LogistiqueSequence.next_for("AFF", "AFF")
        return super().save(*args, **kwargs)

    def clean(self):
        eq = self.equipement
        if eq.statut in (EquipementParc.Statut.EN_LOCATION, EquipementParc.Statut.HORS_SERVICE):
            raise ValidationError(
                {"equipement": "Équipement en location (GR) ou hors service : non affectable."}
            )
        if self.date_fin and self.date_debut and self.date_fin < self.date_debut:
            raise ValidationError({"date_fin": "La fin doit être postérieure au début."})


class LocationGR(models.Model):
    """Prestation GLOBAL RENTAL — documents BC / GR / BL / GR (RF-ERP-32).

    Location d'équipement intra-groupe : bon de commande (BC) → gréement GR
    → bon de livraison (BL) → retour GR, compteurs de location, refacturation
    au compte 618 (RF-ERP-33).
    """

    class Statut(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        ACTIVE = "active", "Active"
        TERMINEE = "terminee", "Terminée"
        ANNULEE = "annulee", "Annulée"

    class Periodicite(models.TextChoices):
        HEURE = "heure", "À l'heure"
        JOUR = "jour", "À la journée"
        MOIS = "mois", "Au mois"
        FORFAIT = "forfait", "Forfait"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    partenaire = models.ForeignKey(
        "referentiels.Partner",
        on_delete=models.PROTECT,
        related_name="locations_gr",
        verbose_name="Partenaire GR",
    )
    equipement = models.ForeignKey(
        EquipementParc,
        on_delete=models.CASCADE,
        related_name="locations",
        verbose_name="Équipement",
    )
    affaire = models.ForeignKey(
        "commercial.Affaire",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="locations_gr",
        verbose_name="Affaire",
    )
    reference_bc = models.CharField(max_length=40, blank=True, verbose_name="BC (bon de commande)")
    reference_gr = models.CharField(max_length=40, blank=True, verbose_name="GR (gréement)")
    reference_bl = models.CharField(max_length=40, blank=True, verbose_name="BL (livraison)")
    reference_retour = models.CharField(max_length=40, blank=True, verbose_name="Retour GR")
    date_debut = models.DateField(null=True, blank=True, verbose_name="Début location")
    date_fin = models.DateField(null=True, blank=True, verbose_name="Fin location")
    periodicite = models.CharField(
        max_length=7, choices=Periodicite.choices, default=Periodicite.MOIS, verbose_name="Périodicité"
    )
    tarif = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Tarif unitaire"
    )
    devise = models.ForeignKey(
        "referentiels.Currency",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="locations_gr",
        verbose_name="Devise",
    )
    montant_estime = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Montant estimé"
    )
    lecture_initiale = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True, verbose_name="Compteur départ"
    )
    lecture_finale = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True, verbose_name="Compteur retour"
    )
    imputation_618 = models.BooleanField(
        default=True, verbose_name="Refacturation compte 618"
    )
    statut = models.CharField(
        max_length=12, choices=Statut.choices, default=Statut.BROUILLON, verbose_name="Statut"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="logistique_created_locations",
        verbose_name="Créé par",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Prestation GLOBAL RENTAL"
        verbose_name_plural = "Prestations GLOBAL RENTAL"
        indexes = [models.Index(fields=["statut", "partenaire"])]

    def __str__(self):
        return f"{self.code} — {self.equipement.label}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = LogistiqueSequence.next_for("LOC", "LOC")
        return super().save(*args, **kwargs)

    def clean(self):
        if not self.partenaire.is_global_rental:
            raise ValidationError(
                {"partenaire": "Le partenaire doit être marqué GLOBAL RENTAL (intra-groupe)."}
            )
        if self.date_debut and self.date_fin and self.date_fin < self.date_debut:
            raise ValidationError({"date_fin": "La fin doit être postérieure au début."})
        if self.tarif < 0:
            raise ValidationError({"tarif": "Le tarif ne peut être négatif."})
        if self.lecture_initiale is not None and self.lecture_finale is not None:
            if self.lecture_finale < self.lecture_initiale:
                raise ValidationError(
                    {"lecture_finale": "Le compteur de retour doit être ≥ au compteur de départ."}
                )

    @property
    def consommation(self):
        if (
            self.lecture_initiale is not None
            and self.lecture_finale is not None
        ):
            return self.lecture_finale - self.lecture_initiale
        return None

    @property
    def libelle_montant(self):
        return f"{self.montant_estime} {self.devise.code if self.devise else ''}".strip()


class LectureCompteur(models.Model):
    """Relevé de compteur de location (heure / km) — RF-ERP-33.

    Lecture seule pour M8 / M10 ; la location en cours fait foi du dernier
    relevé (source d'une refacturation intra-groupe au compte 618).
    """

    class TypeLecture(models.TextChoices):
        INITIALE = "initiale", "Initiale"
        PERIODIQUE = "periodique", "Périodique"
        FINALE = "finale", "Finale"

    class Source(models.TextChoices):
        SAISIE = "saisie", "Saisie ETSL"
        GR = "gr", "Reçu GLOBAL RENTAL"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    location = models.ForeignKey(
        LocationGR,
        on_delete=models.CASCADE,
        related_name="lectures",
        verbose_name="Prestation GR",
    )
    date = models.DateField(verbose_name="Date du relevé")
    valeur = models.DecimalField(
        max_digits=14, decimal_places=2, verbose_name="Valeur compteur"
    )
    type_lecture = models.CharField(
        max_length=10, choices=TypeLecture.choices, default=TypeLecture.PERIODIQUE,
        verbose_name="Type",
    )
    source = models.CharField(
        max_length=6, choices=Source.choices, default=Source.SAISIE, verbose_name="Source"
    )
    releve_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="logistique_lectures",
        verbose_name="Relevé par",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "Lecture de compteur"
        verbose_name_plural = "Lectures de compteur"
        indexes = [models.Index(fields=["location", "date"])]

    def __str__(self):
        return f"{self.code} — {self.location.code} — {self.valeur}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = LogistiqueSequence.next_for("CPT", "CPT")
        return super().save(*args, **kwargs)

    def clean(self):
        if self.valeur < 0:
            raise ValidationError({"valeur": "La valeur du compteur ne peut être négative."})