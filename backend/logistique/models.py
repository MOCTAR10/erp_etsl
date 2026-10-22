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
    # EX-G-03 : site ETSL de rattachement (référentiel paramétrable ; reconnu automatiquement depuis le texte libre).
    site_etsl = models.ForeignKey(
        "referentiels.Site", null=True, blank=True, on_delete=models.PROTECT, related_name="equipements_parc", verbose_name="Site ETSL"
    )
    plafond_compteur = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True, verbose_name="Plafond du compteur",
        help_text="Kilométrage / heures maximal avant révision ou réforme (sens provisoire, à confirmer par ETSL).",
    )
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
    tarif_gr = models.ForeignKey(
        "TarifGR",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="locations",
        verbose_name="Version de grille tarifaire GR",
    )
    valide_m2_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Validation Achats (M2) par",
    )
    valide_m2_le = models.DateTimeField(null=True, blank=True, verbose_name="Validation Achats (M2) le")
    valide_dr_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Validation Direction (DR) par",
    )
    valide_dr_le = models.DateTimeField(null=True, blank=True, verbose_name="Validation Direction (DR) le")
    bon_commande_achat = models.ForeignKey(
        "achats.PurchaseOrder", null=True, blank=True, on_delete=models.PROTECT, related_name="locations_gr",
        verbose_name="BC achats GLOBAL RENTAL (M2)",
    )
    facture_achat = models.ForeignKey(
        "achats.PurchaseInvoice", null=True, blank=True, on_delete=models.PROTECT, related_name="locations_gr",
        verbose_name="Facture GLOBAL RENTAL rapprochée",
    )
    facture_ecart = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True, verbose_name="Écart facture / montant attendu",
    )
    facture_conforme = models.BooleanField(null=True, blank=True, verbose_name="Facture dans la tolérance")
    emis_le = models.DateTimeField(null=True, blank=True, verbose_name="BC / GR émis le")
    emis_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="logistique_emissions_gr",
        verbose_name="BC / GR émis par",
    )
    date_retour = models.DateField(null=True, blank=True, verbose_name="Retour effectif")
    jours_retard = models.PositiveIntegerField(default=0, verbose_name="Jours de retard")
    penalite = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Pénalité de retard"
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


class TarifGR(models.Model):
    """Grille tarifaire GLOBAL RENTAL versionnée (lot 14, CDC M4 §12.4 / §12.11).

    Un changement de tarif crée une nouvelle version datée (date d'effet) — jamais de réécriture. La
    prestation retient la version en vigueur à sa date de début, la plus spécifique d'abord : équipement,
    puis catégorie, puis grille générale du partenaire. `penalite_jour` : pénalité par jour de retour tardif.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    partenaire = models.ForeignKey(
        "referentiels.Partner",
        on_delete=models.PROTECT,
        related_name="tarifs_gr",
        verbose_name="Partenaire GR",
    )
    equipement = models.ForeignKey(
        EquipementParc,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="tarifs_gr",
        verbose_name="Équipement (tarif spécifique)",
    )
    categorie = models.CharField(
        max_length=10, choices=EquipementParc.Categorie.choices, blank=True,
        verbose_name="Catégorie (vide = grille générale)",
    )
    periodicite = models.CharField(
        max_length=7, choices=LocationGR.Periodicite.choices, default=LocationGR.Periodicite.JOUR,
        verbose_name="Périodicité",
    )
    tarif = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Tarif unitaire")
    penalite_jour = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Pénalité par jour de retard"
    )
    date_effet = models.DateField(verbose_name="Date d'effet")
    version = models.PositiveIntegerField(default=1, editable=False, verbose_name="Version")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="logistique_tarifs_gr",
        verbose_name="Créé par",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["partenaire", "categorie", "-date_effet", "-version"]
        verbose_name = "Tarif GLOBAL RENTAL (version)"
        verbose_name_plural = "Grille tarifaire GLOBAL RENTAL"
        constraints = [
            models.UniqueConstraint(
                fields=["partenaire", "equipement", "categorie", "periodicite", "date_effet"],
                nulls_distinct=False,
                name="uniq_tarif_gr_date_effet",
            )
        ]

    def __str__(self):
        cible = self.equipement.code if self.equipement_id else (self.get_categorie_display() or "général")
        return f"{self.code} — {self.partenaire.code} {cible} v{self.version}"

    def clean(self):
        if self.partenaire_id and not self.partenaire.is_global_rental:
            raise ValidationError(
                {"partenaire": "Le partenaire doit être marqué GLOBAL RENTAL (intra-groupe)."}
            )
        if self.tarif is not None and self.tarif < 0:
            raise ValidationError({"tarif": "Le tarif ne peut être négatif."})
        if self.penalite_jour is not None and self.penalite_jour < 0:
            raise ValidationError({"penalite_jour": "La pénalité ne peut être négative."})
        if self.equipement_id:
            self.categorie = self.equipement.categorie

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = LogistiqueSequence.next_for("TGR", "TGR")
        if self._state.adding:
            dernier = (
                TarifGR.objects.filter(
                    partenaire_id=self.partenaire_id, equipement_id=self.equipement_id,
                    categorie=self.categorie, periodicite=self.periodicite,
                )
                .aggregate(m=models.Max("version"))["m"]
            )
            self.version = (dernier or 0) + 1
        return super().save(*args, **kwargs)

    @classmethod
    def applicable(cls, partenaire, equipement, periodicite, jour):
        """Version en vigueur au `jour` : la plus spécifique, puis la plus récente."""
        candidats = cls.objects.filter(
            models.Q(equipement=equipement)
            | models.Q(equipement__isnull=True, categorie=equipement.categorie)
            | models.Q(equipement__isnull=True, categorie=""),
            partenaire=partenaire, periodicite=periodicite, date_effet__lte=jour,
        )

        def rang(t):
            specificite = 2 if t.equipement_id else (1 if t.categorie else 0)
            return (specificite, t.date_effet, t.version)

        return max(candidats, key=rang, default=None)


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

class ParametreLogistique(models.Model):
    """Paramètre M4 modifiable par ETSL sans développeur (formule glissante des compteurs, valorisation au mois).

    Tant que `statut_valeur` = « provisoire », les écrans et états qui l'utilisent avertissent. Le défaut est créé à
    la volée par `services.get_param_logistique` (la valeur est une DONNÉE, jamais figée dans le code).
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
        verbose_name = "Paramètre logistique"
        verbose_name_plural = "Paramètres logistique"

    def __str__(self):
        return f"{self.code} = {self.valeur} {self.unite}"

    @property
    def est_provisoire(self):
        return self.statut_valeur != self.StatutValeur.CONFIRME


