"""Module M10 — Comptabilité générale SYSCOHADA & Trésorerie (RF-ERP-90…94).

Périmètre SPEC §2.1 (M10) / MANUEL ch.4 : comptabilité SYSCOHADA révisée &
analytique · trésorerie (comptes bancaires, relevés CFONB / MT940, rapprochement
bancaire) · TVA 18 % · refacturations intra-groupe GR (compte 618) · dépenses &
engagements · factures fournisseurs & paiements · contrôle interne · conservation
des pièces (proc. 4.3–4.8). Les écritures passent par `accounting_kernel`
(journaux, périodes, écritures immuables — RF-ERP-90) : M10 apporte l'étage
opérationnel (trésorerie, TVA, engagements, paiements) et comptabilise via le
noyau. Reprise des données SAGE : import par fichiers via `integrations`
(GLConnector, H-04) — jamais d'écriture directe dans les journaux.
"""

from datetime import date
from decimal import Decimal
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone


class ComptabiliteSequence(models.Model):
    """Numérotation séquentielle par type (BQ, REL, RAP, TVA, ENG, PAI, CON)."""

    kind = models.CharField(max_length=10, unique=True, verbose_name="Type")
    prefix = models.CharField(max_length=10, verbose_name="Préfixe")
    padding = models.PositiveSmallIntegerField(default=5, verbose_name="Zéro-padding")
    next_number = models.PositiveIntegerField(default=1, verbose_name="Prochain numéro")

    class Meta:
        verbose_name = "Séquence Comptabilité"
        verbose_name_plural = "Séquences Comptabilité"

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


class TauxTva(models.Model):
    """Taux de TVA applicable (RF-ERP-90 : 18 %, SYSCOHADA)."""

    code = models.CharField(max_length=10, unique=True, verbose_name="Code")
    label = models.CharField(max_length=120, verbose_name="Libellé")
    taux = models.DecimalField(max_digits=6, decimal_places=2, verbose_name="Taux (%)")
    compte_collecte = models.ForeignKey(
        "referentiels.Account",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Compte TVA collectée (44x)",
    )
    compte_deductible = models.ForeignKey(
        "referentiels.Account",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Compte TVA déductible (44x)",
    )
    is_default = models.BooleanField(default=False, verbose_name="Taux par défaut")
    is_active = models.BooleanField(default=True, verbose_name="Actif")

    class Meta:
        ordering = ["code"]
        verbose_name = "Taux de TVA"
        verbose_name_plural = "Taux de TVA"

    def __str__(self):
        return f"{self.code} — {self.taux}%"


