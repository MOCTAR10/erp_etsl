"""Module M7 — HSE : Hygiène, Sécurité & Environnement (RF-ERP-60…63).

Procédures MANUEL ch.9 : 9.3 politique HSE · 9.4 prévention des risques
chantiers · 9.5 normes ATEX & sécurité des équipements · 9.6 gestion des
incidents et accidents · 9.7 sensibilisation & formation sécurité ·
9.8 gestion des EPI, consignes & discipline HSE · 9.9 archivage & traçabilité.
RF-ERP-60 : permis chaud / hauteur / levage / ATEX · RF-ERP-61 : accidents &
presque-accidents · RF-ERP-62 : tri des déchets & BSD · RF-ERP-63 : reporting
client pétrolier (Couche D) + sensibilisation / EPI. Matrice risque
gravité × probabilité (inspiration OCA management-system — concepts uniquement).
"""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone


class HseSequence(models.Model):
    """Numérotation séquentielle par type (PERM, EVR, ATX, INC, ACT, FOR, EPI, BSD)."""

    kind = models.CharField(max_length=10, unique=True, verbose_name="Type")
    prefix = models.CharField(max_length=10, verbose_name="Préfixe")
    padding = models.PositiveSmallIntegerField(default=5, verbose_name="Zéro-padding")
    next_number = models.PositiveIntegerField(default=1, verbose_name="Prochain numéro")

    class Meta:
        verbose_name = "Séquence HSE"
        verbose_name_plural = "Séquences HSE"

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