# --------------------------------------------------------------------------------------------------
# Écarts M4 : historique des compteurs du parc, lignes BC / BL, réception BL, archive GR, audit photo
# --------------------------------------------------------------------------------------------------
class ReleveCompteurParc(models.Model):
    """Historique du kilométrage / des heures d'un équipement du parc (interne ou GR) — jamais à la baisse."""

    class Source(models.TextChoices):
        SAISIE = "saisie", "Saisie parc"
        LOCATION = "location", "Relevé de location GR"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    equipement = models.ForeignKey(
        EquipementParc, on_delete=models.CASCADE, related_name="releves", verbose_name="Équipement"
    )
    date = models.DateField(verbose_name="Date du relevé")
    valeur = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Valeur compteur")
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.SAISIE, verbose_name="Source")
    commentaire = models.CharField(max_length=200, blank=True, verbose_name="Commentaire")
    saisi_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Saisi par",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "Relevé de compteur du parc"
        verbose_name_plural = "Historique des compteurs du parc"
        indexes = [models.Index(fields=["equipement", "date"])]

    def __str__(self):
        return f"{self.equipement.code} — {self.date} — {self.valeur}"


class HistoriqueEquipement(models.Model):
    """Piste d'audit des modifications d'un équipement (champ, ancienne / nouvelle valeur) — inaltérable."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    equipement = models.ForeignKey(
        EquipementParc, on_delete=models.PROTECT, related_name="historique", verbose_name="Équipement"
    )
    champ = models.CharField(max_length=60, verbose_name="Champ modifié")
    ancienne_valeur = models.TextField(blank=True, verbose_name="Ancienne valeur")
    nouvelle_valeur = models.TextField(blank=True, verbose_name="Nouvelle valeur")
    modifie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Modifié par",
    )
    modifie_le = models.DateTimeField(auto_now_add=True, verbose_name="Modifié le")

    class Meta:
        ordering = ["-modifie_le"]
        verbose_name = "Historique d'équipement"
        verbose_name_plural = "Historique des équipements"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Historique inaltérable : modification interdite.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Historique inaltérable : suppression interdite.")


class AuditEquipement(models.Model):
    """Audit d'un équipement avec photo de la machine (empreinte SHA-256), conservé N années (paramètre)."""

    class Etat(models.TextChoices):
        BON = "bon", "Bon état"
        USAGE = "usage", "Usure normale"
        DEGRADE = "degrade", "Dégradé"
        HORS_SERVICE = "hors_service", "Hors service"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    equipement = models.ForeignKey(
        EquipementParc, on_delete=models.PROTECT, related_name="audits", verbose_name="Équipement"
    )
    date_audit = models.DateField(verbose_name="Date de l'audit")
    etat = models.CharField(max_length=12, choices=Etat.choices, default=Etat.BON, verbose_name="État constaté")
    compteur = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True, verbose_name="Compteur constaté"
    )
    observations = models.TextField(blank=True, verbose_name="Observations")
    photo = models.FileField(upload_to="logistique/audits/%Y/", verbose_name="Photo de la machine")
    photo_sha256 = models.CharField(max_length=64, verbose_name="Empreinte SHA-256 de la photo")
    conserver_jusqu_au = models.DateField(verbose_name="Conservation jusqu'au")
    auditeur = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Auditeur",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_audit", "-created_at"]
        verbose_name = "Audit d'équipement (photo)"
        verbose_name_plural = "Audits d'équipement (photo)"

    def __str__(self):
        return f"{self.code} — {self.equipement.code}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Audit scellé : modification interdite.")
        if not self.code:
            self.code = LogistiqueSequence.next_for("AUD", "AUD")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Audit conservé (durée de conservation) : suppression interdite.")


