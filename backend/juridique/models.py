"""Module M12 — Juridique & GED (enrichissement) (RF-ERP-B0...B4).

Périmètre ARCHITECTURE §2.1 (M12) / MANUEL ch.3 & ch.8 : courrier & gestion
documentaire interne (§3.3, §3.5) · contrats & conventions (§3.6, §8.3) ·
réunions & comptes rendus (§3.7) · conformité (§3.8, §8.4) · archivage &
conservation (§3.9, §8.7 — 10 ans Oil & Gas) · contentieux (§8.5) ·
protections : cautions & assurances / sinistres (§8.6) · dossier
intra-groupe GLOBAL RENTAL (fil rouge compte 618).

L'app `juridique` enrichit le socle GED (`documents` / `workflow` / `registres`) :
chaque objet peut être rattaché à un `documents.Document` (pièce classée &
conservée) et passer par les circuits de validation (`RF-ERP-W1`). Codes additifs
`RF-ERP-B0`...`B4` — ne pas renuméroter les `RF-xx`/`H-xx`.
"""

import uuid

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from config.echeances import bande
from config.i18n import tr


class JuridiqueSequence(models.Model):
    """Numérotation séquentielle M12 (COU, CON, LIT, CAU, ASS, REU, GRD)."""

    kind = models.CharField(max_length=10, unique=True, verbose_name="Type")
    prefix = models.CharField(max_length=10, verbose_name="Préfixe")
    padding = models.PositiveSmallIntegerField(default=5, verbose_name="Zéro-padding")
    next_number = models.PositiveIntegerField(default=1, verbose_name="Prochain numéro")

    class Meta:
        verbose_name = "Séquence Juridique"
        verbose_name_plural = "Séquences Juridique"

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


class Courrier(models.Model):
    """Courrier — bureau d'ordre (§3.3) : correspondance entrante / sortante."""

    class Sens(models.TextChoices):
        ENTRANT = "entrant", "Entrant"
        SORTANT = "sortant", "Sortant"

    class Type(models.TextChoices):
        LETTRE = "lettre", "Lettre"
        EMAIL = "email", "E-mail"
        NOTE = "note", "Note interne"
        CONVOCATION = "convocation", "Convocation"
        PROCES = "proces", "Procès-verbal"
        AUTRE = "autre", "Autre"

    class Statut(models.TextChoices):
        RECU = "recu", "Reçu"
        ENREGISTRE = "enregistre", "Enregistré (bureau d'ordre)"
        CLASSE = "classe", "Classé & indexé"
        ARCHIVE = "archive", "Archivé & conservé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    sens = models.CharField(max_length=8, choices=Sens.choices, verbose_name="Sens")
    type = models.CharField(max_length=12, choices=Type.choices, verbose_name="Type")
    objet = models.CharField(max_length=250, verbose_name="Objet")
    reference = models.CharField(max_length=120, blank=True, verbose_name="Référence")
    tiers = models.ForeignKey(
        "referentiels.Partner",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="courriers",
        verbose_name="Correspondant",
    )
    expediteur = models.CharField(max_length=200, blank=True, verbose_name="Expéditeur")
    destinataire = models.CharField(max_length=200, blank=True, verbose_name="Destinataire")
    date_courrier = models.DateField(default=timezone.localdate, verbose_name="Date du courrier")
    date_reception = models.DateField(
        null=True, blank=True, verbose_name="Date de réception (entrant)"
    )
    statut = models.CharField(
        max_length=12, choices=Statut.choices, default=Statut.RECU, verbose_name="Statut"
    )
    document = models.ForeignKey(
        "documents.Document",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="courriers",
        verbose_name="Document classé (GED)",
    )
    notes = models.TextField(blank=True, verbose_name="Annotations")
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="courriers_juridique",
        verbose_name="Créé par",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_courrier", "-created_at"]
        verbose_name = "Courrier"
        verbose_name_plural = "Courriers (bureau d'ordre)"

    def __str__(self):
        return f"{self.code} — {self.objet}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = JuridiqueSequence.next_for("COU", "COU")
        return super().save(*args, **kwargs)

    def enregistrer(self):
        if self.statut != self.Statut.RECU:
            raise ValueError(tr("Courrier %(statut)s : déjà enregistré.") % {"statut": self.get_statut_display().lower()})
        self.statut = self.Statut.ENREGISTRE
        return self.save(update_fields=["statut", "updated_at"])

    def classer(self):
        # Un courrier archivé ne revient pas en arrière (traçabilité du bureau d'ordre, §3.3).
        if self.statut not in (self.Statut.RECU, self.Statut.ENREGISTRE):
            raise ValueError(tr("Courrier %(statut)s : classement impossible.") % {"statut": self.get_statut_display().lower()})
        if self.statut == self.Statut.RECU:
            self.enregistrer()
        self.statut = self.Statut.CLASSE
        return self.save(update_fields=["statut", "updated_at"])

    def archiver(self):
        if self.statut in (self.Statut.RECU,):
            raise ValueError("Enregistrez le courrier avant de l'archiver.")
        self.statut = self.Statut.ARCHIVE
        return self.save(update_fields=["statut", "updated_at"])


