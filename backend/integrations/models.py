"""Framework d'intégration par fichiers (H-04 : CSV/XML, sans API) — incr.16.

Couvre la reprise de données (SAGE/ALAN) et les flux CFONB/MT940, CNSSG/CNAMGS, GR.
L'idempotence repose sur l'empreinte SHA-256 du fichier + une clé métier par ligne.
"""

import uuid

from django.conf import settings
from django.db import models


class ImportBatch(models.Model):
    """Lot d'import — journal de bord : idempotence par empreinte + compteurs."""

    class Connector(models.TextChoices):
        PARTNERS = "partners", "Tiers (CSV)"
        GL = "gl", "Écritures générales (CSV / XML — reprise SAGE)"
        SAGE = "sage", "Écritures SAGE (fichier d'export, gabarit paramétrable)"
        CFONB = "cfonb", "Relevés bancaires CFONB"
        MT940 = "mt940", "Relevé bancaire SWIFT MT940"
        CNSSG = "cnssg", "Cotisations CNSSG"
        CNAMGS = "cnamgs", "Cotisations CNAMGS"
        GENERIC = "generic", "Table générique"

    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        RUNNING = "running", "En cours"
        SUCCESS = "success", "Succès"
        PARTIAL = "partial", "Partiel (erreurs)"
        FAILED = "failed", "Échoué"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    connector = models.CharField(
        max_length=12, choices=Connector.choices, verbose_name="Connecteur", db_index=True
    )
    status = models.CharField(
        max_length=8, choices=Status.choices, default=Status.PENDING, verbose_name="Statut"
    )
    filename = models.CharField(max_length=255, verbose_name="Fichier")
    file_hash = models.CharField(max_length=64, verbose_name="SHA-256", db_index=True)
    total_rows = models.PositiveIntegerField(default=0, verbose_name="Lignes")
    created_rows = models.PositiveIntegerField(default=0, verbose_name="Créées")
    updated_rows = models.PositiveIntegerField(default=0, verbose_name="Mises à jour")
    error_rows = models.PositiveIntegerField(default=0, verbose_name="En erreur")
    error_message = models.TextField(blank=True, verbose_name="Message d'erreur global")
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="import_batches",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Lot d'import"
        verbose_name_plural = "Lots d'import"

    def __str__(self):
        return f"{self.get_connector_display()} [{self.status}] {self.filename}"

    @property
    def has_errors(self):
        return self.error_rows > 0


class BatchRow(models.Model):
    """Résultat par ligne importée — journal d'erreurs (rapprochement / audit)."""

    class Status(models.TextChoices):
        SUCCESS = "success", "Traitée"
        DUPLICATE = "duplicate", "Déjà présente (écartée)"
        ERROR = "error", "En erreur"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(
        ImportBatch, on_delete=models.CASCADE, related_name="rows", verbose_name="Lot"
    )
    row_number = models.PositiveIntegerField(verbose_name="N° de ligne")
    status = models.CharField(
        max_length=10, choices=Status.choices, verbose_name="Statut"
    )
    data = models.JSONField(default=dict, blank=True, verbose_name="Données")
    error_message = models.TextField(blank=True, verbose_name="Erreur")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["batch", "row_number"]
        verbose_name = "Ligne d'import"
        verbose_name_plural = "Lignes d'import"
        constraints = [
            models.UniqueConstraint(
                fields=["batch", "row_number"], name="uniq_batchrow_number"
            )
        ]

    def __str__(self):
        return f"{self.batch} l.{self.row_number} [{self.status}]"