class CompteBancaire(models.Model):
    """Compte bancaire de trésorerie (RF-ERP-91, CFONB / MT940)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    label = models.CharField(max_length=200, verbose_name="Désignation")
    banque = models.CharField(max_length=120, verbose_name="Banque")
    numero = models.CharField(max_length=80, blank=True, verbose_name="N° de compte / IBAN")
    compte_comptable = models.ForeignKey(
        "referentiels.Account",
        on_delete=models.PROTECT,
        related_name="comptes_bancaires",
        verbose_name="Compte comptable (512x)",
    )
    devise = models.ForeignKey(
        "referentiels.Currency",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="comptes_bancaires",
        verbose_name="Devise",
    )
    solde_initial = models.DecimalField(
        max_digits=16, decimal_places=2, default=0, verbose_name="Solde initial"
    )
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "Compte bancaire"
        verbose_name_plural = "Comptes bancaires"

    def __str__(self):
        return f"{self.code} — {self.label}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = ComptabiliteSequence.next_for("BQ", "BQ")
        return super().save(*args, **kwargs)


class ReleveBancaire(models.Model):
    """Relevé bancaire — import CFONB / MT940 ou saisie manuelle (RF-ERP-91)."""

    class Statut(models.TextChoices):
        IMPORTE = "importe", "Importé"
        VALIDE = "valide", "Validé"

    class Source(models.TextChoices):
        CFONB = "cfonb", "CFONB"
        MT940 = "mt940", "MT940"
        MANUEL = "manuel", "Saisie manuelle"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    compte_bancaire = models.ForeignKey(
        CompteBancaire,
        on_delete=models.PROTECT,
        related_name="releves",
        verbose_name="Compte bancaire",
    )
    date_debut = models.DateField(verbose_name="Date début")
    date_fin = models.DateField(verbose_name="Date fin")
    solde_initial = models.DecimalField(
        max_digits=16, decimal_places=2, default=0, verbose_name="Solde initial"
    )
    solde_final = models.DecimalField(
        max_digits=16, decimal_places=2, default=0, verbose_name="Solde final"
    )
    statut = models.CharField(
        max_length=10, choices=Statut.choices, default=Statut.IMPORTE, verbose_name="Statut"
    )
    source = models.CharField(
        max_length=10, choices=Source.choices, default=Source.MANUEL, verbose_name="Source"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="releves_bancaires",
    )
    empreinte = models.CharField(
        max_length=64, blank=True, db_index=True, verbose_name="Empreinte SHA-256 du fichier importé",
        help_text="Empêche d'importer deux fois le même fichier pour un compte.",
    )
    anomalies = models.JSONField(default=list, blank=True, verbose_name="Anomalies détectées à l'import")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_fin"]
        verbose_name = "Relevé bancaire"
        verbose_name_plural = "Relevés bancaires"

    def __str__(self):
        return f"{self.code} — {self.compte_bancaire.label}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = ComptabiliteSequence.next_for("REL", "REL")
        return super().save(*args, **kwargs)

    @property
    def total_debit(self):
        return sum((ligne.debit for ligne in self.lignes.all()), Decimal("0"))

    @property
    def total_credit(self):
        return sum((ligne.credit for ligne in self.lignes.all()), Decimal("0"))

    @property
    def total_rapprochees(self):
        return self.lignes.filter(rapprochee=True).count()


class LigneReleve(models.Model):
    """Ligne de relevé bancaire — rapprochée ou non (RF-ERP-91)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    releve = models.ForeignKey(
        ReleveBancaire, on_delete=models.CASCADE, related_name="lignes", verbose_name="Relevé"
    )
    date = models.DateField(verbose_name="Date")
    libelle = models.CharField(max_length=250, verbose_name="Libellé")
    reference = models.CharField(max_length=120, blank=True, verbose_name="Référence")
    debit = models.DecimalField(max_digits=16, decimal_places=2, default=0, verbose_name="Débit")
    credit = models.DecimalField(max_digits=16, decimal_places=2, default=0, verbose_name="Crédit")
    rapprochee = models.BooleanField(default=False, verbose_name="Rapprochée")
    paiement = models.ForeignKey(
        "Paiement", null=True, blank=True, on_delete=models.SET_NULL, related_name="lignes_releve",
        verbose_name="Paiement rapproché",
    )

    class Meta:
        ordering = ["date", "id"]
        verbose_name = "Ligne de relevé"
        verbose_name_plural = "Lignes de relevé"

    def __str__(self):
        return f"[{self.date:%d/%m}] {self.libelle} — D{self.debit} C{self.credit}"


class RapprochementBancaire(models.Model):
    """Rapprochement bancaire : rapproche les lignes de relevé (RF-ERP-91)."""

    class Statut(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        VALIDE = "valide", "Validé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    compte_bancaire = models.ForeignKey(
        CompteBancaire,
        on_delete=models.PROTECT,
        related_name="rapprochements",
        verbose_name="Compte bancaire",
    )
    date = models.DateField(default=timezone.localdate, verbose_name="Date")
    statut = models.CharField(
        max_length=10, choices=Statut.choices, default=Statut.BROUILLON, verbose_name="Statut"
    )
    notes = models.TextField(blank=True, verbose_name="Notes")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="rapprochements_bancaires",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]
        verbose_name = "Rapprochement bancaire"
        verbose_name_plural = "Rapprochements bancaires"

    def __str__(self):
        return f"{self.code} — {self.compte_bancaire.label}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = ComptabiliteSequence.next_for("RAP", "RAP")
        return super().save(*args, **kwargs)

    @property
    def total_lignes(self):
        return self.lignes.count()


