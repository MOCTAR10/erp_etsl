"""Module M9 — RH & Paie (moteur de paie natif CNSSG / CNAMGS, RF-ERP-80…83).

Procédures MANUEL ch.7 : 7.3 recrutement & intégration · 7.4 contrats de travail ·
7.5 formation & développement des compétences · 7.6 congés & rotations · 7.7
discipline & sanctions · 7.8 administration du personnel · 7.9 archivage et
traçabilité RH. Pointages M3 (RF-ERP-21) remontés en saisie temps (RF-ERP-81).
Bulletins de paie CNSSG / CNAMGS, barèmes versionnés par date d'effet (RF-ERP-82).
"""

import uuid
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from config.fields import EncryptedCharField


class RhPaieSequence(models.Model):
    """Numérotation séquentielle par type (EMP, CTR, REC, FOR, CON, SAN, BUL...)."""

    kind = models.CharField(max_length=10, unique=True, verbose_name="Type")
    prefix = models.CharField(max_length=10, verbose_name="Préfixe")
    padding = models.PositiveSmallIntegerField(default=5, verbose_name="Zéro-padding")
    next_number = models.PositiveIntegerField(default=1, verbose_name="Prochain numéro")

    class Meta:
        verbose_name = "Séquence RH & Paie"
        verbose_name_plural = "Séquences RH & Paie"

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


class Employe(models.Model):
    """Dossier salarié — administration du personnel (RF-ERP-80, proc. 7.3/7.8)."""

    class Sexe(models.TextChoices):
        MASCULIN = "masculin", "Masculin"
        FEMININ = "feminin", "Féminin"

    class Statut(models.TextChoices):
        ACTIF = "actif", "En poste"
        CONGE = "conge", "En congé / rotation"
        SUSPENDU = "suspendu", "Suspendu"
        SORTI = "sorti", "Sorti"

    class Categorie(models.TextChoices):
        CADRE = "cadre", "Cadre"
        AGENT_MAITRISE = "agent_maitrise", "Agent de maîtrise"
        TECHNICIEN = "technicien", "Technicien"
        OUVRIER = "ouvrier", "Ouvrier / chantier"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Matricule")
    civilite = models.CharField(max_length=14, choices=Sexe.choices, verbose_name="Civilité")
    nom = models.CharField(max_length=150, verbose_name="Nom")
    prenom = models.CharField(max_length=150, blank=True, verbose_name="Prénom")
    date_naissance = models.DateField(null=True, blank=True, verbose_name="Date de naissance")
    lieu_naissance = models.CharField(max_length=120, blank=True, verbose_name="Lieu de naissance")
    nationalite = models.CharField(max_length=80, blank=True, verbose_name="Nationalité")
    numero_securite_sociale = EncryptedCharField(blank=True, verbose_name="N° sécurité sociale (CNSS)")
    telephone = models.CharField(max_length=40, blank=True, verbose_name="Téléphone")
    email = models.EmailField(blank=True, verbose_name="Email personnel")
    adresse = models.CharField(max_length=200, blank=True, verbose_name="Adresse")
    categorie = models.CharField(
        max_length=20, choices=Categorie.choices, default=Categorie.OUVRIER,
        verbose_name="Catégorie",
    )
    fonction = models.CharField(max_length=150, blank=True, verbose_name="Fonction")
    departement = models.CharField(max_length=120, blank=True, verbose_name="Département")
    site = models.CharField(max_length=120, blank=True, verbose_name="Site / affectation")
    statut = models.CharField(
        max_length=10, choices=Statut.choices, default=Statut.ACTIF, verbose_name="Statut"
    )
    matricule_cnps = EncryptedCharField(blank=True, verbose_name="Matricule CNAMGS")
    date_embauche = models.DateField(null=True, blank=True, verbose_name="Date d'embauche")
    date_sortie = models.DateField(null=True, blank=True, verbose_name="Date de sortie")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


    # Coordonnées bancaires (RIB 5/5/11/2) pour le virement des salaires — données sensibles : cercle paie seul.
    rib_banque = EncryptedCharField(blank=True, verbose_name="RIB — code banque")
    rib_guichet = EncryptedCharField(blank=True, verbose_name="RIB — code guichet")
    rib_compte = EncryptedCharField(blank=True, verbose_name="RIB — numéro de compte")
    rib_cle = EncryptedCharField(blank=True, verbose_name="RIB — clé")
    banque_nom = models.CharField(max_length=24, blank=True, verbose_name="Domiciliation bancaire")
    parts_fiscales = models.DecimalField(
        max_digits=4, decimal_places=2, default=1, verbose_name="Parts fiscales (quotient familial)",
        help_text="Nombre de parts pour le calcul de l'impôt sur le revenu (1 = célibataire sans charge).",
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="fiche_employe", verbose_name="Compte utilisateur",
        help_text="Lie le salarié à son compte : active son espace libre-service (bulletins, congés).",
    )
    class Meta:
        ordering = ["nom", "prenom"]
        verbose_name = "Employé (dossier RH)"
        verbose_name_plural = "Employés — dossiers RH"
        indexes = [models.Index(fields=["statut", "departement"])]

    def __str__(self):
        return f"{self.code} — {self.prenom} {self.nom}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = RhPaieSequence.next_for("EMP", "EMP")
        return super().save(*args, **kwargs)

    @property
    def nom_complet(self):
        return f"{self.prenom} {self.nom}".strip()

    @property
    def rib_complet(self):
        return bool(self.rib_banque and self.rib_guichet and self.rib_compte and self.rib_cle)

    @property
    def contrat_actif(self):
        # via `.all()` : exploite le prefetch_related("contrats") de la vue (pas de requête par salarié)
        return next((c for c in self.contrats.all() if c.statut == ContratTravail.Statut.ACTIF), None)

    @property
    def solde_conges(self):
        """Jours de congé annuel restants de l'année en cours (8.9 registres).

        Acquis (30 j/an, tolérance CNSS) - congés ANNUELS approuvés/validés dont le début
        tombe dans l'année. Maladie, maternité, sans solde, exceptionnel et rotation
        n'entament pas le solde de congé annuel.
        """
        acquis = DemandesConge.DUREE_CONGE_CNSS
        pris = float(
            DemandesConge.objects.filter(
                employe=self,
                type=DemandesConge.Type.ANNUEL,
                date_debut__year=timezone.localdate().year,
                statut__in=[
                    DemandesConge.Statut.APPROUVE,
                    DemandesConge.Statut.VALIDE_RH,
                ],
            ).aggregate(t=models.Sum("nb_jours"))["t"] or 0
        )
        return round(acquis - pris, 1)


