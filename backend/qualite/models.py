"""Module M6 — Qualité industrielle, Soudage & Contrôle Qualité / Inspection (RF-ERP-50…53).

Procédures MANUEL 5.4 (Tuyauterie et soudure) + 5.8 (Contrôle qualité – QA/QC):
qualifications soudeurs ISO 9606-1 / ASME IX · WPS / WPQR / CND / PDA / ITP ·
non-conformités & CAPA (actions correctives) · PV de contrôle & levée de réserve ·
réception interne · archivage 10 ans (Oil & Gas). Circuit technique `RF-ERP-W2`
(Direction des Opérations → QA-QC → HSE).
Dérivé du schéma `Architecture ERP ETSL.png` §2.1 (M6).
"""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone


class QualiteSequence(models.Model):
    """Numérotation séquentielle par type (SOU, QUAL, WPS, CTR, PV, NC, CAP)."""

    kind = models.CharField(max_length=10, unique=True, verbose_name="Type")
    prefix = models.CharField(max_length=10, verbose_name="Préfixe")
    padding = models.PositiveSmallIntegerField(default=5, verbose_name="Zéro-padding")
    next_number = models.PositiveIntegerField(default=1, verbose_name="Prochain numéro")

    class Meta:
        verbose_name = "Séquence Qualité"
        verbose_name_plural = "Séquences Qualité"

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


class Soudeur(models.Model):
    """Soudeur — carte d'identité professionnelle (RF-ERP-50)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    nom = models.CharField(max_length=150, verbose_name="Nom")
    prenoms = models.CharField(max_length=150, blank=True, verbose_name="Prénoms")
    matricule = models.CharField(max_length=60, blank=True, verbose_name="Matricule")
    qualification = models.CharField(
        max_length=120, blank=True, verbose_name="Qualification principale"
    )
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "Soudeur"
        verbose_name_plural = "Soudeurs"

    def __str__(self):
        initials = f" ({self.matricule})" if self.matricule else ""
        return f"{self.code} — {self.nom} {self.prenoms}{initials}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = QualiteSequence.next_for("SOU", "SOU")
        return super().save(*args, **kwargs)

    @property
    def display_name(self):
        return f"{self.nom} {self.prenoms}".strip()


class QualificationSoudeur(models.Model):
    """Qualification d'un soudeur — ISO 9606-1 / ASME IX (RF-ERP-50)."""

    class Norme(models.TextChoices):
        ISO_9606 = "iso9606", "ISO 9606-1"
        ASME_IX = "asme_ix", "ASME IX"

    class Procede(models.TextChoices):
        SMAW = "smaw", "SMAW (électrode enrobée)"
        GTAW = "gtaw", "GTAW (TIG)"
        GMAW = "gmaw", "GMAW (MIG/MAG)"
        FCAW = "fcaw", "FCAW (fil fourré)"

    class Statut(models.TextChoices):
        VALIDE = "valide", "Valide"
        EXPIREE = "expiree", "Expirée"
        SUSPENDUE = "suspendue", "Suspendue"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    soudeur = models.ForeignKey(
        Soudeur, on_delete=models.CASCADE, related_name="qualifications", verbose_name="Soudeur"
    )
    norme = models.CharField(
        max_length=12, choices=Norme.choices, default=Norme.ISO_9606, verbose_name="Norme"
    )
    procede = models.CharField(
        max_length=6, choices=Procede.choices, default=Procede.SMAW, verbose_name="Procédé"
    )
    position = models.CharField(max_length=60, blank=True, verbose_name="Position(s)")
    groupe_materiaux = models.CharField(
        max_length=120, blank=True, verbose_name="Groupe de matériaux"
    )
    epaisseur_min = models.DecimalField(
        max_digits=8, decimal_places=2, default=0, verbose_name="Épaisseur min (mm)"
    )
    epaisseur_max = models.DecimalField(
        max_digits=8, decimal_places=2, default=0, verbose_name="Épaisseur max (mm)"
    )
    gamme_diametre = models.CharField(
        max_length=120, blank=True, verbose_name="Gamme diamètre (tubes)"
    )
    date_qualification = models.DateField(verbose_name="Date de qualification")
    date_validite = models.DateField(verbose_name="Date de validité")
    statut = models.CharField(
        max_length=12, choices=Statut.choices, default=Statut.VALIDE, verbose_name="Statut"
    )
    certificat = models.CharField(max_length=80, blank=True, verbose_name="N° certificat")
    notes = models.TextField(blank=True, verbose_name="Notes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_validite"]
        verbose_name = "Qualification soudeur"
        verbose_name_plural = "Qualifications soudeurs"
        indexes = [models.Index(fields=["soudeur", "norme"])]

    def __str__(self):
        return f"{self.code} — {self.soudeur.display_name} ({self.get_norme_display()})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = QualiteSequence.next_for("QUAL", "QUAL")
        return super().save(*args, **kwargs)

    def clean(self):
        if self.date_validite and self.date_qualification:
            if self.date_validite < self.date_qualification:
                raise ValidationError(
                    {"date_validite": "La date de validité doit être postérieure à la qualification."}
                )
            if self.date_validite < timezone.localdate():
                self.statut = self.Statut.EXPIREE

    @property
    def est_valide(self):
        return (
            self.statut == self.Statut.VALIDE
            and self.date_validite >= timezone.localdate()
        )