class LigneLocationGR(models.Model):
    """Ligne détaillée du BC GR (désignation, quantité, prix) et quantité livrée au BL."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    location = models.ForeignKey(
        LocationGR, on_delete=models.CASCADE, related_name="lignes", verbose_name="Prestation GR"
    )
    designation = models.CharField(max_length=200, verbose_name="Désignation")
    quantite = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Quantité commandée")
    unite = models.CharField(max_length=20, blank=True, default="u", verbose_name="Unité")
    prix_unitaire = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Prix unitaire")
    quantite_livree = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True, verbose_name="Quantité livrée (BL)"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Ligne de prestation GR"
        verbose_name_plural = "Lignes de prestation GR"

    def __str__(self):
        return f"{self.location.code} — {self.designation}"

    def clean(self):
        if self.quantite is not None and self.quantite <= 0:
            raise ValidationError({"quantite": "La quantité doit être strictement positive."})
        if self.prix_unitaire is not None and self.prix_unitaire < 0:
            raise ValidationError({"prix_unitaire": "Le prix ne peut être négatif."})

    @property
    def montant(self):
        return (self.quantite or 0) * (self.prix_unitaire or 0)


class ReceptionBLGR(models.Model):
    """Réception contrôlée du bon de livraison GR : écarts par ligne, escalade M12 au-delà du seuil."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    location = models.ForeignKey(
        LocationGR, on_delete=models.PROTECT, related_name="receptions_bl", verbose_name="Prestation GR"
    )
    reference_bl = models.CharField(max_length=40, verbose_name="Référence du BL")
    date_reception = models.DateField(verbose_name="Date de réception")
    lignes = models.JSONField(default=list, blank=True, verbose_name="Contrôle par ligne")
    ecart_pct = models.DecimalField(max_digits=7, decimal_places=2, default=0, verbose_name="Écart global (%)")
    reserves = models.TextField(blank=True, verbose_name="Réserves")
    litige = models.BooleanField(default=False, verbose_name="Litige")
    contentieux = models.ForeignKey(
        "juridique.Contentieux", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Contentieux M12",
    )
    dossier_gr = models.ForeignKey(
        "juridique.DossierGlobalRental", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Dossier GR M12",
    )
    recu_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Reçu par",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_reception", "-created_at"]
        verbose_name = "Réception de BL GR"
        verbose_name_plural = "Réceptions de BL GR"

    def __str__(self):
        return f"{self.code} — {self.reference_bl}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = LogistiqueSequence.next_for("RBL", "RBL")
        return super().save(*args, **kwargs)


class ArchiveCompteurGR(models.Model):
    """Archive scellée des compteurs d'une prestation GR à sa clôture (relevés, formule glissante, coût)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    location = models.OneToOneField(
        LocationGR, on_delete=models.PROTECT, related_name="archive_compteurs", verbose_name="Prestation GR"
    )
    contenu = models.JSONField(default=dict, verbose_name="Contenu archivé")
    sha256 = models.CharField(max_length=64, verbose_name="Empreinte SHA-256")
    conserver_jusqu_au = models.DateField(verbose_name="Conservation jusqu'au")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Archive des compteurs GR"
        verbose_name_plural = "Archives des compteurs GR"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Archive scellée : modification interdite.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Archive scellée : suppression interdite.")
