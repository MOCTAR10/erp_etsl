"""Sonde de santé `GET /api/health/` (supervision, CI, répartiteur de charge).

200 si toutes les dépendances vérifiées répondent, **503** sinon (la supervision détecte la panne). La base est
toujours vérifiée ; le stockage objet S3 et Redis (broker Celery) le sont si `HEALTH_CHECK_S3` / `HEALTH_CHECK_REDIS`
sont vrais (env, faux par défaut : une sonde de vivacité ne doit pas dépendre d'un service optionnel en dev).
Chaque dépendance est rapportée : `ok`, `error` ou `non_verifie`. Aucun détail d'erreur n'est exposé (sonde publique).
"""

import logging

from django.conf import settings
from django.db import connection
from django.http import JsonResponse

logger = logging.getLogger(__name__)

OK, ERREUR, NON_VERIFIE = "ok", "error", "non_verifie"


def _base():
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")


def _stockage():
    from django.core.files.storage import default_storage

    default_storage.exists("health-check")


def _redis():
    from kombu import Connection

    with Connection(settings.CELERY_BROKER_URL, connect_timeout=2) as conn:
        conn.ensure_connection(max_retries=1, timeout=2)


def _verifier(nom, sonde):
    try:
        sonde()
        return OK
    except Exception as exc:  # noqa: BLE001 — toute panne de dépendance = « error »
        logger.error("Sonde de santé : %s en échec (%s)", nom, exc.__class__.__name__)
        return ERREUR


def health(request):
    """Vivacité + dépendances : 200 si tout est « ok », 503 dès qu'une dépendance vérifiée est en échec."""
    etats = {"database": _verifier("base", _base)}
    etats["storage"] = _verifier("stockage", _stockage) if getattr(settings, "HEALTH_CHECK_S3", False) else NON_VERIFIE
    etats["redis"] = _verifier("redis", _redis) if getattr(settings, "HEALTH_CHECK_REDIS", False) else NON_VERIFIE
    en_echec = ERREUR in etats.values()
    return JsonResponse({"status": ERREUR if en_echec else OK, **etats}, status=503 if en_echec else 200)