class PermisTravail(models.Model):
    """Permis de travail — chaud, hauteur, levage, ATEX, espaces confinés… (RF-ERP-60)."""

    class TypePermis(models.TextChoices):
        CHAUD = "chaud", "Travaux à chaud"
        HAUTEUR = "hauteur", "Travaux en hauteur"
        LEVAGE = "levage", "Levage / manutention"
        CONFINE = "confine", "Espaces confinés"
        ATEX = "atex", "Atmosphère explosive (ATEX)"
        FROID = "froid", "Travaux à froid"
        ELECTRIQUE = "electrique", "Travaux électriques"
        FOUILLE = "fouille", "Fouille / excavations"
        CHIMIQUE = "chimique", "Manipulation produits chimiques"

    class Statut(models.TextChoices):
        DEMANDE = "demande", "Demandé"
        VALIDE = "valide", "Validé"
        ACTIF = "actif", "Actif"
        CLOTURE = "cloture", "Clôturé"
        REFUSE = "refuse", "Refusé"
        ANNULE = "annule", "Annulé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    type_permis = models.CharField(
        max_length=14, choices=TypePermis.choices, default=TypePermis.CHAUD,
        verbose_name="Type de permis",
    )
    affaire = models.ForeignKey(
        "commercial.Affaire",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="permis_travail",
        verbose_name="Affaire",
    )
    ordre = models.ForeignKey(
        "operations.OrdreFabrication",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="permis_travail",
        verbose_name="Ordre de fabrication",
    )
    emplacement = models.CharField(max_length=200, verbose_name="Emplacement / zone")
    description = models.TextField(verbose_name="Nature des travaux")
    mesures = models.TextField(blank=True, verbose_name="Mesures de prévention")
    demandeur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="hse_permis_demandes",
        verbose_name="Demandeur",
    )
    validateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="hse_permis_valides",
        verbose_name="Validateur HSE",
    )
    date_debut = models.DateField(default=timezone.localdate, verbose_name="Date de début")
    date_fin = models.DateField(null=True, blank=True, verbose_name="Date de fin")
    statut = models.CharField(
        max_length=10, choices=Statut.choices, default=Statut.DEMANDE, verbose_name="Statut"
    )
    date_validation = models.DateTimeField(null=True, blank=True, verbose_name="Validation le")
    date_cloture = models.DateTimeField(null=True, blank=True, verbose_name="Clôture le")
    notes = models.TextField(blank=True, verbose_name="Notes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Permis de travail"
        verbose_name_plural = "Permis de travail"
        indexes = [models.Index(fields=["type_permis", "statut"])]

    def __str__(self):
        return f"{self.code} — {self.get_type_permis_display()} ({self.get_statut_display()})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = HseSequence.next_for("PERM", "PERM")
        return super().save(*args, **kwargs)

    def clean(self):
        if self.date_debut and self.date_fin and self.date_fin < self.date_debut:
            raise ValidationError(
                {"date_fin": "La date de fin doit être postérieure à la date de début."}
            )


class EvaluationRisque(models.Model):
    """Évaluation / identification des risques chantier — matrice gravité × probabilité (9.4)."""

    class Criticite(models.TextChoices):
        FAIBLE = "faible", "Faible"
        MOYENNE = "moyenne", "Moyenne"
        ELEVEE = "elevee", "Élevée"
        CRITIQUE = "critique", "Critique"

    class Statut(models.TextChoices):
        OUVERTE = "ouverte", "Ouverte"
        TRAITEE = "traitee", "Mesures en place"
        CLOTUREE = "cloturee", "Clôturée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    lieux = models.CharField(max_length=200, verbose_name="Lieu / zone")
    activite = models.CharField(
        max_length=200, blank=True, verbose_name="Activité / tâche concernée"
    )
    description = models.TextField(verbose_name="Risque identifié")
    probabilite = models.PositiveSmallIntegerField(
        default=1, verbose_name="Probabilité (1-5)"
    )
    gravite = models.PositiveSmallIntegerField(default=1, verbose_name="Gravité (1-5)")
    mesure = models.TextField(blank=True, verbose_name="Mesure de prévention")
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="hse_risques",
        verbose_name="Responsable du suivi",
    )
    affaire = models.ForeignKey(
        "commercial.Affaire",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="evaluations_risques",
        verbose_name="Affaire",
    )
    statut = models.CharField(
        max_length=10, choices=Statut.choices, default=Statut.OUVERTE, verbose_name="Statut"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Évaluation de risque"
        verbose_name_plural = "Évaluations de risques"
        indexes = [models.Index(fields=["statut"])]

    def __str__(self):
        return f"{self.code} — {self.get_criticite_display()} ({self.get_statut_display()})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = HseSequence.next_for("EVR", "EVR")
        return super().save(*args, **kwargs)

    def clean(self):
        if not 1 <= self.probabilite <= 5:
            raise ValidationError({"probabilite": "Probabilité entre 1 et 5."})
        if not 1 <= self.gravite <= 5:
            raise ValidationError({"gravite": "Gravité entre 1 et 5."})

    @property
    def criticite_scores(self):
        score = self.probabilite * self.gravite
        if score >= 15:
            return score, self.Criticite.CRITIQUE
        if score >= 9:
            return score, self.Criticite.ELEVEE
        if score >= 4:
            return score, self.Criticite.MOYENNE
        return score, self.Criticite.FAIBLE

    @property
    def criticite(self):
        return self.criticite_scores[1]

    @property
    def score(self):
        return self.criticite_scores[0]


class EquipementAtex(models.Model):
    """Équipements en atmosphère potentiellement explosive — conformité & inspections (9.5)."""

    class Statut(models.TextChoices):
        DISPONIBLE = "disponible", "Disponible"
        QUARANTAINE = "quarantaine", "En quarantaine"
        ECARTE = "ecarte", "Écarté du service"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    designation = models.CharField(max_length=200, verbose_name="Désignation")
    zone_atex = models.CharField(
        max_length=120, blank=True, verbose_name="Zone classée (ex. Zone 1)"
    )
    marquage = models.CharField(
        max_length=120, blank=True, verbose_name="Marquage (catégorie / groupe)"
    )
    fabricant = models.CharField(max_length=120, blank=True, verbose_name="Fabricant")
    numero_serie = models.CharField(max_length=80, blank=True, verbose_name="N° de série")
    certificat = models.CharField(max_length=80, blank=True, verbose_name="Certificat")
    date_expiration_certificat = models.DateField(
        null=True, blank=True, verbose_name="Validité du certificat"
    )
    date_derniere_inspection = models.DateField(
        null=True, blank=True, verbose_name="Dernière inspection"
    )
    prochaine_inspection = models.DateField(
        null=True, blank=True, verbose_name="Prochaine inspection"
    )
    statut = models.CharField(
        max_length=12, choices=Statut.choices, default=Statut.DISPONIBLE, verbose_name="Statut"
    )
    notes = models.TextField(blank=True, verbose_name="Notes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Équipement ATEX"
        verbose_name_plural = "Équipements ATEX"

    def __str__(self):
        return f"{self.code} — {self.designation} ({self.get_statut_display()})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = HseSequence.next_for("ATX", "ATX")
        return super().save(*args, **kwargs)

    @property
    def certificat_expire(self):
        return bool(
            self.date_expiration_certificat
            and self.date_expiration_certificat < timezone.localdate()
        )


class Incident(models.Model):
    """Incident / accident HSE — déclaration immédiate, enquête, plan d'action (9.6, RF-ERP-61)."""

    class TypeIncident(models.TextChoices):
        INCIDENT = "incident", "Incident"
        ACCIDENT = "accident", "Accident"
        QUASI_ACCIDENT = "quasi_accident", "Quasi-accident / presque-accident"
        BLESSURE = "blessure", "Blessure"
        DEPART_FEU = "depart_feu", "Départ de feu"
        POLLUTION = "pollution", "Pollution"
        DEVERSEMENT = "deversement", "Déversement"
        DOMMAGE = "dommage_materiel", "Dommage matériel"
        SITUATION_DANGEREUSE = "situation_dangereuse", "Situation dangereuse"

    class Gravite(models.TextChoices):
        MINEURE = "mineure", "Mineure"
        MAJEURE = "majeure", "Majeure"
        CRITIQUE = "critique", "Critique"

    class Statut(models.TextChoices):
        DECLARE = "declare", "Déclaré"
        EN_ENQUETE = "en_enquete", "Enquête en cours"
        PLAN_ACTION = "plan_action", "Plan d'action"
        CLOTURE = "cloture", "Clôturé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    type_incident = models.CharField(
        max_length=22, choices=TypeIncident.choices, default=TypeIncident.INCIDENT,
        verbose_name="Type",
    )
    gravite = models.CharField(
        max_length=10, choices=Gravite.choices, default=Gravite.MINEURE, verbose_name="Gravité"
    )
    date_evenement = models.DateTimeField(verbose_name="Date / heure de l'événement")
    lieu = models.CharField(max_length=200, verbose_name="Lieu")
    description = models.TextField(verbose_name="Description des faits")
    personnes_impliquees = models.TextField(
        blank=True, verbose_name="Personnes impliquées / témoins"
    )
    cause_immediate = models.TextField(blank=True, verbose_name="Cause immédiate")
    cause_profonde = models.TextField(blank=True, verbose_name="Cause profonde / racine")
    consequences = models.TextField(blank=True, verbose_name="Conséquences / blessures")
    rapport = models.TextField(blank=True, verbose_name="Rapport d'enquête")
    statut = models.CharField(
        max_length=12, choices=Statut.choices, default=Statut.DECLARE, verbose_name="Statut"
    )
    archive = models.BooleanField(default=False, verbose_name="Archivée (traçabilité HSE)")
    declared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="hse_incidents_declares",
        verbose_name="Déclaré par",
    )
    enqueteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="hse_enquetes",
        verbose_name="Responsable d'enquête",
    )
    date_ouverture_enquete = models.DateTimeField(null=True, blank=True, verbose_name="Enquête ouverte le")
    date_rapport = models.DateField(null=True, blank=True, verbose_name="Date du rapport")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_evenement"]
        verbose_name = "Incident / accident"
        verbose_name_plural = "Incidents / accidents"
        indexes = [models.Index(fields=["type_incident", "statut"])]

    def __str__(self):
        return f"{self.code} — {self.get_type_incident_display()} ({self.get_statut_display()})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = HseSequence.next_for("INC", "INC")
        return super().save(*args, **kwargs)

    def clean(self):
        if not self.description.strip():
            raise ValidationError({"description": "La description est requise."})


