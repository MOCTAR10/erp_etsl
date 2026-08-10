"""Application Celery du backend ETSL (relances RF-35, ingestion, OCR, exports)."""

import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("etls")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    # RF-35 : relances des tâches en retard + escalade N+1 (chaque jour 08:00).
    "check-overdue-workflow-tasks": {
        "task": "workflow.tasks.check_overdue_tasks",
        "schedule": crontab(hour=8, minute=0),
    },
    # RF-04 : ingestion des boîtes mail Outlook (chaque 15 min).
    "poll-imap-mailboxes": {
        "task": "ingestion.tasks.poll_imap_mailboxes",
        "schedule": crontab(minute="*/15"),
    },
}
