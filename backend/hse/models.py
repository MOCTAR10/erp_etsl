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
from calendar import monthrange

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
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
        EXPIRE = "expire", "Expiré"

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
    visa_superviseur_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        verbose_name="Visa superviseur",
    )
    visa_superviseur_le = models.DateTimeField(null=True, blank=True, verbose_name="Date du visa superviseur")
    visa_hse_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        verbose_name="Visa HSE",
    )
    visa_hse_le = models.DateTimeField(null=True, blank=True, verbose_name="Date du visa HSE")
    visa_dg_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        verbose_name="Visa Direction Générale",
    )
    visa_dg_le = models.DateTimeField(null=True, blank=True, verbose_name="Date du visa Direction Générale")
    date_validation = models.DateTimeField(null=True, blank=True, verbose_name="Validation le")
    date_cloture = models.DateTimeField(null=True, blank=True, verbose_name="Clôture le")
    # Test d'atmosphère (CL-OM-07) : obligatoire avant démarrage pour les types à risque gaz.
    test_gaz_resultat = models.CharField(
        max_length=12, blank=True, choices=[("conforme", "Conforme"), ("non_conforme", "Non conforme")],
        verbose_name="Test gaz - résultat",
    )
    test_gaz_valeur = models.CharField(
        max_length=120, blank=True, verbose_name="Test gaz - mesures (LIE, O2, H2S...)"
    )
    test_gaz_date = models.DateTimeField(null=True, blank=True, verbose_name="Test gaz - le")
    test_gaz_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="hse_tests_gaz", verbose_name="Test gaz - par",
    )
    intervenants = models.ManyToManyField(
        "rh_paie.Employe", blank=True, related_name="permis_hse", verbose_name="Intervenants",
    )
    notes = models.TextField(blank=True, verbose_name="Notes")
    photo = models.FileField(upload_to="hse/permis/photos/", blank=True, verbose_name="Photo de la zone")
    plan = models.FileField(upload_to="hse/permis/plans/", blank=True, verbose_name="Plan / croquis")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    #: Statuts où le permis est figé (pièces jointes, intervenants).
    STATUTS_FIGES = ("cloture", "refuse", "annule", "expire")
    #: Types de permis exigeant un test d'atmosphère avant démarrage.
    GAZ_TYPES = ("chaud", "confine", "atex", "chimique")
    #: Validité d'un test gaz (heures) - à confirmer avec la procédure HSE d'ETSL.
    TEST_GAZ_VALIDITE_HEURES = 12

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
    @property
    def gaz_obligatoire(self):
        return self.type_permis in self.GAZ_TYPES

    @property
    def test_gaz_valide(self):
        """Test gaz conforme et encore dans sa duree de validite."""
        if self.test_gaz_resultat != "conforme" or not self.test_gaz_date:
            return False
        age = timezone.now() - self.test_gaz_date
        return age <= timezone.timedelta(hours=self.TEST_GAZ_VALIDITE_HEURES)

    @property
    def prochain_niveau(self):
        """Prochain niveau de validation attendu (None si le circuit est complet ou le permis n'est plus en demande)."""
        from django.conf import settings as dj_settings

        if self.statut != self.Statut.DEMANDE:
            return None
        for niveau in dj_settings.HSE_PERMIS_NIVEAUX:
            if not getattr(self, f"visa_{niveau}_par_id"):
                return niveau
        return None


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
    duer = models.ForeignKey(
        "hse.Duer", null=True, blank=True, on_delete=models.PROTECT, related_name="risques",
        verbose_name="DUER",
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

    class ConsequenceHumaine(models.TextChoices):
        AUCUNE = "aucune", "Aucune blessure"
        PREMIERS_SECOURS = "premiers_secours", "Premiers secours"
        SOINS_MEDICAUX = "soins_medicaux", "Soins médicaux"
        RESTRICTION = "restriction", "Travail restreint / poste aménagé"
        ARRET = "arret", "Arrêt de travail"
        DECES = "deces", "Décès"

    # TRIR : cas enregistrables (au-delà des premiers secours) ; LTIR / LTIFR : cas avec arrêt (lot 15, CDC M7 §9.7).
    CONSEQUENCES_ENREGISTRABLES = ("soins_medicaux", "restriction", "arret", "deces")
    CONSEQUENCES_AVEC_ARRET = ("arret", "deces")

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
    consequence_humaine = models.CharField(
        max_length=16, choices=ConsequenceHumaine.choices, default=ConsequenceHumaine.AUCUNE,
        verbose_name="Conséquence humaine (TRIR / LTIR)",
    )
    jours_arret = models.PositiveIntegerField(default=0, verbose_name="Jours d'arrêt (jours perdus)")
    zone = models.CharField(
        max_length=12, blank=True,
        choices=[("atelier", "Atelier"), ("chantier", "Chantier"), ("bureau", "Bureaux"), ("site_client", "Site client"),
                 ("site_gr", "Site GLOBAL RENTAL")],
        verbose_name="Zone (atelier / chantier…)",
    )
    retour_experience = models.TextField(blank=True, verbose_name="Retour d'expérience (REX)")
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
    escalade_dg_le = models.DateTimeField(
        null=True, blank=True, verbose_name="Escalade Direction Générale",
        help_text="CDC M7 §9.8 : escalade DG obligatoire pour les accidents graves.",
    )
    date_rapport = models.DateField(null=True, blank=True, verbose_name="Date du rapport")
    plan_action_le = models.DateTimeField(null=True, blank=True, verbose_name="Plan d'action arrêté le")
    document = models.ForeignKey(
        "documents.Document", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        verbose_name="Rapport d'incident archivé (GED)",
    )
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
        if self.jours_arret and self.consequence_humaine not in self.CONSEQUENCES_AVEC_ARRET:
            raise ValidationError(
                {"jours_arret": "Des jours d'arrêt supposent une conséquence « arrêt de travail » ou « décès »."}
            )

    @property
    def classification_osha(self):
        """Colonne du registre OSHA 300 : décès, arrêt, travail restreint, autre cas enregistrable (sinon None)."""
        return {
            "deces": "deces", "arret": "arret", "restriction": "restriction", "soins_medicaux": "autre_enregistrable",
        }.get(self.consequence_humaine)

    @property
    def est_grave(self):
        """Accident grave (CDC M7 §9.8) : gravité critique, ou accident / blessure de gravité majeure."""
        if self.gravite == self.Gravite.CRITIQUE:
            return True
        return self.gravite == self.Gravite.MAJEURE and self.type_incident in (
            self.TypeIncident.ACCIDENT, self.TypeIncident.BLESSURE,
        )


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
    participants = models.ManyToManyField(
        "rh_paie.Employe", blank=True, related_name="formations_hse", verbose_name="Participants (nominatif)"
    )
    validite_mois = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="Validité (mois) avant recyclage", help_text="Vide = sans échéance."
    )
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
    employe = models.ForeignKey(
        "rh_paie.Employe", null=True, blank=True, on_delete=models.PROTECT, related_name="epi_dotes",
        verbose_name="Salarié doté (fiche individuelle)",
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
    document = models.ForeignKey(
        "documents.Document", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        verbose_name="BSD archivé (GED)",
    )
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


class ExigenceHabilitation(models.Model):
    """Habilitation exigée pour un type de permis : une qualification RH valide dont l'intitulé contient `mot_cle`."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type_permis = models.CharField(max_length=14, choices=PermisTravail.TypePermis.choices, verbose_name="Type de permis")
    mot_cle = models.CharField(max_length=80, verbose_name="Mot-clé de l'intitulé de qualification")
    actif = models.BooleanField(default=True, verbose_name="Actif")

    class Meta:
        ordering = ["type_permis", "mot_cle"]
        verbose_name = "Exigence d'habilitation"
        verbose_name_plural = "Exigences d'habilitation"
        constraints = [models.UniqueConstraint(fields=["type_permis", "mot_cle"], name="uniq_exigence_hab")]

    def __str__(self):
        return f"{self.get_type_permis_display()} → {self.mot_cle}"


class AuditHse(models.Model):
    """Audit ou inspection HSE planifié, réalisé puis clôturé quand tous les écarts ont une action clôturée."""

    class TypeAudit(models.TextChoices):
        AUDIT = "audit", "Audit"
        INSPECTION = "inspection", "Inspection"

    class Statut(models.TextChoices):
        PLANIFIE = "planifie", "Planifié"
        REALISE = "realise", "Réalisé"
        CLOTURE = "cloture", "Clôturé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    type_audit = models.CharField(max_length=12, choices=TypeAudit.choices, default=TypeAudit.AUDIT, verbose_name="Type")
    zone = models.CharField(max_length=200, verbose_name="Zone / périmètre")
    referentiel = models.CharField(max_length=120, blank=True, verbose_name="Référentiel (ISO 45001, ISO 14001…)")
    date_prevue = models.DateField(default=timezone.localdate, verbose_name="Date prévue")
    date_realisation = models.DateField(null=True, blank=True, verbose_name="Réalisé le")
    score = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Score de conformité (%)")
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.PLANIFIE, verbose_name="Statut")
    realise_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Réalisé par",
    )
    cloture_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Clôturé par",
    )
    cloture_le = models.DateTimeField(null=True, blank=True, verbose_name="Clôturé le")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_prevue"]
        verbose_name = "Audit / inspection HSE"
        verbose_name_plural = "Audits & inspections HSE"

    def __str__(self):
        return f"{self.code} — {self.get_type_audit_display()} {self.zone}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = HseSequence.next_for("AUD", "AUD")
        return super().save(*args, **kwargs)

    @property
    def ecarts_ouverts(self):
        """Écarts (constats non conformes) sans action, ou dont l'action n'est pas clôturée."""
        return [
            c for c in self.constats.select_related("action")
            if c.gravite != ConstatAudit.Gravite.CONFORME
            and (c.action_id is None or c.action.statut != ActionHse.Statut.CLOTUREE)
        ]


class ConstatAudit(models.Model):
    """Constat d'un audit ; un écart (non conforme) doit être rattaché à une action HSE."""

    class Gravite(models.TextChoices):
        CONFORME = "conforme", "Conforme"
        MINEUR = "mineur", "Écart mineur"
        MAJEUR = "majeur", "Écart majeur"
        CRITIQUE = "critique", "Écart critique"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    audit = models.ForeignKey(AuditHse, on_delete=models.CASCADE, related_name="constats", verbose_name="Audit")
    description = models.TextField(verbose_name="Constat")
    gravite = models.CharField(max_length=10, choices=Gravite.choices, default=Gravite.MINEUR, verbose_name="Gravité")
    action = models.ForeignKey(
        ActionHse, null=True, blank=True, on_delete=models.SET_NULL, related_name="constats_audit",
        verbose_name="Action corrective",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Constat d'audit"
        verbose_name_plural = "Constats d'audit"

    def __str__(self):
        return f"{self.audit.code} — {self.get_gravite_display()}"


class Duer(models.Model):
    """Document unique d'évaluation des risques : versionné par (année, périmètre), scellé à l'approbation."""

    class Statut(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        APPROUVE = "approuve", "Approuvé"

    #: Revue au moins annuelle (obligation légale du DUER).
    REVUE_JOURS = 365

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    annee = models.PositiveSmallIntegerField(verbose_name="Année")
    perimetre = models.CharField(max_length=200, verbose_name="Périmètre (site / unité)")
    version = models.PositiveSmallIntegerField(default=1, verbose_name="Version")
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.BROUILLON, verbose_name="Statut")
    approuve_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Approuvé par",
    )
    approuve_le = models.DateTimeField(null=True, blank=True, verbose_name="Approuvé le")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-annee", "-version"]
        verbose_name = "DUER"
        verbose_name_plural = "DUER"
        constraints = [models.UniqueConstraint(fields=["annee", "perimetre", "version"], name="uniq_duer_version")]

    def __str__(self):
        return f"{self.code} — {self.perimetre} {self.annee} v{self.version}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = HseSequence.next_for("DUER", "DUER")
            self.version = (
                Duer.objects.filter(annee=self.annee, perimetre=self.perimetre).aggregate(m=models.Max("version"))["m"] or 0
            ) + 1
        return super().save(*args, **kwargs)

    @property
    def a_revoir(self):
        if self.statut != self.Statut.APPROUVE or not self.approuve_le:
            return False
        return (timezone.now() - self.approuve_le).days > self.REVUE_JOURS


class PlanUrgence(models.Model):
    """Plan d'urgence / d'intervention (ISO 14001, ISO 45001) avec périodicité d'exercice."""

    class TypePlan(models.TextChoices):
        INCENDIE = "incendie", "Incendie / évacuation"
        DEVERSEMENT = "deversement", "Déversement / pollution"
        MEDICAL = "medical", "Urgence médicale"
        ATEX = "atex", "Explosion / ATEX"
        AUTRE = "autre", "Autre"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    type_plan = models.CharField(max_length=12, choices=TypePlan.choices, default=TypePlan.INCENDIE, verbose_name="Type")
    intitule = models.CharField(max_length=200, verbose_name="Intitulé")
    perimetre = models.CharField(max_length=200, blank=True, verbose_name="Site / périmètre")
    periodicite_mois = models.PositiveSmallIntegerField(
        default=12, validators=[MinValueValidator(1)], verbose_name="Périodicité des exercices (mois)",
    )
    actif = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["intitule"]
        verbose_name = "Plan d'urgence"
        verbose_name_plural = "Plans d'urgence"

    def __str__(self):
        return f"{self.code} — {self.intitule}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = HseSequence.next_for("PUR", "PUR")
        return super().save(*args, **kwargs)

    @property
    def dernier_exercice(self):
        ex = self.exercices.order_by("-date_exercice").first()
        return ex.date_exercice if ex else None

    @property
    def prochain_exercice(self):
        dernier = self.dernier_exercice
        if not dernier:
            return None
        total = dernier.month - 1 + self.periodicite_mois
        annee, mois = dernier.year + total // 12, total % 12 + 1
        return dernier.replace(year=annee, month=mois, day=min(dernier.day, monthrange(annee, mois)[1]))

    @property
    def en_retard(self):
        if not self.actif:
            return False
        prochain = self.prochain_exercice
        return prochain is None or prochain < timezone.localdate()


class ExerciceUrgence(models.Model):
    """Exercice (simulation) d'un plan d'urgence, avec résultat et observations."""

    class Resultat(models.TextChoices):
        SATISFAISANT = "satisfaisant", "Satisfaisant"
        INSUFFISANT = "insuffisant", "Insuffisant"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan = models.ForeignKey(PlanUrgence, on_delete=models.CASCADE, related_name="exercices", verbose_name="Plan")
    date_exercice = models.DateField(verbose_name="Date de l'exercice")
    participants = models.PositiveIntegerField(default=0, verbose_name="Participants")
    resultat = models.CharField(max_length=12, choices=Resultat.choices, default=Resultat.SATISFAISANT, verbose_name="Résultat")
    observations = models.TextField(blank=True, verbose_name="Observations / axes d'amélioration")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_exercice"]
        verbose_name = "Exercice d'urgence"
        verbose_name_plural = "Exercices d'urgence"

    def __str__(self):
        return f"{self.plan.code} — {self.date_exercice}"

    def clean(self):
        if self.date_exercice and self.date_exercice > timezone.localdate():
            raise ValidationError({"date_exercice": "Un exercice ne peut pas être daté dans le futur."})
        if self.resultat == self.Resultat.INSUFFISANT and not (self.observations or "").strip():
            raise ValidationError({"observations": "Observations obligatoires pour un exercice insuffisant."})


class AptitudeMedicale(models.Model):
    """Visite médicale d'aptitude (CDC M7-05 « certificats médicaux ») : résultat et validité par salarié."""

    class Resultat(models.TextChoices):
        APTE = "apte", "Apte"
        APTE_RESTRICTIONS = "apte_restrictions", "Apte avec restrictions"
        INAPTE = "inapte", "Inapte"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employe = models.ForeignKey("rh_paie.Employe", on_delete=models.PROTECT, related_name="aptitudes", verbose_name="Salarié")
    date_visite = models.DateField(verbose_name="Date de la visite")
    date_validite = models.DateField(null=True, blank=True, verbose_name="Valable jusqu'au")
    resultat = models.CharField(max_length=18, choices=Resultat.choices, default=Resultat.APTE, verbose_name="Résultat")
    restrictions = models.TextField(blank=True, verbose_name="Restrictions / aménagements")
    medecin = models.CharField(max_length=120, blank=True, verbose_name="Médecin du travail")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_visite"]
        verbose_name = "Aptitude médicale"
        verbose_name_plural = "Aptitudes médicales"

    def __str__(self):
        return f"{self.employe} — {self.get_resultat_display()} ({self.date_visite})"

    def clean(self):
        if self.date_validite and self.date_validite < self.date_visite:
            raise ValidationError({"date_validite": "La validité doit suivre la date de visite."})
        if self.resultat == self.Resultat.APTE_RESTRICTIONS and not self.restrictions.strip():
            raise ValidationError({"restrictions": "Préciser les restrictions."})


class ParametreHse(models.Model):
    """Paramètres M7 modifiables par ETSL (délais d'alerte) : défauts provisoires tant qu'ETSL ne les confirme pas."""

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
        verbose_name = "Paramètre HSE"
        verbose_name_plural = "Paramètres HSE"

    def __str__(self):
        return f"{self.code} = {self.valeur} {self.unite}"

    @property
    def est_provisoire(self):
        return self.statut_valeur != self.StatutValeur.CONFIRME


class ConsommationEnvironnement(models.Model):
    """Relevé mensuel d'une consommation (ISO 14001, CDC M7-06) ; les émissions se calculent par facteur paramétré."""

    class Ressource(models.TextChoices):
        ELECTRICITE = "electricite", "Électricité"
        GAZOLE = "gazole", "Gazole"
        ESSENCE = "essence", "Essence"
        GAZ = "gaz", "Gaz (GPL)"
        EAU = "eau", "Eau"

    UNITES = {"electricite": "kWh", "gazole": "L", "essence": "L", "gaz": "kg", "eau": "m³"}
    #: Ressource → paramètre HSE portant son facteur d'émission (kg CO2e par unité) ; l'eau n'en a pas.
    FACTEURS = {"electricite": "FE_ELECTRICITE", "gazole": "FE_GAZOLE", "essence": "FE_ESSENCE", "gaz": "FE_GAZ"}

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    ressource = models.CharField(max_length=12, choices=Ressource.choices, verbose_name="Ressource")
    periode = models.DateField(verbose_name="Mois (1er jour)")
    site = models.CharField(max_length=120, default="Siège / atelier", verbose_name="Site")
    quantite = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Quantité")
    source = models.CharField(max_length=200, blank=True, verbose_name="Source (facture, compteur…)")
    saisi_par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-periode", "ressource"]
        verbose_name = "Consommation environnementale"
        verbose_name_plural = "Consommations environnementales"
        constraints = [models.UniqueConstraint(fields=["ressource", "periode", "site"], name="hse_conso_unique_mois_site")]

    def __str__(self):
        return f"{self.get_ressource_display()} {self.periode:%m/%Y} : {self.quantite} {self.unite}"

    @property
    def unite(self):
        return self.UNITES.get(self.ressource, "")

    def clean(self):
        if self.quantite is not None and self.quantite < 0:
            raise ValidationError({"quantite": "La quantité ne peut pas être négative."})
        if self.periode and self.periode > timezone.localdate():
            raise ValidationError({"periode": "Le mois relevé ne peut pas être futur."})

    def save(self, *args, **kwargs):
        if self.periode:
            self.periode = self.periode.replace(day=1)
        if not self.code:
            self.code = HseSequence.next_for("ENV", "ENV")
        return super().save(*args, **kwargs)


class PlanReductionImpact(models.Model):
    """Plan de réduction d'impact environnemental (ISO 14001, CDC M7-06) : cible mesurée sur les consommations."""

    class Statut(models.TextChoices):
        EN_COURS = "en_cours", "En cours"
        ATTEINT = "atteint", "Objectif atteint"
        ABANDONNE = "abandonne", "Abandonné"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    objectif = models.CharField(max_length=200, verbose_name="Objectif")
    ressource = models.CharField(
        max_length=12, blank=True, choices=ConsommationEnvironnement.Ressource.choices,
        verbose_name="Consommation suivie (vide = objectif qualitatif)",
    )
    annee_reference = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Année de référence")
    annee_cible = models.PositiveSmallIntegerField(verbose_name="Année cible")
    reduction_cible_pct = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="Réduction visée (%)"
    )
    actions = models.TextField(blank=True, verbose_name="Actions prévues")
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.EN_COURS, verbose_name="Statut")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["annee_cible", "code"]
        verbose_name = "Plan de réduction d'impact"
        verbose_name_plural = "Plans de réduction d'impact"

    def __str__(self):
        return f"{self.code} — {self.objectif}"

    def clean(self):
        if self.ressource and (self.annee_reference is None or self.reduction_cible_pct is None):
            raise ValidationError({"reduction_cible_pct": "Un objectif chiffré exige l'année de référence et la réduction visée."})
        if self.annee_reference and self.annee_cible and self.annee_cible <= self.annee_reference:
            raise ValidationError({"annee_cible": "L'année cible doit suivre l'année de référence."})
        if self.reduction_cible_pct is not None and not (0 < self.reduction_cible_pct <= 100):
            raise ValidationError({"reduction_cible_pct": "La réduction visée est comprise entre 0 et 100 %."})

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = HseSequence.next_for("PRI", "PRI")
        return super().save(*args, **kwargs)


