"""Module M5 — Stocks, Magasins & Traçabilité matière (RF-ERP-40…43).

Multi-dépôts & lots · certificats matière MTC / CoC · méthodes de valorisation
FIFO / PEPS / CUMP / PP · traçabilité amont/aval · inventaires périodiques.
Stock en double-entrée (modélisation Odoo `quant` + `move`, jamais copiée) :
un mouvement débite un dépôt source et crédite un dépôt destination.
Valorisation (compte 31 SYSCOHADA) → M10 via `accounting_kernel`.
Dérivé du schéma `Architecture ERP ETSL.png` §2.1 (M5).
"""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone


class StocksSequence(models.Model):
    """Numérotation séquentielle par type (DEP, LOT, MVT, CERT, INV)."""

    kind = models.CharField(max_length=10, unique=True, verbose_name="Type")
    prefix = models.CharField(max_length=10, verbose_name="Préfixe")
    padding = models.PositiveSmallIntegerField(default=5, verbose_name="Zéro-padding")
    next_number = models.PositiveIntegerField(default=1, verbose_name="Prochain numéro")

    class Meta:
        verbose_name = "Séquence Stocks"
        verbose_name_plural = "Séquences Stocks"

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


class Depot(models.Model):
    """Entrepôt / magasin multi-dépôts ETSL (RF-ERP-40)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    label = models.CharField(max_length=200, verbose_name="Désignation")
    site = models.CharField(max_length=120, blank=True, verbose_name="Site / localisation")
    # EX-G-03 : site ETSL de rattachement (référentiel paramétrable ; reconnu automatiquement depuis le texte libre).
    site_etsl = models.ForeignKey(
        "referentiels.Site", null=True, blank=True, on_delete=models.PROTECT, related_name="depots", verbose_name="Site ETSL"
    )
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="stocks_depots",
        verbose_name="Responsable magasin",
    )
    description = models.TextField(blank=True, verbose_name="Description")
    methode_valorisation = models.CharField(
        max_length=8, blank=True, choices=[("fifo", "FIFO / PEPS"), ("peps", "PEPS"), ("cump", "CUMP"), ("pp", "Prix standard")],
        verbose_name="Méthode de valorisation du dépôt (vide = celle de l'article)",
    )
    is_global_rental = models.BooleanField(
        default=False, verbose_name="Site GLOBAL RENTAL (consultation seule)",
        help_text="CDC M5 §7.8 : les sites GR sont consultables en lecture seule, aucun mouvement ETSL.",
    )
    roles_autorises = models.JSONField(
        default=list, blank=True, verbose_name="Fonctions autorisées à mouvementer (vide = toutes les fonctions stock)"
    )
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "Dépôt / magasin"
        verbose_name_plural = "Dépôts / magasins"

    def __str__(self):
        return f"{self.code} — {self.label}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = StocksSequence.next_for("DEP", "DEP")
        return super().save(*args, **kwargs)


class ArticleStock(models.Model):
    """Paramétrage stock par article — méthode de valorisation (RF-ERP-42)."""

    class Methode(models.TextChoices):
        FIFO = "fifo", "FIFO / PEPS"
        PEPS = "peps", "PEPS"
        CUMP = "cump", "CUMP (coût moyen pondéré)"
        PP = "pp", "Prix préétabli / standard"

    article = models.OneToOneField(
        "referentiels.Article",
        on_delete=models.CASCADE,
        related_name="stock_config",
        verbose_name="Article",
    )
    methode = models.CharField(
        max_length=8, choices=Methode.choices, default=Methode.CUMP,
        verbose_name="Méthode de valorisation",
    )
    prix_standard = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        verbose_name="Prix préétabli (standard)",
    )
    seuil_minimal = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Seuil minimum de stock"
    )
    gestion_lots = models.BooleanField(default=False, verbose_name="Gestion par lots")
    certificat_requis = models.BooleanField(
        default=False, verbose_name="Certificat MTC / CoC exigé",
        help_text="Traçabilité client pétrolier (CDC M5 §7.8) : aucune sortie d'un lot sans certificat validé et conforme.",
    )
    lot_obligatoire = models.BooleanField(
        default=False, verbose_name="Lot obligatoire sur tout mouvement",
        help_text="Traçabilité client pétrolier sur toute la chaîne matière (CDC M5 §7.8 / §7.11).",
    )
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["article__code"]
        verbose_name = "Paramétrage stock article"
        verbose_name_plural = "Paramétrages stock articles"

    def __str__(self):
        return f"{self.article.code} — {self.methode}"


class LotMatiere(models.Model):
    """Lot de matière réceptionné avec certificat (RF-ERP-40/41)."""

    class Statut(models.TextChoices):
        DISPONIBLE = "disponible", "Disponible"
        PARTIEL = "partiel", "Partiellement consommé"
        EPUISE = "epuise", "Épuisé"
        BLOQUE = "bloque", "Bloqué"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    article = models.ForeignKey(
        "referentiels.Article",
        on_delete=models.CASCADE,
        related_name="lots",
        verbose_name="Article",
    )
    numero_lot = models.CharField(max_length=80, verbose_name="N° lot fournisseur")
    numero_coulee = models.CharField(max_length=80, blank=True, verbose_name="N° de coulée")
    date_reception = models.DateField(verbose_name="Date de réception")
    date_peremption = models.DateField(null=True, blank=True, verbose_name="Date de péremption")
    quantite_initiale = models.DecimalField(
        max_digits=14, decimal_places=2, verbose_name="Quantité initiale"
    )
    quantite_restante = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Quantité restante"
    )
    statut = models.CharField(
        max_length=12, choices=Statut.choices, default=Statut.DISPONIBLE, verbose_name="Statut"
    )
    motif_blocage = models.CharField(max_length=255, blank=True, verbose_name="Motif de quarantaine")
    bloque_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Mis en quarantaine par",
    )
    bloque_le = models.DateTimeField(null=True, blank=True, verbose_name="Mis en quarantaine le")
    nc_blocage = models.ForeignKey(
        "qualite.NonConformite", null=True, blank=True, on_delete=models.SET_NULL, related_name="lots_bloques",
        verbose_name="NC à l'origine de la quarantaine",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_reception", "code"]
        verbose_name = "Lot de matière"
        verbose_name_plural = "Lots de matière"
        indexes = [models.Index(fields=["article", "statut"])]

    def __str__(self):
        return f"{self.code} — {self.article.label} ({self.numero_lot})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = StocksSequence.next_for("LOT", "LOT")
        return super().save(*args, **kwargs)

    def clean(self):
        if self.quantite_initiale < 0:
            raise ValidationError({"quantite_initiale": "La quantité brute ne peut être négative."})
        self.refresh_statut()
        if self.statut == "epuise" and float(self.quantite_restante) > 0:
            self.statut = self.Statut.DISPONIBLE

    def refresh_statut(self):
        if self.statut == self.Statut.BLOQUE:
            return  # la quarantaine ne se lève que par `lever_quarantaine`
        if float(self.quantite_restante) <= 0:
            self.statut = self.Statut.EPUISE
        elif self.statut == self.Statut.DISPONIBLE and float(self.quantite_restante) < float(self.quantite_initiale):
            self.statut = self.Statut.PARTIEL

    def mettre_en_quarantaine(self, motif, user=None, nc=None):
        self.statut = self.Statut.BLOQUE
        self.motif_blocage = motif[:255]
        self.bloque_par = user
        self.bloque_le = timezone.now()
        self.nc_blocage = nc
        self.save(update_fields=["statut", "motif_blocage", "bloque_par", "bloque_le", "nc_blocage", "updated_at"])

    def lever_quarantaine(self):
        self.statut = self.Statut.DISPONIBLE
        self.motif_blocage = ""
        self.nc_blocage = None
        self.refresh_statut()
        if self.statut == self.Statut.DISPONIBLE and float(self.quantite_restante) < float(self.quantite_initiale):
            self.statut = self.Statut.PARTIEL
        self.save(update_fields=["statut", "motif_blocage", "nc_blocage", "updated_at"])


class CertificatMatiere(models.Model):
    """Certificat matière MTC / CoC attaché à un lot (RF-ERP-41)."""

    class Type(models.TextChoices):
        MTC = "mtc", "MTC (Mill Test Certificate)"
        COC = "coc", "CoC (Certificate of Conformity)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    lot = models.ForeignKey(
        LotMatiere,
        on_delete=models.CASCADE,
        related_name="certificats",
        verbose_name="Lot",
    )
    type = models.CharField(
        max_length=4, choices=Type.choices, default=Type.MTC, verbose_name="Type"
    )
    numero_certificat = models.CharField(max_length=80, verbose_name="N° certificat")
    fournisseur = models.ForeignKey(
        "referentiels.Partner",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="certificats_matiere",
        verbose_name="Fournisseur",
    )
    organisme = models.CharField(max_length=120, blank=True, verbose_name="Organisme / labo")
    date_emission = models.DateField(null=True, blank=True, verbose_name="Date d'émission")
    date_validation = models.DateField(null=True, blank=True, verbose_name="Date de validation QA-QC")
    valide_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Validé par (QA/QC)",
    )
    document = models.ForeignKey(
        "documents.Document", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        verbose_name="Certificat numérisé (GED)",
    )
    conforme = models.BooleanField(default=True, verbose_name="Conforme")
    notes = models.TextField(blank=True, verbose_name="Notes / observations")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Certificat matière"
        verbose_name_plural = "Certificats matière"
        unique_together = [("lot", "numero_certificat")]

    def __str__(self):
        return f"{self.code} — {self.get_type_display()} {self.numero_certificat}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = StocksSequence.next_for("CERT", "CERT")
        return super().save(*args, **kwargs)

    def clean(self):
        if not self.numero_certificat.strip():
            raise ValidationError({"numero_certificat": "N° de certificat requis."})


class StockQuant(models.Model):
    """Quantité & valeur en stock par dépôt + article (+ lot optionnel) (RF-ERP-40/42)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    depot = models.ForeignKey(
        Depot,
        on_delete=models.CASCADE,
        related_name="quants",
        verbose_name="Dépôt",
    )
    article = models.ForeignKey(
        "referentiels.Article",
        on_delete=models.CASCADE,
        related_name="quants",
        verbose_name="Article",
    )
    lot = models.ForeignKey(
        LotMatiere,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="quants",
        verbose_name="Lot",
    )
    quantity = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Quantité en stock"
    )
    stock_value = models.DecimalField(
        max_digits=16, decimal_places=2, default=0, verbose_name="Valeur du stock"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["depot", "article__code"]
        verbose_name = "Quant en stock"
        verbose_name_plural = "Quants en stock"
        constraints = [
            models.UniqueConstraint(
                fields=["depot", "article"],
                condition=models.Q(lot__isnull=True),
                name="quant_sans_lot_uniq",
            ),
            models.UniqueConstraint(
                fields=["depot", "article", "lot"],
                condition=models.Q(lot__isnull=False),
                name="quant_lot_uniq",
            ),
        ]

    def __str__(self):
        lot = f" / {self.lot.code}" if self.lot else ""
        return f"{self.depot.code} — {self.article.code}{lot} : {self.quantity}"


class MouvementStock(models.Model):
    """Mouvement de stock en double-entrée (source → destination) (RF-ERP-40/41/43).

    Une réception crédite un dépôt, une consommation (OF M3) débite un dépôt,
    un transfert débite la source et crédite la destination dans le même mouvement.
    """

    class Type(models.TextChoices):
        RECEPTION = "reception", "Réception"
        TRANSFERT = "transfert", "Transfert entre dépôts"
        CONSOMMATION = "consommation", "Consommation (OF / chantier)"
        RETOUR = "retour", "Retour"
        INVENTAIRE = "inventaire", "Ajustement d'inventaire"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    type_mouvement = models.CharField(
        max_length=12, choices=Type.choices, default=Type.RECEPTION, verbose_name="Type"
    )
    article = models.ForeignKey(
        "referentiels.Article",
        on_delete=models.CASCADE,
        related_name="mouvements_stock",
        verbose_name="Article",
    )
    quantite = models.DecimalField(
        max_digits=14, decimal_places=2, verbose_name="Quantité"
    )
    prix_unitaire = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Prix unitaire"
    )
    devise = models.ForeignKey(
        "referentiels.Currency",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="mouvements_stock",
        verbose_name="Devise",
    )
    source = models.ForeignKey(
        Depot,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="mouvements_sortants",
        verbose_name="Dépôt source",
    )
    destination = models.ForeignKey(
        Depot,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="mouvements_entrants",
        verbose_name="Dépôt destination",
    )
    lot = models.ForeignKey(
        LotMatiere,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="mouvements",
        verbose_name="Lot",
    )
    ordre = models.ForeignKey(
        "operations.OrdreFabrication",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="mouvements_stock",
        verbose_name="Ordre de fabrication",
    )
    analytic = models.ForeignKey(
        "referentiels.AnalyticAccount", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="mouvements_stock", verbose_name="Compte analytique (M11)",
        help_text="Imputation de la consommation ; reprise de l'affaire de l'OF si non renseigné.",
    )
    cout_unitaire = models.DecimalField(
        max_digits=16, decimal_places=4, default=0, editable=False, verbose_name="Coût unitaire appliqué (CUMP)"
    )
    document = models.ForeignKey(
        "documents.Document", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        verbose_name="Pièce jointe (BL, bon de sortie) en GED",
    )
    document_reference = models.CharField(
        max_length=60, blank=True, verbose_name="Réf. document (BC / BL / INV)"
    )
    date = models.DateField(verbose_name="Date du mouvement")
    executed = models.BooleanField(default=False, verbose_name="Appliqué aux quants")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="stocks_mouvements",
        verbose_name="Créé par",
    )
    notes = models.TextField(blank=True, verbose_name="Notes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "Mouvement de stock"
        verbose_name_plural = "Mouvements de stock"
        indexes = [models.Index(fields=["article", "type_mouvement"])]

    def __str__(self):
        ref = f" ({self.document_reference})" if self.document_reference else ""
        return f"{self.code} — {self.article.label}{ref}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = StocksSequence.next_for("MVT", "MVT")
        return super().save(*args, **kwargs)

    def clean(self):
        if self.quantite <= 0:
            raise ValidationError({"quantite": "La quantité doit être strictement positive."})
        if self.prix_unitaire < 0:
            raise ValidationError({"prix_unitaire": "Le prix unitaire ne peut être négatif."})
        if not self.source and not self.destination:
            raise ValidationError(
                "Le mouvement doit avoir au moins un dépôt source ou destination."
            )
        if self.type_mouvement == self.Type.TRANSFERT and not (self.source and self.destination):
            raise ValidationError(
                {"destination": "Un transfert exige un dépôt source ET destination."}
            )

    def delete(self, *args, **kwargs):
        if self.executed:
            raise ValidationError("Mouvement exécuté : suppression interdite (passez un mouvement inverse).")
        return super().delete(*args, **kwargs)

    @property
    def montant_total(self):
        return self.quantite * self.prix_unitaire

    @property
    def libelle_montant(self):
        return f"{self.montant_total} {self.devise.code if self.devise else ''}".strip()


class Inventaire(models.Model):
    """Inventaire périodique d'un dépôt (RF-ERP-43)."""

    class Statut(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        EN_COURS = "en_cours", "En cours"
        CLOTURE = "cloture", "Clôturé"
        ANNULE = "annule", "Annulé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    depot = models.ForeignKey(
        Depot,
        on_delete=models.PROTECT,
        related_name="inventaires",
        verbose_name="Dépôt",
    )
    class Type(models.TextChoices):
        COMPLET = "complet", "Inventaire complet"
        TOURNANT = "tournant", "Inventaire tournant"

    type = models.CharField(max_length=10, choices=Type.choices, default=Type.COMPLET, verbose_name="Type")
    plan = models.ForeignKey(
        "PlanInventaireTournant", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="inventaires", verbose_name="Plan tournant",
    )
    date = models.DateField(verbose_name="Date d'inventaire")
    statut = models.CharField(
        max_length=12, choices=Statut.choices, default=Statut.BROUILLON, verbose_name="Statut"
    )
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="stocks_inventaires",
        verbose_name="Responsable",
    )
    note = models.TextField(blank=True, verbose_name="Note")
    ecarts_valides_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Régularisation MAD validée par",
    )
    ecarts_valides_le = models.DateTimeField(null=True, blank=True, verbose_name="Régularisation MAD validée le")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="stocks_inventaires_cree",
        verbose_name="Créé par",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "Inventaire"
        verbose_name_plural = "Inventaires"
        indexes = [models.Index(fields=["depot", "statut"])]

    def __str__(self):
        return f"{self.code} — {self.depot.label} ({self.date})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = StocksSequence.next_for("INV", "INV")
        return super().save(*args, **kwargs)

    @property
    def ecart_total(self):
        return sum(l.ecart for l in self.lignes.all())