class ActionHse(models.Model):
    """Action corrective / préventive issue d'un événement HSE ou d'un risque (9.6.8)."""

    class TypeAction(models.TextChoices):
        CORRECTIVE = "corrective", "Corrective"
        PREVENTIVE = "preventive", "Préventive"

    class Statut(models.TextChoices):
        OUVERTE = "ouverte", "Ouverte"
        EN_COURS = "en_cours", "En cours"
        CLOTUREE = "cloturee", "Clôturée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    incident = models.ForeignKey(
        Incident,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="actions",
        verbose_name="Événement HSE",
    )
    risque = models.ForeignKey(
        EvaluationRisque,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="actions",
        verbose_name="Risque associé",
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
        related_name="hse_actions",
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
        verbose_name = "Action HSE"
        verbose_name_plural = "Actions HSE"

    def __str__(self):
        return f"{self.code} — {self.get_type_display()} ({self.get_statut_display()})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = HseSequence.next_for("ACT", "ACT")
        return super().save(*args, **kwargs)


class FormationSecurite(models.Model):
    """Sensibilisation & formation sécurité — sessions, exercices, évaluation (9.7)."""

    class TypeSession(models.TextChoices):
        FORMATION = "formation", "Formation en salle"
        DEMONSTRATION = "demonstration", "Démonstration pratique"
        CAUSERIE = "causerie", "Causerie sécurité"
        EXERCICE = "exercice", "Exercice / mise en situation"
        CAMPAGNE = "campagne", "Campagne thématique"
        RECYCLAGE = "recyclage", "Recyclage périodique"

    class Statut(models.TextChoices):
        PLANIFIEE = "planifiee", "Planifiée"
        REALISEE = "realisee", "Réalisée"
        ANNULEE = "annulee", "Annulée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    type_session = models.CharField(
        max_length=14, choices=TypeSession.choices, default=TypeSession.CAUSERIE,
        verbose_name="Type",
    )
    theme = models.CharField(max_length=200, verbose_name="Thème")
    formateur = models.CharField(max_length=120, blank=True, verbose_name="Formateur / animateur")
    organisme = models.CharField(max_length=120, blank=True, verbose_name="Organisme")
    date_session = models.DateField(verbose_name="Date de la session")
    duree_heures = models.DecimalField(
        max_digits=5, decimal_places=2, default=1, verbose_name="Durée (h)"
    )
    nb_participants = models.PositiveIntegerField(default=0, verbose_name="Participants")
    evalue = models.BooleanField(default=False, verbose_name="Évaluation des acquis réalisée")
    statut = models.CharField(
        max_length=12, choices=Statut.choices, default=Statut.PLANIFIEE, verbose_name="Statut"
    )
    notes = models.TextField(blank=True, verbose_name="Notes / compte rendu")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_session"]
        verbose_name = "Session de formation sécurité"
        verbose_name_plural = "Formations sécurité"

    def __str__(self):
        return f"{self.code} — {self.theme} ({self.get_statut_display()})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = HseSequence.next_for("FOR", "FOR")
        return super().save(*args, **kwargs)