class ContratTravail(models.Model):
    """Contrat de travail — CDD/CDI/chantier (RF-ERP-80, proc. 7.4)."""

    class Type(models.TextChoices):
        CDD = "cdd", "CDD"
        CDI = "cdi", "CDI"
        CHANTIER = "chantier", "Contrat de chantier"
        MISSION = "mission", "Mission / intérim"
        STAGE = "stage", "Stage / apprentissage"
        EXPATRIE = "expatrie", "Expatrié"

    class Statut(models.TextChoices):
        ACTIF = "actif", "Actif"
        EN_PERIODE_ESSAI = "essai", "Période d'essai"
        EXPIRE = "expire", "Expiré"
        RESILIE = "resilie", "Résilié"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    employe = models.ForeignKey(
        Employe,
        on_delete=models.PROTECT,
        related_name="contrats",
        verbose_name="Employé",
    )
    type = models.CharField(max_length=12, choices=Type.choices, default=Type.CDD, verbose_name="Type")
    date_debut = models.DateField(verbose_name="Date de début")
    date_fin = models.DateField(null=True, blank=True, verbose_name="Date de fin (CDD)")
    salaire_base = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Salaire de base (FCFA)"
    )
    regime_horaire = models.CharField(
        max_length=40, blank=True, verbose_name="Régime horaire"
    )
    lieu_affectation = models.CharField(max_length=120, blank=True, verbose_name="Lieu d'affectation")
    grille = models.ForeignKey(
        "GrilleSalaire", null=True, blank=True, on_delete=models.PROTECT, related_name="contrats",
        verbose_name="Position dans la grille de salaires",
        help_text="Si renseignée, le salaire de base du bulletin est celui de la grille en vigueur à la période.",
    )
    statut = models.CharField(
        max_length=8, choices=Statut.choices, default=Statut.ACTIF, verbose_name="Statut"
    )
    notes = models.TextField(blank=True, verbose_name="Notes / avenants")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_debut"]
        verbose_name = "Contrat de travail"
        verbose_name_plural = "Contrats de travail"
        indexes = [models.Index(fields=["type", "statut"])]

    def __str__(self):
        return f"{self.code} — {self.employe.nom_complet} ({self.get_type_display()})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = RhPaieSequence.next_for("CTR", "CTR")
        return super().save(*args, **kwargs)

    def clean(self):
        if self.date_fin and self.date_fin < self.date_debut:
            raise ValidationError(
                {"date_fin": "La date de fin doit être postérieure à la date de début."}
            )

    @property
    def expire_dans(self):
        if not self.date_fin:
            return None
        return (self.date_fin - timezone.localdate()).days

    @property
    def a_renouveler(self):
        days = self.expire_dans
        return days is not None and days <= 90


class Qualification(models.Model):
    """Habilitation / certification du salarié (RF-ERP-80, proc. 7.5)."""

    class Type(models.TextChoices):
        HABILITATION = "habilitation", "Habilitation"
        PERMIS = "permis", "Permis / carte professionnelle"
        CERTIFICAT = "certificat", "Certificat / attestation"
        DIPLOME = "diplome", "Diplôme"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    employe = models.ForeignKey(
        Employe,
        on_delete=models.PROTECT,
        related_name="qualifications",
        verbose_name="Employé",
    )
    type = models.CharField(max_length=14, choices=Type.choices, default=Type.HABILITATION, verbose_name="Type")
    intitule = models.CharField(max_length=180, verbose_name="Intitulé")
    organisme = models.CharField(max_length=120, blank=True, verbose_name="Organisme délivrant")
    date_obtention = models.DateField(null=True, blank=True, verbose_name="Date d'obtention")
    date_validite = models.DateField(null=True, blank=True, verbose_name="Date de validité")
    notes = models.TextField(blank=True, verbose_name="Notes")

    class Source(models.TextChoices):
        RH = "rh", "Saisie RH"
        M6 = "m6", "Qualification soudeur (M6)"
        FORMATION = "formation", "Délivrée par une formation"

    source = models.CharField(max_length=10, choices=Source.choices, default=Source.RH, verbose_name="Origine")
    source_ref = models.CharField(
        max_length=80, blank=True, verbose_name="Référence d'origine",
        help_text="Qualification soudeur M6 ou formation + salarié : clé de synchronisation.",
    )
    formation = models.ForeignKey(
        "Formation", null=True, blank=True, on_delete=models.SET_NULL, related_name="qualifications_delivrees",
        verbose_name="Formation d'origine",
    )

    class Meta:
        ordering = ["-date_validite"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "source_ref"], condition=~models.Q(source_ref=""), name="uniq_qualif_source_ref"
            )
        ]
        verbose_name = "Qualification / habilitation"
        verbose_name_plural = "Qualifications & habilitations"

    def __str__(self):
        return f"{self.code} — {self.intitule} ({self.employe.nom_complet})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = RhPaieSequence.next_for("SQH", "SQH")
        return super().save(*args, **kwargs)

    @property
    def expiree(self):
        return bool(self.date_validite and self.date_validite < timezone.localdate())

    @property
    def a_renouveler(self):
        if not self.date_validite or self.expiree:
            return False
        return (self.date_validite - timezone.localdate()).days <= 90


class DemandeRecrutement(models.Model):
    """Recrutement & intégration (RF-ERP-83, proc. 7.3)."""

    class Type(models.TextChoices):
        CREATION = "creation", "Création de poste"
        REMPLACEMENT = "remplacement", "Remplacement"
        RENFORT = "renfort", "Renfort temporaire"
        CHANTIER = "chantier", "Besoin chantier"

    class Statut(models.TextChoices):
        DEMANDE = "demande", "Demandé"
        VALIDEE = "validee", "Besoin validé"
        CANDIDATS = "candidats", "Sélection candidats"
        ENTREVUE = "entrevue", "Entretiens"
        INTEGRE = "integre", "Candidat intégré"
        ANNULEE = "annulee", "Annulée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    poste = models.CharField(max_length=150, verbose_name="Poste à pourvoir")
    type = models.CharField(max_length=12, choices=Type.choices, default=Type.CREATION, verbose_name="Type de besoin")
    justification = models.TextField(verbose_name="Justification du besoin")
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="rh_recrutements",
        verbose_name="Responsable",
    )
    date_souhaitee = models.DateField(null=True, blank=True, verbose_name="Prise de poste souhaitée")
    statut = models.CharField(
        max_length=10, choices=Statut.choices, default=Statut.DEMANDE, verbose_name="Statut"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Demande de recrutement"
        verbose_name_plural = "Demandes de recrutement"

    def __str__(self):
        return f"{self.code} — {self.poste} ({self.get_statut_display()})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = RhPaieSequence.next_for("REC", "REC")
        return super().save(*args, **kwargs)

    def avancer(self, statut_int):
        if self.statut == self.Statut.DEMANDE and statut_int == self.Statut.VALIDEE:
            self.statut = statut_int
        elif self.statut in (self.Statut.VALIDEE, self.Statut.CANDIDATS) and statut_int == self.Statut.CANDIDATS:
            self.statut = self.Statut.CANDIDATS
        elif self.statut in (self.Statut.CANDIDATS, self.Statut.ENTREVUE) and statut_int == self.Statut.ENTREVUE:
            self.statut = self.Statut.ENTREVUE
        elif self.statut in (self.Statut.ENTREVUE, self.Statut.VALIDEE) and statut_int == self.Statut.INTEGRE:
            self.statut = self.Statut.INTEGRE
        else:
            self.statut = statut_int
        self.save(update_fields=["statut", "updated_at"])


class Formation(models.Model):
    """Formation & développement des compétences (RF-ERP-83, proc. 7.5)."""

    class Type(models.TextChoices):
        PLANIFIE = "planifie", "Prévue"
        REALISEE = "realisee", "Réalisée"
        ANNULEE = "annulee", "Annulée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    theme = models.CharField(max_length=180, verbose_name="Thème")
    organisme = models.CharField(max_length=120, blank=True, verbose_name="Organisme")
    formateur = models.CharField(max_length=120, blank=True, verbose_name="Formateur")
    date_session = models.DateField(verbose_name="Date de session")
    duree_heures = models.DecimalField(
        max_digits=6, decimal_places=2, default=0, verbose_name="Durée (heures)"
    )
    participants = models.ManyToManyField(
        Employe, blank=True, related_name="formations", verbose_name="Participants"
    )
    type = models.CharField(
        max_length=12, choices=Type.choices, default=Type.PLANIFIE, verbose_name="Statut"
    )
    evaluation = models.CharField(max_length=400, blank=True, verbose_name="Évaluation post-formation")
    catalogue = models.ForeignKey(
        "CatalogueFormation", null=True, blank=True, on_delete=models.PROTECT, related_name="sessions",
        verbose_name="Formation du catalogue",
    )
    plan = models.ForeignKey(
        "PlanFormation", null=True, blank=True, on_delete=models.PROTECT, related_name="formations",
        verbose_name="Plan de formation",
    )
    cout_prevu = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Coût prévu (FCFA)")
    cout_reel = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True, verbose_name="Coût réel (FCFA)"
    )
    gain_estime = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True, verbose_name="Gain estimé (FCFA)",
        help_text="Base du ROI (méthode provisoire) : gains de productivité, non-qualité évitée…",
    )
    note_evaluation = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="Note d'évaluation (/20)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_session"]
        verbose_name = "Formation"
        verbose_name_plural = "Formations & développement des compétences"

    def __str__(self):
        return f"{self.code} — {self.theme} ({self.date_session})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = RhPaieSequence.next_for("FOR", "FOR")
        return super().save(*args, **kwargs)


