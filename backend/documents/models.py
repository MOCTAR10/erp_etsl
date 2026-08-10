import uuid

from django.conf import settings
from django.db import models


class DocumentType(models.Model):
    """Type de document — référence la durée de rétention (RF-51, spec §3.1)."""

    code = models.SlugField(max_length=60, unique=True)
    label = models.CharField(max_length=120, verbose_name="Libellé")
    retention_years = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="Durée de rétention (années)"
    )
    is_restricted_rh = models.BooleanField(
        default=False, verbose_name="Accès restreint RH (RF-33)"
    )

    class Meta:
        ordering = ["label"]
        verbose_name = "Type de document"
        verbose_name_plural = "Types de document"

    def __str__(self):
        return self.label


class Dossier(models.Model):
    """Collection hiérarchique — plan de classement multi-critères (RF-20/21)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, verbose_name="Nom du dossier")
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
        verbose_name="Dossier parent",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="created_dossiers",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Dossier"
        verbose_name_plural = "Dossiers"
        constraints = [
            models.UniqueConstraint(
                fields=["parent", "name"], name="uniq_dossier_sibling_name"
            )
        ]

    def __str__(self):
        return self.name

    @property
    def path(self):
        """Chemin complet de l'arborescence (ex : Client A / 2026 / Factures)."""
        parts = []
        node = self
        while node is not None:
            parts.append(node.name)
            node = node.parent
        return " / ".join(reversed(parts))


class Version(models.Model):
    """Version d'un document (RF-42/43) — fichier stocké dans MinIO."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey("Document", on_delete=models.CASCADE, related_name="versions")
    number = models.PositiveIntegerField(verbose_name="Numéro de version")
    file = models.FileField(upload_to="documents/%Y/%m/", verbose_name="Fichier")
    sha256 = models.CharField(max_length=64, verbose_name="Empreinte SHA-256 (RF-67)")
    size = models.PositiveBigIntegerField(verbose_name="Taille (octets)")
    original_filename = models.CharField(max_length=255, verbose_name="Nom d'origine")
    note = models.CharField(max_length=255, blank=True, verbose_name="Note de version")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["document", "-number"]
        verbose_name = "Version"

    def __str__(self):
        return f"{self.document_id} v{self.number}"


class Document(models.Model):
    """Document archivé — statuts, métadonnées, intégrité (RF-19/41-44, RF-67)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Brouillon"
        IN_VALIDATION = "in_validation", "En validation"
        REJECTED = "rejected", "Rejeté"
        ARCHIVED = "archived", "Archivé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, verbose_name="Titre")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name="Statut (RF-41)",
    )
    dossier = models.ForeignKey(
        Dossier,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="documents",
        verbose_name="Dossier",
    )
    type = models.ForeignKey(
        DocumentType,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="documents",
        verbose_name="Type de document",
    )

    # Métadonnées (RF-19 : date, fournisseur/client, projet/affaire, créateur,
    # type, montant, n° facture/contrat, mots-clés)
    document_date = models.DateField(null=True, blank=True, verbose_name="Date du document")
    counterparty = models.CharField(
        max_length=200, blank=True, verbose_name="Fournisseur / client"
    )
    project = models.CharField(max_length=200, blank=True, verbose_name="Projet / affaire")
    reference = models.CharField(
        max_length=200, blank=True, verbose_name="N° facture / contrat"
    )
    amount = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True, verbose_name="Montant"
    )
    keywords = models.JSONField(default=list, blank=True, verbose_name="Mots-clés")

    current_version = models.ForeignKey(
        Version,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Version courante",
    )
    sha256 = models.CharField(max_length=64, blank=True, verbose_name="Empreinte courante")

    # Verrouillage check-in / check-out (RF-44)
    checked_out_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="checked_out_documents",
        verbose_name="Verrouillé par",
    )
    checked_out_at = models.DateTimeField(null=True, blank=True, verbose_name="Verrouillé le")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="created_documents",
        verbose_name="Créé par",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Document"
        verbose_name_plural = "Documents"

    def __str__(self):
        return self.title

    @property
    def is_checked_out(self):
        return self.checked_out_by_id is not None