class Epi(models.Model):
    """Équipement de protection individuelle — dotation, renouvellement, discipline (9.8)."""

    class TypeEpi(models.TextChoices):
        CASQUE = "casque", "Casque de protection"
        LUNETTES = "lunettes", "Lunettes de protection"
        ECRAN = "ecran_facial", "Écran facial"
        AUDITIF = "protection_auditive", "Protection auditive"
        GANTS = "gants", "Gants"
        CHAUSSURES = "chaussures", "Chaussures de sécurité"
        VESTE = "veste_haute_visibilite", "Veste haute visibilité"
        HARNAIS = "harnais", "Harnais / longe"
        MASQUE = "masque", "Masque respiratoire"
        BAUDRIER = "baudrier", "Baudrier de travail"

    class Statut(models.TextChoices):
        EN_USAGE = "en_usage", "En usage"
        DISPONIBLE = "disponible", "Disponible (stock)"
        RENDU = "rendu", "Rendu"
        HORS_SERVICE = "hors_service", "Hors service"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    type_epi = models.CharField(
        max_length=24, choices=TypeEpi.choices, default=TypeEpi.CASQUE, verbose_name="Type d'EPI"
    )
    designation = models.CharField(max_length=200, verbose_name="Désignation")
    taille = models.CharField(max_length=20, blank=True, verbose_name="Taille")
    beneficiaire = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="hse_epi",
        verbose_name="Bénéficiaire",
    )
    date_dotation = models.DateField(default=timezone.localdate, verbose_name="Date de dotation")
    date_renouvellement = models.DateField(null=True, blank=True, verbose_name="Renouvellement")
    statut = models.CharField(
        max_length=12, choices=Statut.choices, default=Statut.EN_USAGE, verbose_name="Statut"
    )
    notes = models.TextField(blank=True, verbose_name="Notes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_dotation"]
        verbose_name = "Équipement de protection individuelle"
        verbose_name_plural = "EPI"

    def __str__(self):
        return f"{self.code} — {self.get_type_epi_display()} ({self.get_statut_display()})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = HseSequence.next_for("EPI", "EPI")
        return super().save(*args, **kwargs)

    @property
    def a_renouveler(self):
        if self.statut != self.Statut.EN_USAGE or not self.date_renouvellement:
            return False
        return self.date_renouvellement <= timezone.localdate() + timezone.timedelta(days=30)