class IdempotencyRecord(models.Model):
    """Réponse mémorisée d'une requête rejouable (saisies terrain hors-ligne, CL-OM-08).

    Clé `Idempotency-Key` générée par le mobile à la saisie : un rejeu (coupure réseau en plein
    envoi, double synchronisation) renvoie la réponse d'origine au lieu de dupliquer l'effet.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE,
        related_name="idempotency_records",
    )
    client = models.ForeignKey(
        "ApiClient", null=True, blank=True, on_delete=models.CASCADE, related_name="idempotency_records"
    )
    key = models.CharField(max_length=80, verbose_name="Idempotency-Key")
    method = models.CharField(max_length=8)
    path = models.CharField(max_length=255)
    status_code = models.PositiveSmallIntegerField()
    body = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Requête idempotente"
        verbose_name_plural = "Requêtes idempotentes"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "key"], condition=models.Q(user__isnull=False), name="uniq_idempotency_user_key"
            ),
            models.UniqueConstraint(
                fields=["client", "key"], condition=models.Q(client__isnull=False), name="uniq_idempotency_client_key"
            ),
        ]

    def __str__(self):
        return f"{self.method} {self.path} [{self.key}]"


class ApiClient(models.Model):
    """Client d'API externe (ex. système GLOBAL RENTAL) authentifié par jeton (CL-OM-09).

    La clé n'est JAMAIS stockée en clair : seul son SHA-256 l'est (la clé est aléatoire à 256 bits, un
    hachage rapide suffit). Elle n'est montrée qu'à la création. Droits = `scopes` (ex. `gr:read`, `gr:write`).
    """

    KEY_PREFIX = "etsl_gr_"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120, verbose_name="Nom du client")
    key_prefix = models.CharField(max_length=16, db_index=True, verbose_name="Préfixe de la clé")
    key_hash = models.CharField(max_length=64, unique=True, verbose_name="Empreinte SHA-256")
    scopes = models.JSONField(default=list, verbose_name="Droits (scopes)")
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="api_clients"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Client d'API"
        verbose_name_plural = "Clients d'API"

    def __str__(self):
        return f"{self.name} ({self.key_prefix}…)"

    @staticmethod
    def hash_key(key):
        import hashlib

        return hashlib.sha256(key.encode()).hexdigest()

    @classmethod
    def issue(cls, name, scopes, user=None):
        """Crée un client et renvoie `(client, clé_en_clair)` — la clé ne sera plus jamais affichée."""
        import secrets

        key = f"{cls.KEY_PREFIX}{secrets.token_urlsafe(32)}"
        client = cls.objects.create(
            name=name, scopes=list(scopes), key_prefix=key[:12], key_hash=cls.hash_key(key), created_by=user
        )
        return client, key

    def has_scope(self, scope):
        return self.is_active and scope in (self.scopes or [])


class WebhookEndpoint(models.Model):
    """Destination d'événements sortants (webhooks signés HMAC-SHA256)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    url = models.URLField(max_length=500)
    secret = models.CharField(max_length=120, verbose_name="Secret de signature")
    topics = models.JSONField(default=list, verbose_name="Sujets abonnés")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Webhook"
        verbose_name_plural = "Webhooks"

    def __str__(self):
        return f"{self.name} → {self.url}"


class WebhookDelivery(models.Model):
    """Une livraison (un événement vers un endpoint), avec reprise bornée."""

    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        DELIVERED = "delivered", "Livrée"
        FAILED = "failed", "Abandonnée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    endpoint = models.ForeignKey(WebhookEndpoint, on_delete=models.CASCADE, related_name="deliveries")
    topic = models.CharField(max_length=60, db_index=True)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    response_code = models.PositiveSmallIntegerField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Livraison de webhook"
        verbose_name_plural = "Livraisons de webhook"

    def __str__(self):
        return f"{self.topic} → {self.endpoint_id} [{self.status}]"


class GabaritImport(models.Model):
    """Gabarit de lecture d'un fichier d'export (SAGE transitoire, H-04 : fichier, jamais d'API).

    Séparateur, encodage, format de date, décimale et correspondance des colonnes sont des DONNÉES ETSL, modifiables
    à l'écran ; provisoire tant qu'ETSL ne l'a pas confirmé sur un export réel.
    """

    class StatutValeur(models.TextChoices):
        PROVISOIRE = "provisoire", "Provisoire"
        CONFIRME = "confirme", "Confirmé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=30, unique=True, verbose_name="Code")
    label = models.CharField(max_length=200, verbose_name="Libellé")
    separateur = models.CharField(max_length=3, default=";", verbose_name="Séparateur de colonnes")
    encodage = models.CharField(max_length=20, default="cp1252", verbose_name="Encodage")
    format_date = models.CharField(max_length=20, default="%d/%m/%Y", verbose_name="Format de date (strftime)")
    separateur_decimal = models.CharField(max_length=1, default=",", verbose_name="Séparateur décimal")
    colonnes = models.JSONField(default=dict, blank=True, verbose_name="Champ ERP → colonne du fichier")
    statut_valeur = models.CharField(
        max_length=10, choices=StatutValeur.choices, default=StatutValeur.PROVISOIRE, verbose_name="Statut"
    )
    confirme_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Confirmé par",
    )
    confirme_le = models.DateTimeField(null=True, blank=True, verbose_name="Confirmé le")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "Gabarit d'import"
        verbose_name_plural = "Gabarits d'import"

    def __str__(self):
        return f"{self.code} — {self.label}"

    @property
    def est_provisoire(self):
        return self.statut_valeur != self.StatutValeur.CONFIRME
