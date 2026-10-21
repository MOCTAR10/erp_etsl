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
    # Lien M9 : le soudeur est un salarié (dossier RH, contrats, pointages) ; vide pour un intérimaire.
    employe = models.ForeignKey(
        "rh_paie.Employe", null=True, blank=True, on_delete=models.SET_NULL, related_name="soudeurs",
        verbose_name="Fiche salarié (M9)",
    )
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
    # Un WPS s'appuie sur un WPQR (PQR) qualifié ; la fiche signée est jointe (PDF / scan).
    wpqr = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="wps_supportes",
        verbose_name="WPQR support", limit_choices_to={"type": "wpqr"},
    )
    fichier = models.FileField(upload_to="qualite/wps/%Y/", blank=True, verbose_name="Fiche WPS / PQR (PDF)")
    obsolete_le = models.DateTimeField(null=True, blank=True, verbose_name="Rendu obsolète le")
    obsolete_motif = models.CharField(max_length=250, blank=True, verbose_name="Motif d'obsolescence")
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
        RECEPTION = "reception", "Contrôle à réception (achats M2)"
        GENIE_CIVIL = "genie_civil", "Génie civil (béton, armatures)"
        ELECTRIQUE = "electrique", "Électricité et instrumentation"
        ESSAI = "essai", "Essai fonctionnel"
        TTH = "tth", "Traitement thermique (TTH)"

    class MethodeCnd(models.TextChoices):
        RT = "RT", "Radiographie (RT)"
        UT = "UT", "Ultrasons (UT)"
        PT = "PT", "Ressuage (PT)"
        MT = "MT", "Magnétoscopie (MT)"

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
    # Réception fournisseur contrôlée (clôture M2, CDC §5.11 : chaque réception déclenche le contrôle M6).
    reception = models.ForeignKey(
        "achats.GoodsReceipt",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="controles_qualite",
        verbose_name="Réception fournisseur",
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
    methode_cnd = models.CharField(
        max_length=2, choices=MethodeCnd.choices, blank=True, verbose_name="Méthode CND"
    )
    instrument = models.ForeignKey(
        "InstrumentMesure", null=True, blank=True, on_delete=models.PROTECT,
        related_name="controles", verbose_name="Instrument de mesure",
    )
    # Approbation du plan (ITP) : préalable à tout soudage sur l'OF ; le plan est ensuite figé.
    approuve_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="itp_approuves", verbose_name="ITP approuvé par",
    )
    approuve_le = models.DateTimeField(null=True, blank=True, verbose_name="ITP approuvé le")
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

    def clean(self):
        if self.methode_cnd and self.type_controle != self.TypeControle.CND:
            raise ValidationError({"methode_cnd": "La méthode (RT/UT/PT/MT) est réservée aux contrôles de type CND."})


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
    # NCR-SD : variante soudage du socle NC ; clôturée uniquement par un re-CND conforme.
    type_ncr = models.CharField(
        max_length=10, choices=[("generique", "Générique"), ("soudage", "Soudage (NCR-SD)"), ("hse", "HSE (NCR-HSE)")],
        default="generique", verbose_name="Type de NC",
    )
    incident_hse = models.ForeignKey(
        "hse.Incident", null=True, blank=True, on_delete=models.PROTECT, related_name="ncr_hse",
        verbose_name="Événement HSE d'origine (NCR-HSE)",
    )
    constat_audit_hse = models.ForeignKey(
        "hse.ConstatAudit", null=True, blank=True, on_delete=models.PROTECT, related_name="ncr_hse",
        verbose_name="Écart d'audit HSE d'origine (NCR-HSE)",
    )
    joint = models.ForeignKey(
        "JointSoude", null=True, blank=True, on_delete=models.PROTECT,
        related_name="non_conformites", verbose_name="Joint soudé",
    )
    recontrole = models.ForeignKey(
        ControleQualite, null=True, blank=True, on_delete=models.PROTECT,
        related_name="ncr_cloturees", verbose_name="Re-CND de clôture",
    )
    instrument = models.ForeignKey(
        "InstrumentMesure", null=True, blank=True, on_delete=models.PROTECT, related_name="non_conformites",
        verbose_name="Équipement hors tolérance (métrologie)",
    )
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
            # NCR-HSE : numérotation propre, même socle (traitement, CAPA, clôture) que les NC qualité.
            if self.type_ncr == "hse":
                self.code = QualiteSequence.next_for("NCRHSE", "NCR-HSE-")
            elif self.type_ncr == "soudage":
                self.code = QualiteSequence.next_for("NCRSD", "NCR-SD-")
            else:
                self.code = QualiteSequence.next_for("NC", "NC")
        result = super().save(*args, **kwargs)
        self._synchroniser_quarantaine()
        return result


    def _synchroniser_quarantaine(self):
        """M5 ↔ M6 (CDC M5 §7.10) : une NC **matière** ouverte (contrôle à réception, ou NC d'origine fournisseur) met
        le lot contrôlé en quarantaine ; sa clôture la lève s'il ne reste aucune autre NC matière ouverte sur ce lot.
        Une NC de fabrication (soudure, CND sur un joint) qui cite le lot pour la traçabilité ne bloque pas la matière."""
        lot = self.controle.lot if self.controle_id and self.controle.lot_id else None
        if lot is None or not self.est_nc_matiere():
            return
        ouvertes = [nc for nc in NonConformite.objects.filter(controle__lot=lot).exclude(statut=self.Statut.CLOTUREE)
                    .select_related("controle") if nc.est_nc_matiere()]
        if self.statut != self.Statut.CLOTUREE:
            if lot.statut != lot.Statut.BLOQUE:
                lot.mettre_en_quarantaine(f"NC {self.code} : {self.description}", user=self.decided_by, nc=self)
        elif lot.statut == lot.Statut.BLOQUE and lot.nc_blocage_id and not ouvertes:
            lot.lever_quarantaine()

    def est_nc_matiere(self):
        return self.source == self.Source.FOURNISSEUR or (
            self.controle_id is not None and self.controle.type_controle == ControleQualite.TypeControle.RECEPTION
        )
    def clean(self):
        if not self.description.strip():
            raise ValidationError({"description": "La description de la non-conformité est requise."})
        if self.type_ncr == "soudage" and not self.joint_id:
            raise ValidationError({"joint": "Une NCR-SD (soudage) se rattache à un joint soudé."})
        if self.type_ncr == "hse" and not (self.incident_hse_id or self.constat_audit_hse_id):
            raise ValidationError({"incident_hse": "Une NCR-HSE se rattache à un événement HSE ou à un écart d'audit HSE."})


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
    escaladee_le = models.DateTimeField(null=True, blank=True, verbose_name="Escaladée à la direction le")
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

    @property
    def en_retard(self):
        return bool(self.echeance and self.statut != self.Statut.CLOTUREE and self.echeance < timezone.localdate())


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
    dossier_document = models.ForeignKey(
        "documents.Document", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Dossier qualité scellé (GED)",
    )
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


