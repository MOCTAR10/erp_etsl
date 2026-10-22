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
from config.i18n import tr

ZERO = Decimal("0")


class OpeningConflict(Exception):
    """Une balance d'ouverture différente existe déjà pour cet exercice."""


def _amount(raw, line_no, column):
    text = (raw or "").strip().replace(" ", "").replace(",", ".") or "0"
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValidationError(tr("Ligne %(line_no)s : %(column)s invalide (%(raw)s).") % {"line_no": line_no, "column": column, "raw": repr(raw)})
    if value < 0:
        raise ValidationError(tr("Ligne %(line_no)s : %(column)s négatif interdit (%(raw)s).") % {"line_no": line_no, "column": column, "raw": raw})
    return value


def parse_balance(content: bytes):
    """CSV `compte,debit,credit[,libelle]` → {compte: solde net (débit - crédit)}."""
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    missing = {"compte", "debit", "credit"} - set(reader.fieldnames or ())
    if missing:
        raise ValidationError(tr("Colonnes manquantes : %(liste)s.") % {"liste": ", ".join(sorted(missing))})
    net = {}
    for line_no, row in enumerate(reader, start=2):
        compte = (row.get("compte") or "").strip()
        if not compte:
            raise ValidationError(tr("Ligne %(line_no)s : compte manquant.") % {"line_no": line_no})
        debit, credit = _amount(row.get("debit"), line_no, "débit"), _amount(row.get("credit"), line_no, "crédit")
        if debit and credit:
            raise ValidationError(tr("Ligne %(line_no)s : débit ET crédit sur la même ligne (compte %(compte)s).") % {"line_no": line_no, "compte": compte})
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
        raise ValidationError(tr("Aucun exercice comptable ne couvre le %(day)s.") % {"day": day})
    if fy.status != FiscalYear.Status.OPEN:
        raise ValidationError(tr("Exercice %(fy_year)s clôturé : balance d'ouverture impossible.") % {"fy_year": fy.year})
    if day != fy.start_date:
        raise ValidationError(tr("La balance d'ouverture se date du premier jour de l'exercice (%(fy_start_date)s).") % {"fy_start_date": fy.start_date})

    digest = hashlib.sha256(content).hexdigest()[:40]  # source_ref est limité à 60 caractères
    reference = f"AN-{fy.year}"
    existing = AccountMove.objects.filter(reference=reference, source="integrations").first()
    if existing:
        if existing.source_ref == f"opening/{digest}":
            return existing, True
        raise OpeningConflict(
            tr("Une balance d'ouverture (%(reference)s) existe déjà pour l'exercice %(fy_year)s : extournez-la avant d'en importer une autre.") % {"reference": reference, "fy_year": fy.year}
        )

    net = parse_balance(content)
    accounts = {a.code: a for a in Account.objects.filter(code__in=net)}
    unknown = sorted(set(net) - set(accounts))
    if unknown:
        raise ValidationError(tr("Comptes absents du plan comptable : %(liste)s.") % {"liste": ", ".join(unknown)})

    total_debit = sum((v for v in net.values() if v > 0), ZERO)
    total_credit = sum((-v for v in net.values() if v < 0), ZERO)
    if total_debit != total_credit:
        raise ValidationError(
            tr("Balance déséquilibrée : débit %(total_debit)s ≠ crédit %(total_credit)s (écart %(valeur)s).") % {"total_debit": total_debit, "total_credit": total_credit, "valeur": abs(total_debit - total_credit)}
        )
    if control_total not in (None, ""):
        try:
            expected = Decimal(str(control_total).replace(",", "."))
        except InvalidOperation:
            raise ValidationError("Total de contrôle invalide.")
        if expected != total_debit:
            raise ValidationError(tr("Total de contrôle SAGE %(expected)s ≠ total importé %(total_debit)s.") % {"expected": expected, "total_debit": total_debit})

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
