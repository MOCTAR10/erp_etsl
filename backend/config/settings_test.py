"""Réglages de TEST (pytest : voir backend/pytest.ini).

Objectif : suite complète en quelques minutes au lieu de ~45 min.
- Stockage en mémoire : les uploads réels vers MinIO/S3 étaient le premier coût de la suite ; aucun test ne dépend du
  vrai stockage (la GED forçait déjà InMemoryStorage au cas par cas). Une intégration MinIO réelle reste vérifiable
  par `documents/test_minio_integration.py` (activée par MINIO_INTEGRATION=1, jouée en CI).
- Hachage MD5 des mots de passe : `create_user` est appelé des centaines de fois ; PBKDF2 coûte ~100 ms par appel.
  Réservé aux tests (jamais en dev / prod).
- Celery en mode synchrone : pas de broker requis.
"""

from .settings import *  # noqa: F401,F403

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# MFA non imposée par défaut : les tests qui l'exercent posent `MFA_ROLES` par `override_settings`.
MFA_ROLES = []

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
