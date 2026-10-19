"""Tâches Celery de la couche D — notifications d'échéance J-90 / J-30 / J-15 / J-0 (CDC EX-G-05)."""

from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from config.echeances import PALIERS_NOTIFICATION
from users.models import User
from workflow.models import Notification
from workflow.notifications import notify

from .services import alertes_agregees

# Destinataires par famille d'échéance (rôles métier responsables du renouvellement).
DESTINATAIRES = {
    "convention": (User.Role.SECRETAIRE_GENERAL, User.Role.PDG, User.Role.DGA),
    "caution": (User.Role.SECRETAIRE_GENERAL, User.Role.PDG, User.Role.DGA),
    "assurance": (User.Role.SECRETAIRE_GENERAL, User.Role.PDG, User.Role.DGA),
    "contrat_rh": (User.Role.RH,),
    "qualification_rh": (User.Role.RH, User.Role.HSE),
    "aptitude_medicale": (User.Role.RH, User.Role.HSE),
    "epi": (User.Role.HSE,),
    "document": (User.Role.ADMIN,),
    "inspection_reglementaire": (User.Role.MAINTENANCE, User.Role.DIRECTEUR_OPERATIONS),
    "qualification_soudeur": (User.Role.QAQC, User.Role.DIRECTEUR_OPERATIONS),
}


def _items(alertes):
    yield from alertes["documents"]
    for famille in ("conventions", "cautions", "assurances"):
        yield from alertes["juridique"][famille]
    yield from alertes["rh"]
    yield from alertes.get("qualite", [])
    yield from alertes["maintenance"]


@shared_task
def notifier_echeances():
    """Prévient les responsables des échéances atteignant un palier J-90 / J-30 / J-15 / J-0 aujourd'hui.

    Passe d'abord en « expiré » les permis de travail dont la date de fin est dépassée (CDC M7-11), puis relance les
    CAPA, points d'ITP et réserves en retard (escalade d'une CAPA à la direction, CDC M6)."""
    from hse.services import expirer_permis
    from qualite.ecarts import relances_qualite

    expirer_permis()
    relances_qualite()
    debut_jour = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    envoyees = 0
    for item in _items(alertes_agregees()):
        if item.get("jours") not in PALIERS_NOTIFICATION:
            continue
        roles = DESTINATAIRES.get(item["type"])
        if not roles:
            continue
        sujet = f"Échéance J-{item['jours']} : {item['code']} — {item['libelle']}"[:255]
        message = (
            f"L'échéance « {item['libelle']} » ({item['code']}) arrive le "
            f"{item['date_echeance']:%d/%m/%Y}. Merci d'engager le renouvellement ou la clôture."
        )
        for user in User.objects.filter(role__in=roles, is_active=True):
            if Notification.objects.filter(user=user, subject=sujet, created_at__gte=debut_jour).exists():
                continue
            notify(user, sujet, message, kind="reminder")
            envoyees += 1
    return envoyees


@shared_task
def alimenter_cubes():
    """Alimente chaque jour, sans ressaisie, les cubes du mois courant et du mois précédent (si non archivés)."""
    from . import cubes

    aujourdhui = timezone.localdate()
    mois = [aujourdhui.strftime("%Y-%m"), (aujourdhui.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")]
    faits = 0
    for periode in mois:
        try:
            faits += cubes.alimenter_cube(periode)
        except ValueError:
            continue  # mois déjà archivé : on ne le touche plus
    return faits