class PointInspection(models.Model):
    """Point d'un ITP (plan d'inspection et d'essais) - CL-OM-07.

    Point d'ARRÊT (hold) : les travaux ne continuent pas tant qu'il n'est pas levé.
    Point d'OBSERVATION (witness) : le contrôle peut se faire en présence du client / organisme,
    sans bloquer la suite. La levée est tracée (qui, quand, résultat, commentaire).
    """

    class TypePoint(models.TextChoices):
        ARRET = "arret", "Point d'arrêt (hold)"
        OBSERVATION = "observation", "Point d'observation (witness)"

    class Statut(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente"
        LEVE = "leve", "Levé"
        NON_CONFORME = "non_conforme", "Non conforme"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    controle = models.ForeignKey(
        ControleQualite, on_delete=models.CASCADE, related_name="points", verbose_name="ITP"
    )
    ordre = models.PositiveSmallIntegerField(verbose_name="N° d'ordre dans l'ITP")
    description = models.CharField(max_length=250, verbose_name="Point d'inspection")
    type_point = models.CharField(
        max_length=12, choices=TypePoint.choices, default=TypePoint.ARRET, verbose_name="Type de point"
    )
    responsable_levee = models.CharField(
        max_length=120, blank=True, verbose_name="Levée par (QA/QC, client, organisme...)"
    )
    date_prevue = models.DateField(null=True, blank=True, verbose_name="Date prévue")
    statut = models.CharField(
        max_length=12, choices=Statut.choices, default=Statut.EN_ATTENTE, verbose_name="Statut"
    )
    leve_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="points_itp_leves", verbose_name="Levé par",
    )
    leve_le = models.DateTimeField(null=True, blank=True, verbose_name="Levé le")
    commentaire = models.CharField(max_length=250, blank=True, verbose_name="Commentaire")

    class Meta:
        ordering = ["controle", "ordre"]
        verbose_name = "Point d'inspection (ITP)"
        verbose_name_plural = "Points d'inspection (ITP)"
        constraints = [
            models.UniqueConstraint(fields=["controle", "ordre"], name="uniq_itp_point_ordre")
        ]

    def __str__(self):
        return f"{self.controle_id} #{self.ordre} {self.get_type_point_display()}"

    def clean(self):
        if self.controle_id and self.controle.type_controle != ControleQualite.TypeControle.ITP:
            raise ValidationError({"controle": "Des points d'inspection se rattachent à un contrôle de type ITP."})

    @property
    def en_retard(self):
        return bool(self.date_prevue and self.statut == self.Statut.EN_ATTENTE and self.date_prevue < timezone.localdate())