class InventaireLigne(models.Model):
    """Ligne d'inventaire : écart système vs réel (RF-ERP-43)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    inventaire = models.ForeignKey(
        Inventaire,
        on_delete=models.CASCADE,
        related_name="lignes",
        verbose_name="Inventaire",
    )
    article = models.ForeignKey(
        "referentiels.Article",
        on_delete=models.CASCADE,
        related_name="inventaire_lignes",
        verbose_name="Article",
    )
    lot = models.ForeignKey(
        LotMatiere,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="inventaire_lignes",
        verbose_name="Lot",
    )
    quantite_systeme = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Quantité système"
    )
    quantite_reelle = models.DecimalField(
        max_digits=14, decimal_places=2, verbose_name="Quantité réelle"
    )
    comptee = models.BooleanField(
        default=True, verbose_name="Comptée",
        help_text="Faux sur les lignes préparées par un plan tournant tant que le comptage n'est pas saisi.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["inventaire", "article__code"]
        verbose_name = "Ligne d'inventaire"
        verbose_name_plural = "Lignes d'inventaire"

    @property
    def ecart(self):
        return self.quantite_reelle - self.quantite_systeme

    def clean(self):
        if self.quantite_reelle < 0:
            raise ValidationError({"quantite_reelle": "La quantité réelle ne peut être négative."})


class PlanInventaireTournant(models.Model):
    """Plan d'inventaire tournant d'un dépôt (CDC M5 §7.11) : chaque passage compte une tranche d'articles."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    depot = models.ForeignKey(Depot, on_delete=models.PROTECT, related_name="plans_inventaire", verbose_name="Dépôt")
    periodicite_jours = models.PositiveIntegerField(default=30, verbose_name="Périodicité (jours)")
    articles_par_passage = models.PositiveIntegerField(default=10, verbose_name="Articles par passage")
    curseur = models.PositiveIntegerField(default=0, editable=False, verbose_name="Position dans la rotation")
    prochaine_date = models.DateField(verbose_name="Prochain passage")
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="stocks_plans_inventaire", verbose_name="Responsable",
    )
    actif = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["prochaine_date"]
        verbose_name = "Plan d'inventaire tournant"
        verbose_name_plural = "Plans d'inventaire tournant"

    def __str__(self):
        return f"{self.code} — {self.depot.label}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = StocksSequence.next_for("PLT", "PLT")
        return super().save(*args, **kwargs)

    def clean(self):
        if self.periodicite_jours < 1 or self.articles_par_passage < 1:
            raise ValidationError("Périodicité et nombre d'articles par passage doivent être positifs.")


