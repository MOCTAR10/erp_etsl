"""Tâches Celery M5 — inventaires tournants planifiés (clôture M5, CDC §7.11)."""

from celery import shared_task

from .cloture import planifier_inventaires_tournants
from .services import notifier_alertes_stock


@shared_task
def planifier_inventaires():
    """Prépare chaque jour les inventaires tournants des plans échus, puis notifie les alertes stock (seuil minimal,
    péremption, fournisseur non agréé) à la logistique et à la direction des opérations."""
    codes = [inv.code for inv in planifier_inventaires_tournants()]
    notifier_alertes_stock()
    return codes