class Convention(models.Model):
    """Contrats & conventions (§3.6, §8.3) — cycle de vie et échéances."""

    class Type(models.TextChoices):
        MARCHE_TRAVAUX = "marche_travaux", "Marché de travaux"
        MAINTENANCE = "maintenance", "Contrat de maintenance"
        PRESTATION = "prestation", "Prestation de services"
        BAIL = "bail", "Bail / loyer"
        PARTENARIAT = "partenariat", "Partenariat / coopération"
        AVENANT = "avenant", "Avenant"
        AUTRE = "autre", "Autre"

    class Statut(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        EN_SIGNATURE = "en_signature", "En signature"
        SIGNE = "signe", "Signé (en cours de validité)"
        CLOTURE = "cloture", "Clôturé"
        RESILIE = "resilie", "Résilié"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    type = models.CharField(max_length=16, choices=Type.choices, verbose_name="Type")
    titre = models.CharField(max_length=250, verbose_name="Intitulé")
    partenaire = models.ForeignKey(
        "referentiels.Partner",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="conventions",
        verbose_name="Partenaire / cocontractant",
    )
    montant = models.DecimalField(
        max_digits=16, decimal_places=2, blank=True, null=True, verbose_name="Montant (FCFA)"
    )
    date_debut = models.DateField(verbose_name="Date de début")
    date_fin = models.DateField(verbose_name="Date de fin")
    renouvelable = models.BooleanField(default=False, verbose_name="Renouvelable")
    affaire = models.ForeignKey(
        "commercial.Affaire",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="conventions",
        verbose_name="Affaire M1",
    )
    statut = models.CharField(
        max_length=14, choices=Statut.choices, default=Statut.BROUILLON, verbose_name="Statut"
    )
    document = models.ForeignKey(
        "documents.Document",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="conventions_juridique",
        verbose_name="Convention signée (GED)",
    )
    commentaire = models.TextField(blank=True, verbose_name="Commentaire")
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="conventions_juridique",
        verbose_name="Créé par",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_fin"]
        verbose_name = "Convention / contrat"
        verbose_name_plural = "Conventions / contrats"

    def __str__(self):
        return f"{self.code} — {self.titre}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = JuridiqueSequence.next_for("CON", "CON")
        return super().save(*args, **kwargs)

    @property
    def days_left(self):
        return (self.date_fin - timezone.localdate()).days

    @property
    def expiry_status(self):
        """Créneau d'échéance : expiree / j0 / j15 / j30 / j60 / j90 / en_cours (RF-ERP-B0, EX-G-05)."""
        return bande(self.days_left)

    @property
    def a_renouveler(self):
        return self.days_left <= 90

    def signer(self):
        if self.statut not in (self.Statut.BROUILLON, self.Statut.EN_SIGNATURE):
            raise ValueError("Seule une convention brouillon / en signature peut être signée.")
        self.statut = self.Statut.SIGNE
        return self.save(update_fields=["statut", "updated_at"])

    def cloturer(self):
        if self.statut == self.Statut.CLOTURE:
            raise ValueError("Convention déjà clôturée.")
        self.statut = self.Statut.CLOTURE
        return self.save(update_fields=["statut", "updated_at"])

    def resilier(self):
        self.statut = self.Statut.RESILIE
        return self.save(update_fields=["statut", "updated_at"])


class Contentieux(models.Model):
    """Contentieux (§8.5) — procédures, phases, décision, archivage."""

    class Nature(models.TextChoices):
        COMMERCIAL = "commercial", "Commercial"
        SOCIAL = "social", "Social / prud'homal"
        FISCAL = "fiscal", "Fiscal"
        ASSURANCES = "assurances", "Assurances"
        FOURNISSEUR = "fournisseur", "Fournisseur / sous-traitant"
        CLIENT = "client", "Client"
        AUTRE = "autre", "Autre"

    class Phase(models.TextChoices):
        PRE_CONTENTIEUX = "pre_contentieux", "Pré-contentieux / mise en demeure"
        TRIBUNAL = "tribunal", "Instance (tribunal)"
        ARBITRAGE = "arbitrage", "Arbitrage"
        APPEL = "appel", "Appel"

    class Statut(models.TextChoices):
        OUVERT = "ouvert", "Ouvert"
        EN_INSTRUCTION = "en_instruction", "En instruction"
        GAGNE = "gagne", "Gagné"
        PERDU = "perdu", "Perdu"
        TRANSACTION = "transaction", "Transaction / accord"
        CLOTURE = "cloture", "Clôturé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    nature = models.CharField(max_length=14, choices=Nature.choices, verbose_name="Nature")
    objet = models.CharField(max_length=250, verbose_name="Objet du litige")
    partie_adverse = models.CharField(max_length=200, verbose_name="Partie adverse")
    conseil_ext = models.CharField(max_length=200, blank=True, verbose_name="Conseil / avocat")
    montant_en_jeu = models.DecimalField(
        max_digits=16, decimal_places=2, blank=True, null=True, verbose_name="Montant en jeu (FCFA)"
    )
    reference = models.CharField(max_length=120, blank=True, verbose_name="Référence")
    date_ouverture = models.DateField(default=timezone.localdate, verbose_name="Date d'ouverture")
    phase = models.CharField(
        max_length=20, choices=Phase.choices, default=Phase.PRE_CONTENTIEUX, verbose_name="Phase"
    )
    statut = models.CharField(
        max_length=20, choices=Statut.choices, default=Statut.OUVERT, verbose_name="Statut"
    )
    decision = models.TextField(blank=True, verbose_name="Décision / issue")
    # Écarts M12 : juridiction saisie (liste paramétrable) et cotation du risque (vue Risk).
    juridiction = models.CharField(max_length=200, blank=True, verbose_name="Juridiction")
    probabilite = models.CharField(
        max_length=10, blank=True, default="",
        choices=[("faible", "Faible"), ("moyenne", "Moyenne"), ("forte", "Forte"), ("certaine", "Certaine")],
        verbose_name="Probabilité de condamnation / perte",
    )
    document = models.ForeignKey(
        "documents.Document",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="contentieux_juridique",
        verbose_name="Dossier contentieux (GED)",
    )
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="contentieux_juridique",
        verbose_name="Créé par",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_ouverture"]
        verbose_name = "Contentieux"
        verbose_name_plural = "Contentieux"

    def __str__(self):
        return f"{self.code} — {self.objet}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = JuridiqueSequence.next_for("LIT", "LIT")
        return super().save(*args, **kwargs)

    def instruire(self):
        if self.statut not in (self.Statut.OUVERT, self.Statut.EN_INSTRUCTION):
            raise ValueError("Contentieux déjà traité.")
        self.statut = self.Statut.EN_INSTRUCTION
        return self.save(update_fields=["statut", "updated_at"])

    def cloturer(self, issue, decision=""):
        if self.statut == self.Statut.CLOTURE:
            raise ValueError("Contentieux déjà clôturé.")
        mapping = {
            "gagne": self.Statut.GAGNE,
            "perdu": self.Statut.PERDU,
            "transaction": self.Statut.TRANSACTION,
        }
        if issue not in mapping:
            raise ValueError("Issue attendue : gagne / perdu / transaction.")
        self.statut = mapping[issue]
        if decision:
            self.decision = decision
        return self.save(update_fields=["statut", "decision", "updated_at"])


class Caution(models.Model):
    """Protections (§8.6) — cautions & garanties bancaires."""

    class Type(models.TextChoices):
        BON_SOUMISSION = "bon_soumission", "Bon de soumission"
        BONNE_EXECUTION = "bonne_execution", "Bonne exécution"
        AVANCE = "avance", "Remboursement d'avance"
        RETENUE = "retenue", "Retenue de garantie"

    class Statut(models.TextChoices):
        EN_COURS = "en_cours", "En cours de validité"
        LEVEE = "levee", "Levée / restituée"
        APPELEE = "appelee", "Appelée"
        EXPIREE = "expiree", "Expirée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    type = models.CharField(max_length=18, choices=Type.choices, verbose_name="Type")
    emetteur = models.ForeignKey(
        "referentiels.Partner",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="cautions_emises",
        verbose_name="Émetteur (banque / assureur)",
    )
    beneficiaire = models.CharField(max_length=200, verbose_name="Bénéficiaire / maître d'ouvrage")
    objet = models.CharField(max_length=250, verbose_name="Objet de la garantie")
    montant = models.DecimalField(
        max_digits=16, decimal_places=2, verbose_name="Montant (FCFA)"
    )
    numero_instrument = models.CharField(
        max_length=120, blank=True, verbose_name="N° instrument bancaire"
    )
    date_emission = models.DateField(verbose_name="Date d'émission")
    date_echeance = models.DateField(verbose_name="Date d'échéance")
    statut = models.CharField(
        max_length=10, choices=Statut.choices, default=Statut.EN_COURS, verbose_name="Statut"
    )
    convention = models.ForeignKey(
        Convention,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="cautions",
        verbose_name="Convention liée",
    )
    document = models.ForeignKey(
        "documents.Document",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="cautions_juridique",
        verbose_name="Garantie (GED)",
    )
    # Validation DG obligatoire (CDC M12 §14.8).
    valide_dg_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        verbose_name="Validé par la Direction Générale",
    )
    valide_dg_le = models.DateTimeField(null=True, blank=True, verbose_name="Date de validation DG")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_echeance"]
        verbose_name = "Caution / garantie"
        verbose_name_plural = "Cautions / garanties"

    def __str__(self):
        return f"{self.code} — {self.get_type_display()}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = JuridiqueSequence.next_for("CAU", "CAU")
        return super().save(*args, **kwargs)

    @property
    def days_left(self):
        return (self.date_echeance - timezone.localdate()).days

    @property
    def expiry_status(self):
        return bande(self.days_left)

    def lever(self):
        if self.statut != self.Statut.EN_COURS:
            raise ValueError("Seule une caution en cours peut être levée / restituée.")
        self.statut = self.Statut.LEVEE
        return self.save(update_fields=["statut", "updated_at"])

    def appeler(self):
        if self.statut != self.Statut.EN_COURS:
            raise ValueError("Seule une caution en cours peut être appelée.")
        self.statut = self.Statut.APPELEE
        return self.save(update_fields=["statut", "updated_at"])


