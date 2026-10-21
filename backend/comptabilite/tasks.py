"""Tâches Celery M10 — suivi des clôtures mensuelles : envoi Direction à J+4 et alerte de retard."""

from datetime import timedelta

from celery import shared_task
from django.core.exceptions import ValidationError
from django.utils import timezone

from .cloture import envoyer_direction
from .models import ClotureMensuelle
from .services import get_param


@shared_task
def suivre_clotures_mensuelles():
    """Envoie à la Direction les synthèses échues (J+n) et alerte la comptabilité des clôtures en retard."""
    from accounting_kernel.models import Period
    from users.models import User
    from workflow.models import Notification

    jour = timezone.localdate()
    envoyees, alertes = [], []

    for cm in ClotureMensuelle.objects.filter(
        statut=ClotureMensuelle.Statut.CLOTUREE, envoyee_le__isnull=True, echeance_envoi__lte=jour
    ).select_related("period"):
        try:
            envoyer_direction(cm, None)
            envoyees.append(str(cm.period))
        except ValidationError:
            continue  # pas de destinataire Direction : réessayé au prochain passage

    delai = timedelta(days=int(get_param("CLOTURE_JOUR_ENVOI")))
    # Mois récents seulement : on n'alerte pas sur l'historique ancien.
    for periode in Period.objects.filter(
        status=Period.Status.OPEN, end_date__lt=jour - delai, end_date__gte=jour - timedelta(days=62)
    ):
        sujet = f"Clôture comptable {periode} en retard"
        debut_jour = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        message = (
            f"La période {periode} n'est pas clôturée alors que l'échéance d'envoi à la Direction "
            f"(J+{int(get_param('CLOTURE_JOUR_ENVOI'))}) est dépassée."
        )
        for user in User.objects.filter(is_active=True, role__in=(User.Role.FINANCE, User.Role.COMPTABLE)):
            if not Notification.objects.filter(user=user, subject=sujet, created_at__gte=debut_jour).exists():
                Notification.objects.create(user=user, subject=sujet, message=message, kind="reminder")
        alertes.append(str(periode))
    return {
        "envoyees": envoyees, "alertes": alertes, "tresorerie": alerter_tresorerie_13_semaines(),
        "locations_gr": comptabiliser_locations_gr(),
    }


def comptabiliser_locations_gr():
    """Fil rouge 618 : passe l'écriture Dr 618 / Cr 401100 des locations GR terminées (M4) non encore comptabilisées."""
    from .gr import comptabiliser_location_gr_auto, locations_a_comptabiliser

    return [loc.code for loc in locations_a_comptabiliser() if comptabiliser_location_gr_auto(loc)]


@shared_task
def alerter_tresorerie_13_semaines():
    """Alerte (notification + e-mail) si le solde de trésorerie prévu passe sous le seuil dans l'horizon."""
    from .tresorerie import alerter_tresorerie

    return alerter_tresorerie()
