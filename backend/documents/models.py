import uuid

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from django.utils import timezone


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
    circuit = models.ForeignKey(
        "workflow.Circuit",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="document_types",
        verbose_name="Circuit de validation (RF-29 à 31)",
    )
    officiel = models.BooleanField(
        default=False, verbose_name="Document officiel (signé et scellé)",
        help_text="Archivage seulement avec une signature avancée achevée sur la version courante (CDC M12).",
    )
    officiel_confirme_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Caractère officiel confirmé par",
    )
    officiel_confirme_le = models.DateTimeField(null=True, blank=True, verbose_name="Confirmé le")
    # Écarts M12 : durée de rétention éditable à l'écran, provisoire tant qu'ETSL ne l'a pas confirmée.
    retention_confirmee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Durée de rétention confirmée par",
    )
    retention_confirmee_le = models.DateTimeField(null=True, blank=True, verbose_name="Rétention confirmée le")

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

    # Cycle de vie / workflow (RF-40 : actions automatiques au changement de statut)
    submitted_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Soumis le (circuit de validation)"
    )
    archived_at = models.DateTimeField(null=True, blank=True, verbose_name="Archivé le")
    rejected_at = models.DateTimeField(null=True, blank=True, verbose_name="Rejeté le")
    rejection_reason = models.TextField(blank=True, verbose_name="Motif de rejet (RF-39)")

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

    # Recherche full-text (RF-23/26/27) — OCR invisible + métadonnées.
    extracted_text = models.TextField(
        blank=True, verbose_name="Texte extrait (OCR invisible, RF-27)"
    )
    search_vector = SearchVectorField(
        null=True, editable=False, verbose_name="Index full-text"
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Document"
        verbose_name_plural = "Documents"
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["document_date"]),
            GinIndex(fields=["search_vector"], name="doc_search_gin"),
        ]

    def __str__(self):
        return self.title

    @property
    def is_checked_out(self):
        return self.checked_out_by_id is not None


