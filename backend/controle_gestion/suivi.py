"""Suivi inter-modules M11 : marge à terminaison reçue de M3 (outbox) et balance âgée lue depuis M10.

- M3 → M11 : M3 publie un événement outbox `operations.marge_terminaison` par affaire ; l'abonné ci-dessous garde le
  dernier relevé de chaque affaire (`MargeTerminaisonAffaire`), affiché dans le contrôle de gestion.
- M10 → M11 : la balance âgée clients (411) / fournisseurs (401) de la comptabilité est servie telle quelle (mêmes
  tranches paramétrées `BAL_AGEE_TRANCHE_*`), sans recalcul côté M11.
"""

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from outbox.subscribers import subscriber

TOPIC_MARGE = "operations.marge_terminaison"


def _dec(v):
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


@subscriber(TOPIC_MARGE)
def recevoir_marge_terminaison(event):
    """Abonné outbox : enregistre (ou remplace) la marge à terminaison publiée par M3 pour l'affaire."""
    from commercial.models import Affaire

    from .models import MargeTerminaisonAffaire

    data = event.payload or {}
    affaire = Affaire.objects.filter(pk=data.get("affaire")).first() if data.get("affaire") else None
    if affaire is None and data.get("affaire_code"):
        affaire = Affaire.objects.filter(code=data["affaire_code"]).first()
    if affaire is None:
        return None  # affaire supprimée entre-temps : événement consommé sans effet
    publie = parse_datetime(data.get("publie_le") or "") or timezone.now()
    with transaction.atomic():
        obj = MargeTerminaisonAffaire.objects.select_for_update().filter(affaire=affaire).first()
        if obj is not None and obj.publie_le and obj.publie_le > publie:
            return obj  # événement plus ancien que le relevé détenu : ignoré (livraison hors ordre)
        valeurs = {
            "avancement_pct": _dec(data.get("avancement_pct")),
            "chiffre_affaires": _dec(data.get("chiffre_affaires")),
            "couts_engages": _dec(data.get("couts_engages")),
            "cout_a_terminaison": _dec(data.get("cout_a_terminaison")),
            "marge_a_terminaison": _dec(data.get("marge_a_terminaison")),
            "marge_pct": _dec(data.get("marge_pct")),
            "ordres": list(data.get("ordres") or [])[:200],
            "publie_le": publie,
            "publie_par": (data.get("publie_par") or "")[:254],
            "evenement": event.pk,
        }
        if obj is None:
            return MargeTerminaisonAffaire.objects.create(affaire=affaire, **valeurs)
        for k, v in valeurs.items():
            setattr(obj, k, v)
        obj.save()
        return obj


def balances_agees(date_to=None):
    from comptabilite.etats import balance_agee

    return {"clients": balance_agee("clients", date_to), "fournisseurs": balance_agee("fournisseurs", date_to)}