class ValorisationMensuelle(models.Model):
    """Valorisation du stock d'un dépôt figée à la clôture mensuelle (CDC M5 §7.11 → M11), non modifiable."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    periode = models.CharField(max_length=7, verbose_name="Période (AAAA-MM)")
    depot = models.ForeignKey(Depot, on_delete=models.PROTECT, related_name="valorisations", verbose_name="Dépôt")
    quantite = models.DecimalField(max_digits=16, decimal_places=2, default=0, verbose_name="Quantité en stock")
    valeur_stock = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="Valeur du stock (CUMP)")
    consommation = models.DecimalField(
        max_digits=18, decimal_places=2, default=0, verbose_name="Consommations du mois (OF, affaires)"
    )
    ventilation = models.JSONField(default=list, verbose_name="Consommations par compte analytique")
    valeur_par_compte = models.JSONField(default=dict, verbose_name="Valeur du stock par compte de classe 3")
    move = models.ForeignKey(
        "accounting_kernel.AccountMove", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        verbose_name="Écriture de variation de stock",
    )
    motif_ecriture = models.CharField(max_length=255, blank=True, verbose_name="Écriture non passée : motif")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", verbose_name="Figée par",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-periode", "depot__code"]
        verbose_name = "Valorisation mensuelle"
        verbose_name_plural = "Valorisations mensuelles"
        constraints = [models.UniqueConstraint(fields=["periode", "depot"], name="stocks_valorisation_unique")]

    def __str__(self):
        return f"{self.periode} — {self.depot.code}"


class ParametreStock(models.Model):
    """Paramètres M5 modifiables par ETSL (délais d'alerte) : défauts provisoires tant qu'ETSL ne les confirme pas."""

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
        verbose_name = "Paramètre stocks"
        verbose_name_plural = "Paramètres stocks"

    def __str__(self):
        return f"{self.code} = {self.valeur} {self.unite}"

    @property
    def est_provisoire(self):
        return self.statut_valeur != self.StatutValeur.CONFIRME


class ReservationStock(models.Model):
    """Réservation physique d'un besoin matière M3 (préparation atelier validée / OF lancé) — voir `reservations.py`."""

    class Statut(models.TextChoices):
        ACTIVE = "active", "Active"
        CONSOMMEE = "consommee", "Consommée"
        LIBEREE = "liberee", "Libérée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    article = models.ForeignKey(
        "referentiels.Article", on_delete=models.PROTECT, related_name="reservations_stock", verbose_name="Article"
    )
    ordre = models.ForeignKey(
        "operations.OrdreFabrication", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="reservations_stock", verbose_name="OF réservataire",
    )
    besoin_id = models.UUIDField(null=True, blank=True, db_index=True, verbose_name="Besoin matière (M3)")
    quantite = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Quantité réservée")
    quantite_consommee = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Quantité consommée")
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.ACTIVE, db_index=True, verbose_name="Statut")
    motif = models.CharField(max_length=250, blank=True, verbose_name="Motif (libération / consommation)")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="Créée par"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    cloturee_le = models.DateTimeField(null=True, blank=True, verbose_name="Soldée / libérée le")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Réservation de stock"
        verbose_name_plural = "Réservations de stock"
        indexes = [models.Index(fields=["article", "statut"])]

    def __str__(self):
        return f"{self.article_id} × {self.quantite} [{self.statut}]"

    @property
    def reste(self):
        return self.quantite - self.quantite_consommee