class DemandesConge(models.Model):
    """Congés & rotations (RF-ERP-83, proc. 7.6)."""

    class Type(models.TextChoices):
        ANNUEL = "annuel", "Congé annuel"
        ROTATION = "rotation", "Rotation / rapatriement"
        MALADIE = "maladie", "Congé maladie"
        MATERNITE = "maternite", "Congé maternité"
        SANS_SOLDE = "sans_solde", "Congé sans solde"
        EXCEPTIONNEL = "exceptionnel", "Congé exceptionnel"

    class Statut(models.TextChoices):
        DEMANDE = "demande", "Demandé"
        APPROUVE = "approuve", "Approuvé hiérarchie"
        VALIDE_RH = "valide", "Validé RH"
        REFUSE = "refuse", "Refusé"
        ANNULE = "annule", "Annulé"

    DUREE_CONGE_CNSS = 30  # jours ouvrés / an (tolérance CNSS GABON)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    employe = models.ForeignKey(
        Employe, on_delete=models.PROTECT, related_name="demandes_conges", verbose_name="Employé"
    )
    type = models.CharField(max_length=14, choices=Type.choices, default=Type.ANNUEL, verbose_name="Type")
    date_debut = models.DateField(verbose_name="Date de début")
    date_fin = models.DateField(verbose_name="Date de fin")
    nb_jours = models.PositiveIntegerField(verbose_name="Nombre de jours")
    motif = models.CharField(max_length=200, blank=True, verbose_name="Motif / commentaire")
    statut = models.CharField(
        max_length=10, choices=Statut.choices, default=Statut.DEMANDE, verbose_name="Statut"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Demande de congé"
        verbose_name_plural = "Congés & rotations"
        indexes = [models.Index(fields=["statut", "date_debut"])]

    def __str__(self):
        return f"{self.code} — {self.employe.nom_complet} ({self.get_type_display()})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = RhPaieSequence.next_for("CON", "CON")
        return super().save(*args, **kwargs)

    def clean(self):
        if not (self.date_debut and self.date_fin):
            return
        if self.date_fin < self.date_debut:
            raise ValidationError(
                {"date_fin": "La date de fin doit être postérieure à la date de début."}
            )
        duree = (self.date_fin - self.date_debut).days + 1
        if not self.nb_jours or self.nb_jours < 1 or self.nb_jours > duree:
            raise ValidationError(
                {"nb_jours": f"Le nombre de jours doit être compris entre 1 et {duree} (durée de la période)."}
            )
        if self.employe_id:
            chevauche = DemandesConge.objects.filter(
                employe_id=self.employe_id,
                statut__in=[self.Statut.DEMANDE, self.Statut.APPROUVE, self.Statut.VALIDE_RH],
                date_debut__lte=self.date_fin,
                date_fin__gte=self.date_debut,
            ).exclude(pk=self.pk)
            if chevauche.exists():
                raise ValidationError(
                    {"date_debut": "Cette période chevauche un autre congé de l'employé."}
                )


class Sanction(models.Model):
    """Discipline & sanctions (RF-ERP-83, proc. 7.7)."""

    class Type(models.TextChoices):
        RAPPEL_ORDRE = "rappel", "Rappel à l'ordre"
        AVERTISSEMENT = "avertissement", "Avertissement"
        MISE_A_PIED = "mise_a_pied", "Mise à pied"
        SUSPENSION = "suspension", "Suspension"
        LICENCIEMENT = "licenciement", "Licenciement"
        AUTRE = "autre", "Autre mesure"

    class Statut(models.TextChoices):
        CONSTATE = "constate", "Constaté"
        INSTRUITE = "instruite", "En instruction"
        DECIDEE = "decidee", "Décision prise"
        ARCHIVEE = "archivee", "Archivée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    employe = models.ForeignKey(
        Employe, on_delete=models.PROTECT, related_name="sanctions", verbose_name="Employé"
    )
    type = models.CharField(max_length=16, choices=Type.choices, default=Type.AVERTISSEMENT, verbose_name="Type de sanction")
    faits = models.TextField(verbose_name="Faits reprochés")
    rapport = models.TextField(blank=True, verbose_name="Rapport disciplinaire")
    date_constat = models.DateField(verbose_name="Date de constat")
    date_decision = models.DateField(null=True, blank=True, verbose_name="Date de décision")
    statut = models.CharField(
        max_length=10, choices=Statut.choices, default=Statut.CONSTATE, verbose_name="Statut"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_constat"]
        verbose_name = "Sanction disciplinaire"
        verbose_name_plural = "Discipline & sanctions"
        indexes = [models.Index(fields=["type", "statut"])]

    def __str__(self):
        return f"{self.code} — {self.employe.nom_complet} ({self.get_type_display()})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = RhPaieSequence.next_for("SAN", "SAN")
        return super().save(*args, **kwargs)


class SaisieTemps(models.Model):
    """Saisie temps / pointage (RF-ERP-81) — source M3 (RF-ERP-21) ou RH directe."""

    class Type(models.TextChoices):
        NORMAL = "normal", "Heures normales"
        SUPPLEMENTAIRE = "supplementaire", "Heures supplémentaires"
        NUIT = "nuit", "Heures de nuit"
        ASTREINTE = "astreinte", "Astreinte"

    class Statut(models.TextChoices):
        SAISI = "saisi", "Saisi"
        TRANSFERE_PAIE = "transfere", "Transféré en paie"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    employe = models.ForeignKey(
        Employe, on_delete=models.PROTECT, related_name="saisies_temps", verbose_name="Employé"
    )
    date = models.DateField(verbose_name="Date")
    heures = models.DecimalField(
        max_digits=8, decimal_places=2, default=0, verbose_name="Heures"
    )
    type = models.CharField(max_length=14, choices=Type.choices, default=Type.NORMAL, verbose_name="Type")
    source = models.CharField(max_length=20, default="saisie", verbose_name="Source")
    cout_charge = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True, verbose_name="Coût chargé (FCFA)",
        help_text="Heures × coût horaire chargé du salarié, posé au transfert du pointage M3 (aval M3 / M11).",
    )
    statut = models.CharField(
        max_length=10, choices=Statut.choices, default=Statut.SAISI, verbose_name="Statut"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date"]
        verbose_name = "Saisie temps / pointage"
        verbose_name_plural = "Pointages & saisie temps"
        indexes = [models.Index(fields=["date", "statut"])]

    def __str__(self):
        return f"{self.code} — {self.employe.nom_complet} — {self.date}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = RhPaieSequence.next_for("TMP", "TMP")
        return super().save(*args, **kwargs)

    def clean(self):
        if self.heures <= 0:
            raise ValidationError({"heures": "Le nombre d'heures doit être strictement positif."})


class RubriquePaie(models.Model):
    """Rubrique de bulletin de paie (RF-ERP-82) — éléments du bulletin."""

    class Nature(models.TextChoices):
        GAIN = "gain", "Gain (rémunération)"
        RETENUE = "retenue", "Retenue / cotisation"

    class Base(models.TextChoices):
        FIXE = "fixe", "Montant fixe"
        SALAIRE = "salaire", "% du salaire de base"
        BRUT = "brut", "% du brut"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    label = models.CharField(max_length=150, verbose_name="Libellé")
    nature = models.CharField(
        max_length=10, choices=Nature.choices, default=Nature.GAIN, verbose_name="Nature"
    )
    base = models.CharField(max_length=10, choices=Base.choices, default=Base.FIXE, verbose_name="Base de calcul")
    taux = models.DecimalField(
        max_digits=6, decimal_places=3, null=True, blank=True,
        verbose_name="Taux (%) si base %",
    )
    ordre = models.PositiveSmallIntegerField(default=0, verbose_name="Ordre d'affichage")

    class Meta:
        ordering = ["nature", "ordre", "code"]
        verbose_name = "Rubrique de paie"
        verbose_name_plural = "Rubriques de paie"

    def __str__(self):
        return f"{self.code} — {self.label}"


class ValeurLegale(models.Model):
    """Traçabilité d'une valeur légale paramétrable (taux, plafond, tranches…).

    Tant que `statut_valeur` = « provisoire », bulletins et déclarations qui l'utilisent portent un
    avertissement. « Confirmé » = validé par ETSL / le cabinet de paie (posé côté serveur par `confirmer`).
    """

    class StatutValeur(models.TextChoices):
        PROVISOIRE = "provisoire", "Provisoire"
        CONFIRME = "confirme", "Confirmé"

    statut_valeur = models.CharField(
        max_length=10, choices=StatutValeur.choices, default=StatutValeur.PROVISOIRE,
        verbose_name="Statut de la valeur",
    )
    source = models.CharField(max_length=300, blank=True, verbose_name="Source (URL / organisme)")
    reference_texte = models.CharField(
        max_length=200, blank=True, verbose_name="Référence du texte (loi, décret, communiqué)"
    )
    confirme_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", verbose_name="Confirmé par",
    )
    confirme_le = models.DateTimeField(null=True, blank=True, verbose_name="Confirmé le")

    class Meta:
        abstract = True

    @property
    def est_provisoire(self):
        return self.statut_valeur != self.StatutValeur.CONFIRME