class WpsWpqr(models.Model):
    """Procédure de soudage WPS / qualification WPQR (RF-ERP-51)."""

    class Type(models.TextChoices):
        WPS = "wps", "WPS (procédure de soudage)"
        WPQR = "wpqr", "WPQR (qualification mode opératoire)"

    class Statut(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        VALIDE = "valide", "Validé"
        OBSOLETE = "obsolete", "Obsolète"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    type = models.CharField(
        max_length=5, choices=Type.choices, default=Type.WPS, verbose_name="Type"
    )
    reference = models.CharField(max_length=80, blank=True, verbose_name="Référence")
    norme = models.CharField(
        max_length=12, choices=QualificationSoudeur.Norme.choices,
        default=QualificationSoudeur.Norme.ISO_9606, verbose_name="Norme",
    )
    procede = models.CharField(
        max_length=6, choices=QualificationSoudeur.Procede.choices,
        default=QualificationSoudeur.Procede.SMAW, verbose_name="Procédé",
    )
    materiau = models.CharField(
        max_length=120, blank=True, verbose_name="Matériau de base"
    )
    position = models.CharField(max_length=60, blank=True, verbose_name="Position(s)")
    epaisseur = models.CharField(max_length=120, blank=True, verbose_name="Épaisseur / diamètre")
    gaz_protection = models.CharField(
        max_length=120, blank=True, verbose_name="Gaz de protection"
    )
    parametres = models.JSONField(default=dict, blank=True, verbose_name="Paramètres de soudage")
    revue = models.CharField(max_length=60, blank=True, verbose_name="Revue")
    statut = models.CharField(
        max_length=10, choices=Statut.choices, default=Statut.BROUILLON, verbose_name="Statut"
    )
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="qualite_wps_validated",
        verbose_name="Validé par QA/QC",
    )
    date_validation = models.DateField(null=True, blank=True, verbose_name="Date de validation")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "WPS / WPQR"
        verbose_name_plural = "WPS / WPQR"

    def __str__(self):
        return f"{self.code} — {self.get_type_display()} ({self.get_procede_display()})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = QualiteSequence.next_for("WPS", "WPS")
        return super().save(*args, **kwargs)


