"""Module M9 — RH & Paie (moteur de paie natif CNSSG / CNAMGS, RF-ERP-80…83).

Procédures MANUEL ch.7 : 7.3 recrutement & intégration · 7.4 contrats de travail ·
7.5 formation & développement des compétences · 7.6 congés & rotations · 7.7
discipline & sanctions · 7.8 administration du personnel · 7.9 archivage et
traçabilité RH. Pointages M3 (RF-ERP-21) remontés en saisie temps (RF-ERP-81).
Bulletins de paie CNSSG / CNAMGS, barèmes versionnés par date d'effet (RF-ERP-82).
"""

import uuid
from datetime import date, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone


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
    numero_securite_sociale = models.CharField(
        max_length=40, blank=True, verbose_name="N° sécurité sociale (CNSS)"
    )
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
    matricule_cnps = models.CharField(max_length=40, blank=True, verbose_name="Matricule CNAMGS")
    date_embauche = models.DateField(null=True, blank=True, verbose_name="Date d'embauche")
    date_sortie = models.DateField(null=True, blank=True, verbose_name="Date de sortie")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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
    def contrat_actif(self):
        return self.contrats.filter(statut=ContratTravail.Statut.ACTIF).first()

    @property
    def solde_conges(self):
        """Jours de congé acquis (CON) − pris/validés (8.9 registres)."""
        acquis = DemandesConge.DUREE_CONGE_CNSS
        pris = float(
            DemandesConge.objects.filter(
                employe=self,
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

    class Meta:
        ordering = ["-date_validite"]
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
        if self.date_fin < self.date_debut:
            raise ValidationError(
                {"date_fin": "La date de fin doit être postérieure à la date de début."}
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
            models.UniqueConstraint(fields=["employe", "periode"], name="uniq_employe_periode")
        ]

    def __str__(self):
        return f"{self.code} — {self.employe.nom_complet} ({self.periode:%m/%Y})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = RhPaieSequence.next_for("BUL", "BUL")
        return super().save(*args, **kwargs)

    @property
    def total_gains(self):
        return self.lignes.filter(rubrique__nature=RubriquePaie.Nature.GAIN).aggregate(
            t=models.Sum("montant")
        )["t"] or 0

    @property
    def total_retenues(self):
        return self.lignes.filter(rubrique__nature=RubriquePaie.Nature.RETENUE).aggregate(
            t=models.Sum("montant")
        )["t"] or 0


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