class InstrumentMesure(models.Model):
    """Instrument de mesure soumis à étalonnage (métrologie). Hors échéance ou hors tolérance : usage bloqué."""

    class Statut(models.TextChoices):
        ACTIF = "actif", "En service"
        BLOQUE = "bloque", "Bloqué (hors tolérance)"

    class TypeEquipement(models.TextChoices):
        INSTRUMENT = "instrument", "Instrument de mesure"
        POSTE_SOUDER = "poste_souder", "Poste à souder"
        FOUR_TTH = "four_tth", "Four / équipement de traitement thermique"
        MANOMETRE = "manometre", "Manomètre / enregistreur de pression"
        THERMOMETRE = "thermometre", "Thermomètre / thermocouple"
        AUTRE = "autre", "Autre équipement"

    #: Opération de métrologie attendue par type : étalonnage (instrument), vérification (poste), validation (four).
    OPERATION_PAR_TYPE = {"poste_souder": "verification", "four_tth": "validation"}

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    designation = models.CharField(max_length=150, verbose_name="Désignation")
    type_equipement = models.CharField(
        max_length=14, choices=TypeEquipement.choices, default=TypeEquipement.INSTRUMENT, verbose_name="Type d'équipement"
    )
    periodicite_mois = models.PositiveSmallIntegerField(default=12, verbose_name="Périodicité (mois)")
    organisme = models.CharField(max_length=150, blank=True, verbose_name="Organisme d'étalonnage")
    localisation = models.CharField(max_length=120, blank=True, verbose_name="Localisation")
    numero_serie = models.CharField(max_length=80, verbose_name="N° de série")
    date_etalonnage = models.DateField(verbose_name="Dernier étalonnage")
    echeance_etalonnage = models.DateField(verbose_name="Échéance d'étalonnage")
    statut = models.CharField(max_length=8, choices=Statut.choices, default=Statut.ACTIF, verbose_name="Statut")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["echeance_etalonnage"]
        verbose_name = "Instrument de mesure"
        verbose_name_plural = "Instruments de mesure"

    def __str__(self):
        return f"{self.code} — {self.designation}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = QualiteSequence.next_for("MET", "MET-")
        return super().save(*args, **kwargs)

    def clean(self):
        if self.echeance_etalonnage and self.date_etalonnage and self.echeance_etalonnage < self.date_etalonnage:
            raise ValidationError({"echeance_etalonnage": "L'échéance précède la date d'étalonnage."})

    @property
    def utilisable(self):
        return self.statut == self.Statut.ACTIF and self.echeance_etalonnage >= timezone.localdate()

    @property
    def operation_attendue(self):
        return self.OPERATION_PAR_TYPE.get(self.type_equipement, "etalonnage")