class LigneRapprochement(models.Model):
    """Une ligne de rapprochement : une ligne de relevé que l'on rapproche."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rapprochement = models.ForeignKey(
        RapprochementBancaire,
        on_delete=models.CASCADE,
        related_name="lignes",
        verbose_name="Rapprochement",
    )
    ligne_releve = models.ForeignKey(
        LigneReleve,
        on_delete=models.CASCADE,
        related_name="rapprochements",
        verbose_name="Ligne de relevé",
    )

    class Meta:
        verbose_name = "Ligne de rapprochement"
        verbose_name_plural = "Lignes de rapprochement"
        constraints = [
            models.UniqueConstraint(
                fields=["rapprochement", "ligne_releve"],
                name="uniq_rapprochement_ligne_releve",
            )
        ]

    def __str__(self):
        return f"{self.rapprochement.code} → {self.ligne_releve.libelle}"


class Engagement(models.Model):
    """Engagement de dépense (proc. 4.3) — avant engagement, circuit RF-ERP-W1."""

    class Statut(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        SOUMIS = "soumis", "Soumis pour visa"
        APPROUVE = "approuve", "Approuvé"
        ANNULE = "annule", "Annulé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    objet = models.CharField(max_length=250, verbose_name="Objet de la dépense")
    montant = models.DecimalField(max_digits=16, decimal_places=2, verbose_name="Montant")
    compte_depense = models.ForeignKey(
        "referentiels.Account",
        on_delete=models.PROTECT,
        related_name="engagements",
        verbose_name="Compte de dépense (6xx)",
    )
    fournisseur = models.ForeignKey(
        "referentiels.Partner",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="engagements",
        verbose_name="Fournisseur",
    )
    statut = models.CharField(
        max_length=10, choices=Statut.choices, default=Statut.BROUILLON, verbose_name="Statut"
    )
    date_engagement = models.DateField(null=True, blank=True, verbose_name="Date d'engagement")
    demande_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="engagements_demandes",
        verbose_name="Demandé par",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Engagement de dépense"
        verbose_name_plural = "Engagements de dépense"

    def __str__(self):
        return f"{self.code} — {self.objet}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = ComptabiliteSequence.next_for("ENG", "ENG")
        return super().save(*args, **kwargs)

    @property
    def total_paye(self):
        """Montant effectivement décaissé : paiements VALIDÉS uniquement (ni brouillons ni annulés)."""
        return sum(
            (p.montant for p in self.paiements.filter(statut="valide")), Decimal("0")
        )

    @property
    def solde(self):
        return self.montant - self.total_paye


class Paiement(models.Model):
    """Règlement fournisseur / encaissement (proc. 4.5) — comptabilisé via le noyau."""

    class Sens(models.TextChoices):
        SORTIE = "sortie", "Décaissement (fournisseur)"
        ENTREE = "entree", "Encaissement (client / cession)"

    class Mode(models.TextChoices):
        ESPECES = "especes", "Espèces"
        CHEQUE = "cheque", "Chèque"
        VIREMENT = "virement", "Virement"
        CFONB = "cfonb", "CFONB / MT940"
        AUTRE = "autre", "Autre"

    class Statut(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        VALIDE = "valide", "Validé"
        ANNULE = "annule", "Annulé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    sens = models.CharField(max_length=8, choices=Sens.choices, verbose_name="Sens")
    mode = models.CharField(max_length=10, choices=Mode.choices, verbose_name="Mode")
    montant = models.DecimalField(max_digits=16, decimal_places=2, verbose_name="Montant")
    date = models.DateField(default=timezone.localdate, verbose_name="Date de paiement")
    compte_bancaire = models.ForeignKey(
        CompteBancaire,
        on_delete=models.PROTECT,
        related_name="paiements",
        verbose_name="Compte bancaire",
    )
    engagement = models.ForeignKey(
        Engagement,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="paiements",
        verbose_name="Engagement",
    )
    tiers = models.ForeignKey(
        "referentiels.Partner",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="paiements",
        verbose_name="Tiers",
    )
    facture = models.ForeignKey(
        "achats.PurchaseInvoice",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="paiements",
        verbose_name="Facture fournisseur",
    )
    imputation_618 = models.BooleanField(
        default=False, verbose_name="Refacturation intra-groupe (compte 618)"
    )
    analytic_account = models.ForeignKey(
        "referentiels.AnalyticAccount", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Imputation analytique (affaire / chantier / centre)",
        help_text="À défaut, reprise de l'imputation du bon de commande de la facture fournisseur (M10 → M11).",
    )
    retenue_source = models.BooleanField(
        default=False, verbose_name="Retenue à la source",
        help_text="Décaissement : retenue au taux paramétré, créditée au 447 et reversée à l'État.",
    )
    montant_retenue = models.DecimalField(
        max_digits=16, decimal_places=2, default=0, verbose_name="Montant retenu à la source"
    )
    move = models.ForeignKey(
        "accounting_kernel.AccountMove",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="paiements_m10",
        verbose_name="Écriture comptable",
        help_text="Écriture générée à la validation (noyau comptable).",
    )
    reference = models.CharField(max_length=120, blank=True, verbose_name="Référence")
    statut = models.CharField(
        max_length=10, choices=Statut.choices, default=Statut.BROUILLON, verbose_name="Statut"
    )
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="paiements_m10",
        verbose_name="Créé par",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "Paiement / encaissement"
        verbose_name_plural = "Paiements / encaissements"

    def __str__(self):
        return f"{self.code} — {self.montant} FCFA ({self.get_sens_display()})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = ComptabiliteSequence.next_for("PAI", "PAI")
        return super().save(*args, **kwargs)


class DeclarationTva(models.Model):
    """Déclaration de TVA (RF-ERP-90 : TVA 18 %), assise sur les écritures validées."""

    class SourceCalcul(models.TextChoices):
        ECRITURES = "ecritures", "Écritures 443 / 445"
        PAIEMENTS = "paiements", "Paiements validés (encaissements)"

    class Statut(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        DEPOSEE = "deposee", "Déposée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    mois = models.DateField(verbose_name="Période", help_text="Premier jour du mois concerné.")
    taux_tva = models.ForeignKey(
        TauxTva,
        on_delete=models.PROTECT,
        related_name="declarations",
        verbose_name="Taux de TVA",
    )
    base_imposable = models.DecimalField(
        max_digits=16, decimal_places=2, default=0, verbose_name="Base imposable (HT)"
    )
    tva_collectee = models.DecimalField(
        max_digits=16, decimal_places=2, default=0, verbose_name="TVA collectée"
    )
    tva_deductible = models.DecimalField(
        max_digits=16, decimal_places=2, default=0, verbose_name="TVA déductible"
    )
    net_a_payer = models.DecimalField(
        max_digits=16, decimal_places=2, default=0, verbose_name="TVA nette à payer"
    )
    tva_autoliquidee = models.DecimalField(
        max_digits=16, decimal_places=2, default=0, verbose_name="dont TVA autoliquidée (autofacturation)"
    )
    retenues_source = models.DecimalField(
        max_digits=16, decimal_places=2, default=0, verbose_name="Retenues à la source à reverser (447)"
    )
    source_calcul = models.CharField(max_length=10, choices=SourceCalcul.choices, blank=True, verbose_name="Calculée sur")
    document = models.ForeignKey(
        "documents.Document", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Déclaration archivée en GED",
    )
    statut = models.CharField(
        max_length=10, choices=Statut.choices, default=Statut.BROUILLON, verbose_name="Statut"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="declarations_tva",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-mois"]
        verbose_name = "Déclaration TVA"
        verbose_name_plural = "Déclarations TVA"
        constraints = [
            models.UniqueConstraint(
                fields=["mois", "taux_tva"], name="uniq_tva_mois_taux"
            )
        ]

    def __str__(self):
        return f"{self.code} — {self.mois:%m/%Y} ({self.taux_tva.taux}%)"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = ComptabiliteSequence.next_for("TVA", "TVA")
        # « Premier jour du mois » : normalise toute date du mois (sinon les paiements
        # antérieurs au jour saisi seraient ignorés du calcul).
        if isinstance(self.mois, date):
            self.mois = self.mois.replace(day=1)
        return super().save(*args, **kwargs)


class ControleInterne(models.Model):
    """Contrôle interne & conservation des pièces comptables (proc. 4.6, 4.8)."""

    class Statut(models.TextChoices):
        PLANIFIE = "planifie", "Planifié"
        REALISE = "realise", "Réalisé"
        CLOTURE = "cloture", "Clôturé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    libelle = models.CharField(max_length=250, verbose_name="Point de contrôle")
    reference_procedure = models.CharField(
        max_length=40, blank=True, verbose_name="Réf. procédure (proc. 4.x)"
    )
    statut = models.CharField(
        max_length=10, choices=Statut.choices, default=Statut.PLANIFIE, verbose_name="Statut"
    )
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="controles_internes",
        verbose_name="Responsable",
    )
    date_prevue = models.DateField(null=True, blank=True, verbose_name="Date prévue")
    date_realise = models.DateField(null=True, blank=True, verbose_name="Date de réalisation")
    constat = models.TextField(blank=True, verbose_name="Constat / observations")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Contrôle interne"
        verbose_name_plural = "Contrôles internes"

    def __str__(self):
        return f"{self.code} — {self.libelle}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = ComptabiliteSequence.next_for("CON", "CON")
        return super().save(*args, **kwargs)

def clean(self):
        if self.reference_procedure and not self.reference_procedure.startswith("proc. 4."):
            raise ValidationError(
                {"reference_procedure": "Référence invalide — attendue 'proc. 4.x'."}
            )


class ParametreCompta(models.Model):
    """Paramètre de comptabilité modifiable par ETSL sans développeur (tolérances, délais, jours d'envoi…).

    Tant que `statut_valeur` = « provisoire », les écrans et les états qui l'utilisent affichent un
    avertissement. Le défaut est créé à la volée par `services.get_param` (valeur = DONNÉE, jamais figée).
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
        verbose_name = "Paramètre de comptabilité"
        verbose_name_plural = "Paramètres de comptabilité"

    def __str__(self):
        return f"{self.code} = {self.valeur} {self.unite}"

    @property
    def est_provisoire(self):
        return self.statut_valeur != self.StatutValeur.CONFIRME


class Lettrage(models.Model):
    """Lettrage d'un groupe de lignes d'un même compte lettrable (débits = crédits, à tolérance près).

    Vit dans ses propres tables : les lignes d'écriture comptabilisées restent immuables.
    Un dé-lettrage est tracé (statut « annulé », motif, auteur) et libère les lignes.
    """

    class Statut(models.TextChoices):
        ACTIF = "actif", "Actif"
        ANNULE = "annule", "Annulé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Lettre")
    compte = models.ForeignKey(
        "referentiels.Account", on_delete=models.PROTECT, related_name="lettrages", verbose_name="Compte"
    )
    partner = models.ForeignKey(
        "referentiels.Partner", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="lettrages", verbose_name="Tiers",
    )
    date = models.DateField(default=timezone.localdate, verbose_name="Date")
    ecart = models.DecimalField(max_digits=16, decimal_places=2, default=0, verbose_name="Écart accepté")
    automatique = models.BooleanField(default=False, verbose_name="Lettrage automatique")
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.ACTIF, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="lettrages"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    annule_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    annule_le = models.DateTimeField(null=True, blank=True)
    motif_annulation = models.CharField(max_length=250, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Lettrage"
        verbose_name_plural = "Lettrages"

    def __str__(self):
        return f"{self.code} — {self.compte_id}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = ComptabiliteSequence.next_for("LET", "LET")
        return super().save(*args, **kwargs)


class LigneLettree(models.Model):
    """Rattachement d'une ligne d'écriture à un lettrage actif (une ligne n'est lettrée qu'une fois)."""

    lettrage = models.ForeignKey(Lettrage, on_delete=models.CASCADE, related_name="lignes")
    ligne = models.OneToOneField(
        "accounting_kernel.AccountMoveLine", on_delete=models.PROTECT, related_name="lettrage_actif"
    )

    class Meta:
        verbose_name = "Ligne lettrée"
        verbose_name_plural = "Lignes lettrées"


class ModeleFacture(models.Model):
    """Modèle de facture client (en-tête, mentions légales, conditions) — modifiable par ETSL sans développeur.

    Un seul enregistrement (`code="DEFAUT"`), créé à la volée avec des textes PROVISOIRES : le PDF porte un
    avertissement tant qu'ETSL n'a pas confirmé son modèle (NIF, RCCM, banque, mentions légales).
    """

    class StatutValeur(models.TextChoices):
        PROVISOIRE = "provisoire", "Provisoire"
        CONFIRME = "confirme", "Confirmé"

    code = models.CharField(max_length=20, unique=True, default="DEFAUT")
    entete = models.TextField(verbose_name="En-tête (raison sociale, adresse, NIF, RCCM)")
    mentions_legales = models.TextField(blank=True, verbose_name="Mentions légales")
    conditions_paiement = models.TextField(blank=True, verbose_name="Conditions de paiement")
    coordonnees_bancaires = models.TextField(blank=True, verbose_name="Coordonnées bancaires")
    pied_page = models.TextField(blank=True, verbose_name="Pied de page")
    delai_paiement_jours = models.PositiveSmallIntegerField(default=30, verbose_name="Délai de paiement (jours)")
    statut_valeur = models.CharField(
        max_length=10, choices=StatutValeur.choices, default=StatutValeur.PROVISOIRE,
        verbose_name="Statut du modèle",
    )
    confirme_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    confirme_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Modèle de facture client"
        verbose_name_plural = "Modèles de facture client"

    def __str__(self):
        return f"Modèle {self.code} ({self.statut_valeur})"

    @property
    def est_provisoire(self):
        return self.statut_valeur != self.StatutValeur.CONFIRME


class FactureClient(models.Model):
    """Facture ou avoir client — émise via le noyau comptable (411 / 706 / 443), puis scellée.

    Toute correction d'une facture émise passe par un avoir (jamais de modification)."""

    class Nature(models.TextChoices):
        FACTURE = "facture", "Facture"
        AVOIR = "avoir", "Avoir"

    class Statut(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        EMISE = "emise", "Émise"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Numéro")
    nature = models.CharField(max_length=8, choices=Nature.choices, default=Nature.FACTURE, db_index=True)
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.BROUILLON, db_index=True)
    client = models.ForeignKey(
        "referentiels.Partner", on_delete=models.PROTECT, related_name="factures_clients", verbose_name="Client"
    )
    affaire = models.ForeignKey(
        "commercial.Affaire", null=True, blank=True, on_delete=models.SET_NULL, related_name="factures_clients"
    )
    jalon = models.ForeignKey(
        "commercial.Milestone", null=True, blank=True, on_delete=models.SET_NULL, related_name="factures_clients"
    )
    situation = models.ForeignKey(
        "operations.SituationTravaux", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="factures_clients",
    )
    facture_origine = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="avoirs",
        verbose_name="Facture d'origine (avoir)",
    )
    objet = models.CharField(max_length=250, blank=True, verbose_name="Objet")
    date = models.DateField(default=timezone.localdate, verbose_name="Date de facture")
    echeance = models.DateField(null=True, blank=True, verbose_name="Échéance")
    taux_tva = models.ForeignKey(
        TauxTva, null=True, blank=True, on_delete=models.PROTECT, related_name="+", verbose_name="Taux de TVA"
    )
    montant_ht = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    montant_tva = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    montant_ttc = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    move = models.ForeignKey(
        "accounting_kernel.AccountMove", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="factures_clients",
    )
    document = models.ForeignKey(
        "documents.Document", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="PDF archivé en GED",
    )
    modele_provisoire = models.BooleanField(
        default=False, help_text="Le modèle de facture était provisoire à l'émission (avertissement sur le PDF)."
    )
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    emise_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    emise_le = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "Facture client"
        verbose_name_plural = "Factures clients"

    def __str__(self):
        return f"{self.code} — {self.client_id}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = (
                ComptabiliteSequence.next_for("AVO", "AVO") if self.nature == self.Nature.AVOIR
                else ComptabiliteSequence.next_for("FAC", "FAC")
            )
        return super().save(*args, **kwargs)

    def recalculer(self):
        """Totaux depuis les lignes et le taux de TVA (arrondi au franc, FCFA sans décimales significatives)."""
        ht = sum((l.montant for l in self.lignes.all()), Decimal("0"))
        taux = self.taux_tva.taux if self.taux_tva_id else Decimal("0")
        tva = (ht * taux / Decimal("100")).quantize(Decimal("0.01"))
        self.montant_ht, self.montant_tva, self.montant_ttc = ht, tva, ht + tva
        self.save(update_fields=["montant_ht", "montant_tva", "montant_ttc"])