class BordereauDechet(models.Model):
    """Déchets & bordereaux de suivi BSD — tri, enlèvement, traçabilité (RF-ERP-62)."""

    class TypeDechet(models.TextChoices):
        HUILES = "huiles", "Dangereux — huiles usagées"
        SOLVANTS = "solvants", "Dangereux — solvants"
        BATTERIES = "batteries", "Dangereux — batteries / plomb"
        PEINTURES = "peintures", "Dangereux — déchets de peinture"
        DIB = "dib", "Non dangereux — DIB"
        DEEE = "deee", "DEEE (équipements électriques)"
        METAUX = "metaux", "Métaux / ferrailles"
        PAPIER = "papier_carton", "Papier / carton"

    class Unite(models.TextChoices):
        KG = "kg", "kg"
        T = "t", "tonne"
        L = "l", "litre"
        UNITE = "unite", "unité"

    class Statut(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente d'enlèvement"
        EMIS = "emis", "BSD émis"
        TRAITE = "traite", "Traité / valorisé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    type_dechet = models.CharField(
        max_length=14, choices=TypeDechet.choices, default=TypeDechet.DIB,
        verbose_name="Type de déchet",
    )
    quantite = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Quantité"
    )
    unite = models.CharField(
        max_length=6, choices=Unite.choices, default=Unite.KG, verbose_name="Unité"
    )
    transporteur = models.ForeignKey(
        "referentiels.Partner",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="bordereaux_dechets",
        verbose_name="Transporteur / filière",
    )
    numero_bsd = models.CharField(max_length=80, blank=True, verbose_name="N° BSD")
    date_enlevement = models.DateField(null=True, blank=True, verbose_name="Date d'enlèvement")
    destination = models.CharField(
        max_length=200, blank=True, verbose_name="Destination (exutoire / valorisation)"
    )
    statut = models.CharField(
        max_length=12, choices=Statut.choices, default=Statut.EN_ATTENTE, verbose_name="Statut"
    )
    notes = models.TextField(blank=True, verbose_name="Notes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Bordereau de déchet"
        verbose_name_plural = "Bordereaux de déchets BSD"

    def __str__(self):
        return f"{self.code} — {self.get_type_dechet_display()} ({self.get_statut_display()})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = HseSequence.next_for("BSD", "BSD")
        return super().save(*args, **kwargs)