class RevueDirectionHse(models.Model):
    """Revue de direction HSE annuelle (ISO 45001 / 14001 §9.3) : bilan figé à la création, scellée et archivée en GED."""

    class Statut(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        VALIDEE = "validee", "Validée (scellée)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    annee = models.PositiveSmallIntegerField(unique=True, verbose_name="Année revue")
    date_revue = models.DateField(default=timezone.localdate, verbose_name="Date de la revue")
    participants = models.TextField(blank=True, verbose_name="Participants")
    conclusions = models.TextField(blank=True, verbose_name="Conclusions (efficacité du système HSE)")
    decisions = models.TextField(blank=True, verbose_name="Décisions et objectifs de l'année suivante")
    bilan = models.JSONField(default=dict, blank=True, verbose_name="Bilan annuel (données d'entrée)")
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.BROUILLON, verbose_name="Statut")
    validee_par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    validee_le = models.DateTimeField(null=True, blank=True)
    document = models.ForeignKey(
        "documents.Document", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        verbose_name="Compte rendu archivé (GED)",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-annee"]
        verbose_name = "Revue de direction HSE"
        verbose_name_plural = "Revues de direction HSE"

    def __str__(self):
        return f"{self.code} — revue {self.annee}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = HseSequence.next_for("RDD", "RDD")
        return super().save(*args, **kwargs)
