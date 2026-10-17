"""Authentification multifacteur TOTP (RFC 6238) des rôles sensibles — lot 15b, CDC §8.2.

Implémentation native (HMAC-SHA1, pas de 30 s, 6 chiffres), compatible avec les applications d'authentification
courantes (Google Authenticator, Microsoft Authenticator, FreeOTP…). Aucune dépendance externe.

Étape MFA : après un mot de passe correct, le serveur remet un **jeton MFA signé** (5 min) au lieu des jetons JWT ;
les JWT ne sont délivrés qu'après un code TOTP valide. Un code déjà utilisé ne peut pas être rejoué.
"""

import base64
import hashlib
import hmac
import os
import struct
import time
from urllib.parse import quote

from django.conf import settings
from django.core import signing

PAS = 30
CHIFFRES = 6
FENETRE = 1  # tolérance d'horloge : ± 1 pas
DUREE_JETON = 300
SEL = "etls.mfa"
EMETTEUR = "ETSL ERP"


def generer_secret():
    return base64.b32encode(os.urandom(20)).decode().rstrip("=")


def _cle(secret):
    secret = secret.strip().replace(" ", "").upper()
    return base64.b32decode(secret + "=" * (-len(secret) % 8))


def _code(secret, compteur):
    digest = hmac.new(_cle(secret), struct.pack(">Q", compteur), hashlib.sha1).digest()
    decalage = digest[-1] & 0x0F
    valeur = struct.unpack(">I", digest[decalage:decalage + 4])[0] & 0x7FFFFFFF
    return f"{valeur % 10 ** CHIFFRES:0{CHIFFRES}d}"


def totp(secret, instant=None):
    return _code(secret, int((time.time() if instant is None else instant) // PAS))


def verifier(secret, code, dernier_pas=None):
    """Renvoie le pas validé (à mémoriser contre le rejeu) ou None."""
    code = str(code or "").strip().replace(" ", "")
    if not secret or len(code) != CHIFFRES or not code.isdigit():
        return None
    courant = int(time.time() // PAS)
    for pas in range(courant - FENETRE, courant + FENETRE + 1):
        if dernier_pas is not None and pas <= dernier_pas:
            continue
        if hmac.compare_digest(_code(secret, pas), code):
            return pas
    return None


def uri_otpauth(secret, email):
    libelle = quote(f"{EMETTEUR}:{email}")
    return f"otpauth://totp/{libelle}?secret={secret}&issuer={quote(EMETTEUR)}&digits={CHIFFRES}&period={PAS}"


def mfa_requise(user):
    roles = [r for r in getattr(settings, "MFA_ROLES", []) if r]
    return bool(user.mfa_active or user.role in roles)


def emettre_jeton(user):
    return signing.dumps({"u": str(user.pk)}, salt=SEL)


def lire_jeton(jeton):
    """Identifiant d'utilisateur porté par un jeton MFA valide et non expiré, sinon None."""
    try:
        return signing.loads(str(jeton or ""), salt=SEL, max_age=DUREE_JETON)["u"]
    except (signing.BadSignature, KeyError, TypeError):
        return None