class ParametrePaie(ValeurLegale):
    """Paramètre de paie versionné par date d'effet (SMIG, durée légale, majorations d'heures sup., taxes
    patronales…). Valeur = DONNÉE, jamais codée en dur."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=40, verbose_name="Code")
    label = models.CharField(max_length=150, verbose_name="Libellé")
    valeur = models.DecimalField(max_digits=14, decimal_places=3, verbose_name="Valeur")
    unite = models.CharField(max_length=20, blank=True, verbose_name="Unité (%, FCFA, h…)")
    date_effet = models.DateField(verbose_name="Date d'effet")
    date_fin = models.DateField(null=True, blank=True, verbose_name="Date de fin")

    class Meta:
        ordering = ["code", "-date_effet"]
        verbose_name = "Paramètre de paie"
        verbose_name_plural = "Paramètres de paie"
        constraints = [models.UniqueConstraint(fields=["code", "date_effet"], name="uniq_param_paie_effet")]

    def __str__(self):
        return f"{self.code} = {self.valeur} {self.unite} dès {self.date_effet}"

    def clean(self):
        if self.date_fin and self.date_fin < self.date_effet:
            raise ValidationError({"date_fin": "La date de fin précède la date d'effet."})


class HistoriqueBareme(models.Model):
    """Journal INALTÉRABLE des changements de barèmes / paramètres (création, modification, confirmation)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    objet = models.CharField(max_length=20, verbose_name="Type (cotisation, impot, parametre)")
    objet_id = models.UUIDField(verbose_name="Identifiant de l'objet")
    code = models.CharField(max_length=40, verbose_name="Code")
    action = models.CharField(max_length=20, verbose_name="Action")
    avant = models.JSONField(null=True, blank=True)
    apres = models.JSONField(null=True, blank=True)
    par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+", verbose_name="Par"
    )
    le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-le"]
        verbose_name = "Historique de barème"
        verbose_name_plural = "Historique des barèmes"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("L'historique des barèmes est inaltérable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("L'historique des barèmes est inaltérable.")


class BaremeCotisation(ValeurLegale):
    """Barème de cotisation sociale, **versionné par date d'effet** (RF-ERP-82).

    Les taux sont des DONNÉES paramétrables, jamais codées en dur : à renseigner et valider avec
    ETSL / la CNSSG / la CNAMGS. Une cotisation s'applique à la base (brut ou salaire de base),
    éventuellement plafonnée (base mensuelle maximale).
    """

    class Nature(models.TextChoices):
        SALARIALE = "salariale", "Retenue salariale"
        PATRONALE = "patronale", "Charge patronale"

    class Base(models.TextChoices):
        BRUT = "brut", "Brut"
        SALAIRE = "salaire", "Salaire de base"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, verbose_name="Code")
    label = models.CharField(max_length=150, verbose_name="Libellé")
    organisme = models.CharField(max_length=60, blank=True, verbose_name="Organisme (CNSSG, CNAMGS…)")
    nature = models.CharField(max_length=10, choices=Nature.choices, verbose_name="Nature")
    base = models.CharField(max_length=10, choices=Base.choices, default=Base.BRUT, verbose_name="Base")
    taux = models.DecimalField(max_digits=6, decimal_places=3, verbose_name="Taux (%)")
    plafond = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        verbose_name="Plafond mensuel de la base (FCFA)",
    )
    date_effet = models.DateField(verbose_name="Date d'effet")
    date_fin = models.DateField(null=True, blank=True, verbose_name="Date de fin")
    ordre = models.PositiveSmallIntegerField(default=0, verbose_name="Ordre")
    exclure_expatries = models.BooleanField(
        default=False, verbose_name="Non applicable aux contrats expatriés",
        help_text="Cotisation non retenue sur le bulletin d'un salarié sous contrat « expatrié ».",
    )

    class Meta:
        ordering = ["nature", "ordre", "code", "-date_effet"]
        verbose_name = "Barème de cotisation"
        verbose_name_plural = "Barèmes de cotisation"
        constraints = [
            models.UniqueConstraint(fields=["code", "date_effet"], name="uniq_bareme_code_effet"),
            models.CheckConstraint(check=models.Q(taux__gte=0), name="bareme_taux_positif"),
        ]

    def __str__(self):
        return f"{self.code} {self.taux} % ({self.get_nature_display()}) dès {self.date_effet}"

    def clean(self):
        if self.date_fin and self.date_fin < self.date_effet:
            raise ValidationError({"date_fin": "La date de fin précède la date d'effet."})


