"""Reprise de données (CDC §10, plan ETSL-ERP-MIG) : lots de reprise par gabarit, historique de paie, paramètres.

Distinct de `ImportBatch` (flux d'intégration courants) : un lot de reprise porte un MODE (à blanc / réel), un
gabarit métier, un rapport d'anomalies ligne par ligne et un taux d'erreur comparé au seuil provisoire d'ETSL.
"""

import uuid

from django.conf import settings
from django.db import models


class LotReprise(models.Model):
    """Lot de reprise : un fichier (CSV, XML ou ZIP GED) chargé par gabarit, à blanc ou réellement."""

    class Mode(models.TextChoices):
        BLANC = "blanc", "À blanc (validation sans écriture)"
        REEL = "reel", "Réel"

    class Statut(models.TextChoices):
        VALIDE = "valide", "Validé à blanc"
        SUCCES = "succes", "Chargé"
        PARTIEL = "partiel", "Chargé avec anomalies (sous le seuil)"
        REJETE = "rejete", "Rejeté (seuil d'erreur dépassé, rien écrit)"
        ECHEC = "echec", "Échec (fichier illisible)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    gabarit = models.CharField(max_length=30, db_index=True, verbose_name="Gabarit")
    mode = models.CharField(max_length=6, choices=Mode.choices, verbose_name="Mode")
    format = models.CharField(max_length=4, verbose_name="Format (csv / xml / zip)")
    statut = models.CharField(max_length=8, choices=Statut.choices, verbose_name="Statut")
    fichier = models.CharField(max_length=255, verbose_name="Fichier")
    empreinte = models.CharField(max_length=64, db_index=True, verbose_name="SHA-256 du fichier")
    lignes = models.PositiveIntegerField(default=0, verbose_name="Lignes")
    creees = models.PositiveIntegerField(default=0, verbose_name="Créées")
    mises_a_jour = models.PositiveIntegerField(default=0, verbose_name="Mises à jour")
    doublons = models.PositiveIntegerField(default=0, verbose_name="Déjà présentes")
    erreurs = models.PositiveIntegerField(default=0, verbose_name="En erreur")
    taux_erreur = models.DecimalField(max_digits=6, decimal_places=2, default=0, verbose_name="Taux d'erreur (%)")
    seuil_erreur = models.DecimalField(max_digits=6, decimal_places=2, default=0, verbose_name="Seuil appliqué (%)")
    message = models.TextField(blank=True, verbose_name="Message global")
    rejeu_de = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="Rejeu du lot"
    )
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="lots_reprise",
        verbose_name="Chargé par",
    )
    cree_le = models.DateTimeField(auto_now_add=True, verbose_name="Chargé le")

    class Meta:
        ordering = ["-cree_le"]
        verbose_name = "Lot de reprise"
        verbose_name_plural = "Lots de reprise"
        indexes = [models.Index(fields=["gabarit", "mode", "statut"])]

    def __str__(self):
        return f"{self.gabarit} [{self.mode}/{self.statut}] {self.fichier}"


class LigneReprise(models.Model):
    """Rapport d'anomalies ligne par ligne (ETSL-ERP-RAN) ; colonnes sensibles masquées (RIB, salaires)."""

    class Statut(models.TextChoices):
        CREEE = "creee", "Créée"
        MAJ = "maj", "Mise à jour"
        DOUBLON = "doublon", "Déjà présente"
        ERREUR = "erreur", "En erreur"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lot = models.ForeignKey(LotReprise, on_delete=models.CASCADE, related_name="lignes_rapport", verbose_name="Lot")
    numero = models.PositiveIntegerField(verbose_name="N° de ligne")
    statut = models.CharField(max_length=8, choices=Statut.choices, verbose_name="Statut")
    cle = models.CharField(max_length=200, blank=True, verbose_name="Clé métier")
    donnees = models.JSONField(default=dict, blank=True, verbose_name="Données source (masquées)")
    erreur = models.TextField(blank=True, verbose_name="Anomalie")

    class Meta:
        ordering = ["lot", "numero"]
        verbose_name = "Ligne de reprise"
        verbose_name_plural = "Lignes de reprise"
        constraints = [models.UniqueConstraint(fields=["lot", "numero"], name="uniq_ligne_reprise_numero")]

    def __str__(self):
        return f"{self.lot_id} l.{self.numero} [{self.statut}]"


class HistoriquePaie(models.Model):
    """Historique de paie repris d'ALAN (CDC §10 : 12 mois) — cumul par salarié, mois et rubrique, LECTURE SEULE.

    Aucune saisie à l'écran : seul le gabarit `paie_historique` l'alimente (clé matricule + période + rubrique).
    """

    class Nature(models.TextChoices):
        GAIN = "gain", "Gain"
        RETENUE = "retenue", "Retenue"
        COTISATION_SALARIALE = "cot_sal", "Cotisation salariale"
        COTISATION_PATRONALE = "cot_pat", "Cotisation patronale"
        CUMUL = "cumul", "Cumul (brut, net, imposable…)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employe = models.ForeignKey(
        "rh_paie.Employe", on_delete=models.PROTECT, related_name="historique_paie_reprise", verbose_name="Salarié"
    )
    periode = models.DateField(verbose_name="Période (1er du mois)")
    rubrique = models.CharField(max_length=30, verbose_name="Code rubrique ALAN")
    libelle = models.CharField(max_length=150, blank=True, verbose_name="Libellé")
    nature = models.CharField(max_length=8, choices=Nature.choices, default=Nature.CUMUL, verbose_name="Nature")
    base = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True, verbose_name="Base")
    montant = models.DecimalField(max_digits=16, decimal_places=2, verbose_name="Montant")
    lot = models.ForeignKey(
        LotReprise, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="Lot d'origine"
    )
    importe_le = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["employe", "-periode", "rubrique"]
        verbose_name = "Historique de paie (reprise)"
        verbose_name_plural = "Historique de paie (reprise)"
        constraints = [
            models.UniqueConstraint(fields=["employe", "periode", "rubrique"], name="uniq_histo_paie_cle")
        ]

    def __str__(self):
        return f"{self.employe_id} {self.periode:%Y-%m} {self.rubrique} = {self.montant}"


class ParametreReprise(models.Model):
    """Paramètres de reprise (taux d'erreur toléré, échantillon C10, tailles max) : provisoires jusqu'à confirmation ETSL."""

    class StatutValeur(models.TextChoices):
        PROVISOIRE = "provisoire", "Provisoire"
        CONFIRME = "confirme", "Confirmé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=40, unique=True, verbose_name="Identifiant")
    label = models.CharField(max_length=200, verbose_name="Libellé")
    valeur = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Valeur")
    unite = models.CharField(max_length=20, blank=True, verbose_name="Unité")
    statut_valeur = models.CharField(
        max_length=10, choices=StatutValeur.choices, default=StatutValeur.PROVISOIRE, verbose_name="Statut de la valeur"
    )
    confirme_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Confirmé par",
    )
    confirme_le = models.DateTimeField(null=True, blank=True, verbose_name="Confirmé le")

    class Meta:
        ordering = ["code"]
        verbose_name = "Paramètre de reprise"
        verbose_name_plural = "Paramètres de reprise"

    def __str__(self):
        return f"{self.code} = {self.valeur} {self.unite}"

    @property
    def est_provisoire(self):
        return self.statut_valeur != self.StatutValeur.CONFIRME
