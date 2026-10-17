"""Tâches Celery M5 — inventaires tournants planifiés (clôture M5, CDC §7.11)."""

from celery import shared_task

from .cloture import planifier_inventaires_tournants


@shared_task
def planifier_inventaires():
    """Prépare chaque jour les inventaires tournants des plans échus."""
    return [inv.code for inv in planifier_inventaires_tournants()]
