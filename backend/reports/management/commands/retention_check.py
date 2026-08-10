"""Signale les documents dont la durée de rétention est atteinte (RF-50/51/52).

Usage : python manage.py retention_check [--csv rapport.csv]
"""
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q

from documents.models import Document


class Command(BaseCommand):
    help = "Liste les documents à échéance de rétention (RF-50/51/52)."

    def add_arguments(self, parser):
        parser.add_argument("--csv", type=str, help="Chemin du fichier bordereau CSV")
        parser.add_argument(
            "--horizon", type=int, default=180,
            help="Jours avant échéance à signaler (défaut 180)",
        )

    def handle(self, *args, **options):
        today = date.today()
        horizon = options["horizon"]
        limite = today + timedelta(days=horizon)

        due = Document.objects.filter(
            Q(type__isnull=False),
            Q(document_date__isnull=False),
        ).exclude(
            Q(status=Document.Status.REJECTED)
        )
        results = []
        for doc in due.select_related("type"):
            end = doc.document_date + timedelta(days=365 * doc.type.retention_years) \
                if doc.type.retention_years else None
            if end and end <= limite:
                results.append((doc, end))

        for doc, end in sorted(results, key=lambda r: r[1]):
            days = (end - today).days
            self.stdout.write(
                f"- {doc.id} | {doc.title} | {doc.type.label} | échéance {end} "
                f"({days:+d} j)"
            )
        self.stdout.write(self.style.SUCCESS(f"Rétention : {len(results)} document(s) à signaler."))

        if options["csv"] and results:
            import csv

            with open(options["csv"], "w", newline="", encoding="utf-8-sig") as fh:
                writer = csv.writer(fh, delimiter=";")
                writer.writerow(["id", "titre", "type", "retention_fin"])
                for doc, end in results:
                    writer.writerow([doc.id, doc.title, doc.type.label, end.isoformat()])
            self.stdout.write(f"Bordereau écrit : {options['csv']}")
