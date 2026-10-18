from django.core.management.base import BaseCommand
from django_celery_beat.models import CrontabSchedule, PeriodicTask

SCHEDULES = [
    (
        "ETSL — dispatch outbox",
        "outbox.tasks.dispatch_outbox",
        {"minute": "*/1", "hour": "*", "day_of_week": "*", "day_of_month": "*", "month_of_year": "*"},
    ),
    (
        "ETSL — relance des webhooks (CL-OM-09)",
        "integrations.tasks.retry_webhook_deliveries",
        {"minute": "*/1", "hour": "*", "day_of_week": "*", "day_of_month": "*", "month_of_year": "*"},
    ),
    (
        "ETSL — relances workflow (RF-35)",
        "workflow.tasks.check_overdue_tasks",
        {"minute": "0", "hour": "8", "day_of_week": "*", "day_of_month": "*", "month_of_year": "*"},
    ),
    (
        "ETSL — inventaires tournants (clôture M5, CDC M5 §7.11)",
        "stocks.tasks.planifier_inventaires",
        {"minute": "15", "hour": "6", "day_of_week": "*", "day_of_month": "*", "month_of_year": "*"},
    ),
    (
        "ETSL — maintenance préventive (lot 14, CDC M8 §13.4)",
        "maintenance.tasks.declencher_plans_preventifs",
        {"minute": "0", "hour": "6", "day_of_week": "*", "day_of_month": "*", "month_of_year": "*"},
    ),
    (
        "ETSL — notifications d'échéance J-90/J-30/J-15/J-0 (lot 15, EX-G-05)",
        "analytics.tasks.notifier_echeances",
        {"minute": "30", "hour": "7", "day_of_week": "*", "day_of_month": "*", "month_of_year": "*"},
    ),
    (
        "ETSL — écarts budgétaires > 10 % (lot 15, CDC M11 §4.4)",
        "controle_gestion.tasks.detecter_ecarts_budgetaires",
        {"minute": "0", "hour": "7", "day_of_week": "*", "day_of_month": "*", "month_of_year": "*"},
    ),
    (
        "ETSL — clôture mensuelle : envoi Direction J+4 et alerte de retard (M10)",
        "comptabilite.tasks.suivre_clotures_mensuelles",
        {"minute": "45", "hour": "7", "day_of_week": "*", "day_of_month": "*", "month_of_year": "*"},
    ),
]

# Tâches périodiques supprimées : l'app `ingestion` (IMAP, RF-04) n'existe pas dans le code ; planifier une tâche
# inexistante produisait « Received unregistered task » toutes les 15 min. Retirée aussi des bases déjà seedées.
STALE_NAMES = ["ETSL — ingestion IMAP"]


class Command(BaseCommand):
    """Enregistre les tâches périodiques dans django-celery-beat (idempotent)."""

    help = "Peuple l'ordonnanceur django-celery-beat (incr.17)."

    def handle(self, *args, **options):
        created = updated = 0
        PeriodicTask.objects.filter(name__in=STALE_NAMES).delete()
        for name, task, cron_fields in SCHEDULES:
            cron, _ = CrontabSchedule.objects.get_or_create(**cron_fields)
            _, was_created = PeriodicTask.objects.update_or_create(
                name=name,
                defaults={"task": task, "crontab": cron, "enabled": True},
            )
            created += was_created
            updated += not was_created
        self.stdout.write(
            self.style.SUCCESS(
                f"Terminé — {created} tâche(s) créée(s), {updated} mise(s) à jour."
            )
        )