"""Moteur d'import générique : parsing CSV, mapping, validation, idempotence.

Idempotence :
  1. empreinte SHA-256 du fichier → un batch non-échoué identique est réutilisé (replay) ;
  2. clé métier par ligne (update_or_create / détection de doublon) → re-run sans doublons.
"""

import csv
import hashlib
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from accounting_kernel.models import AccountMove, AccountMoveLine, Journal
from accounting_kernel.services import period_for_date, post_move
from referentiels.models import Currency, Partner

from .models import BatchRow, ImportBatch


class RowError(Exception):
    """Erreur applicable à une seule ligne (journal d'erreurs)."""


class ImportError(Exception):
    """Erreur bloquante pour tout le lot (en-têtes manquants, etc.)."""


class BaseHandler:
    """Interface des connecteurs de lecture (CSV aujourd'hui, XML à venir)."""

    REQUIRED_FIELDS = ()

    def validate_headers(self, fieldnames):
        missing = set(self.REQUIRED_FIELDS) - set(fieldnames)
        if missing:
            raise ImportError(
                "Colonnes manquantes : " + ", ".join(sorted(missing)) + "."
            )

    def handle_row(self, row):
        # Retourne (type, libellé) avec type dans {created, updated, duplicate, error}.
        raise NotImplementedError


class PartnerConnector(BaseHandler):
    """Import des tiers (clients / fournisseurs / intra-groupe) — CSV."""

    REQUIRED_FIELDS = ("code", "name")

    def handle_row(self, row):
        code = (row.get("code") or "").strip()
        name = (row.get("name") or "").strip()
        if not code or not name:
            raise RowError("code et name sont requis.")

        kind = (row.get("kind") or "both").strip().lower()
        if kind not in Partner.Kind.values:
            raise RowError(f"kind invalide : {kind}")
        is_global_rental = (row.get("is_global_rental") or "").strip().lower() in (
            "1",
            "true",
            "yes",
        )

        defaults = {
            "name": name,
            "kind": kind,
            "tax_id": (row.get("tax_id") or "").strip(),
            "phone": (row.get("phone") or "").strip(),
            "email": (row.get("email") or "").strip(),
            "is_global_rental": is_global_rental,
        }
        currency_code = (row.get("currency_code") or "").strip().upper()
        if currency_code:
            currency = Currency.objects.filter(code=currency_code).first()
            if currency is None:
                raise RowError(f"devise inconnue : {currency_code}")
            defaults["currency"] = currency

        partner, was_created = Partner.objects.update_or_create(
            code=code, defaults=defaults
        )
        return ("created" if was_created else "updated", partner.name)


class GLConnector(BaseHandler):
    """Reprise d'écritures (SAGE) — CSV → écritures comptables via accounting_kernel.

    Colonnes : date, journal, account_debit, account_credit, label, amount, reference.
    """

    REQUIRED_FIELDS = ("date", "journal", "account_debit", "account_credit", "amount")

    def handle_row(self, row):
        raw_amount = (row.get("amount") or "").strip().replace(",", ".")
        try:
            amount = Decimal(raw_amount)
        except InvalidOperation:
            raise RowError(f"montant invalide : {raw_amount}")
        if amount <= 0:
            raise RowError("montant doit être strictement positif.")

        journal_code = (row.get("journal") or "").strip().upper()
        journal = Journal.objects.filter(code=journal_code).first()
        if journal is None:
            raise RowError(f"journal inconnu : {journal_code}")

        debit_code = (row.get("account_debit") or "").strip()
        credit_code = (row.get("account_credit") or "").strip()
        from referentiels.models import Account

        debit_account = Account.objects.filter(code=debit_code).first()
        credit_account = Account.objects.filter(code=credit_code).first()
        if debit_account is None:
            raise RowError(f"compte débit inconnu : {debit_code}")
        if credit_account is None:
            raise RowError(f"compte crédit inconnu : {credit_code}")

        try:
            move_date = datetime.strptime((row.get("date") or "").strip(), "%Y-%m-%d").date()
        except ValueError:
            raise RowError(f"date invalide (attendu AAAA-MM-JJ) : {row.get('date')}")

        reference = (row.get("reference") or "").strip()
        label = (row.get("label") or f"Import {reference}").strip()

        # Clé métier : idempotence de bout en bout (pas de doublon au re-run forcé).
        if AccountMove.objects.filter(
            journal=journal, date=move_date, reference=reference
        ).exists():
            return ("duplicate", reference or move_date.isoformat())

        period = period_for_date(move_date)
        move = AccountMove.objects.create(
            journal=journal,
            period=period,
            date=move_date,
            reference=reference,
            label=label,
            source="integrations",
            source_ref=f"gl/{reference}",
        )
        AccountMoveLine.objects.create(
            move=move, account=debit_account, debit=amount, order=0
        )
        AccountMoveLine.objects.create(
            move=move, account=credit_account, credit=amount, order=1
        )
        post_move(move)
        return ("created", reference or move_date.isoformat())


