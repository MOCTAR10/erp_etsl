"""Chronométrage des traitements lourds (CDC §8.2, CL-OM-01) sur le jeu `seed_volumetrie`.

Mesure : paie complète d'un mois (préparation + calcul de tous les bulletins VOL-), génération des PDF de bulletins,
traitements lourds (alimentation du cube BI du mois, marges M11 de l'exercice). Écrit `resultats/chrono.json`.

Usage (depuis backend/) : `python perf/chrono_traitements.py [--sortie perf/resultats/chrono.json]`.
Base de recette / CI uniquement : crée des bulletins brouillons pour les salariés VOL-.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.db import transaction  # noqa: E402
from django.utils import timezone  # noqa: E402


def chrono(fn):
    t0 = time.perf_counter()
    res = fn()
    return round(time.perf_counter() - t0, 2), res


def paie_complete(periode):
    from rh_paie.models import BulletinPaie, Employe
    from rh_paie.paie_m9a import preparer_bulletin

    ok, erreurs = 0, []
    for emp in Employe.objects.filter(code__startswith="VOL-").order_by("code"):
        try:
            with transaction.atomic():
                b = BulletinPaie.objects.filter(employe=emp, periode=periode).exclude(statut="annule").first() \
                    or BulletinPaie.objects.create(employe=emp, periode=periode)
                if b.statut == BulletinPaie.Statut.BROUILLON:
                    preparer_bulletin(b)
            ok += 1
        except Exception as exc:  # un bulletin en erreur est compté, la campagne continue
            erreurs.append(f"{emp.code}: {str(exc)[:120]}")
    return {"bulletins": ok, "erreurs": len(erreurs), "exemples_erreurs": erreurs[:5]}


def bulletins_pdf(periode):
    from rh_paie.models import BulletinPaie
    from rh_paie.services import bulletin_pdf

    n, octets = 0, 0
    for b in BulletinPaie.objects.filter(employe__code__startswith="VOL-", periode=periode).select_related("employe"):
        octets += len(bulletin_pdf(b))
        n += 1
    return {"pdf": n, "octets": octets}


def traitements_lourds(today):
    from accounting_kernel.models import FiscalYear
    from analytics.cubes import alimenter_cube
    from controle_gestion.services import compute_marges

    mesures = {}
    mesures["cube_mois_s"], _ = chrono(lambda: alimenter_cube(f"{today:%Y-%m}"))
    fy = FiscalYear.objects.filter(start_date__lte=today, end_date__gte=today).first()
    if fy:
        mesures["marges_exercice_s"], _ = chrono(lambda: compute_marges(fy.pk))
    return mesures


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sortie", default=str(BACKEND / "perf" / "resultats" / "chrono.json"))
    args = parser.parse_args()
    today = timezone.localdate()
    periode = today.replace(day=1)
    resultat = {"date": today.isoformat()}
    resultat["paie_complete_s"], resultat["paie"] = chrono(lambda: paie_complete(periode))
    resultat["bulletins_pdf_s"], resultat["bulletins"] = chrono(lambda: bulletins_pdf(periode))
    resultat["traitements"] = traitements_lourds(today)
    sortie = Path(args.sortie)
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_text(json.dumps(resultat, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(resultat, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
