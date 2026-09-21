"""API des registres / tableaux de suivi (MANUEL ch.10, proposition §6.5)."""

from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from users.permissions import IsAdminOrStaff

from .models import Registre, RegistreEntry
from .serializers import RegistreEntrySerializer, RegistreSerializer
from .services import export_entries


class RegistreViewSet(viewsets.ModelViewSet):
    """CRUD des registres. Lecture : authentifié ; écriture : admin."""

    serializer_class = RegistreSerializer
    http_method_names = ["get", "post", "patch", "delete"]

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [IsAuthenticated()]
        return [IsAdminOrStaff()]

    def get_queryset(self):
        qs = Registre.objects.prefetch_related("entries").all()
        kind = self.request.query_params.get("kind")
        year = self.request.query_params.get("year")
        active = self.request.query_params.get("active")
        if kind:
            qs = qs.filter(kind=kind)
        if year:
            qs = qs.filter(year=year)
        if active is not None:
            qs = qs.filter(is_active=active.lower() in ("1", "true", "yes"))
        return qs


class RegistreEntryViewSet(viewsets.ModelViewSet):
    """CRUD des lignes de registre + export CSV/XLSX."""

    serializer_class = RegistreEntrySerializer

    def get_queryset(self):
        qs = RegistreEntry.objects.select_related("registre", "document").all()
        registre = self.request.query_params.get("registre")
        kind = self.request.query_params.get("kind")
        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")
        if registre:
            qs = qs.filter(registre_id=registre)
        if kind:
            qs = qs.filter(registre__kind=kind)
        if date_from:
            qs = qs.filter(entry_date__gte=date_from)
        if date_to:
            qs = qs.filter(entry_date__lte=date_to)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=False, methods=["get"], url_path="export")
    def export(self, request):
        fmt = request.query_params.get("export", "csv")
        if fmt not in ("csv", "xlsx"):
            return Response(
                {"detail": "format invalide (csv/xlsx)"}, status=status.HTTP_400_BAD_REQUEST
            )
        content, media_type, filename = export_entries(self.get_queryset(), fmt)
        response = HttpResponse(content, content_type=media_type)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
