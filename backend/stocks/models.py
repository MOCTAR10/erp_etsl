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
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="stocks_depots",
        verbose_name="Responsable magasin",
    )
    description = models.TextField(blank=True, verbose_name="Description")
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
        if float(self.quantite_restante) <= 0:
            self.statut = self.Statut.EPUISE
        elif self.statut == self.Statut.DISPONIBLE and float(self.quantite_restante) < float(self.quantite_initiale):
            self.statut = self.Statut.PARTIEL


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