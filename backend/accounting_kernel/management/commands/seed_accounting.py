import calendar
from datetime import date

from django.core.management.base import BaseCommand

from accounting_kernel.models import FiscalYear, Journal, Period, Sequence

JOURNALS = [
    ("VTE", "Journal des ventes", Journal.JournalType.VENTE),
    ("ACH", "Journal des achats", Journal.JournalType.ACHAT),
    ("BQ", "Journal de banque", Journal.JournalType.TRESORERIE),
    ("CAI", "Journal de caisse", Journal.JournalType.TRESORERIE),
    ("PAI", "Journal de paie", Journal.JournalType.PAIE),
    ("STK", "Journal de stock", Journal.JournalType.STOCK),
    ("OD", "Opérations diverses", Journal.JournalType.OD),
]


class Command(BaseCommand):
    """Crée l'exercice, les 12 périodes, les journaux et leurs séquences (incr.15)."""

    help = "Seed du noyau comptable : exercice, périodes, journaux, séquences."

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, default=None)

    def handle(self, *args, **options):
        year = options["year"] or date.today().year
        counters = {"exercice": 0, "périodes": 0, "journaux": 0, "séquences": 0}

        _, created = FiscalYear.objects.get_or_create(
            year=year,
            defaults={"start_date": date(year, 1, 1), "end_date": date(year, 12, 31)},
        )
        counters["exercice"] += created
        fiscal_year = FiscalYear.objects.get(year=year)

        for month in range(1, 13):
            last_day = calendar.monthrange(year, month)[1]
            _, created = Period.objects.get_or_create(
                fiscal_year=fiscal_year,
                number=month,
                defaults={
                    "start_date": date(year, month, 1),
                    "end_date": date(year, month, last_day),
                },
            )
            counters["périodes"] += created

        for code, label, journal_type in JOURNALS:
            journal, created = Journal.objects.get_or_create(
                code=code, defaults={"label": label, "journal_type": journal_type}
            )
            counters["journaux"] += created
            _, seq_created = Sequence.objects.get_or_create(
                journal=journal, defaults={"prefix": code, "padding": 5}
            )
            counters["séquences"] += seq_created

        self.stdout.write(
            self.style.SUCCESS(
                f"Terminé pour {year} — "
                + ", ".join(f"{value} {name}" for name, value in counters.items())
                + " créé(s)."
            )
        )