class BaremeImpot(ValeurLegale):
    """Barème PROGRESSIF de l'impôt sur le revenu (IRPP), versionné par date d'effet.

    `tranches` = liste ordonnée `[{"plafond": 500000, "taux": 0}, {"plafond": 1000000, "taux": 10},
    {"plafond": null, "taux": 20}]` : montants MENSUELS par part, dernière tranche sans plafond. Valeurs = DONNÉES
    à saisir et valider avec ETSL / l'administration fiscale (aucune valeur légale n'est codée en dur).
    Calcul : base = brut - cotisations salariales (si `cotisations_deductibles`) puis abattement ; impôt =
    parts x barème(base / parts) (quotient familial).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, verbose_name="Code")
    label = models.CharField(max_length=150, verbose_name="Libellé")
    tranches = models.JSONField(default=list, verbose_name="Tranches (mensuelles, par part)")
    abattement_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, verbose_name="Abattement (%)"
    )
    cotisations_deductibles = models.BooleanField(default=True, verbose_name="Cotisations salariales déductibles")
    abattement_plafond_annuel = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True, verbose_name="Plafond annuel de l'abattement (FCFA)",
        help_text="Abattement forfaitaire maximal (ex. 833 333 FCFA / an) : l'abattement mensuel est plafonné au 1/12.",
    )
    date_effet = models.DateField(verbose_name="Date d'effet")
    date_fin = models.DateField(null=True, blank=True, verbose_name="Date de fin")

    class Meta:
        ordering = ["-date_effet", "code"]
        verbose_name = "Barème d'impôt"
        verbose_name_plural = "Barèmes d'impôt"
        constraints = [models.UniqueConstraint(fields=["code", "date_effet"], name="uniq_bareme_impot_effet")]

    def __str__(self):
        return f"{self.code} dès {self.date_effet}"

    def clean(self):
        t = self.tranches
        if not isinstance(t, list) or not t:
            raise ValidationError({"tranches": "Au moins une tranche est requise."})
        previous = None
        for i, tr in enumerate(t):
            if not isinstance(tr, dict) or "taux" not in tr or "plafond" not in tr:
                raise ValidationError({"tranches": f"Tranche {i + 1} : « plafond » et « taux » requis."})
            if not (0 <= float(tr["taux"]) <= 100):
                raise ValidationError({"tranches": f"Tranche {i + 1} : taux hors de [0, 100]."})
            last = i == len(t) - 1
            if last and tr["plafond"] is not None:
                raise ValidationError({"tranches": "La dernière tranche doit être sans plafond (null)."})
            if not last:
                if tr["plafond"] is None or float(tr["plafond"]) <= 0:
                    raise ValidationError({"tranches": f"Tranche {i + 1} : plafond positif requis."})
                if previous is not None and float(tr["plafond"]) <= previous:
                    raise ValidationError({"tranches": "Plafonds strictement croissants requis."})
                previous = float(tr["plafond"])
        if self.date_fin and self.date_fin < self.date_effet:
            raise ValidationError({"date_fin": "La date de fin précède la date d'effet."})

    def impot_par_part(self, base):
        """Impôt (progressif) sur `base` pour UNE part."""
        impot, bas = Decimal("0"), Decimal("0")
        for tr in self.tranches:
            haut = None if tr["plafond"] is None else Decimal(str(tr["plafond"]))
            if base <= bas:
                break
            tranche = (base if haut is None else min(base, haut)) - bas
            impot += tranche * Decimal(str(tr["taux"])) / 100
            if haut is None:
                break
            bas = haut
        return impot


class BulletinPaie(models.Model):
    """Bulletin de paie mensuel — CNSSG / CNAMGS (RF-ERP-82)."""

    class Statut(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        VALIDE = "valide", "Validé"
        CLOTURE = "cloture", "Clôturé"
        ANNULE = "annule", "Annulé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    employe = models.ForeignKey(
        Employe, on_delete=models.PROTECT, related_name="bulletins", verbose_name="Employé"
    )
    periode = models.DateField(verbose_name="Période (1er du mois)")
    salaire_base = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Salaire de base (FCFA)"
    )
    brut = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Brut (FCFA)")
    net = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Net à payer (FCFA)")
    disponible_le = models.DateTimeField(
        null=True, blank=True, verbose_name="Mis à disposition le",
        help_text="Accusé de dépôt horodaté : le bulletin devient visible dans l'espace du salarié.",
    )
    consulte_le = models.DateTimeField(
        null=True, blank=True, verbose_name="Première consultation le",
        help_text="Horodatage de la première ouverture par le salarié (accusé de consultation).",
    )
    charges_patronales = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Charges patronales (FCFA)",
        help_text="Cotisations à la charge de l'employeur (barèmes « patronale ») — hors net du salarié.",
    )
    baremes_utilises = models.JSONField(
        default=list, blank=True, verbose_name="Barèmes appliqués (instantané)",
        help_text="Version, taux et statut de chaque barème utilisé au dernier calcul : permet de rejouer "
        "un bulletin passé et d'afficher l'avertissement « provisoire ».",
    )
    document = models.ForeignKey(
        "documents.Document", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        verbose_name="PDF archivé (GED)",
        help_text="Bulletin PDF scellé en GED (type « bulletins de paie », conservation ≥ 10 ans).",
    )
    ordre_virement = models.ForeignKey(
        "OrdreVirement", null=True, blank=True, on_delete=models.PROTECT, related_name="bulletins",
        verbose_name="Ordre de virement",
    )
    move = models.ForeignKey(
        "accounting_kernel.AccountMove", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="bulletins_paie", verbose_name="Écriture comptable",
        help_text="Écriture du journal de paie générée par `comptabiliser` (noyau comptable).",
    )
    statut = models.CharField(
        max_length=10, choices=Statut.choices, default=Statut.BROUILLON, verbose_name="Statut"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-periode", "employe__nom"]
        verbose_name = "Bulletin de paie"
        verbose_name_plural = "Bulletins de paie"
        constraints = [
            # Un bulletin annulé ne bloque pas l'émission d'un nouveau bulletin du mois.
            models.UniqueConstraint(
                fields=["employe", "periode"],
                condition=~models.Q(statut="annule"),
                name="uniq_employe_periode",
            )
        ]

    def __str__(self):
        return f"{self.code} — {self.employe.nom_complet} ({self.periode:%m/%Y})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = RhPaieSequence.next_for("BUL", "BUL")
        # "Periode (1er du mois)" : normalise toute date du mois.
        if isinstance(self.periode, date):
            self.periode = self.periode.replace(day=1)
        return super().save(*args, **kwargs)

    @property
    def baremes_provisoires(self):
        return [b["code"] for b in (self.baremes_utilises or []) if b.get("statut") != "confirme"]

    @property
    def total_gains(self):
        return sum(
            (l.montant for l in self.lignes.all() if l.rubrique.nature == RubriquePaie.Nature.GAIN), 0
        )

    @property
    def total_retenues(self):
        return sum(
            (l.montant for l in self.lignes.all() if l.rubrique.nature == RubriquePaie.Nature.RETENUE), 0
        )


class BulletinLigne(models.Model):
    """Ligne de bulletin — gain ou retenue (RF-ERP-82)."""

    bulletin = models.ForeignKey(
        BulletinPaie, on_delete=models.CASCADE, related_name="lignes", verbose_name="Bulletin"
    )
    rubrique = models.ForeignKey(
        RubriquePaie, on_delete=models.PROTECT, verbose_name="Rubrique"
    )
    libelle = models.CharField(max_length=150, verbose_name="Libellé")
    montant = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Montant (FCFA)"
    )

    class Meta:
        ordering = ["rubrique__nature", "rubrique__ordre"]
        verbose_name = "Ligne de bulletin"
        verbose_name_plural = "Lignes de bulletins"
        constraints = [
            models.UniqueConstraint(fields=["bulletin", "rubrique"], name="uniq_bulletin_rubrique")
        ]

    def __str__(self):
        return f"{self.bulletin.code} — {self.libelle} ({self.montant})"

class CompteEmetteur(models.Model):
    """Compte bancaire de l'entreprise qui émet les virements de salaires (CFONB)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    raison_sociale = models.CharField(max_length=24, verbose_name="Raison sociale (24 car. max)")
    numero_emetteur = models.CharField(max_length=6, verbose_name="N° d'émetteur (6 chiffres, fourni par la banque)")
    code_banque = models.CharField(max_length=5, verbose_name="Code banque")
    code_guichet = models.CharField(max_length=5, verbose_name="Code guichet")
    numero_compte = models.CharField(max_length=11, verbose_name="Numéro de compte")
    cle_rib = models.CharField(max_length=2, verbose_name="Clé RIB")
    actif = models.BooleanField(default=True, verbose_name="Actif")

    class Meta:
        ordering = ["raison_sociale"]
        verbose_name = "Compte émetteur de paie"
        verbose_name_plural = "Comptes émetteurs de paie"

    def __str__(self):
        return f"{self.raison_sociale} — {self.code_banque} {self.numero_compte}"

    def clean(self):
        for champ, n in (("numero_emetteur", 6), ("code_banque", 5), ("code_guichet", 5), ("numero_compte", 11), ("cle_rib", 2)):
            v = getattr(self, champ)
            ok = v.isalnum() if champ == "numero_compte" else v.isdigit()
            if not ok or len(v) > n:
                raise ValidationError({champ: f"Chiffres uniquement, {n} au plus."})