class ControleQualite(models.Model):
    """Contrôle qualité / inspection — visuel, dimensionnel, CND, PDA, ITP (RF-ERP-51)."""

    class TypeControle(models.TextChoices):
        VISUEL = "visuel", "Contrôle visuel"
        DIMENSIONNEL = "dimensionnel", "Contrôle dimensionnel"
        CND = "cnd", "CND (radiographie, ultrasons, ressuage, magnétoscopie)"
        PDA = "pda", "PDA (plan de détection)"
        ITP = "itp", "ITP (plan d'inspection et d'essais)"
        PEINTURE = "peinture", "Peinture / anticorrosion"

    class OrganismeCnd(models.TextChoices):
        INTERNE = "interne", "Interne QA/QC"
        ORGANISME_AGREE = "agrege", "Organisme agréé"

    class Resultat(models.TextChoices):
        CONFORME = "conforme", "Conforme"
        RESERVE = "reserve", "Accepté sous réserve"
        NON_CONFORME = "non_conforme", "Non conforme"

    class Statut(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente"
        EN_COURS = "en_cours", "En cours"
        VALIDE = "valide", "Validé"
        ANNULE = "annule", "Annulé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    type_controle = models.CharField(
        max_length=14, choices=TypeControle.choices, default=TypeControle.VISUEL,
        verbose_name="Type de contrôle",
    )
    organisme = models.CharField(
        max_length=14, choices=OrganismeCnd.choices, default=OrganismeCnd.INTERNE,
        verbose_name="Réalisé par",
    )
    organisme_libelle = models.CharField(
        max_length=150, blank=True, verbose_name="Organisme (si agréé)"
    )
    affaire = models.ForeignKey(
        "commercial.Affaire",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="controles_qualite",
        verbose_name="Affaire",
    )
    ordre = models.ForeignKey(
        "operations.OrdreFabrication",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="controles_qualite",
        verbose_name="Ordre de fabrication",
    )
    wps = models.ForeignKey(
        WpsWpqr,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="controles",
        verbose_name="WPS",
    )
    lot = models.ForeignKey(
        "stocks.LotMatiere",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="controles_qualite",
        verbose_name="Lot matière contrôlé",
    )
    point_controle = models.CharField(
        max_length=200, blank=True, verbose_name="Point de contrôle (repère / joint)"
    )
    exigence = models.CharField(
        max_length=200, blank=True, verbose_name="Exigence / critère d'acceptation"
    )
    date_controle = models.DateField(default=timezone.localdate, verbose_name="Date du contrôle")
    resultat = models.CharField(
        max_length=14, choices=Resultat.choices, default=Resultat.CONFORME, verbose_name="Résultat"
    )
    statut = models.CharField(
        max_length=12, choices=Statut.choices, default=Statut.EN_ATTENTE, verbose_name="Statut"
    )
    notes = models.TextField(blank=True, verbose_name="Notes / observations")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="qualite_controles",
        verbose_name="Créé par",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_controle", "-created_at"]
        verbose_name = "Contrôle qualité"
        verbose_name_plural = "Contrôles qualité"
        indexes = [models.Index(fields=["type_controle", "resultat"])]

    def __str__(self):
        return f"{self.code} — {self.get_type_controle_display()} ({self.get_resultat_display()})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = QualiteSequence.next_for("CTR", "CTR")
        return super().save(*args, **kwargs)


