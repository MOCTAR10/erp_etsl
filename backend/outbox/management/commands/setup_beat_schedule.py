from django.core.management.base import BaseCommand
from django_celery_beat.models import CrontabSchedule, PeriodicTask

SCHEDULES = [
    (
        "ETSL — dispatch outbox",
        "outbox.tasks.dispatch_outbox",
        {"minute": "*/1", "hour": "*", "day_of_week": "*", "day_of_month": "*", "month_of_year": "*"},
    ),
    (
        "ETSL — relances workflow (RF-35)",
        "workflow.tasks.check_overdue_tasks",
        {"minute": "0", "hour": "8", "day_of_week": "*", "day_of_month": "*", "month_of_year": "*"},
    ),
    (
        "ETSL — ingestion IMAP",
        "ingestion.tasks.poll_imap_mailboxes",
        {"minute": "*/15", "hour": "*", "day_of_week": "*", "day_of_month": "*", "month_of_year": "*"},
    ),
]


class Command(BaseCommand):
    """Enregistre les tâches périodiques dans django-celery-beat (idempotent)."""

    help = "Peuple l'ordonnanceur django-celery-beat (incr.17)."

    def handle(self, *args, **options):
        created = updated = 0
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