class Etalonnage(models.Model):
    """Historique des étalonnages d'un instrument (preuve, non modifiable)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    instrument = models.ForeignKey(InstrumentMesure, on_delete=models.CASCADE, related_name="etalonnages")
    date = models.DateField(default=timezone.localdate)
    echeance = models.DateField(null=True, blank=True)
    conforme = models.BooleanField(default=True, verbose_name="Dans la tolérance")
    type_operation = models.CharField(
        max_length=12, default="etalonnage", verbose_name="Opération",
        choices=[("etalonnage", "Étalonnage"), ("verification", "Vérification"), ("validation", "Validation")],
    )
    organisme = models.CharField(max_length=150, blank=True, verbose_name="Organisme")
    certificat = models.CharField(max_length=80, blank=True, verbose_name="N° certificat")
    par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-date", "-id"]


class JointSoude(models.Model):
    """Registre des joints : un joint = OF + repère + soudeur + WPS + coulée (traçabilité des soudures)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    ordre = models.ForeignKey(
        "operations.OrdreFabrication", on_delete=models.PROTECT, related_name="joints", verbose_name="OF"
    )
    repere = models.CharField(max_length=60, verbose_name="N° de joint")
    soudeur = models.ForeignKey(Soudeur, on_delete=models.PROTECT, related_name="joints")
    wps = models.ForeignKey(WpsWpqr, null=True, blank=True, on_delete=models.PROTECT, related_name="joints")
    numero_coulee = models.CharField(max_length=60, blank=True, verbose_name="N° de coulée (heat number)")
    consommable = models.CharField(max_length=120, blank=True, verbose_name="Consommable (lot de fil / électrode)")
    poste = models.ForeignKey(
        InstrumentMesure, null=True, blank=True, on_delete=models.PROTECT, related_name="joints",
        verbose_name="Poste à souder",
    )
    date_soudage = models.DateField(default=timezone.localdate)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["ordre", "repere"]
        verbose_name = "Joint soudé"
        verbose_name_plural = "Joints soudés"
        constraints = [models.UniqueConstraint(fields=["ordre", "repere"], name="uniq_joint_of_repere")]

    def __str__(self):
        return f"{self.code} — {self.repere}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = QualiteSequence.next_for("JNT", "JNT-")
        return super().save(*args, **kwargs)


