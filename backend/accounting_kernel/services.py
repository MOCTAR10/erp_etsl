"""Services du noyau comptable : validation, comptabilisation, extourne, clôture."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import AccountMove, AccountMoveLine, Period, Sequence

ZERO = Decimal("0")


def period_for_date(date):
    """Retourne la période contenant `date` (exercice non clôturé)."""
    period = Period.objects.filter(start_date__lte=date, end_date__gte=date).first()
    if period is None:
        raise ValidationError(f"Aucune période comptable pour la date {date}.")
    return period


def validate_move(move):
    """Contrôles de cohérence : ≥ 2 lignes, débit XOR crédit, débit = crédit."""
    lines = list(move.lines.all())
    if len(lines) < 2:
        raise ValidationError("Une écriture doit comporter au moins deux lignes.")
    total_debit = ZERO
    total_credit = ZERO
    for line in lines:
        if line.debit < ZERO or line.credit < ZERO:
            raise ValidationError("Les montants doivent être positifs.")
        if line.debit > ZERO and line.credit > ZERO:
            raise ValidationError("Une ligne ne peut être à la fois débit et crédit.")
        if line.debit == ZERO and line.credit == ZERO:
            raise ValidationError("Ligne sans montant.")
        total_debit += line.debit
        total_credit += line.credit
    if total_debit != total_credit:
        raise ValidationError(
            f"Écriture déséquilibrée : débit {total_debit} ≠ crédit {total_credit}."
        )
    return total_debit


@transaction.atomic
def post_move(move, user=None):
    """Comptabilise une écriture : numérotation + figement (immuabilité)."""
    move = AccountMove.objects.select_for_update().get(pk=move.pk)
    if move.status != AccountMove.Status.DRAFT:
        raise ValidationError("Seule une écriture brouillon peut être comptabilisée.")
    if not move.journal.is_active:
        raise ValidationError("Journal inactif.")
    if not move.period.is_open:
        raise ValidationError("Période clôturée — comptabilisation impossible.")
    validate_move(move)
    move.number = Sequence.next_for(move.journal)
    move.status = AccountMove.Status.POSTED
    move.posted_at = timezone.now()
    if user is not None and move.created_by_id is None:
        move.created_by = user
    move.save()
    return move


@transaction.atomic
def reverse_move(move, user=None, date=None, reference="", label=""):
    """Extourne une écriture comptabilisée (contre-écriture, jamais de suppression)."""
    move = AccountMove.objects.select_for_update().get(pk=move.pk)
    if move.status != AccountMove.Status.POSTED:
        raise ValidationError("Seule une écriture comptabilisée peut être extournée.")
    if move.reversed_by_id:
        raise ValidationError("Écriture déjà extournée.")
    reversal_date = date or move.date
    reversal = AccountMove.objects.create(
        journal=move.journal,
        period=period_for_date(reversal_date),
        date=reversal_date,
        reference=reference or f"Extourne {move.number}",
        label=label or f"Extourne : {move.label}",
        source=move.source,
        source_ref=move.source_ref,
        created_by=user or move.created_by,
    )
    for line in move.lines.all():
        AccountMoveLine.objects.create(
            move=reversal,
            account=line.account,
            partner=line.partner,
            analytic_account=line.analytic_account,
            label=line.label,
            debit=line.credit,
            credit=line.debit,
            order=line.order,
        )
    reversal = post_move(reversal, user)
    move.status = AccountMove.Status.REVERSED
    move.reversed_by = reversal
    move.save()
    return reversal


@transaction.atomic
def close_period(period):
    period = Period.objects.select_for_update().get(pk=period.pk)
    period.status = Period.Status.CLOSED
    period.save(update_fields=["status"])
    return period


@transaction.atomic
def reopen_period(period):
    period = Period.objects.select_for_update().get(pk=period.pk)
    period.status = Period.Status.OPEN
    period.save(update_fields=["status"])
    return period
