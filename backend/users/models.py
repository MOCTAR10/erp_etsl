import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class UserManager(BaseUserManager):
    """Custom manager using email as the identifier (RF-55: email + password)."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("L'adresse email est obligatoire")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Utilisateur du système — identifié par email, rôles ETSL (RF-62)."""

    class Role(models.TextChoices):
        # Rôle technique (hors 12 fonctions).
        ADMIN = "admin", "Administrateur (technique)"
        # 12 fonctions ETSL (MANUEL ch.2).
        PDG = "pdg", "PDG"
        DGA = "dga", "DGA"
        SECRETAIRE_GENERAL = "secretaire_general", "Secrétariat Général"
        DIRECTEUR_PROJETS = "directeur_projets", "Directeur Projets"
        DIRECTEUR_OPERATIONS = "directeur_operations", "Directeur Opérations"
        RH = "rh", "Ressources Humaines"
        FINANCE = "finance", "Finance / Comptabilité / Contrôle de gestion"
        QAQC = "qaqc", "QA/QC"
        HSE = "hse", "HSE"
        LOGISTIQUE = "logistique", "Logistique & Magasin"
        MAINTENANCE = "maintenance", "Maintenance"
        CHEF_ATELIER = "chef_atelier", "Chef d'atelier / chantier"
        # Codes hérités (rétro-compatibilité des données existantes).
        DIRECTION = "direction", "Direction (hérité)"
        CHEF_SERVICE = "chef_service", "Chef de service (hérité)"
        COMPTABLE = "comptable", "Comptable (hérité)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, verbose_name="Adresse email")
    first_name = models.CharField(max_length=150, blank=True, verbose_name="Prénom")
    last_name = models.CharField(max_length=150, blank=True, verbose_name="Nom")
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.ADMIN,
        verbose_name="Rôle",
    )
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    # MFA TOTP (lot 15b, CDC §8.2) : le secret ne sort jamais par l'API ; `mfa_dernier_pas` interdit le rejeu d'un code.
    mfa_secret = models.CharField(max_length=64, blank=True, editable=False, verbose_name="Secret TOTP")
    mfa_active = models.BooleanField(default=False, verbose_name="MFA activée")
    mfa_active_le = models.DateTimeField(null=True, blank=True, verbose_name="MFA activée le")
    mfa_dernier_pas = models.BigIntegerField(null=True, blank=True, editable=False)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []


    # Absentes d'AbstractBaseUser : une trentaine de serializers (`demandeur_name`, `created_by_name`…)
    # s'appuient sur `get_full_name` et affichaient donc des noms vides.
    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self):
        return self.first_name

    class Meta:
        verbose_name = "Utilisateur"
        verbose_name_plural = "Utilisateurs"

    def __str__(self):
        return self.email


class JournalAcces(models.Model):
    """Journal des accès inaltérable (EX-G-10) : connexions, tentatives, étapes MFA, exports — conservé 5 ans."""

    class Evenement(models.TextChoices):
        CONNEXION = "connexion", "Connexion réussie"
        ECHEC_CONNEXION = "echec_connexion", "Tentative de connexion échouée"
        CONNEXION_BLOQUEE = "connexion_bloquee", "Tentative bloquée (limite de débit)"
        MFA_ENROLEMENT = "mfa_enrolement", "Enrôlement MFA"
        MFA_SUCCES = "mfa_succes", "Code MFA accepté"
        MFA_ECHEC = "mfa_echec", "Code MFA refusé"
        MFA_REINITIALISATION = "mfa_reinitialisation", "MFA réinitialisée"
        EXPORT = "export", "Export / téléchargement de données"

    RETENTION_ANS = 5

    id = models.BigAutoField(primary_key=True)
    evenement = models.CharField(max_length=24, choices=Evenement.choices, db_index=True, verbose_name="Événement")
    user = models.ForeignKey(
        "users.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="journal_acces",
        verbose_name="Utilisateur",
    )
    email = models.CharField(max_length=254, blank=True, db_index=True, verbose_name="Identifiant saisi")
    ip = models.GenericIPAddressField(null=True, blank=True, verbose_name="Adresse IP")
    user_agent = models.CharField(max_length=255, blank=True, verbose_name="Navigateur")
    chemin = models.CharField(max_length=255, blank=True, verbose_name="Ressource")
    details = models.JSONField(default=dict, blank=True, verbose_name="Détails")
    cree_le = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Horodatage")

    class Meta:
        ordering = ["-cree_le"]
        verbose_name = "Entrée du journal des accès"
        verbose_name_plural = "Journal des accès"

    def __str__(self):
        return f"{self.cree_le:%Y-%m-%d %H:%M:%S} {self.evenement} {self.email}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Journal des accès inaltérable : aucune modification.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Journal des accès inaltérable : aucune suppression.")