class LigneFactureClient(models.Model):
    facture = models.ForeignKey(FactureClient, on_delete=models.CASCADE, related_name="lignes")
    designation = models.CharField(max_length=250, verbose_name="Désignation")
    quantite = models.DecimalField(max_digits=12, decimal_places=3, default=1, verbose_name="Quantité")
    prix_unitaire = models.DecimalField(max_digits=16, decimal_places=2, default=0, verbose_name="Prix unitaire HT")
    montant = models.DecimalField(max_digits=16, decimal_places=2, default=0, verbose_name="Montant HT")
    compte_produit = models.ForeignKey(
        "referentiels.Account", on_delete=models.PROTECT, related_name="+", verbose_name="Compte de produit"
    )

    class Meta:
        ordering = ["id"]
        verbose_name = "Ligne de facture client"
        verbose_name_plural = "Lignes de facture client"

    def save(self, *args, **kwargs):
        self.montant = (self.quantite * self.prix_unitaire).quantize(Decimal("0.01"))
        return super().save(*args, **kwargs)


class ClotureMensuelle(models.Model):
    """Clôture comptable d'une période (mois) : chronométrée (objectif < 2 h) et suivie jusqu'à l'envoi Direction.

    `demarree_le` → `cloturee_le` donne la durée réelle ; la synthèse et les contrôles sont figés à la clôture.
    """

    class Statut(models.TextChoices):
        EN_COURS = "en_cours", "En cours"
        CLOTUREE = "cloturee", "Clôturée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    period = models.OneToOneField(
        "accounting_kernel.Period", on_delete=models.PROTECT, related_name="cloture_mensuelle", verbose_name="Période"
    )
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.EN_COURS, db_index=True)
    demarree_le = models.DateTimeField(default=timezone.now)
    demarree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    cloturee_le = models.DateTimeField(null=True, blank=True)
    cloturee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    duree_minutes = models.DecimalField(max_digits=10, decimal_places=1, null=True, blank=True)
    dans_objectif = models.BooleanField(null=True, blank=True, help_text="Durée ≤ objectif paramétré (2 h par défaut).")
    objectif_minutes = models.PositiveIntegerField(null=True, blank=True)
    echeance_envoi = models.DateField(null=True, blank=True, verbose_name="Échéance d'envoi à la Direction (J+4)")
    controles = models.JSONField(default=list, blank=True)
    synthese = models.JSONField(default=dict, blank=True)
    envoyee_le = models.DateTimeField(null=True, blank=True)
    envoyee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    destinataires = models.JSONField(default=list, blank=True)
    emails_envoyes = models.PositiveIntegerField(default=0, verbose_name="E-mails envoyés à la Direction")
    document = models.ForeignKey(
        "documents.Document", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Journal de la période archivé en GED",
    )
    reouvertures = models.JSONField(default=list, blank=True, help_text="Historique {par, le, motif} des réouvertures.")

    class Meta:
        ordering = ["-period__start_date"]
        verbose_name = "Clôture mensuelle"
        verbose_name_plural = "Clôtures mensuelles"

    def __str__(self):
        return f"Clôture {self.period}"