HANDLERS = {
    ImportBatch.Connector.PARTNERS: PartnerConnector(),
    ImportBatch.Connector.GL: GLConnector(),
}


def compute_hash(content):
    return hashlib.sha256(content).hexdigest()


def parse_csv(content):
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    return list(reader), reader.fieldnames


def run_import(connector, filename, content, user=None, force=False):
    """Exécute un import de fichier. Retourne (batch, replayed).

    - replayed=True si un lot identique (même SHA-256) a déjà abouti et qu'on
      ne force pas : on réutilise le lot existant (idempotence, pas de réinsertion).
    """
    file_hash = compute_hash(content)
    existing = (
        ImportBatch.objects.filter(connector=connector, file_hash=file_hash)
        .exclude(status=ImportBatch.Status.FAILED)
        .order_by("-created_at")
        .first()
    )
    if existing and not force:
        return existing, True

    handler = HANDLERS.get(connector)
    if handler is None:
        raise ImportError(f"connecteur inconnu : {connector}")

    batch = ImportBatch.objects.create(
        connector=connector,
        status=ImportBatch.Status.RUNNING,
        filename=filename,
        file_hash=file_hash,
        created_by=user,
        started_at=timezone.now(),
    )

    try:
        rows, fieldnames = parse_csv(content)
    except Exception as exc:
        batch.status = ImportBatch.Status.FAILED
        batch.error_message = f"parsing CSV : {exc!r}"
        batch.finished_at = timezone.now()
        batch.save()
        return batch, False

    try:
        handler.validate_headers(fieldnames)
    except ImportError as exc:
        batch.status = ImportBatch.Status.FAILED
        batch.error_message = str(exc)
        batch.finished_at = timezone.now()
        batch.save()
        return batch, False

    batch.total_rows = len(rows)
    batch.save(update_fields=["total_rows", "status"])

    for line_number, row in enumerate(rows, start=1):
        try:
            kind, detail = handler.handle_row(row)
        except RowError as exc:
            kind, detail = "error", str(exc)
        except Exception as exc:  # noqa: BLE001 — ligne isolée, jamais bloquante
            kind, detail = "error", f"{exc!r}"

        if kind == "error":
            batch.error_rows += 1
            BatchRow.objects.create(
                batch=batch,
                row_number=line_number,
                status=BatchRow.Status.ERROR,
                data=row,
                error_message=detail,
            )
        elif kind == "created":
            batch.created_rows += 1
            BatchRow.objects.create(
                batch=batch, row_number=line_number, status=BatchRow.Status.SUCCESS, data=row
            )
        elif kind == "updated":
            batch.updated_rows += 1
            BatchRow.objects.create(
                batch=batch, row_number=line_number, status=BatchRow.Status.SUCCESS, data=row
            )
        else:  # duplicate
            batch.updated_rows += 0
            BatchRow.objects.create(
                batch=batch,
                row_number=line_number,
                status=BatchRow.Status.DUPLICATE,
                data=row,
            )

    batch.status = (
        ImportBatch.Status.PARTIAL if batch.error_rows else ImportBatch.Status.SUCCESS
    )
    batch.finished_at = timezone.now()
    batch.save()
    return batch, False