class Assurance(models.Model):
    """Protections (§8.6) — polices d'assurance & échéances, sinistres."""

    class Type(models.TextChoices):
        RC_PRO = "rc_pro", "Responsabilité civile professionnelle"
        TR_CHANTIER = "tous_risques", "Tous risques chantier"
        FLOTTE = "flotte", "Flotte automobile"
        ENGINS = "engins", "Engins & matériel"
        BRI_MACHINE = "bris_machine", "Bris de machine"
        VIE_GROUPE = "vie_groupe", "Prévoyance / vie de groupe"
        MULTIRISQUE = "multirisque", "Multirisque immeuble"
        AUTRE = "autre", "Autre"

    class Statut(models.TextChoices):
        ACTIVE = "active", "Active"
        A_RENOUVELER = "a_renouveler", "À renouveler (échéance proche)"
        EXPIREE = "expiree", "Expirée"
        RESILIEE = "resiliee", "Résiliée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    type = models.CharField(max_length=16, choices=Type.choices, verbose_name="Type")
    assureur = models.ForeignKey(
        "referentiels.Partner",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="assurances",
        verbose_name="Assureur",
    )
    numero_police = models.CharField(max_length=120, verbose_name="N° police")
    prime_annuelle = models.DecimalField(
        max_digits=16, decimal_places=2, blank=True, null=True, verbose_name="Prime annuelle (FCFA)"
    )
    date_debut = models.DateField(verbose_name="Date d'effet")
    date_echeance = models.DateField(verbose_name="Échéance")
    objets_couverts = models.CharField(
        max_length=250, blank=True, verbose_name="Objets couverts"
    )
    statut = models.CharField(
        max_length=14, choices=Statut.choices, default=Statut.ACTIVE, verbose_name="Statut"
    )
    nb_sinistres = models.PositiveSmallIntegerField(
        default=0, verbose_name="Nombre de sinistres"
    )
    sinistres = models.JSONField(default=list, blank=True, verbose_name="Sinistres déclarés")
    document = models.ForeignKey(
        "documents.Document",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="assurances_juridique",
        verbose_name="Police (GED)",
    )
    # Validation DG obligatoire (CDC M12 §14.8).
    valide_dg_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        verbose_name="Validé par la Direction Générale",
    )
    valide_dg_le = models.DateTimeField(null=True, blank=True, verbose_name="Date de validation DG")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_echeance"]
        verbose_name = "Assurance"
        verbose_name_plural = "Assurances"

    def __str__(self):
        return f"{self.code} — {self.numero_police}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = JuridiqueSequence.next_for("ASS", "ASS")
        return super().save(*args, **kwargs)

    @property
    def days_left(self):
        return (self.date_echeance - timezone.localdate()).days

    @property
    def expiry_status(self):
        return bande(self.days_left)

    def renouveler(self, date_echeance=None):
        if self.statut == self.Statut.RESILIEE:
            raise ValueError("Police résiliée : souscrivez une nouvelle police plutôt que de la renouveler.")
        if date_echeance and self.date_echeance and date_echeance <= self.date_echeance:
            raise ValueError("La nouvelle échéance doit être postérieure à l'échéance en cours.")
        self.statut = self.Statut.ACTIVE
        if date_echeance:
            self.date_echeance = date_echeance
        return self.save(update_fields=["statut", "date_echeance", "updated_at"])

    def resilier(self):
        if self.statut == self.Statut.RESILIEE:
            raise ValueError("Assurance déjà résiliée.")
        self.statut = self.Statut.RESILIEE
        return self.save(update_fields=["statut", "updated_at"])

    def declarer_sinistre(self, detail):
        self.nb_sinistres += 1
        self.sinistres = (self.sinistres or []) + [
            {"date": timezone.localdate().isoformat(), "detail": detail}
        ]
        return self.save(update_fields=["nb_sinistres", "sinistres", "updated_at"])


