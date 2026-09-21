"""Export des registres (CSV/XLSX) — RF-98, réutilise le style de `reports`."""

import csv
import io

from openpyxl import Workbook
from openpyxl.styles import Font


def _data_keys(entries):
    keys = []
    for entry in entries:
        for key in (entry.data or {}):
            if key not in keys:
                keys.append(key)
    return keys


def _rows(queryset):
    entries = list(queryset)
    data_keys = _data_keys(entries)
    header = ["numero", "date", "registre", "type"] + data_keys + ["document"]
    rows = []
    for entry in entries:
        row = [
            entry.number,
            entry.entry_date.isoformat(),
            entry.registre.label,
            entry.registre.get_kind_display(),
        ]
        row += [(entry.data or {}).get(key, "") for key in data_keys]
        row.append(entry.document.title if entry.document else "")
        rows.append(row)
    return header, rows


def _write_csv(header, rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")


def _write_xlsx(header, rows):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Registres"
    sheet.append(header)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in rows:
        sheet.append(row)
    for index, name in enumerate(header, start=1):
        sheet.column_dimensions[sheet.cell(row=1, column=index).column_letter].width = max(
            14, len(str(name)) + 4
        )
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def export_entries(queryset, fmt):
    """Retourne (contenu, content_type, nom_fichier) pour une sélection de lignes."""
    header, rows = _rows(queryset)
    if fmt == "xlsx":
        content = _write_xlsx(header, rows)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = "registres.xlsx"
    else:
        content = _write_csv(header, rows)
        media_type = "text/csv"
        filename = "registres.csv"
    return content, media_type, filename
