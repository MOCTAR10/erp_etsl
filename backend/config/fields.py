"""Champs transverses — chiffrement au repos des données personnelles (PII)."""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models

PREFIX = "enc1:"


def _fernet():
    """Clé dédiée `FIELD_ENCRYPTION_KEY` (clé Fernet) ; à défaut dérivée de `SECRET_KEY` (dev/tests)."""
    cle = getattr(settings, "FIELD_ENCRYPTION_KEY", "") or ""
    if not cle:
        cle = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest()).decode()
    return Fernet(cle.encode() if isinstance(cle, str) else cle)


class EncryptedCharField(models.TextField):
    """Texte chiffré (Fernet) en base ; clair côté Python.

    Non filtrable en SQL (chiffrement non déterministe). Une valeur historique en clair (sans préfixe) est lue
    telle quelle puis chiffrée à la prochaine écriture.
    """

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if not value or str(value).startswith(PREFIX):
            return value
        return PREFIX + _fernet().encrypt(str(value).encode()).decode()

    def from_db_value(self, value, expression, connection):
        if value and value.startswith(PREFIX):
            try:
                return _fernet().decrypt(value[len(PREFIX):].encode()).decode()
            except InvalidToken:
                return ""  # clé changée : jamais de donnée chiffrée exposée telle quelle
        return value