class Reunion(models.Model):
    """Réunions & comptes rendus (§3.7) — décisions suivies."""

    class Type(models.TextChoices):
        COMITE_DIRECTION = "comite_direction", "Comité de direction"
        REVUE_CHANTIER = "revue_chantier", "Réunion de chantier"
        REVUE_ATELIER = "revue_atelier", "Réunion d'atelier"
        REVUE_QUALITE = "revue_qualite", "Revue qualité"
        SECURITE = "securite", "Réunion sécurité (HSE)"
        RETROPLANNING = "retroplanning", "Revue planning / rétroplanning"
        LANCEMENT = "lancement", "Réunion de lancement d'affaire (CRRL)"
        AUTRE = "autre", "Autre"

    class Statut(models.TextChoices):
        PLANIFIEE = "planifiee", "Planifiée"
        TENUE = "tenue", "Tenue"
        CLOTUREE = "cloturee", "Clôturée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    type = models.CharField(max_length=20, choices=Type.choices, verbose_name="Type")
    objet = models.CharField(max_length=250, verbose_name="Objet / ordre du jour")
    date_reunion = models.DateTimeField(verbose_name="Date")
    lieu = models.CharField(max_length=200, blank=True, verbose_name="Lieu")
    animateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reunions_animees",
        verbose_name="Animateur",
    )
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="reunions_participations",
        verbose_name="Participants",
    )
    compte_rendu = models.ForeignKey(
        "documents.Document",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="reunions_juridique",
        verbose_name="Compte rendu (GED)",
    )
    # Réunion de lancement : rattachée à l'affaire (CRRL exigé au démarrage, clôture M1).
    affaire = models.ForeignKey(
        "commercial.Affaire", blank=True, null=True, on_delete=models.SET_NULL,
        related_name="reunions", verbose_name="Affaire",
    )
    statut = models.CharField(
        max_length=10, choices=Statut.choices, default=Statut.PLANIFIEE, verbose_name="Statut"
    )
    decisions = models.JSONField(
        default=list, blank=True, verbose_name="Décisions & actions"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_reunion"]
        verbose_name = "Réunion"
        verbose_name_plural = "Réunions"

    def __str__(self):
        return f"{self.code} — {self.objet}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = JuridiqueSequence.next_for("REU", "REU")
        return super().save(*args, **kwargs)

    @property
    def nb_decisions(self):
        return len(self.decisions or [])

    @property
    def nb_decisions_ouvertes(self):
        return sum(
            1 for d in (self.decisions or []) if d.get("statut") in ("a_faire", "en_cours")
        )

    def tenir(self, compte_rendu=None):
        if self.statut != self.Statut.PLANIFIEE:
            raise ValueError("Réunion déjà tenue / clôturée.")
        self.statut = self.Statut.TENUE
        if compte_rendu:
            self.compte_rendu = compte_rendu
        return self.save(update_fields=["statut", "compte_rendu", "updated_at"])

    def cloturer(self):
        if self.statut == self.Statut.CLOTUREE:
            raise ValueError("Réunion déjà clôturée.")
        self.statut = self.Statut.CLOTUREE
        return self.save(update_fields=["statut", "updated_at"])


class DossierGlobalRental(models.Model):
    """Dossier intra-groupe GLOBAL RENTAL (fil rouge compte 618) — M12."""

    class Statut(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        OUVERT = "ouvert", "Ouvert"
        CLOTURE = "cloture", "Clôturé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    partenaire_gr = models.ForeignKey(
        "referentiels.Partner",
        on_delete=models.PROTECT,
        related_name="dossiers_gr",
        verbose_name="Partenaire GLOBAL RENTAL",
    )
    affaire = models.ForeignKey(
        "commercial.Affaire",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="dossiers_gr",
        verbose_name="Affaire M1",
    )
    reference_contrat = models.CharField(
        max_length=120, blank=True, verbose_name="Référence contrat / convention"
    )
    objet = models.CharField(max_length=250, verbose_name="Objet de la prestation")
    montant_estime = models.DecimalField(
        max_digits=16, decimal_places=2, blank=True, null=True, verbose_name="Montant estimé (FCFA)"
    )
    signe_618 = models.BooleanField(
        default=False, verbose_name="Refacturation imputée au compte 618000"
    )
    date_debut = models.DateField(verbose_name="Date de début")
    date_fin = models.DateField(verbose_name="Date de fin")
    statut = models.CharField(
        max_length=10, choices=Statut.choices, default=Statut.BROUILLON, verbose_name="Statut"
    )
    references_documents = models.JSONField(
        default=list, blank=True, verbose_name="Références BC / GR / BL / retour GR"
    )
    # Écarts M12 : mandat intra-groupe et revue périodique (contrôle « à jour »).
    mandat_reference = models.CharField(max_length=120, blank=True, verbose_name="Référence du mandat")
    mandat_date_fin = models.DateField(null=True, blank=True, verbose_name="Fin de validité du mandat")
    date_revue = models.DateField(null=True, blank=True, verbose_name="Dernière revue du dossier")
    revu_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Revu par",
    )
    commentaire = models.TextField(blank=True, verbose_name="Commentaire")
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="dossiers_gr",
        verbose_name="Créé par",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_fin"]
        verbose_name = "Dossier intra-groupe GLOBAL RENTAL"
        verbose_name_plural = "Dossiers intra-groupe GLOBAL RENTAL"

    def __str__(self):
        return f"{self.code} — {self.objet}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = JuridiqueSequence.next_for("GRD", "GRD")
        return super().save(*args, **kwargs)

    def ouvrir(self):
        if self.partenaire_gr and not self.partenaire_gr.is_global_rental:
            raise ValueError("Le partenaire doit être flaggé GLOBAL RENTAL (RF-ERP-B4).")
        self.statut = self.Statut.OUVERT
        return self.save(update_fields=["statut", "updated_at"])

    def cloturer(self):
        if self.statut != self.Statut.OUVERT:
            raise ValueError("Seul un dossier ouvert peut être clôturé.")
        self.statut = self.Statut.CLOTURE
        return self.save(update_fields=["statut", "updated_at"])

