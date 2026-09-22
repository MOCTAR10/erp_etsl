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
        return sum((paiement.montant for paiement in self.paiements.all()), Decimal("0"))

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
