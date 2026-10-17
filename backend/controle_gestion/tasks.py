"""Tâches Celery M11 — détection des écarts budgétaires > 10 % (lot 15, CDC M11 §4.4)."""

from celery import shared_task

from .services import detecter_ecarts


@shared_task
def detecter_ecarts_budgetaires():
    """Ouvre chaque jour les analyses d'écart des périodes écoulées (échéance J+5)."""
    return [analyse.code for analyse in detecter_ecarts()]