class DocumentAccess(models.Model):
    """ACL au niveau document (RF-57) — outrepasse la matrice des rôles."""

    class Permission(models.TextChoices):
        READ = "read", "Lecture"
        WRITE = "write", "Écriture"
        DENY = "deny", "Refus explicite"

    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="acl"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="document_acls"
    )
    permission = models.CharField(
        max_length=10, choices=Permission.choices, default=Permission.READ
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Droit document (ACL)"
        verbose_name_plural = "Droits document (ACL)"
        constraints = [
            models.UniqueConstraint(
                fields=["document", "user"], name="uniq_document_access"
            )
        ]


class DossierAccess(models.Model):
    """ACL au niveau dossier / collection (RF-58) — hérité par les descendants."""

    class Permission(models.TextChoices):
        READ = "read", "Lecture"
        WRITE = "write", "Écriture"
        DENY = "deny", "Refus explicite"

    dossier = models.ForeignKey(
        Dossier, on_delete=models.CASCADE, related_name="acl"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="dossier_acls"
    )
    permission = models.CharField(
        max_length=10, choices=Permission.choices, default=Permission.READ
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Droit dossier (ACL)"
        verbose_name_plural = "Droits dossier (ACL)"
        constraints = [
            models.UniqueConstraint(
                fields=["dossier", "user"], name="uniq_dossier_access"
            )
        ]


class AuditLog(models.Model):
    """Piste d'audit (RF-63 à 65) — traçabilité des actions sensibles."""

    class Action(models.TextChoices):
        CREATE = "create", "Création"
        UPDATE = "update", "Modification"
        DELETE = "delete", "Suppression"
        DOWNLOAD = "download", "Téléchargement / export"
        PRINT = "print", "Impression"
        ACL_GRANT = "acl_grant", "Droit accordé"
        ACL_REVOKE = "acl_revoke", "Droit retiré"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
        verbose_name="Utilisateur",
    )
    action = models.CharField(max_length=20, choices=Action.choices, verbose_name="Action")
    object_type = models.CharField(max_length=50, verbose_name="Type d'objet")
    object_id = models.CharField(max_length=36, verbose_name="Identifiant de l'objet")
    detail = models.JSONField(default=dict, blank=True, verbose_name="Détail")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="Adresse IP")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Horodatage")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Entrée d'audit"
        verbose_name_plural = "Piste d'audit"
        indexes = [
            models.Index(fields=["object_type", "object_id"]),
            models.Index(fields=["user", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.action} {self.object_type}:{self.object_id} ({self.created_at:%Y-%m-%d %H:%M})"


class SignatureRequest(models.Model):
    """Demande de signature électronique avancée d'une version de document (CL-OM-06).

    Signataires ordonnés ; l'empreinte SHA-256 de la version est FIGÉE à la création : toute altération du
    document avant ou après signature est détectée (identification du signataire + intégrité du document).
    """

    class Status(models.TextChoices):
        PENDING = "pending", "En cours"
        COMPLETED = "completed", "Signée"
        REFUSED = "refused", "Refusée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    version = models.ForeignKey(Version, on_delete=models.PROTECT, related_name="signature_requests")
    title = models.CharField(max_length=200, blank=True)
    message = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    document_sha256 = models.CharField(max_length=64, verbose_name="Empreinte figée de la version")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="signature_requests"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Demande de signature"
        verbose_name_plural = "Demandes de signature"

    def __str__(self):
        return f"{self.title or self.version_id} [{self.status}]"

    @property
    def is_expired(self):
        return self.status == self.Status.PENDING and timezone.now() > self.expires_at


class Signer(models.Model):
    """Signataire d'une demande : authentification forte (mot de passe + code e-mail) et scellé de preuve."""

    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        SIGNED = "signed", "A signé"
        REFUSED = "refused", "A refusé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(SignatureRequest, on_delete=models.CASCADE, related_name="signers")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="signatures")
    order = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    otp_hash = models.CharField(max_length=64, blank=True)
    otp_sent_at = models.DateTimeField(null=True, blank=True)
    otp_expires_at = models.DateTimeField(null=True, blank=True)
    otp_attempts = models.PositiveSmallIntegerField(default=0)
    signed_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    document_sha256 = models.CharField(max_length=64, blank=True)
    refusal_reason = models.CharField(max_length=300, blank=True)
    seal = models.CharField(max_length=64, blank=True, verbose_name="Sceau HMAC chaîné")

    class Meta:
        ordering = ["request", "order"]
        constraints = [
            models.UniqueConstraint(fields=["request", "order"], name="uniq_signer_order"),
            models.UniqueConstraint(fields=["request", "user"], name="uniq_signer_user"),
        ]

    def __str__(self):
        return f"{self.request_id} #{self.order} {self.user_id} [{self.status}]"


class DemandePurge(models.Model):
    """Purge d'un document arrivé au terme de sa durée de rétention (écarts M12, archivage légal).

    Proposée par le Secrétariat Général / l'administrateur, exécutée seulement après validation de la Direction
    Générale. La trace (titre, empreinte, type, fin de rétention, validateur) survit au document purgé.
    """

    class Statut(models.TextChoices):
        PROPOSEE = "proposee", "Proposée"
        EXECUTEE = "executee", "Validée et exécutée"
        REJETEE = "rejetee", "Rejetée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        Document, null=True, blank=True, on_delete=models.SET_NULL, related_name="demandes_purge",
        verbose_name="Document",
    )
    document_title = models.CharField(max_length=255, verbose_name="Titre du document")
    document_sha256 = models.CharField(max_length=64, blank=True, verbose_name="Empreinte du document")
    type_label = models.CharField(max_length=120, blank=True, verbose_name="Type de document")
    fin_retention = models.DateField(verbose_name="Fin de rétention")
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.PROPOSEE, verbose_name="Statut")
    motif = models.CharField(max_length=255, blank=True, verbose_name="Motif / commentaire")
    propose_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Proposée par",
    )
    valide_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Validée / rejetée par",
    )
    traite_le = models.DateTimeField(null=True, blank=True, verbose_name="Traitée le")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Demande de purge"
        verbose_name_plural = "Demandes de purge (fin de rétention)"

    def __str__(self):
        return f"{self.document_title} [{self.statut}]"