class OrdreVirement(models.Model):
    """Fichier de virement des salaires d'un mois (CFONB 160) — scellé après génération."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    periode = models.DateField(verbose_name="Période (1er du mois)")
    compte = models.ForeignKey(CompteEmetteur, on_delete=models.PROTECT, related_name="ordres", verbose_name="Compte émetteur")
    date_execution = models.DateField(verbose_name="Date d'exécution")
    nb_virements = models.PositiveIntegerField(default=0)
    total = models.DecimalField(max_digits=16, decimal_places=2, default=0, verbose_name="Total (FCFA)")
    contenu = models.TextField(verbose_name="Fichier CFONB 160")
    sha256 = models.CharField(max_length=64, verbose_name="Empreinte SHA-256")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+", verbose_name="Généré par"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-periode", "-created_at"]
        verbose_name = "Ordre de virement"
        verbose_name_plural = "Ordres de virement"

    def __str__(self):
        return f"{self.code} — {self.periode:%m/%Y}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Un ordre de virement généré est scellé.")
        if not self.code:
            self.code = RhPaieSequence.next_for("VIR", "VIR")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Un ordre de virement généré est scellé.")


class DeclarationSociale(models.Model):
    """Déclaration sociale / fiscale générée depuis les bulletins (sans ressaisie) — scellée à la génération.

    Les gabarits de colonnes sont des PROPOSITIONS à valider avec les organismes (CNSS, CNAMGS, DGI) : les formats
    officiels de fichier (DADS, état 2460) n'ont pas pu être consultés. Un avertissement est imprimé tant qu'un
    barème utilisé est provisoire.
    """

    class Type(models.TextChoices):
        CNSS = "cnss", "CNSS — cotisations"
        CNAMGS = "cnamgs", "CNAMGS — déclaration trimestrielle des salaires"
        IRPP = "irpp", "IRPP — état des retenues (2460)"
        DADS = "dads", "DADS — déclaration annuelle des salaires"
        FNH = "fnh", "FNH — Fonds national de l'habitat"
        CFP = "cfp", "CFP — contribution à la formation professionnelle"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    type = models.CharField(max_length=10, choices=Type.choices, verbose_name="Type")
    periode_debut = models.DateField(verbose_name="Du (1er du mois)")
    periode_fin = models.DateField(verbose_name="Au (1er du mois)")
    nb_salaries = models.PositiveIntegerField(default=0)
    total_brut = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    total_salarial = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    total_patronal = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    total_impot = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    contenu = models.TextField(verbose_name="Fichier CSV")
    sha256 = models.CharField(max_length=64)
    baremes_provisoires = models.JSONField(default=list, blank=True, verbose_name="Barèmes provisoires utilisés")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+", verbose_name="Généré par"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Déclaration sociale"
        verbose_name_plural = "Déclarations sociales"

    def __str__(self):
        return f"{self.code} — {self.get_type_display()}"

    @property
    def provisoire(self):
        return bool(self.baremes_provisoires)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Une déclaration générée est scellée.")
        if not self.code:
            self.code = RhPaieSequence.next_for("DEC", "DEC")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Une déclaration générée est scellée.")


# --------------------------------------------------------------------------------------------
# Écarts M9-A : grille de salaires, primes récurrentes, carrière, absences, calendrier déclaratif
# --------------------------------------------------------------------------------------------
class GrilleSalaire(ValeurLegale):
    """Grille de salaires conventionnelle (catégorie, classe, échelon), versionnée par date d'effet.

    Valeurs = DONNÉES à fournir par ETSL (convention collective applicable), provisoires tant que non confirmées.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    convention = models.CharField(max_length=120, blank=True, verbose_name="Convention collective")
    categorie = models.CharField(max_length=20, choices=Employe.Categorie.choices, verbose_name="Catégorie")
    classe = models.CharField(max_length=20, blank=True, verbose_name="Classe / niveau")
    echelon = models.PositiveSmallIntegerField(default=1, verbose_name="Échelon")
    salaire_base = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Salaire de base mensuel (FCFA)")
    date_effet = models.DateField(verbose_name="Date d'effet")
    date_fin = models.DateField(null=True, blank=True, verbose_name="Date de fin")

    class Meta:
        ordering = ["categorie", "classe", "echelon", "-date_effet"]
        verbose_name = "Grille de salaires"
        verbose_name_plural = "Grilles de salaires"
        constraints = [
            models.UniqueConstraint(
                fields=["convention", "categorie", "classe", "echelon", "date_effet"], name="uniq_grille_position_effet"
            )
        ]

    def __str__(self):
        return f"{self.code} : {self.salaire_base} FCFA dès {self.date_effet}"

    @property
    def code(self):
        return f"{self.categorie}-{self.classe or '0'}-E{self.echelon}"[:40]

    def clean(self):
        if self.salaire_base is not None and self.salaire_base <= 0:
            raise ValidationError({"salaire_base": "Le salaire de base doit être positif."})
        if self.date_fin and self.date_effet and self.date_fin < self.date_effet:
            raise ValidationError({"date_fin": "La date de fin précède la date d'effet."})