class ImageControle(models.Model):
    """Image / film CND archivé (empreinte SHA-256) ; pièce d'archive, non modifiable."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    controle = models.ForeignKey(ControleQualite, on_delete=models.PROTECT, related_name="images")
    fichier = models.FileField(upload_to="qualite/cnd/%Y/%m/")
    legende = models.CharField(max_length=200, blank=True)
    sha256 = models.CharField(max_length=64, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class EpreuvePression(models.Model):
    """Épreuve hydraulique / d'étanchéité : relevés P/T dans le temps, conclusion calculée puis scellée."""

    class Type(models.TextChoices):
        HYDRAULIQUE = "hydraulique", "Épreuve hydraulique"
        ETANCHEITE = "etancheite", "Test d'étanchéité (leak test)"

    class Statut(models.TextChoices):
        EN_COURS = "en_cours", "En cours"
        CONCLUE = "conclue", "Conclue"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    ordre = models.ForeignKey(
        "operations.OrdreFabrication", on_delete=models.PROTECT, related_name="epreuves", verbose_name="OF"
    )
    joint = models.ForeignKey(JointSoude, null=True, blank=True, on_delete=models.PROTECT, related_name="epreuves")
    instrument = models.ForeignKey(
        InstrumentMesure, null=True, blank=True, on_delete=models.PROTECT, related_name="epreuves"
    )
    type_epreuve = models.CharField(max_length=12, choices=Type.choices, default=Type.HYDRAULIQUE)
    pression_essai = models.DecimalField(max_digits=9, decimal_places=2, verbose_name="Pression d'essai (bar)")
    duree_minutes = models.PositiveIntegerField(verbose_name="Durée de maintien (min)")
    chute_max = models.DecimalField(max_digits=9, decimal_places=2, verbose_name="Chute de pression admissible (bar)")
    releves = models.JSONField(default=list, blank=True, verbose_name="Relevés (minute, pression, température)")
    statut = models.CharField(max_length=8, choices=Statut.choices, default=Statut.EN_COURS)
    resultat = models.CharField(max_length=14, choices=ControleQualite.Resultat.choices, blank=True)
    conclu_par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    conclu_le = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Épreuve de pression"
        verbose_name_plural = "Épreuves de pression"

    def __str__(self):
        return f"{self.code} — {self.get_type_epreuve_display()}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = QualiteSequence.next_for("EPR", "EPR-")
        return super().save(*args, **kwargs)


