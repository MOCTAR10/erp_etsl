"""Passerelle SMS (CDC M7 : alerte « permis imminent à valider », escalade d'un accident grave).

Paramétrée par l'environnement : sans `SMS_GATEWAY_URL`, rien n'est envoyé (notification interne + email seulement).
Fournisseur générique : POST JSON `{"to", "message", "sender"}` avec `Authorization: Bearer <SMS_GATEWAY_TOKEN>` ;
le numéro est le téléphone de la fiche salarié liée au compte. Un échec d'envoi n'interrompt jamais le traitement.
"""

import json
import logging
import urllib.request

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist

logger = logging.getLogger(__name__)


def numero_de(user):
    try:
        return (user.fiche_employe.telephone or "").strip()
    except ObjectDoesNotExist:
        return ""


def sms_actif():
    return bool(getattr(settings, "SMS_GATEWAY_URL", ""))


def envoyer_sms(user, message):
    """Envoie le SMS si la passerelle est configurée et le numéro connu ; retourne True si le fournisseur l'accepte."""
    numero = numero_de(user)
    if not (sms_actif() and numero):
        return False
    corps = json.dumps({"to": numero, "message": message[:480], "sender": settings.SMS_SENDER}).encode()
    entetes = {"Content-Type": "application/json"}
    if settings.SMS_GATEWAY_TOKEN:
        entetes["Authorization"] = f"Bearer {settings.SMS_GATEWAY_TOKEN}"
    requete = urllib.request.Request(settings.SMS_GATEWAY_URL, data=corps, headers=entetes, method="POST")
    try:
        with urllib.request.urlopen(requete, timeout=settings.SMS_GATEWAY_TIMEOUT) as reponse:  # noqa: S310 (URL de config)
            return 200 <= reponse.status < 300
    except Exception as exc:  # passerelle indisponible : la notification interne reste la référence
        logger.warning("SMS non envoyé à %s : %s", numero, exc)
        return False
