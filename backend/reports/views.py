"""Rapports, exports et tableaux de bord (RF-74/80/94/95/98)."""

from django.http import HttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from documents.audit import log_audit, request_ip
from documents.models import AuditLog, Document
from documents.services import visible_documents

from .services import dashboard, export_sage, export_selection


class ExportView(APIView):
    """Export d'une sélection de documents visibles — CSV/XLSX/PDF (RF-98, RF-74)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        format = request.query_params.get("export", "csv")
        if format not in ("csv", "xlsx", "pdf"):
            return Response({"detail": "format invalide (csv/xlsx/pdf)"}, status=400)
        try:
            content, media_type, filename = export_selection(
                request.user, format, request.query_params
            )
        except Exception as exc:
            return Response({"detail": f"export error: {exc!r}"}, status=500)
        log_audit(
            request.user,
            AuditLog.Action.DOWNLOAD,
            "rapport",
            None,
            {"format": format, "filters": dict(request.query_params)},
            request_ip(request),
        )
        response = HttpResponse(content, content_type=media_type)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class SageExportView(APIView):
    """Export SAGE I7 — écritures comptables validées (RF-68/80)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = visible_documents(request.user).filter(
            status__in=[Document.Status.ARCHIVED, "in_validation"]
        )
        content = export_sage(queryset)
        log_audit(
            request.user,
            AuditLog.Action.DOWNLOAD,
            "sage_export",
            None,
            {"rows": queryset.count()},
            request_ip(request),
        )
        response = HttpResponse(content, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="export_sage.csv"'
        return response


class DashboardView(APIView):
    """Tableau de bord direction (RF-94) / service (RF-95), temps de traitement (RF-96)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(dashboard(request.user))


class RetentionReportView(APIView):
    """Documents à échéance de rétention + bordereau de destruction CSV (RF-50/51/52)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        data = dashboard(request.user)
        payload = {
            "due_count": data["retention"]["due_count"],
            "due": data["retention"]["due"],
        }
        if request.query_params.get("export") == "csv":
            import csv
            import io
            from datetime import date

            buffer = io.StringIO()
            writer = csv.writer(buffer, delimiter=";")
            writer.writerow(["id", "titre", "type", "retention_fin"])
            for d in data["retention"]["due"]:
                writer.writerow([d["id"], d["titre"], d["type"], d["retention_fin"]])
            content = buffer.getvalue().encode("utf-8-sig")
            response = HttpResponse(content, content_type="text/csv")
            response["Content-Disposition"] = (
                f'attachment; filename="bordereau_destruction_{date.today().isoformat()}.csv"'
            )
            return response
        return Response(payload)
