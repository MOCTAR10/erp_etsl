import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.conf import settings
from django.db import models

from config.fields import EncryptedCharField


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
        # Consommateurs de la Couche D (CDC : DG, DAF, CG, responsable projet, chargé d'affaires).
        CHARGE_AFFAIRES = "charge_affaires", "Chargé d'affaires"
        CONTROLEUR_GESTION = "controleur_gestion", "Contrôleur de gestion"
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
    # Écarts transverses (§8.2 chiffrement au repos) : secret chiffré en base (Fernet, `FIELD_ENCRYPTION_KEY`).
    mfa_secret = EncryptedCharField(blank=True, default="", editable=False, verbose_name="Secret TOTP (chiffré)")
    mfa_active = models.BooleanField(default=False, verbose_name="MFA activée")
    mfa_active_le = models.DateTimeField(null=True, blank=True, verbose_name="MFA activée le")
    mfa_dernier_pas = models.BigIntegerField(null=True, blank=True, editable=False)
    # Réinitialisation par l'administrateur : changement de mot de passe imposé à la prochaine connexion.
    doit_changer_mdp = models.BooleanField(default=False, verbose_name="Doit changer son mot de passe")
    # EX-G-03 : site ETSL de rattachement (référentiel paramétrable ; reconnu automatiquement depuis le texte libre).
    site_etsl = models.ForeignKey(
        "referentiels.Site", null=True, blank=True, on_delete=models.PROTECT, related_name="utilisateurs", verbose_name="Site ETSL"
    )

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
        MDP_CHANGE = "mdp_change", "Mot de passe changé par l'utilisateur"
        MDP_OUBLI = "mdp_oubli", "Demande de lien « mot de passe oublié »"
        MDP_REINITIALISATION = "mdp_reinitialisation", "Mot de passe réinitialisé"

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


class ParametreTransverse(models.Model):
    """Paramètre transverse (socle) modifiable par ETSL : rétention de la piste d'audit, courriels d'alerte,
    fenêtre de maintenance, exercice de restauration, seuil de performance (écarts transverses).

    Valeur provisoire tant qu'ETSL ne l'a pas confirmée ; défauts créés à la volée par `users.parametres`.
    `valeur` porte les nombres, `texte` les valeurs libres (fenêtre, responsable).
    """

    class StatutValeur(models.TextChoices):
        PROVISOIRE = "provisoire", "Provisoire"
        CONFIRME = "confirme", "Confirmé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=40, unique=True, verbose_name="Identifiant")
    label = models.CharField(max_length=200, verbose_name="Libellé")
    valeur = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Valeur")
    texte = models.CharField(max_length=200, blank=True, verbose_name="Valeur texte")
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
        verbose_name = "Paramètre transverse"
        verbose_name_plural = "Paramètres transverses"

    def __str__(self):
        return f"{self.code} = {self.texte or self.valeur} {self.unite}"

    @property
    def est_provisoire(self):
        return self.statut_valeur != self.StatutValeur.CONFIRME
