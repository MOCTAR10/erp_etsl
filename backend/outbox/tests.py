from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, TransactionTestCase
from django_celery_beat.models import PeriodicTask
from rest_framework import status
from rest_framework.test import APITestCase

from workflow.models import Notification

from .models import OutboxEvent, publish
from .subscribers import SUBSCRIBERS
from .tasks import dispatch_outbox

User = get_user_model()


class OutboxDispatchTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@etls.local", password="MotDePasse#2026",
            role=User.Role.ADMIN, is_staff=True,
        )

    def test_publish_and_dispatch_notifies_admins(self):
        def notifier(event):
            Notification.objects.create(user=self.admin, subject="Test", message=event.payload["number"], kind="info")

        SUBSCRIBERS["test.notify"] = [notifier]
        try:
            event = publish("test.notify", {"number": "VTE00001"})
            result = dispatch_outbox.run()
        finally:
            del SUBSCRIBERS["test.notify"]
        self.assertEqual(result["delivered"], 1)
        event.refresh_from_db()
        self.assertEqual(event.status, OutboxEvent.Status.DELIVERED)
        self.assertIsNotNone(event.delivered_at)
        self.assertEqual(Notification.objects.filter(user=self.admin).count(), 1)

    def test_chaque_sujet_publie_a_un_abonne_ou_est_documente(self):
        """Écart E3 (ETSL-ERP-INT) : pas d'abonné mort, pas de sujet publié sans abonné non documenté."""
        import re
        from pathlib import Path

        from django.conf import settings

        from .subscribers import SUJETS_SANS_ABONNE_INTERNE

        racine = Path(settings.BASE_DIR)
        publies = set()
        for fichier in racine.glob("*/**/*.py"):
            if ".venv" in fichier.parts or fichier.name.startswith("test"):
                continue
            publies |= set(re.findall(r"publish\(\s*\"([a-z0-9_.]+)\"", fichier.read_text(encoding="utf-8")))
        self.assertIn("operations.marge_terminaison", publies)
        for sujet in publies:
            self.assertTrue(sujet in SUBSCRIBERS or sujet in SUJETS_SANS_ABONNE_INTERNE, sujet)
        for sujet in SUBSCRIBERS:
            self.assertTrue(sujet == "*" or sujet.startswith("test") or sujet in publies, f"abonné sans publication : {sujet}")
        self.assertNotIn("accounting.move.posted", SUBSCRIBERS)

    def test_delivered_events_are_not_reprocessed(self):
        publish("noop.topic", {})
        dispatch_outbox.run()
        result = dispatch_outbox.run()
        self.assertEqual(result["processed"], 0)

    def test_failing_subscriber_retries_then_fails(self):
        def boom(event):
            raise RuntimeError("boom")

        SUBSCRIBERS["test.failing"] = [boom]
        try:
            event = publish("test.failing", {})
            for _ in range(3):
                dispatch_outbox.run()
            event.refresh_from_db()
            self.assertEqual(event.status, OutboxEvent.Status.FAILED)
            self.assertEqual(event.attempt_count, 3)
            self.assertIn("boom", event.error_message)
        finally:
            del SUBSCRIBERS["test.failing"]

    def test_unsubscribed_topic_is_consumed(self):
        event = publish("topic.sans.souscripteur", {})
        result = dispatch_outbox.run()
        self.assertEqual(result["delivered"], 1)
        event.refresh_from_db()
        self.assertEqual(event.status, OutboxEvent.Status.DELIVERED)


class OutboxBeatScheduleTests(TestCase):
    def test_setup_beat_schedule_is_idempotent(self):
        call_command("setup_beat_schedule")
        self.assertEqual(PeriodicTask.objects.count(), 9)
        self.assertTrue(
            PeriodicTask.objects.filter(task="outbox.tasks.dispatch_outbox").exists()
        )
        call_command("setup_beat_schedule")
        self.assertEqual(PeriodicTask.objects.count(), 9)


class OutboxAPITests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@etls.local", password="MotDePasse#2026",
            role=User.Role.ADMIN, is_staff=True,
        )

    def test_list_requires_auth(self):
        resp = self.client.get("/api/outbox/events/")
        self.assertIn(
            resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        )

    def test_non_admin_forbidden(self):
        user = User.objects.create_user(email="cs@etls.local", password="x", role="chef_service")
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get("/api/outbox/events/").status_code, status.HTTP_403_FORBIDDEN)

    def test_list_filters_by_status(self):
        publish("test.topic", {"number": "VTE00001"})
        self.client.force_authenticate(self.admin)
        resp = self.client.get("/api/outbox/events/?status=pending")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)
        resp = self.client.get("/api/outbox/events/?status=delivered")
        self.assertEqual(resp.data["count"], 0)

class DispatchConcurrentTests(TransactionTestCase):
    """Deux workers simultanés ne livrent jamais le même événement deux fois (skip_locked)."""

    def test_pas_de_double_livraison(self):
        import threading
        import time

        from django.db import connection

        from .subscribers import SUBSCRIBERS, subscriber
        from .tasks import dispatch_outbox

        livres = []

        @subscriber("test.concurrent")
        def handler(event):
            time.sleep(0.15)  # laisse l'autre worker tenter de prendre le même événement
            livres.append(str(event.id))

        try:
            for i in range(6):
                OutboxEvent.objects.create(topic="test.concurrent", payload={"i": i})

            def worker():
                try:
                    dispatch_outbox()
                finally:
                    connection.close()

            threads = [threading.Thread(target=worker) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=60)
        finally:
            SUBSCRIBERS.pop("test.concurrent", None)

        self.assertEqual(len(livres), 6, livres)
        self.assertEqual(len(set(livres)), 6, "un événement a été livré deux fois")
        self.assertEqual(OutboxEvent.objects.filter(status=OutboxEvent.Status.DELIVERED).count(), 6)
