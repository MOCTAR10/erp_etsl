from django.db import models


class Annexe(models.Model):
    """Annexe du MANUEL DE PROCEDURE ETSL (ch.10) — référentiel transverse (§10.4).

    Codification ``ANN-{F|R|M|TS}-{DOMAINE}-###`` (RF-ERP-xx). 270 annexes :
    108 formulaires / 56 registres / 55 modèles / 51 tableaux de suivi.
    """

    class Kind(models.TextChoices):
        FORMULAIRE = "F", "Formulaire"
        REGISTRE = "R", "Registre"
        MODELE = "M", "Modèle"
        TABLEAU = "TS", "Tableau de suivi"

    class Domain(models.TextChoices):
        ADM = "ADM", "Administratif"
        FIN = "FIN", "Finance"
        TEC = "TEC", "Technique"
        COM = "COM", "Commercial"
        RH = "RH", "Ressources humaines"
        JUR = "JUR", "Juridique"
        HSE = "HSE", "HSE"

    code = models.CharField(
        max_length=30, unique=True, verbose_name="Code", db_index=True
    )
    label = models.CharField(max_length=200, verbose_name="Intitulé")
    kind = models.CharField(
        max_length=2, choices=Kind.choices, verbose_name="Nature", db_index=True
    )
    domain = models.CharField(
        max_length=3, choices=Domain.choices, verbose_name="Domaine", db_index=True
    )
    description = models.TextField(blank=True, verbose_name="Description")
    source_ref = models.CharField(
        max_length=120,
        blank=True,
        verbose_name="Référence MANUEL",
        help_text="Ex. chapitre / §10.4 (les intitulés précis seront complétés par le client).",
    )
    is_active = models.BooleanField(default=True, verbose_name="Active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["domain", "kind", "code"]
        verbose_name = "Annexe"
        verbose_name_plural = "Annexes"
        indexes = [
            models.Index(fields=["domain", "kind"]),
        ]

    def __str__(self):
        return f"{self.code} — {self.label}"


class Currency(models.Model):
    """Devise (XAF par défaut) — noyau partagé M10/M2/M4."""

    code = models.CharField(max_length=3, unique=True, verbose_name="Code ISO")
    label = models.CharField(max_length=60, verbose_name="Libellé")
    symbol = models.CharField(max_length=8, blank=True, verbose_name="Symbole")
    decimals = models.PositiveSmallIntegerField(default=0, verbose_name="Décimales")
    is_active = models.BooleanField(default=True, verbose_name="Active")

    class Meta:
        ordering = ["code"]
        verbose_name = "Devise"
        verbose_name_plural = "Devises"

    def __str__(self):
        return f"{self.code} — {self.label}"


class UnitOfMeasure(models.Model):
    """Unité de mesure (articles, stocks, prestations) — M5/M2/M3."""

    code = models.CharField(max_length=10, unique=True, verbose_name="Code")
    label = models.CharField(max_length=60, verbose_name="Libellé")
    is_active = models.BooleanField(default=True, verbose_name="Active")

    class Meta:
        ordering = ["code"]
        verbose_name = "Unité de mesure"
        verbose_name_plural = "Unités de mesure"

    def __str__(self):
        return f"{self.code} — {self.label}"


class Account(models.Model):
    """Compte du plan SYSCOHADA révisée — noyau comptable (M10, RF-ERP-90)."""

    class AccountClass(models.IntegerChoices):
        RESSOURCES_DURABLES = 1, "Comptes de ressources durables"
        ACTIF_IMMOBILISE = 2, "Comptes d'actif immobilisé"
        STOCKS = 3, "Comptes de stocks"
        TIERS = 4, "Comptes de tiers"
        TRESORERIE = 5, "Comptes de trésorerie"
        CHARGES = 6, "Comptes de charges"
        PRODUITS = 7, "Comptes de produits"
        AUTRES = 8, "Comptes des autres charges et autres produits"

    class AccountType(models.TextChoices):
        ASSET = "asset", "Actif"
        LIABILITY = "liability", "Passif"
        EQUITY = "equity", "Capitaux propres"
        INCOME = "income", "Produit"
        EXPENSE = "expense", "Charge"

    code = models.CharField(max_length=20, unique=True, verbose_name="Numéro de compte")
    label = models.CharField(max_length=200, verbose_name="Intitulé")
    account_class = models.PositiveSmallIntegerField(
        choices=AccountClass.choices, verbose_name="Classe", db_index=True
    )
    account_type = models.CharField(
        max_length=10, choices=AccountType.choices, verbose_name="Nature"
    )
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
        verbose_name="Compte parent",
    )
    reconcile = models.BooleanField(
        default=False, verbose_name="Lettrable", help_text="Rapprochement / lettrage."
    )
    is_active = models.BooleanField(default=True, verbose_name="Actif")

    class Meta:
        ordering = ["code"]
        verbose_name = "Compte"
        verbose_name_plural = "Comptes"
        indexes = [models.Index(fields=["account_class", "account_type"])]

    def __str__(self):
        return f"{self.code} — {self.label}"