class DiffusionWps(models.Model):
    """Diffusion d'un WPS validé vers un OF (atelier / chantier M3) : seuls les WPS diffusés s'utilisent sur l'OF."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wps = models.ForeignKey(WpsWpqr, on_delete=models.PROTECT, related_name="diffusions")
    ordre = models.ForeignKey("operations.OrdreFabrication", on_delete=models.PROTECT, related_name="wps_diffuses")
    diffuse_par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    diffuse_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-diffuse_le"]
        verbose_name = "Diffusion de WPS"
        verbose_name_plural = "Diffusions de WPS"
        constraints = [models.UniqueConstraint(fields=["wps", "ordre"], name="uniq_diffusion_wps_of")]


class PunchItem(models.Model):
    """Réserve de la punch list (fin de travaux) : catégorie A = bloque la libération de l'OF, B / C = à lever."""

    class Categorie(models.TextChoices):
        A = "A", "A — bloquante (avant libération)"
        B = "B", "B — avant réception client"
        C = "C", "C — mineure"

    class Statut(models.TextChoices):
        OUVERTE = "ouverte", "Ouverte"
        LEVEE = "levee", "Levée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    ordre = models.ForeignKey(
        "operations.OrdreFabrication", on_delete=models.PROTECT, related_name="punch_items", verbose_name="OF"
    )
    itp = models.ForeignKey(
        ControleQualite, null=True, blank=True, on_delete=models.PROTECT, related_name="punch_items", verbose_name="ITP"
    )
    repere = models.CharField(max_length=80, blank=True, verbose_name="Repère (spool, ligne, joint)")
    description = models.CharField(max_length=250, verbose_name="Réserve")
    categorie = models.CharField(max_length=1, choices=Categorie.choices, default=Categorie.B)
    responsable = models.CharField(max_length=120, blank=True, verbose_name="Responsable de la levée")
    echeance = models.DateField(null=True, blank=True, verbose_name="Échéance")
    statut = models.CharField(max_length=8, choices=Statut.choices, default=Statut.OUVERTE)
    leve_par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    leve_le = models.DateTimeField(null=True, blank=True)
    commentaire = models.CharField(max_length=250, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["statut", "categorie", "echeance"]
        verbose_name = "Réserve (punch list)"
        verbose_name_plural = "Punch list"

    def __str__(self):
        return f"{self.code} — {self.description}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = QualiteSequence.next_for("PCH", "PCH-")
        return super().save(*args, **kwargs)

    @property
    def en_retard(self):
        return bool(self.echeance and self.statut == self.Statut.OUVERTE and self.echeance < timezone.localdate())


class ParametreQualite(models.Model):
    """Paramètres M6 modifiables par ETSL (délai CAPA, escalade, alertes) : provisoires tant qu'ETSL ne les confirme pas."""

    class StatutValeur(models.TextChoices):
        PROVISOIRE = "provisoire", "Provisoire"
        CONFIRME = "confirme", "Confirmé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=40, unique=True, verbose_name="Identifiant")
    label = models.CharField(max_length=200, verbose_name="Libellé")
    valeur = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Valeur")
    unite = models.CharField(max_length=20, blank=True, verbose_name="Unité")
    statut_valeur = models.CharField(max_length=10, choices=StatutValeur.choices, default=StatutValeur.PROVISOIRE)
    confirme_par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    confirme_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "Paramètre qualité"
        verbose_name_plural = "Paramètres qualité"

    def __str__(self):
        return f"{self.code} = {self.valeur} {self.unite}"

    @property
    def est_provisoire(self):
        return self.statut_valeur != self.StatutValeur.CONFIRME


class CritereControle(models.Model):
    """Critère d'acceptation paramétrable par type de contrôle (peinture, génie civil, électricité, essais) :
    unité et seuils mini / maxi. Valeurs livrées provisoires, à confirmer par ETSL (fiches de contrôle)."""

    class StatutValeur(models.TextChoices):
        PROVISOIRE = "provisoire", "Provisoire"
        CONFIRME = "confirme", "Confirmé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type_controle = models.CharField(max_length=14, choices=ControleQualite.TypeControle.choices)
    code = models.CharField(max_length=30, verbose_name="Identifiant")
    libelle = models.CharField(max_length=150, verbose_name="Critère")
    unite = models.CharField(max_length=20, blank=True)
    mini = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True, verbose_name="Minimum")
    maxi = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True, verbose_name="Maximum")
    norme = models.CharField(max_length=80, blank=True, verbose_name="Norme / méthode")
    actif = models.BooleanField(default=True)
    statut_valeur = models.CharField(max_length=10, choices=StatutValeur.choices, default=StatutValeur.PROVISOIRE)
    confirme_par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    confirme_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["type_controle", "code"]
        verbose_name = "Critère de contrôle"
        verbose_name_plural = "Critères de contrôle"
        constraints = [models.UniqueConstraint(fields=["type_controle", "code"], name="uniq_critere_type_code")]

    def __str__(self):
        return f"{self.get_type_controle_display()} — {self.libelle}"

    def clean(self):
        if self.mini is None and self.maxi is None:
            raise ValidationError({"mini": "Renseigner un minimum et/ou un maximum."})
        if self.mini is not None and self.maxi is not None and self.mini > self.maxi:
            raise ValidationError({"maxi": "Le maximum doit être supérieur au minimum."})

    @property
    def est_provisoire(self):
        return self.statut_valeur != self.StatutValeur.CONFIRME

    def accepte(self, valeur):
        return (self.mini is None or valeur >= self.mini) and (self.maxi is None or valeur <= self.maxi)


class MesureControle(models.Model):
    """Mesure structurée d'un contrôle ; le résultat est calculé contre les seuils figés au moment de la saisie."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    controle = models.ForeignKey(ControleQualite, on_delete=models.CASCADE, related_name="mesures")
    critere = models.ForeignKey(CritereControle, on_delete=models.PROTECT, related_name="mesures")
    valeur = models.DecimalField(max_digits=12, decimal_places=3)
    mini = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    maxi = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    conforme = models.BooleanField()
    repere = models.CharField(max_length=80, blank=True, verbose_name="Repère / point de mesure")
    saisi_par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    saisi_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["controle", "saisi_le"]
        verbose_name = "Mesure de contrôle"
        verbose_name_plural = "Mesures de contrôle"
