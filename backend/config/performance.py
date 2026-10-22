"""Mesure du temps de réponse (CDC §8.2 « < 3 s ») : en-tête `Server-Timing` sur chaque réponse API et journal
`etls.performance` des requêtes plus lentes que le seuil provisoire PERF_SEUIL_MS (écran « Paramètres ETSL »).

Le seuil est relu au plus toutes les 5 minutes (aucune requête SQL supplémentaire par appel).
"""

import logging
import time

logger = logging.getLogger("etls.performance")
_CACHE = {"seuil": None, "lu": 0.0}
RELECTURE_S = 300


def seuil_ms():
    maintenant = time.monotonic()
    if _CACHE["seuil"] is None or maintenant - _CACHE["lu"] > RELECTURE_S:
        from users.parametres import valeur_transverse

        _CACHE["seuil"] = float(valeur_transverse("PERF_SEUIL_MS"))
        _CACHE["lu"] = maintenant
    return _CACHE["seuil"]


class MesurePerformanceMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        debut = time.perf_counter()
        response = self.get_response(request)
        if not request.path.startswith("/api/"):
            return response
        duree = (time.perf_counter() - debut) * 1000
        response["Server-Timing"] = f"app;dur={duree:.0f}"
        try:
            if duree > seuil_ms():
                logger.warning("Requête lente %s %s : %.0f ms", request.method, request.path, duree)
        except Exception:  # noqa: BLE001 — la mesure ne bloque jamais la réponse
            pass
        return response
