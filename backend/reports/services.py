"""Exportations, rapports et tableaux de bord (RF-74/80, RF-94/95/96, RF-98)."""

import csv
import io
from datetime import timedelta

from django.db.models import Avg, Count
from django.db.models.functions import ExtractDay
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Font
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from documents.models import Document, DocumentType
from documents.services import visible_documents
from workflow.models import Task


def _export_rows(queryset):
    """Lignes d'export d'une sélection de documents (RF-98 / RF-74)."""
    rows = []
    for doc in queryset:
        rows.append(
            {
                "id": doc.id,
                "titre": doc.title,
                "statut": doc.get_status_display(),
                "type": doc.type.label if doc.type else "",
                "contrepartie": doc.counterparty,
                "reference": doc.reference,
                "projet": doc.project,
                "date_document": doc.document_date.isoformat() if doc.document_date else "",
                "montant": doc.amount if doc.amount is not None else "",
                "dossier": doc.dossier.name if doc.dossier else "",
                "cree_par": doc.created_by.email if doc.created_by else "",
                "cree_le": doc.created_at.strftime("%Y-%m-%d"),
                "retention_fin": _retention_end(doc),
            }
        )
    return rows


def _retention_end(doc):
    if doc.type and doc.type.retention_years and doc.document_date:
        return (doc.document_date + timedelta(days=365 * doc.type.retention_years)).isoformat()
    return ""


def _write_csv(rows, columns):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")


def _write_xlsx(rows, columns):
    buffer = io.BytesIO()
    wb = Workbook()
    ws = wb.active
    ws.title = "Documents"
    ws.append(columns)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append(["" if row.get(col) is None else str(row.get(col, "")) for col in columns])
    for column_cells in ws.columns:
        width = max(len(str(c.value or "")) for c in column_cells) + 2
        ws.column_dimensions[column_cells[0].column_letter].width = min(width, 40)
    wb.save(buffer)
    return buffer.getvalue()


def _write_pdf(rows, columns):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4), leftMargin=10 * mm, rightMargin=10 * mm,
        topMargin=10 * mm, bottomMargin=10 * mm,
    )
    styles = getSampleStyleSheet()
    elements = [Paragraph("Rapport documents — ETSL (RF-98)", styles["Title"]), Spacer(1, 6 * mm)]
    data = [columns] + [[str(row.get(col, "")) for col in columns] for row in rows]
    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.whitesmoke]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    elements.append(table)
    doc.build(elements)
    return buffer.getvalue()


def export_selection(user, format, params=None):
    """Export des documents visibles (CSV/XLSX/PDF) — RF-98, RF-74."""
    queryset = visible_documents(user)
    params = params or {}
    if doc_type := params.get("type"):
        queryset = queryset.filter(type_id=doc_type)
    if doc_status := params.get("status"):
        queryset = queryset.filter(status=doc_status)
    if dossier := params.get("dossier"):
        queryset = queryset.filter(dossier_id=dossier)
    if search := params.get("search"):
        queryset = queryset.filter(title__icontains=search)
    if year := params.get("year"):
        queryset = queryset.filter(document_date__year=year)

    columns = [
        "id", "titre", "statut", "type", "contrepartie", "reference", "projet",
        "date_document", "montant", "dossier", "cree_par", "cree_le", "retention_fin",
    ]
    rows = _export_rows(queryset)
    if format == "csv":
        content = _write_csv(rows, columns)
        media_type = "text/csv"
    elif format == "xlsx":
        content = _write_xlsx(rows, columns)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        content = _write_pdf(rows, columns)
        media_type = "application/pdf"
    return content, media_type, f"rapport_documents.{format}"


def export_sage(queryset):
    """Export SAGE I7 — écritures validées/archivées (RF-68/80)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(["type", "date_piece", "libelle", "tiers", "montant", "reference", "projet"])
    for doc in queryset:
        if not doc.amount and not doc.document_date:
            continue
        writer.writerow(
            [
                doc.type.code if doc.type else "",
                doc.document_date.isoformat() if doc.document_date else "",
                doc.title,
                doc.counterparty,
                doc.amount,
                doc.reference,
                doc.project,
            ]
        )
    return buffer.getvalue().encode("utf-8-sig")


def dashboard(user):
    """Tableau de bord direction (RF-94) / service (RF-95) + temps de traitement (RF-96)."""
    docs = visible_documents(user)
    overdue = Task.objects.filter(status=Task.Status.PENDING, due_date__lt=timezone.now())

    avg_days = Task.objects.filter(
        status=Task.Status.DONE, completed_at__isnull=False
    ).aggregate(
        total=Avg(ExtractDay("completed_at") - ExtractDay("created_at"))
    )["total"]

    retention_due = [
        {
            "id": d.id,
            "titre": d.title,
            "type": d.type.label if d.type else "",
            "retention_fin": _retention_end(d),
        }
        for d in docs
        if _retention_end(d)
        and _retention_end(d) <= timezone.now().date().isoformat()
    ]

    return {
        "documents": {
            "total": docs.count(),
            "by_status": dict(docs.values_list("status").annotate(count=Count("id")).order_by()),
            "by_type": list(
                docs.values("type__label").annotate(count=Count("id")).order_by("-count")
            ),
            "storage_bytes": sum(
                (d.current_version.size if d.current_version else 0) for d in docs
            ),
        },
        "workflow": {
            "pending": Task.objects.filter(status=Task.Status.PENDING).count(),
            "overdue": overdue.count(),
            "avg_processing_days": round(avg_days, 1) if avg_days is not None else None,
        },
        "retention": {"due_count": len(retention_due), "due": retention_due[:50]},
    }
