"""Tâches Celery M11 — détection des écarts budgétaires > 10 % (lot 15, CDC M11 §4.4)."""

from celery import shared_task

from .services import alerter_sous_activite, detecter_ecarts, suivre_reporting


@shared_task
def detecter_ecarts_budgetaires():
    """Ouvre chaque jour les analyses d'écart des périodes écoulées (échéance J+5)."""
    alerter_sous_activite()  # budgets qui entrent au centre 99
    suivre_reporting()  # mois dont la publication dépasse J+6
    return [analyse.code for analyse in detecter_ecarts()]
