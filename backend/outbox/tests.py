from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
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
        event = publish("accounting.move.posted", {"number": "VTE00001"})
        result = dispatch_outbox.run()
        self.assertEqual(result["delivered"], 1)
        event.refresh_from_db()
        self.assertEqual(event.status, OutboxEvent.Status.DELIVERED)
        self.assertIsNotNone(event.delivered_at)
        self.assertEqual(Notification.objects.filter(user=self.admin).count(), 1)

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
        self.assertEqual(PeriodicTask.objects.count(), 3)
        self.assertTrue(
            PeriodicTask.objects.filter(task="outbox.tasks.dispatch_outbox").exists()
        )
        call_command("setup_beat_schedule")
        self.assertEqual(PeriodicTask.objects.count(), 3)


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

    def test_list_filters_by_status(self):
        publish("accounting.move.posted", {"number": "VTE00001"})
        self.client.force_authenticate(self.admin)
        resp = self.client.get("/api/outbox/events/?status=pending")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)
        resp = self.client.get("/api/outbox/events/?status=delivered")
        self.assertEqual(resp.data["count"], 0)