class ElementFixe(models.Model):
    """Prime ou indemnité récurrente d'un contrat (transport, logement, panier…) reprise à chaque bulletin préparé."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contrat = models.ForeignKey(
        ContratTravail, on_delete=models.CASCADE, related_name="elements_fixes", verbose_name="Contrat"
    )
    rubrique = models.ForeignKey(RubriquePaie, on_delete=models.PROTECT, related_name="+", verbose_name="Rubrique")
    montant = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True, verbose_name="Montant mensuel (FCFA)"
    )
    taux = models.DecimalField(
        max_digits=6, decimal_places=3, null=True, blank=True, verbose_name="Taux (% du salaire de base)"
    )
    date_debut = models.DateField(verbose_name="Du")
    date_fin = models.DateField(null=True, blank=True, verbose_name="Au")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["contrat", "rubrique__ordre"]
        verbose_name = "Élément fixe de paie"
        verbose_name_plural = "Éléments fixes de paie"

    def __str__(self):
        return f"{self.contrat.code} — {self.rubrique.label}"

    def clean(self):
        if self.rubrique_id and self.rubrique.nature != RubriquePaie.Nature.GAIN:
            raise ValidationError({"rubrique": "Un élément fixe porte sur une rubrique de gain."})
        if (self.montant is None) == (self.taux is None):
            raise ValidationError("Renseigner soit un montant, soit un taux (l'un ou l'autre).")
        if self.date_fin and self.date_debut and self.date_fin < self.date_debut:
            raise ValidationError({"date_fin": "La date de fin précède la date de début."})


class EvenementCarriere(models.Model):
    """Historique de carrière INALTÉRABLE : promotion, reclassement, mutation, augmentation… (avant / après)."""

    class Type(models.TextChoices):
        EMBAUCHE = "embauche", "Embauche"
        PROMOTION = "promotion", "Promotion"
        RECLASSEMENT = "reclassement", "Reclassement"
        MUTATION = "mutation", "Mutation"
        AUGMENTATION = "augmentation", "Augmentation"
        AVENANT = "avenant", "Avenant au contrat"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    employe = models.ForeignKey(Employe, on_delete=models.PROTECT, related_name="carriere", verbose_name="Employé")
    contrat = models.ForeignKey(
        ContratTravail, null=True, blank=True, on_delete=models.PROTECT, related_name="+", verbose_name="Contrat"
    )
    type = models.CharField(max_length=14, choices=Type.choices, verbose_name="Type")
    date_effet = models.DateField(verbose_name="Date d'effet")
    categorie_avant = models.CharField(max_length=20, blank=True, verbose_name="Catégorie avant")
    categorie_apres = models.CharField(max_length=20, blank=True, verbose_name="Catégorie après")
    fonction_avant = models.CharField(max_length=150, blank=True, verbose_name="Fonction avant")
    fonction_apres = models.CharField(max_length=150, blank=True, verbose_name="Fonction après")
    grille_avant = models.ForeignKey(
        GrilleSalaire, null=True, blank=True, on_delete=models.PROTECT, related_name="+", verbose_name="Grille avant"
    )
    grille_apres = models.ForeignKey(
        GrilleSalaire, null=True, blank=True, on_delete=models.PROTECT, related_name="+", verbose_name="Grille après"
    )
    salaire_avant = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    salaire_apres = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    motif = models.TextField(blank=True, verbose_name="Motif / décision")
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Enregistré par",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_effet", "-created_at"]
        verbose_name = "Événement de carrière"
        verbose_name_plural = "Carrière — historique"

    def __str__(self):
        return f"{self.code} — {self.employe.nom_complet} ({self.get_type_display()})"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("L'historique de carrière est inaltérable.")
        if not self.code:
            self.code = RhPaieSequence.next_for("CAR", "CAR")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("L'historique de carrière est inaltérable.")


class Absence(models.Model):
    """Absence hors congés (CDC M9.2) : non rémunérée et validée, elle est retenue au bulletin préparé du mois."""

    class Type(models.TextChoices):
        INJUSTIFIEE = "injustifiee", "Absence injustifiée"
        AUTORISEE_NP = "autorisee_np", "Absence autorisée non payée"
        AUTORISEE_P = "autorisee_p", "Absence autorisée payée"
        MALADIE = "maladie", "Arrêt maladie"
        ACCIDENT_TRAVAIL = "accident_travail", "Accident du travail"
        MISE_A_PIED = "mise_a_pied", "Mise à pied"

    NON_REMUNEREES = ("injustifiee", "autorisee_np", "mise_a_pied")

    class Statut(models.TextChoices):
        SAISIE = "saisie", "Saisie"
        VALIDEE = "validee", "Validée"
        ANNULEE = "annulee", "Annulée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    employe = models.ForeignKey(Employe, on_delete=models.PROTECT, related_name="absences", verbose_name="Employé")
    type = models.CharField(max_length=20, choices=Type.choices, verbose_name="Type")
    date_debut = models.DateField(verbose_name="Du")
    date_fin = models.DateField(verbose_name="Au")
    remuneree = models.BooleanField(
        null=True, blank=True, verbose_name="Rémunérée",
        help_text="Vide = selon le type (injustifiée, autorisée non payée et mise à pied ne sont pas payées).",
    )
    motif = models.CharField(max_length=200, blank=True, verbose_name="Motif / justificatif")
    statut = models.CharField(max_length=8, choices=Statut.choices, default=Statut.SAISIE, verbose_name="Statut")
    valide_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Validée par",
    )
    valide_le = models.DateTimeField(null=True, blank=True, verbose_name="Validée le")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_debut"]
        verbose_name = "Absence"
        verbose_name_plural = "Absences"
        indexes = [models.Index(fields=["employe", "statut", "date_debut"])]

    def __str__(self):
        return f"{self.code} — {self.employe.nom_complet} ({self.get_type_display()})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = RhPaieSequence.next_for("ABS", "ABS")
        if self.remuneree is None:
            self.remuneree = self.type not in self.NON_REMUNEREES
        return super().save(*args, **kwargs)

    def clean(self):
        if self.date_debut and self.date_fin and self.date_fin < self.date_debut:
            raise ValidationError({"date_fin": "La date de fin précède la date de début."})

    @property
    def nb_jours(self):
        return (self.date_fin - self.date_debut).days + 1


class EcheanceDeclaration(ValeurLegale):
    """Date limite de dépôt d'une déclaration sociale ou fiscale (calendrier ETSL), alertée tant qu'elle manque."""

    class Periodicite(models.TextChoices):
        MENSUELLE = "mensuelle", "Mensuelle"
        TRIMESTRIELLE = "trimestrielle", "Trimestrielle"
        ANNUELLE = "annuelle", "Annuelle"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    libelle = models.CharField(max_length=150, verbose_name="Libellé")
    type_declaration = models.CharField(
        max_length=10, choices=DeclarationSociale.Type.choices, verbose_name="Déclaration"
    )
    periodicite = models.CharField(max_length=14, choices=Periodicite.choices, verbose_name="Périodicité")
    jour = models.PositiveSmallIntegerField(verbose_name="Jour limite")
    mois = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="Mois limite (annuelle)",
        help_text="Mensuelle / trimestrielle : le jour limite tombe le mois suivant la période.",
    )
    actif = models.BooleanField(default=True, verbose_name="Active")

    class Meta:
        ordering = ["type_declaration", "code"]
        verbose_name = "Échéance de déclaration"
        verbose_name_plural = "Échéances des déclarations"

    def __str__(self):
        return f"{self.code} — {self.libelle}"

    def clean(self):
        if not self.jour or not 1 <= self.jour <= 31:
            raise ValidationError({"jour": "Jour entre 1 et 31."})
        if self.periodicite == self.Periodicite.ANNUELLE and not (self.mois and 1 <= self.mois <= 12):
            raise ValidationError({"mois": "Mois (1 à 12) requis pour une échéance annuelle."})


# --------------------------------------------------------------------------------------------
# Écarts M9-B : comptes de paie, provision des congés payés
# --------------------------------------------------------------------------------------------
class ComptePaie(models.Model):
    """Compte du plan comptable utilisé par l'écriture de paie, par rôle et, pour les cotisations, par organisme."""

    class Role(models.TextChoices):
        BRUT = "brut", "Charges de personnel (brut)"
        PATRONAL = "patronal", "Charges sociales patronales"
        NET = "net", "Personnel — net à payer"
        ORGANISMES = "organismes", "Cotisations à reverser (par organisme)"
        IMPOT = "impot", "Impôt retenu à la source"
        AUTRES_RETENUES = "autres_retenues", "Autres retenues"
        PROVISION_CHARGE = "provision_charge", "Dotation aux provisions pour congés payés"
        PROVISION_DETTE = "provision_dette", "Dettes provisionnées pour congés payés"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.CharField(max_length=20, choices=Role.choices, verbose_name="Rôle")
    organisme = models.CharField(
        max_length=60, blank=True, verbose_name="Organisme (cotisations)",
        help_text="Même libellé que l'organisme des barèmes (CNSS, CNAMGS…) ; vide = compte par défaut du rôle.",
    )
    compte = models.ForeignKey(
        "referentiels.Account", on_delete=models.PROTECT, related_name="+", verbose_name="Compte"
    )

    class Meta:
        ordering = ["role", "organisme"]
        verbose_name = "Compte de paie"
        verbose_name_plural = "Comptes de paie"
        constraints = [models.UniqueConstraint(fields=["role", "organisme"], name="uniq_compte_paie_role_organisme")]

    def __str__(self):
        return f"{self.get_role_display()}{' ' + self.organisme if self.organisme else ''} → {self.compte_id}"