class LienDocument(models.Model):
    """Lien entre un document GED et un objet métier M1-M11 (recherche juridique interconnectée, CDC M12).

    Lien générique (type « app.modele » + identifiant) restreint à une liste blanche (`services.OBJETS_LIEABLES`) ;
    le libellé de l'objet est figé à la création pour que la recherche n'ait pas à parcourir les modules.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        "documents.Document", on_delete=models.CASCADE, related_name="liens_metier", verbose_name="Document"
    )
    objet_type = models.CharField(max_length=60, verbose_name="Type d'objet (app.modele)")
    objet_id = models.CharField(max_length=64, verbose_name="Identifiant de l'objet")
    objet_label = models.CharField(max_length=255, verbose_name="Libellé de l'objet")
    module = models.CharField(max_length=4, verbose_name="Module ERP")
    note = models.CharField(max_length=255, blank=True, verbose_name="Note")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Lié par",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Lien document ↔ objet métier"
        verbose_name_plural = "Liens documents ↔ objets métier"
        constraints = [
            models.UniqueConstraint(fields=["document", "objet_type", "objet_id"], name="lien_document_uniq"),
        ]
        indexes = [models.Index(fields=["objet_type", "objet_id"])]

    def __str__(self):
        return f"{self.document_id} → {self.objet_type}:{self.objet_label}"


# --------------------------------------------------------------------------------------------------
# Écarts M12 (2026-10) : paramètres provisoires, suivi contentieux, pièces de dossier
# --------------------------------------------------------------------------------------------------
class ParametreJuridique(models.Model):
    """Paramètre M12 modifiable à l'écran : valeur provisoire tant qu'ETSL ne l'a pas confirmée."""

    cle = models.SlugField(max_length=60, unique=True, verbose_name="Clé")
    libelle = models.CharField(max_length=200, verbose_name="Libellé")
    valeur = models.JSONField(default=dict, blank=True, verbose_name="Valeur")
    provisoire = models.BooleanField(default=True, verbose_name="Provisoire (à confirmer par ETSL)")
    modifie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Modifié par",
    )
    modifie_le = models.DateTimeField(null=True, blank=True, verbose_name="Modifié le")
    confirme_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Confirmé par",
    )
    confirme_le = models.DateTimeField(null=True, blank=True, verbose_name="Confirmé le")

    class Meta:
        ordering = ["cle"]
        verbose_name = "Paramètre juridique"
        verbose_name_plural = "Paramètres juridiques"

    def __str__(self):
        return f"{self.cle}{' (provisoire)' if self.provisoire else ''}"


