"""Indicateurs de fréquence HSE — TRIR / LTIR / LTIFR (lot 15, CDC M7 §9.7, reporting pétrolier C2).

TRIR = enregistrables × 200 000 / heures ; LTIR = avec arrêt × 200 000 / heures ;
LTIFR = avec arrêt × 1 000 000 / heures. Heures = pointages M9 de la période, sauf valeur saisie
(personnel sous-traitant inclus). Sans heures, les taux ne sont pas calculables (None).
"""

from decimal import Decimal

from django.db.models import Sum

from .models import Incident

BASE_OSHA = Decimal("200000")
BASE_MILLION = Decimal("1000000")


def _taux(nombre, base, heures):
    if not heures:
        return None
    return str((Decimal(nombre) * base / heures).quantize(Decimal("0.01")))


def indicateurs_frequence(debut, fin, heures=None):
    from rh_paie.models import SaisieTemps

    if heures is None:
        heures = (
            SaisieTemps.objects.filter(date__gte=debut, date__lte=fin).aggregate(total=Sum("heures"))["total"]
            or Decimal("0")
        )
    incidents = Incident.objects.filter(date_evenement__date__gte=debut, date_evenement__date__lte=fin)
    enregistrables = incidents.filter(consequence_humaine__in=Incident.CONSEQUENCES_ENREGISTRABLES)
    avec_arret = incidents.filter(consequence_humaine__in=Incident.CONSEQUENCES_AVEC_ARRET)
    nb_enr, nb_arret = enregistrables.count(), avec_arret.count()
    return {
        "debut": debut,
        "fin": fin,
        "heures": str(Decimal(heures).quantize(Decimal("0.01"))),
        "enregistrables": nb_enr,
        "avec_arret": nb_arret,
        "jours_perdus": avec_arret.aggregate(total=Sum("jours_arret"))["total"] or 0,
        "trir": _taux(nb_enr, BASE_OSHA, heures),
        "ltir": _taux(nb_arret, BASE_OSHA, heures),
        "ltifr": _taux(nb_arret, BASE_MILLION, heures),
    }