class NonConformite(models.Model):
    """Non-conformité détectée — enregistrée, analysée, traitée (RF-ERP-52, MANUEL 5.8.4)."""

    class Source(models.TextChoices):
        CONTROLE = "controle", "Contrôle qualité"
        CLIENT = "client", "Client"
        FOURNISSEUR = "fournisseur", "Fournisseur"
        INTERNE = "interne", "Interne"

    class Gravite(models.TextChoices):
        MINEURE = "mineure", "Mineure"
        MAJEURE = "majeure", "Majeure"
        CRITIQUE = "critique", "Critique"

    class Traitement(models.TextChoices):
        REPRISE = "reprise", "Reprise"
        REPARATION = "reparation", "Réparation"
        REJET = "rejet", "Rejet"
        ACCEPTATION = "acceptation", "Acceptation sous réserve"
        ARBITRAGE = "arbitrage", "Arbitrage technique"

    class Statut(models.TextChoices):
        SIGNALEE = "signalee", "Signalée"
        ANALYSEE = "analysee", "Analysée"
        EN_TRAITEMENT = "en_traitement", "En traitement"
        CLOTUREE = "cloturee", "Clôturée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    controle = models.ForeignKey(
        ControleQualite,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="non_conformites",
        verbose_name="Contrôle d'origine",
    )
    source = models.CharField(
        max_length=14, choices=Source.choices, default=Source.CONTROLE, verbose_name="Source"
    )
    gravite = models.CharField(
        max_length=10, choices=Gravite.choices, default=Gravite.MINEURE, verbose_name="Gravité"
    )
    description = models.TextField(verbose_name="Description")
    traitement = models.CharField(
        max_length=14, choices=Traitement.choices, default=Traitement.REPRISE,
        verbose_name="Traitement",
    )
    statut = models.CharField(
        max_length=14, choices=Statut.choices, default=Statut.SIGNALEE, verbose_name="Statut"
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="qualite_nc_decisions",
        verbose_name="Décision QA/QC",
    )
    date_decision = models.DateField(null=True, blank=True, verbose_name="Date de décision")
    archive = models.BooleanField(default=False, verbose_name="Archivée (10 ans Oil & Gas)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Non-conformité"
        verbose_name_plural = "Non-conformités"
        indexes = [models.Index(fields=["statut", "gravite"])]

    def __str__(self):
        return f"{self.code} — {self.get_gravite_display()} ({self.get_statut_display()})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = QualiteSequence.next_for("NC", "NC")
        return super().save(*args, **kwargs)

    def clean(self):
        if not self.description.strip():
            raise ValidationError({"description": "La description de la non-conformité est requise."})


class ActionCorrective(models.Model):
    """Action corrective / préventive — CAPA (RF-ERP-52)."""

    class TypeAction(models.TextChoices):
        CORRECTIVE = "corrective", "Corrective"
        PREVENTIVE = "preventive", "Préventive"

    class Statut(models.TextChoices):
        OUVERTE = "ouverte", "Ouverte"
        EN_COURS = "en_cours", "En cours"
        CLOTUREE = "cloturee", "Clôturée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    non_conformite = models.ForeignKey(
        NonConformite,
        on_delete=models.CASCADE,
        related_name="actions_correctives",
        verbose_name="Non-conformité",
    )
    type = models.CharField(
        max_length=12, choices=TypeAction.choices, default=TypeAction.CORRECTIVE,
        verbose_name="Type",
    )
    description = models.TextField(verbose_name="Action")
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="qualite_capa_responsable",
        verbose_name="Responsable",
    )
    echeance = models.DateField(null=True, blank=True, verbose_name="Échéance")
    statut = models.CharField(
        max_length=10, choices=Statut.choices, default=Statut.OUVERTE, verbose_name="Statut"
    )
    efficace = models.BooleanField(null=True, blank=True, verbose_name="Efficacité vérifiée")
    closed_at = models.DateTimeField(null=True, blank=True, verbose_name="Clôturée le")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Action corrective"
        verbose_name_plural = "Actions correctives"

    def __str__(self):
        return f"{self.code} — {self.get_type_display()} ({self.get_statut_display()})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = QualiteSequence.next_for("CAP", "CAP")
        return super().save(*args, **kwargs)


class PvControle(models.Model):
    """Procès-verbal de contrôle & levée de réserve / réception interne (RF-ERP-51/53)."""

    class Statut(models.TextChoices):
        EN_COURS = "en_cours", "En cours"
        RESERVE = "reserve", "Sous réserve"
        RECEPTIONNE = "receptionne", "Réceptionné / levée de réserve"
        REJETE = "rejete", "Rejeté"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    affaire = models.ForeignKey(
        "commercial.Affaire",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="pv_controle",
        verbose_name="Affaire",
    )
    ordre = models.ForeignKey(
        "operations.OrdreFabrication",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="pv_controle",
        verbose_name="Ordre de fabrication",
    )
    intitule = models.CharField(max_length=200, verbose_name="Intitulé")
    controles = models.ManyToManyField(
        ControleQualite, blank=True, related_name="pvs", verbose_name="Contrôles couverts"
    )
    date_pv = models.DateField(default=timezone.localdate, verbose_name="Date du PV")
    statut = models.CharField(
        max_length=12, choices=Statut.choices, default=Statut.EN_COURS, verbose_name="Statut"
    )
    resultat = models.CharField(
        max_length=14, choices=ControleQualite.Resultat.choices,
        default=ControleQualite.Resultat.CONFORME, verbose_name="Résultat global",
    )
    reserve_motif = models.TextField(blank=True, verbose_name="Motif de réserve (si réservé)")
    levee_reserve = models.DateField(null=True, blank=True, verbose_name="Levée de réserve")
    retention_years = models.PositiveSmallIntegerField(
        default=10, verbose_name="Conservation (années)"
    )
    date_archivage = models.DateField(null=True, blank=True, verbose_name="Date d'archivage")
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="qualite_pv_validated",
        verbose_name="Validé par",
    )
    notes = models.TextField(blank=True, verbose_name="Notes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_pv"]
        verbose_name = "PV de contrôle"
        verbose_name_plural = "PV de contrôle"

    def __str__(self):
        return f"{self.code} — {self.intitule} ({self.get_statut_display()})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = QualiteSequence.next_for("PV", "PV")
        return super().save(*args, **kwargs)