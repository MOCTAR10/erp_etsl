"""Barèmes de cotisation de DÉMONSTRATION — valeurs illustratives, PAS les taux légaux.

Les taux CNSSG / CNAMGS / plafonds réels doivent être saisis et validés avec ETSL (écran
« Barèmes de cotisation » ou admin). Ce seed ne fait pas partie de `seed_all_demo`.
"""

from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand

from rh_paie.models import BaremeCotisation

DEMO = [
    # code, libellé, organisme, nature, taux %, plafond mensuel
    ("DEMO-S1", "Cotisation vieillesse salariale (démo)", "CNSSG", "salariale", "2.500", "1500000"),
    ("DEMO-S2", "Assurance maladie salariale (démo)", "CNAMGS", "salariale", "1.000", None),
    ("DEMO-P1", "Cotisations patronales (démo)", "CNSSG", "patronale", "10.000", "1500000"),
]


class Command(BaseCommand):
    help = "Crée des barèmes de cotisation de démonstration (taux illustratifs, à remplacer)."

    def handle(self, *args, **options):
        for ordre, (code, label, organisme, nature, taux, plafond) in enumerate(DEMO):
            BaremeCotisation.objects.get_or_create(
                code=code, date_effet=date(2026, 1, 1),
                defaults=dict(
                    label=label, organisme=organisme, nature=nature, taux=Decimal(taux),
                    plafond=Decimal(plafond) if plafond else None, ordre=ordre,
                ),
            )
        self.stdout.write(self.style.WARNING(
            "Barèmes de DÉMONSTRATION créés : taux illustratifs, à remplacer par les taux légaux validés."
        ))
