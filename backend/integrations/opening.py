"""Reprise des balances d'ouverture (SAGE, CL-OM-10) : une écriture d'à-nouveaux équilibrée par exercice."""

import csv
import hashlib
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction

from accounting_kernel.models import AccountMove, AccountMoveLine, FiscalYear, Journal
from accounting_kernel.services import period_for_date, post_move
from referentiels.models import Account

ZERO = Decimal("0")


class OpeningConflict(Exception):
    """Une balance d'ouverture différente existe déjà pour cet exercice."""


def _amount(raw, line_no, column):
    text = (raw or "").strip().replace(" ", "").replace(",", ".") or "0"
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValidationError(f"Ligne {line_no} : {column} invalide ({raw!r}).")
    if value < 0:
        raise ValidationError(f"Ligne {line_no} : {column} négatif interdit ({raw}).")
    return value


def parse_balance(content: bytes):
    """CSV `compte,debit,credit[,libelle]` → {compte: solde net (débit - crédit)}."""
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    missing = {"compte", "debit", "credit"} - set(reader.fieldnames or ())
    if missing:
        raise ValidationError("Colonnes manquantes : " + ", ".join(sorted(missing)) + ".")
    net = {}
    for line_no, row in enumerate(reader, start=2):
        compte = (row.get("compte") or "").strip()
        if not compte:
            raise ValidationError(f"Ligne {line_no} : compte manquant.")
        debit, credit = _amount(row.get("debit"), line_no, "débit"), _amount(row.get("credit"), line_no, "crédit")
        if debit and credit:
            raise ValidationError(f"Ligne {line_no} : débit ET crédit sur la même ligne (compte {compte}).")
        net[compte] = net.get(compte, ZERO) + debit - credit
    if not net:
        raise ValidationError("Fichier vide.")
    return net


@transaction.atomic
def import_opening_balance(content: bytes, date_str: str, user, control_total=None):
    """Retourne `(écriture, rejeu)`. Lève ValidationError (400) ou OpeningConflict (409)."""
    try:
        day = datetime.strptime((date_str or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ValidationError("Date invalide (attendu AAAA-MM-JJ).")
    fy = FiscalYear.objects.filter(start_date__lte=day, end_date__gte=day).first()
    if fy is None:
        raise ValidationError(f"Aucun exercice comptable ne couvre le {day}.")
    if fy.status != FiscalYear.Status.OPEN:
        raise ValidationError(f"Exercice {fy.year} clôturé : balance d'ouverture impossible.")
    if day != fy.start_date:
        raise ValidationError(f"La balance d'ouverture se date du premier jour de l'exercice ({fy.start_date}).")

    digest = hashlib.sha256(content).hexdigest()[:40]  # source_ref est limité à 60 caractères
    reference = f"AN-{fy.year}"
    existing = AccountMove.objects.filter(reference=reference, source="integrations").first()
    if existing:
        if existing.source_ref == f"opening/{digest}":
            return existing, True
        raise OpeningConflict(
            f"Une balance d'ouverture ({reference}) existe déjà pour l'exercice {fy.year} : "
            "extournez-la avant d'en importer une autre."
        )

    net = parse_balance(content)
    accounts = {a.code: a for a in Account.objects.filter(code__in=net)}
    unknown = sorted(set(net) - set(accounts))
    if unknown:
        raise ValidationError("Comptes absents du plan comptable : " + ", ".join(unknown) + ".")

    total_debit = sum((v for v in net.values() if v > 0), ZERO)
    total_credit = sum((-v for v in net.values() if v < 0), ZERO)
    if total_debit != total_credit:
        raise ValidationError(
            f"Balance déséquilibrée : débit {total_debit} ≠ crédit {total_credit} (écart {abs(total_debit - total_credit)})."
        )
    if control_total not in (None, ""):
        try:
            expected = Decimal(str(control_total).replace(",", "."))
        except InvalidOperation:
            raise ValidationError("Total de contrôle invalide.")
        if expected != total_debit:
            raise ValidationError(f"Total de contrôle SAGE {expected} ≠ total importé {total_debit}.")

    journal = Journal.objects.filter(code="OD").first()
    if journal is None:
        raise ValidationError("Journal OD (opérations diverses) absent.")
    move = AccountMove.objects.create(
        journal=journal, period=period_for_date(day), date=day, reference=reference,
        label=f"Balance d'ouverture {fy.year} (reprise SAGE)", source="integrations",
        source_ref=f"opening/{digest}", created_by=user,
    )
    for order, (code, value) in enumerate(sorted(net.items())):
        if value:
            AccountMoveLine.objects.create(
                move=move, account=accounts[code], debit=max(value, ZERO), credit=max(-value, ZERO), order=order,
                label="À-nouveau",
            )
    return post_move(move, user=user), False
