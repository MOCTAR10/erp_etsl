"""Outils communs du jeu vitrine : calendrier glissant (12 mois), aléa déterministe, horodatage rétroactif."""

import calendar
import random
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.utils import timezone

MOIS = 12  # profondeur de l'historique (mois glissants, le mois courant compris)


def debut_mois(today, k):
    """Premier jour du mois situé `k` mois avant le mois de `today` (k = 0 : mois courant)."""
    annee, mois = today.year, today.month - k
    while mois <= 0:
        mois += 12
        annee -= 1
    return date(annee, mois, 1)


def ajouter_mois(jour, n):
    total = jour.month - 1 + n
    annee, mois = jour.year + total // 12, total % 12 + 1
    return jour.replace(year=annee, month=mois, day=min(jour.day, calendar.monthrange(annee, mois)[1]))


MOIS_FR = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
           "novembre", "décembre")


def libelle_mois(jour):
    return f"{MOIS_FR[jour.month - 1]} {jour.year}"


def fin_mois(jour):
    return jour.replace(day=calendar.monthrange(jour.year, jour.month)[1])


def jour_du_mois(today, k, jour):
    """Jour `jour` du mois k (borné à la fin du mois et, pour le mois courant, à hier au plus tard)."""
    d = debut_mois(today, k)
    d = d.replace(day=min(jour, calendar.monthrange(d.year, d.month)[1]))
    if d >= today:
        d = max(today - timedelta(days=1), debut_mois(today, k))
    return d


def ouvre(jour):
    """Ramène un samedi / dimanche au vendredi précédent."""
    while jour.weekday() >= 5:
        jour -= timedelta(days=1)
    return jour


def instant(jour, heure=9):
    return timezone.make_aware(datetime.combine(jour, time(heure, 0)))


CREUX = {12: Decimal("0.85"), 1: Decimal("0.90"), 8: Decimal("0.92")}  # fêtes de fin d'année, congés d'août


def saison(today, k):
    """Coefficient d'activité du mois k : croissance régulière sur l'année, creux saisonniers légers."""
    croissance = Decimal("0.80") + Decimal("0.40") * Decimal(MOIS - 1 - k) / Decimal(MOIS - 1)
    return croissance * CREUX.get(debut_mois(today, k).month, Decimal("1"))


def arrondi(montant, pas=1000):
    """Montant FCFA entier, arrondi au millier (les montants « ronds » sont la norme des situations / achats)."""
    return int(Decimal(montant) / pas + Decimal("0.5")) * pas


def alea(cle):
    """Générateur pseudo-aléatoire déterministe par clé : le jeu est identique d'une base à l'autre."""
    return random.Random(f"etsl-vitrine-{cle}")


def antidater(modele, pk, **champs):
    """Horodatages techniques (created_at, …) ramenés à la date métier : historique crédible des séries mensuelles.

    UPDATE direct (pas de save()) : aucun signal, aucune règle métier rejouée — seules des dates d'audit bougent.
    """
    modele.objects.filter(pk=pk).update(**champs)


@contextmanager
def dater_documents(jour, heure=15):
    """Les pièces GED générées pendant le bloc (PDF de BC, de réception, de facture, PV…) prennent la date métier."""
    from documents.models import Document

    debut = timezone.now()
    yield
    Document.objects.filter(created_at__gte=debut).update(created_at=instant(jour, heure))
