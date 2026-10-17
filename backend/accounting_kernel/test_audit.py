"""Audit métier du noyau comptable (2026-10-16) — régressions des écarts trouvés.

K1  : une écriture EXTOURNÉE (et ses lignes) doit rester immuable, comme une écriture comptabilisée.
K8  : le grand livre n'est lisible/éditable que par le cercle comptable (pas tout authentifié).
K9  : PATCH d'une écriture avec `lines` → 400 propre, jamais 500.
K14 : un exercice clôturé interdit toute comptabilisation.
K13 : on ne clôture pas une période qui contient encore des brouillons.
"""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from referentiels.models import Account

from .models import AccountMove, AccountMoveLine, FiscalYear, Journal, Period
from .services import close_period, post_move, reverse_move

User = get_user_model()


class KernelAuditBase(TestCase):
    def setUp(self):
        call_command("seed_accounting", year=2026)
        self.journal = Journal.objects.get(code="VTE")
        self.a411 = Account.objects.create(
            code="411000", label="Clients", account_class=4, account_type=Account.AccountType.ASSET
        )
        self.a701 = Account.objects.create(
            code="701000", label="Ventes", account_class=7, account_type=Account.AccountType.INCOME
        )
        self.client = APIClient()

    def user(self, role, email=None):
        return User.objects.create_user(
            email=email or f"{role}@etls.local", password="x-Audit-2026", role=role, first_name=role
        )

    def draft(self, day=15):
        move = AccountMove.objects.create(
            journal=self.journal,
            period=Period.objects.get(number=1, fiscal_year__year=2026),
            date=date(2026, 1, day),
            label="Facture",
            source="M10",
        )
        AccountMoveLine.objects.create(move=move, account=self.a411, debit=Decimal("1000"), order=0)
        AccountMoveLine.objects.create(move=move, account=self.a701, credit=Decimal("1000"), order=1)
        return move


class ReversedMoveImmutabilityTests(KernelAuditBase):
    def test_extournee_reste_immuable(self):
        move = post_move(self.draft())
        reverse_move(move)
        move.refresh_from_db()
        self.assertEqual(move.status, AccountMove.Status.REVERSED)
        move.label = "Falsifié"
        with self.assertRaises(ValidationError):
            move.save()

    def test_lignes_d_une_extournee_immuables(self):
        move = post_move(self.draft())
        reverse_move(move)
        line = move.lines.first()
        line.debit = Decimal("1")
        with self.assertRaises(ValidationError):
            line.save()
        with self.assertRaises(ValidationError):
            line.delete()

    def test_statut_non_modifiable_en_retour_arriere(self):
        move = post_move(self.draft())
        move.status = AccountMove.Status.DRAFT
        with self.assertRaises(ValidationError):
            move.save()

    def test_numero_fige_apres_comptabilisation(self):
        move = post_move(self.draft())
        move.number = "VTE99999"
        with self.assertRaises(ValidationError):
            move.save()


class LedgerAccessTests(KernelAuditBase):
    def test_role_hors_cercle_comptable_refuse_en_lecture_et_ecriture(self):
        move = self.draft()
        for role in ("chef_service", "chef_atelier", "logistique"):
            self.client.force_authenticate(self.user(role))
            self.assertEqual(self.client.get("/api/accounting/moves/").status_code, 403, role)
            self.assertEqual(self.client.get(f"/api/accounting/moves/{move.id}/").status_code, 403, role)
            self.assertEqual(self.client.get("/api/accounting/lines/").status_code, 403, role)
            self.assertEqual(self.client.delete(f"/api/accounting/moves/{move.id}/").status_code, 403, role)
        self.assertTrue(AccountMove.objects.filter(pk=move.pk).exists())

    def test_cercle_comptable_lit_et_cree(self):
        self.client.force_authenticate(self.user("comptable"))
        self.assertEqual(self.client.get("/api/accounting/moves/").status_code, 200)
        resp = self.client.post(
            "/api/accounting/moves/",
            {
                "journal": Journal.objects.get(code="OD").pk,
                "date": "2026-01-20",
                "label": "OD",
                "motif": "Reclassement",
                "lines": [
                    {"account": self.a411.pk, "debit": "10.00", "credit": "0"},
                    {"account": self.a701.pk, "debit": "0", "credit": "10.00"},
                ],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)

    def test_patch_avec_lines_renvoie_400_pas_500(self):
        move = self.draft()
        self.client.force_authenticate(self.user("comptable"))
        resp = self.client.patch(
            f"/api/accounting/moves/{move.id}/",
            {"label": "x", "lines": [{"account": self.a411.pk, "debit": "5", "credit": "0"}]},
            format="json",
        )
        self.assertLess(resp.status_code, 500, resp.content)
        self.assertGreaterEqual(resp.status_code, 400)


class ClosingTests(KernelAuditBase):
    def test_exercice_cloture_interdit_la_comptabilisation(self):
        FiscalYear.objects.filter(year=2026).update(status=FiscalYear.Status.CLOSED)
        with self.assertRaises(ValidationError):
            post_move(self.draft())

    def test_cloture_periode_refusee_avec_brouillons(self):
        self.draft()
        period = Period.objects.get(number=1, fiscal_year__year=2026)
        with self.assertRaises(ValidationError):
            close_period(period)

    def test_cloture_periode_ok_sans_brouillon(self):
        move = post_move(self.draft())
        self.assertEqual(move.status, AccountMove.Status.POSTED)
        period = Period.objects.get(number=1, fiscal_year__year=2026)
        self.assertEqual(close_period(period).status, Period.Status.CLOSED)
