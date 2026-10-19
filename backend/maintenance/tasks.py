"""Tâches Celery M8 — maintenance préventive calendaire (lot 14, CDC M8 §13.4)."""

from celery import shared_task

from .preventif import declencher_plans
from .services import notifier_maintenance


@shared_task
def declencher_plans_preventifs():
    """Génère chaque jour les OT préventifs des plans échus (calendrier ou seuil compteur), puis prévient la
    maintenance des échéances proches (pré-alerte) et des machines sous les seuils de fiabilité."""
    codes = [ot.code for ot in declencher_plans()]
    notifier_maintenance()
    return codes
