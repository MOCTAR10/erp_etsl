from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from referentiels.models import Account

from .models import AccountMove, AccountMoveLine, Journal, Period, Sequence
from .services import close_period, post_move, reverse_move

User = get_user_model()


class AccountingKernelTestCase(TestCase):
    def setUp(self):
        call_command("seed_accounting", year=2026)
        self.journal = Journal.objects.get(code="VTE")
        self.client_account = Account.objects.create(
            code="411000", label="Clients", account_class=4,
            account_type=Account.AccountType.ASSET,
        )
        self.sales_account = Account.objects.create(
            code="701000", label="Ventes", account_class=7,
            account_type=Account.AccountType.INCOME,
        )

    def _draft(self, debit="1000.00", credit="1000.00", day=15):
        move = AccountMove.objects.create(
            journal=self.journal, period=Period.objects.get(number=1, fiscal_year__year=2026),
            date=date(2026, 1, day), label="Facture test", source="M10",
        )
        AccountMoveLine.objects.create(
            move=move, account=self.client_account, debit=Decimal(debit), order=0
        )
        AccountMoveLine.objects.create(
            move=move, account=self.sales_account, credit=Decimal(credit), order=1
        )
        return move

    def test_post_balanced_assigns_sequence(self):
        first = post_move(self._draft())
        second = post_move(self._draft(day=16))
        self.assertEqual(first.status, AccountMove.Status.POSTED)
        self.assertEqual(first.number, "VTE00001")
        self.assertEqual(second.number, "VTE00002")
        self.assertIsNotNone(first.posted_at)

    def test_post_unbalanced_rejected(self):
        move = self._draft(debit="1000.00", credit="500.00")
        with self.assertRaises(ValidationError):
            post_move(move)
        move.refresh_from_db()
        self.assertEqual(move.status, AccountMove.Status.DRAFT)
        self.assertIsNone(move.number)

    def test_posted_move_is_immutable(self):
        move = post_move(self._draft())
        move.label = "Modifié"
        with self.assertRaises(ValidationError):
            move.save()
        line = move.lines.first()
        line.debit = Decimal("42.00")
        with self.assertRaises(ValidationError):
            line.save()
        with self.assertRaises(ValidationError):
            line.delete()
        with self.assertRaises(ValidationError):
            move.delete()

    def test_reverse_creates_mirror_and_links(self):
        move = post_move(self._draft())
        reversal = reverse_move(move, reference="EXTOURNE-1")
        move.refresh_from_db()
        self.assertEqual(reversal.status, AccountMove.Status.POSTED)
        self.assertEqual(move.status, AccountMove.Status.REVERSED)
        self.assertEqual(move.reversed_by_id, reversal.id)
        debit_line = reversal.lines.get(order=0)
        credit_line = reversal.lines.get(order=1)
        self.assertEqual(debit_line.credit, Decimal("1000.00"))
        self.assertEqual(debit_line.debit, Decimal("0"))
        self.assertEqual(credit_line.debit, Decimal("1000.00"))

    def test_cannot_reverse_twice(self):
        move = post_move(self._draft())
        reverse_move(move)
        with self.assertRaises(ValidationError):
            reverse_move(move)

    def test_cannot_post_in_closed_period(self):
        period = Period.objects.get(number=1, fiscal_year__year=2026)
        close_period(period)
        with self.assertRaises(ValidationError):
            post_move(self._draft())


class AccountingAPITests(APITestCase):
    def setUp(self):
        call_command("seed_accounting", year=2026)
        self.admin = User.objects.create_user(
            email="admin@etls.local", password="MotDePasse#2026",
            role=User.Role.ADMIN, is_staff=True,
        )
        self.comptable = User.objects.create_user(
            email="compta@etls.local", password="MotDePasse#2026",
            role=User.Role.COMPTABLE,
        )
        self.chef = User.objects.create_user(
            email="chef@etls.local", password="MotDePasse#2026",
            role=User.Role.CHEF_SERVICE,
        )
        self.journal = Journal.objects.get(code="VTE")
        self.account_a = Account.objects.create(
            code="411000", label="Clients", account_class=4,
            account_type=Account.AccountType.ASSET,
        )
        self.account_b = Account.objects.create(
            code="701000", label="Ventes", account_class=7,
            account_type=Account.AccountType.INCOME,
        )

    def _payload(self, debit="1000.00", credit="1000.00"):
        return {
            "journal": self.journal.id,
            "date": "2026-01-15",
            "label": "Facture",
            "source": "M10",
            "lines": [
                {"account": self.account_a.id, "debit": debit, "credit": "0"},
                {"account": self.account_b.id, "debit": "0", "credit": credit},
            ],
        }

    def test_list_requires_auth(self):
        resp = self.client.get("/api/accounting/moves/")
        self.assertIn(
            resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        )

    def test_create_draft_then_post(self):
        self.client.force_authenticate(self.comptable)
        resp = self.client.post("/api/accounting/moves/", self._payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data["status"], "draft")
        move_id = resp.data["id"]

        resp = self.client.post(f"/api/accounting/moves/{move_id}/post/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data["status"], "posted")
        self.assertEqual(resp.data["number"], "VTE00001")

    def test_post_forbidden_for_non_accounting_role(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post("/api/accounting/moves/", self._payload(), format="json")
        move_id = resp.data["id"]
        self.client.force_authenticate(self.chef)
        resp = self.client.post(f"/api/accounting/moves/{move_id}/post/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_unbalanced_post_returns_400(self):
        self.client.force_authenticate(self.comptable)
        resp = self.client.post(
            "/api/accounting/moves/", self._payload(credit="500.00"), format="json"
        )
        move_id = resp.data["id"]
        resp = self.client.post(f"/api/accounting/moves/{move_id}/post/")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_posted_returns_400(self):
        self.client.force_authenticate(self.comptable)
        resp = self.client.post("/api/accounting/moves/", self._payload(), format="json")
        move_id = resp.data["id"]
        self.client.post(f"/api/accounting/moves/{move_id}/post/")
        resp = self.client.patch(
            f"/api/accounting/moves/{move_id}/", {"label": "Modifié"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reverse_action(self):
        self.client.force_authenticate(self.comptable)
        resp = self.client.post("/api/accounting/moves/", self._payload(), format="json")
        move_id = resp.data["id"]
        self.client.post(f"/api/accounting/moves/{move_id}/post/")
        resp = self.client.post(f"/api/accounting/moves/{move_id}/reverse/", {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data["reference"], "Extourne VTE00001")
