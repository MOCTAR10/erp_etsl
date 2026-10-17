"""Tâches Celery de la couche D — notifications d'échéance J-90 / J-30 / J-15 / J-0 (CDC EX-G-05)."""

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
    "qualification_rh": (User.Role.RH,),
    "document": (User.Role.ADMIN,),
}


def _items(alertes):
    yield from alertes["documents"]
    for famille in ("conventions", "cautions", "assurances"):
        yield from alertes["juridique"][famille]
    yield from alertes["rh"]


@shared_task
def notifier_echeances():
    """Prévient les responsables des échéances atteignant un palier J-90 / J-30 / J-15 / J-0 aujourd'hui."""
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