class PrevisionTresorerie(models.Model):
    """Prévision de trésorerie saisie (salaires, impôts, financement, encaissement attendu…) — plan 13 semaines."""

    class Sens(models.TextChoices):
        ENTREE = "entree", "Encaissement"
        SORTIE = "sortie", "Décaissement"

    class Categorie(models.TextChoices):
        CLIENTS = "clients", "Clients"
        FOURNISSEURS = "fournisseurs", "Fournisseurs"
        SALAIRES = "salaires", "Salaires et charges sociales"
        FISCAL = "fiscal", "Impôts et taxes"
        FINANCEMENT = "financement", "Financement / emprunts"
        INTRAGROUPE = "intragroupe", "Intra-groupe GLOBAL RENTAL"
        AUTRE = "autre", "Autre"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    date_prevue = models.DateField(verbose_name="Date prévue")
    sens = models.CharField(max_length=8, choices=Sens.choices, verbose_name="Sens")
    categorie = models.CharField(max_length=12, choices=Categorie.choices, default=Categorie.AUTRE, verbose_name="Catégorie")
    libelle = models.CharField(max_length=200, verbose_name="Libellé")
    montant = models.DecimalField(max_digits=16, decimal_places=2, verbose_name="Montant")
    compte_bancaire = models.ForeignKey(
        CompteBancaire, null=True, blank=True, on_delete=models.SET_NULL, related_name="previsions",
        verbose_name="Compte bancaire",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date_prevue", "code"]
        verbose_name = "Prévision de trésorerie"
        verbose_name_plural = "Prévisions de trésorerie"

    def __str__(self):
        return f"{self.code} — {self.libelle}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = ComptabiliteSequence.next_for("PRV", "PRV")
        return super().save(*args, **kwargs)


class AutoFacture(models.Model):
    """Autofacturation : ETSL établit la facture pour le compte du fournisseur et autoliquide la TVA (443 / 445)."""

    class Statut(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        EMISE = "emise", "Émise"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Numéro")
    fournisseur = models.ForeignKey(
        "referentiels.Partner", on_delete=models.PROTECT, related_name="autofactures", verbose_name="Fournisseur"
    )
    date = models.DateField(default=timezone.localdate, verbose_name="Date")
    objet = models.CharField(max_length=250, verbose_name="Objet de la prestation")
    montant_ht = models.DecimalField(max_digits=16, decimal_places=2, verbose_name="Montant HT")
    taux_tva = models.ForeignKey(TauxTva, on_delete=models.PROTECT, related_name="+", verbose_name="Taux de TVA")
    montant_tva = models.DecimalField(max_digits=16, decimal_places=2, default=0, verbose_name="TVA autoliquidée")
    compte_charge = models.ForeignKey(
        "referentiels.Account", on_delete=models.PROTECT, related_name="+", verbose_name="Compte de charge"
    )
    analytic = models.ForeignKey(
        "referentiels.AnalyticAccount", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Imputation analytique",
    )
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.BROUILLON, db_index=True)
    move = models.ForeignKey(
        "accounting_kernel.AccountMove", null=True, blank=True, on_delete=models.SET_NULL, related_name="autofactures"
    )
    cree_par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    emise_par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    emise_le = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "Autofacture"
        verbose_name_plural = "Autofactures"

    def __str__(self):
        return f"{self.code} — {self.fournisseur_id}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = ComptabiliteSequence.next_for("AUT", "AUT")
        return super().save(*args, **kwargs)


class GabaritEtat(models.Model):
    """Gabarit d'état comptable / fiscal (bilan, résultat, liasse, état 2460) : donnée ETSL modifiable,
    provisoire jusqu'à confirmation (modèles officiels DGI à fournir)."""

    class StatutValeur(models.TextChoices):
        PROVISOIRE = "provisoire", "Provisoire"
        CONFIRME = "confirme", "Confirmé"

    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    label = models.CharField(max_length=200, verbose_name="Libellé")
    parametres = models.JSONField(default=dict, blank=True, verbose_name="Paramètres du gabarit")
    statut_valeur = models.CharField(
        max_length=10, choices=StatutValeur.choices, default=StatutValeur.PROVISOIRE, verbose_name="Statut"
    )
    confirme_par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    confirme_le = models.DateTimeField(null=True, blank=True)
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "Gabarit d'état"
        verbose_name_plural = "Gabarits d'états"

    def __str__(self):
        return f"{self.code} ({self.statut_valeur})"

    @property
    def est_provisoire(self):
        return self.statut_valeur != self.StatutValeur.CONFIRME
