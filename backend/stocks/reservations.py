"""Réservation physique en stock des besoins matière validés en préparation atelier (M3 → M5).

Un besoin matière M3 passé « réservé » (préparation validée ou OF lancé) crée une `ReservationStock` active : la
quantité est retirée du disponible des AUTRES consommations. La consommation de l'OF (mouvement M5 exécuté) solde
la réservation ; l'annulation ou la clôture de l'OF, ou une rupture constatée, la libère. Paramètre provisoire
`RESERVATION_BLOQUANTE` : 1 = une sortie d'un autre OF ne peut pas entamer le stock réservé, 0 = simple alerte.
"""

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from config.i18n import tr

ZERO = Decimal("0")


def _models():
    from .models import ReservationStock, StockQuant

    return ReservationStock, StockQuant


def stock_physique(article_id):
    _, StockQuant = _models()
    return StockQuant.objects.filter(article_id=article_id).aggregate(t=Sum("quantity"))["t"] or ZERO


def reserve_active(article_id, exclure_ordre_id=None):
    ReservationStock, _ = _models()
    qs = ReservationStock.objects.filter(article_id=article_id, statut=ReservationStock.Statut.ACTIVE)
    if exclure_ordre_id:
        qs = qs.exclude(ordre_id=exclure_ordre_id)
    total = ZERO
    for r in qs.only("quantite", "quantite_consommee"):
        total += r.reste
    return total


def disponible(article_id, exclure_ordre_id=None):
    """Stock physique (tous dépôts) moins les réservations actives des autres OF."""
    return stock_physique(article_id) - reserve_active(article_id, exclure_ordre_id)


@transaction.atomic
def reserver_besoin(besoin, user=None):
    """Réservation (idempotente) d'un besoin matière M3 : une réservation active par besoin, quantité mise à jour."""
    ReservationStock, _ = _models()
    resa = ReservationStock.objects.select_for_update().filter(
        besoin_id=besoin.pk, statut=ReservationStock.Statut.ACTIVE
    ).first()
    if resa is None:
        return ReservationStock.objects.create(
            article_id=besoin.article_id, ordre_id=besoin.ordre_id, besoin_id=besoin.pk, quantite=besoin.quantite,
            created_by=user if getattr(user, "is_authenticated", False) else None,
        )
    if resa.quantite != besoin.quantite:
        resa.quantite = besoin.quantite
        resa.save(update_fields=["quantite", "updated_at"])
    return resa


def _cloturer(resa, statut, motif=""):
    resa.statut = statut
    resa.motif = (motif or resa.motif)[:250]
    resa.cloturee_le = timezone.now()
    resa.save(update_fields=["statut", "motif", "cloturee_le", "updated_at"])


@transaction.atomic
def liberer_besoin(besoin_id, motif):
    ReservationStock, _ = _models()
    n = 0
    for resa in ReservationStock.objects.select_for_update().filter(besoin_id=besoin_id, statut=ReservationStock.Statut.ACTIVE):
        _cloturer(resa, ReservationStock.Statut.LIBEREE, motif)
        n += 1
    return n


@transaction.atomic
def liberer_ordre(ordre, motif):
    """Annulation / clôture de l'OF : toutes ses réservations encore actives sont libérées."""
    ReservationStock, _ = _models()
    n = 0
    for resa in ReservationStock.objects.select_for_update().filter(ordre_id=ordre.pk, statut=ReservationStock.Statut.ACTIVE):
        _cloturer(resa, ReservationStock.Statut.LIBEREE, motif)
        n += 1
    return n


@transaction.atomic
def liberer(resa, motif, user=None):
    ReservationStock, _ = _models()
    resa = ReservationStock.objects.select_for_update().get(pk=resa.pk)
    if resa.statut != ReservationStock.Statut.ACTIVE:
        from django.core.exceptions import ValidationError

        raise ValidationError("Réservation déjà soldée ou libérée.")
    _cloturer(resa, ReservationStock.Statut.LIBEREE, motif or f"Libérée manuellement par {getattr(user, 'email', '')}")
    if resa.besoin_id:
        from operations.models import BesoinMatiere

        BesoinMatiere.objects.filter(pk=resa.besoin_id, statut=BesoinMatiere.Statut.RESERVE).update(
            statut=BesoinMatiere.Statut.A_VERIFIER
        )
    return resa


def controler_sortie(mouvement):
    """Avant une consommation : le stock réservé par d'autres OF n'est pas consommable (si paramètre bloquant)."""
    from .models import MouvementStock
    from .services import get_param_stock

    if not mouvement.source_id or mouvement.destination_id or mouvement.type_mouvement != MouvementStock.Type.CONSOMMATION:
        return
    if get_param_stock("RESERVATION_BLOQUANTE") < 1:
        return
    reserve_autres = reserve_active(mouvement.article_id, exclure_ordre_id=mouvement.ordre_id)
    if reserve_autres <= 0:
        return
    libre = stock_physique(mouvement.article_id) - reserve_autres
    if mouvement.quantite > libre:
        raise ValueError(
            tr("Stock réservé par d'autres OF (%(reserve_autres)s) : %(max)s seulement consommable(s) pour %(mouvement_quantite)s demandé(s). Libérez une réservation ou consommez depuis l'OF réservataire.") % {"reserve_autres": reserve_autres, "max": max(libre, ZERO), "mouvement_quantite": mouvement.quantite}
        )


def consommer(mouvement):
    """Après une consommation exécutée pour un OF : solde ses réservations de l'article (FIFO), besoin « servi »."""
    from .models import MouvementStock

    ReservationStock, _ = _models()
    if not mouvement.ordre_id or mouvement.type_mouvement != MouvementStock.Type.CONSOMMATION:
        return
    reste = mouvement.quantite
    for resa in ReservationStock.objects.select_for_update().filter(
        ordre_id=mouvement.ordre_id, article_id=mouvement.article_id, statut=ReservationStock.Statut.ACTIVE
    ).order_by("created_at"):
        if reste <= 0:
            break
        pris = min(reste, resa.reste)
        resa.quantite_consommee += pris
        reste -= pris
        if resa.reste <= 0:
            resa.statut = ReservationStock.Statut.CONSOMMEE
            resa.cloturee_le = timezone.now()
            resa.motif = f"Consommée par {mouvement.code}"[:250]
            if resa.besoin_id:
                from operations.models import BesoinMatiere

                BesoinMatiere.objects.filter(pk=resa.besoin_id).update(statut=BesoinMatiere.Statut.SERVI)
        resa.save(update_fields=["quantite_consommee", "statut", "cloturee_le", "motif", "updated_at"])