class JalonContentieux(models.Model):
    """Jalon de l'échéancier d'un contentieux (audience, dépôt de conclusions, délai d'appel…)."""

    class Statut(models.TextChoices):
        A_VENIR = "a_venir", "À venir"
        REALISE = "realise", "Réalisé"
        ANNULE = "annule", "Annulé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contentieux = models.ForeignKey(
        Contentieux, on_delete=models.CASCADE, related_name="jalons", verbose_name="Contentieux"
    )
    libelle = models.CharField(max_length=200, verbose_name="Jalon")
    date_prevue = models.DateField(verbose_name="Date prévue")
    date_realisee = models.DateField(null=True, blank=True, verbose_name="Date de réalisation")
    statut = models.CharField(max_length=8, choices=Statut.choices, default=Statut.A_VENIR, verbose_name="Statut")
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Créé par",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date_prevue"]
        verbose_name = "Jalon de contentieux"
        verbose_name_plural = "Jalons de contentieux"

    def __str__(self):
        return f"{self.contentieux.code} — {self.libelle}"

    @property
    def days_left(self):
        return (self.date_prevue - timezone.localdate()).days


class ActionContentieux(models.Model):
    """Journal chronologique (inaltérable) des actions menées sur un contentieux."""

    class Type(models.TextChoices):
        AUDIENCE = "audience", "Audience"
        CONCLUSIONS = "conclusions", "Conclusions / mémoire"
        COURRIER = "courrier", "Courrier / mise en demeure"
        EXPERTISE = "expertise", "Expertise"
        NEGOCIATION = "negociation", "Négociation"
        DECISION = "decision", "Décision"
        PHASE = "phase", "Changement de phase"
        STATUT = "statut", "Changement de statut"
        AUTRE = "autre", "Autre"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contentieux = models.ForeignKey(
        Contentieux, on_delete=models.CASCADE, related_name="actions", verbose_name="Contentieux"
    )
    date_action = models.DateField(default=timezone.localdate, verbose_name="Date")
    type = models.CharField(max_length=12, choices=Type.choices, default=Type.AUTRE, verbose_name="Type")
    description = models.TextField(verbose_name="Description")
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Auteur",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_action", "-created_at"]
        verbose_name = "Action de contentieux"
        verbose_name_plural = "Journal des actions de contentieux"

    def __str__(self):
        return f"{self.contentieux.code} — {self.get_type_display()}"


class PieceDossier(models.Model):
    """Pièce versée à un dossier (contentieux, convention, dossier GR) : un document GED par pièce requise."""

    class DossierType(models.TextChoices):
        CONTENTIEUX = "contentieux", "Contentieux"
        CONVENTION = "convention", "Convention / contrat"
        GR = "gr", "Dossier GLOBAL RENTAL"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dossier_type = models.CharField(max_length=12, choices=DossierType.choices, verbose_name="Type de dossier")
    dossier_id = models.CharField(max_length=64, verbose_name="Identifiant du dossier")
    piece = models.CharField(max_length=60, verbose_name="Pièce")
    document = models.ForeignKey(
        "documents.Document", on_delete=models.PROTECT, related_name="pieces_dossier",
        verbose_name="Document (GED)",
    )
    ajoute_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Ajoutée par",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["dossier_type", "piece"]
        verbose_name = "Pièce de dossier"
        verbose_name_plural = "Pièces de dossier"
        constraints = [
            models.UniqueConstraint(fields=["dossier_type", "dossier_id", "piece"], name="piece_dossier_uniq"),
        ]

    def __str__(self):
        return f"{self.dossier_type}:{self.dossier_id} — {self.piece}"