class ProvisionConges(models.Model):
    """Dotation mensuelle aux provisions pour congés payés (écriture du journal PAI), scellée."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    periode = models.DateField(unique=True, verbose_name="Période (1er du mois)")
    base_brut = models.DecimalField(max_digits=16, decimal_places=2, verbose_name="Brut des bulletins du mois")
    taux = models.DecimalField(max_digits=7, decimal_places=3, verbose_name="Taux (%)")
    taux_provisoire = models.BooleanField(default=True, verbose_name="Taux provisoire")
    montant = models.DecimalField(max_digits=16, decimal_places=2, verbose_name="Montant provisionné")
    move = models.ForeignKey(
        "accounting_kernel.AccountMove", on_delete=models.PROTECT, related_name="+", verbose_name="Écriture"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Passée par",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-periode"]
        verbose_name = "Provision pour congés payés"
        verbose_name_plural = "Provisions pour congés payés"

    def __str__(self):
        return f"Provision CP {self.periode:%m/%Y} — {self.montant}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Une provision passée est scellée (extourne en comptabilité).")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Une provision passée est scellée (extourne en comptabilité).")


# --------------------------------------------------------------------------------------------
# Écarts M9-C : catalogue et plan de formation, matrice habilitation ↔ poste
# --------------------------------------------------------------------------------------------
class CatalogueFormation(models.Model):
    """Formation du catalogue : durée, coût de session et qualification délivrée à la réalisation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    intitule = models.CharField(max_length=180, verbose_name="Intitulé")
    organisme = models.CharField(max_length=120, blank=True, verbose_name="Organisme")
    duree_heures = models.DecimalField(max_digits=6, decimal_places=2, default=0, verbose_name="Durée (heures)")
    cout_session = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Coût d'une session (FCFA)"
    )
    qualification_type = models.CharField(
        max_length=14, choices=Qualification.Type.choices, blank=True, verbose_name="Qualification délivrée",
        help_text="Vide = sensibilisation sans qualification.",
    )
    validite_mois = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="Validité (mois)", help_text="Vide = sans échéance."
    )
    actif = models.BooleanField(default=True, verbose_name="Actif")

    class Meta:
        ordering = ["intitule"]
        verbose_name = "Formation du catalogue"
        verbose_name_plural = "Catalogue des formations"

    def __str__(self):
        return f"{self.code} — {self.intitule}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = RhPaieSequence.next_for("CAT", "CAT")
        return super().save(*args, **kwargs)


class PlanFormation(models.Model):
    """Plan de formation annuel : budget voté, sessions rattachées (coût engagé, réalisé, ROI)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    annee = models.PositiveSmallIntegerField(unique=True, verbose_name="Année")
    budget = models.DecimalField(max_digits=16, decimal_places=2, default=0, verbose_name="Budget (FCFA)")
    objectifs = models.TextField(blank=True, verbose_name="Objectifs")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-annee"]
        verbose_name = "Plan de formation"
        verbose_name_plural = "Plans de formation"

    def __str__(self):
        return f"Plan de formation {self.annee}"

    def clean(self):
        if not 2000 <= (self.annee or 0) <= 2100:
            raise ValidationError({"annee": "Année hors plage (2000-2100)."})
        if self.budget is not None and self.budget < 0:
            raise ValidationError({"budget": "Le budget ne peut être négatif."})


class HabilitationPoste(models.Model):
    """Matrice habilitation ↔ poste : un pointage chantier sur un OF dont la gamme comporte ce poste exige une
    qualification valide dont l'intitulé contient `mot_cle`."""

    POSTES = (
        ("decoupe", "Découpe"), ("tuyauterie", "Tuyauterie"), ("soudure", "Soudure"),
        ("chaudronnerie", "Chaudronnerie"), ("structure", "Structures métalliques"), ("montage", "Montage"),
        ("controle", "Contrôle / essais"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    poste = models.CharField(max_length=16, choices=POSTES, verbose_name="Poste (gamme M3)")
    mot_cle = models.CharField(max_length=80, verbose_name="Mot-clé de l'intitulé de qualification")
    actif = models.BooleanField(default=True, verbose_name="Actif")

    class Meta:
        ordering = ["poste", "mot_cle"]
        verbose_name = "Habilitation exigée par poste"
        verbose_name_plural = "Matrice habilitations ↔ postes"
        constraints = [models.UniqueConstraint(fields=["poste", "mot_cle"], name="uniq_habilitation_poste")]

    def __str__(self):
        return f"{self.get_poste_display()} ⇒ {self.mot_cle}"