class Partner(models.Model):
    """Tiers unifié client / fournisseur / intra-groupe (M1/M2/M4, RF-ERP-01/10/30)."""

    class Kind(models.TextChoices):
        CLIENT = "client", "Client"
        FOURNISSEUR = "fournisseur", "Fournisseur"
        BOTH = "both", "Client et fournisseur"
        AUTRE = "autre", "Autre"

    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    name = models.CharField(max_length=200, verbose_name="Raison sociale")
    kind = models.CharField(
        max_length=12, choices=Kind.choices, verbose_name="Type", db_index=True
    )
    tax_id = models.CharField(max_length=40, blank=True, verbose_name="NIF / identifiant fiscal")
    phone = models.CharField(max_length=40, blank=True, verbose_name="Téléphone")
    email = models.EmailField(blank=True, verbose_name="Email")
    address = models.TextField(blank=True, verbose_name="Adresse")
    currency = models.ForeignKey(
        Currency,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="partners",
        verbose_name="Devise",
    )
    is_global_rental = models.BooleanField(
        default=False, verbose_name="Intra-groupe GLOBAL RENTAL"
    )
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Tiers"
        verbose_name_plural = "Tiers"
        indexes = [models.Index(fields=["kind", "is_active"])]

    def __str__(self):
        return f"{self.code} — {self.name}"


class Article(models.Model):
    """Article / prestation (produit, service, matière) — M2/M3/M5, RF-ERP-10/20/40."""

    class ArticleType(models.TextChoices):
        PRODUIT = "produit", "Produit"
        SERVICE = "service", "Service / prestation"
        MATIERE = "matiere", "Matière première"
        CONSOMMABLE = "consommable", "Consommable"

    code = models.CharField(max_length=30, unique=True, verbose_name="Code")
    label = models.CharField(max_length=200, verbose_name="Désignation")
    article_type = models.CharField(
        max_length=12, choices=ArticleType.choices, verbose_name="Type", db_index=True
    )
    unit = models.ForeignKey(
        UnitOfMeasure,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="articles",
        verbose_name="Unité",
    )
    purchase_price = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Prix d'achat"
    )
    sale_price = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Prix de vente"
    )
    account = models.ForeignKey(
        Account,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="articles",
        verbose_name="Compte de rattachement",
    )
    is_stockable = models.BooleanField(default=False, verbose_name="Géré en stock")
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "Article"
        verbose_name_plural = "Articles"
        indexes = [models.Index(fields=["article_type", "is_active"])]

    def __str__(self):
        return f"{self.code} — {self.label}"


class AnalyticAxis(models.Model):
    """Axe analytique (référentiel multi-axes) — M11, RF-ERP-A0."""

    class AxisType(models.TextChoices):
        PROJET = "projet", "Projet / affaire"
        CHANTIER = "chantier", "Chantier"
        CENTRE_COUT = "centre_cout", "Centre de coût"
        SITE = "site", "Site"

    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    label = models.CharField(max_length=120, verbose_name="Libellé")
    axis_type = models.CharField(
        max_length=12, choices=AxisType.choices, verbose_name="Type d'axe", db_index=True
    )
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
        verbose_name="Axe parent",
    )
    is_active = models.BooleanField(default=True, verbose_name="Actif")

    class Meta:
        ordering = ["code"]
        verbose_name = "Axe analytique"
        verbose_name_plural = "Axes analytiques"

    def __str__(self):
        return f"{self.code} — {self.label}"


class AnalyticAccount(models.Model):
    """Valeur d'un axe analytique (ex. chantier OF-2026-014)."""

    axis = models.ForeignKey(
        AnalyticAxis, on_delete=models.CASCADE, related_name="values", verbose_name="Axe"
    )
    code = models.CharField(max_length=30, verbose_name="Code")
    label = models.CharField(max_length=200, verbose_name="Libellé")
    is_active = models.BooleanField(default=True, verbose_name="Active")

    class Meta:
        ordering = ["axis", "code"]
        verbose_name = "Valeur analytique"
        verbose_name_plural = "Valeurs analytiques"
        constraints = [
            models.UniqueConstraint(fields=["axis", "code"], name="uniq_analytic_value")
        ]

    def __str__(self):
        return f"{self.axis.code}:{self.code}"
