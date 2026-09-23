"""API des intégrations par fichiers (H-04) — upload idempotent + journal des lots."""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .importers import ImportError, run_import
from .models import ImportBatch
from .serializers import ImportBatchSerializer


@extend_schema(
    request={
        "multipart/form-data": {
            "type": "object",
            "properties": {
                "connector": {
                    "type": "string",
                    "enum": ["partners", "gl"],
                    "description": "Connecteur d'import (tiers ou écritures).",
                },
                "file": {"type": "string", "format": "binary"},
                "force": {"type": "string", "description": "true pour rejouer un lot existant."},
            },
            "required": ["connector", "file"],
        }
    },
    responses={200: ImportBatchSerializer},
)
class ImportFileView(APIView):
    """POST multipart : `connector`, `file`, `force` (optionnel).

    Idempotence : un fichier déjà importé (même SHA-256, lot non-échoué) est
    rejoué sans ré-insertion (HTTP 200 + batch existant) sauf `force=true`.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        connector = request.data.get("connector")
        if connector not in ImportBatch.Connector.values:
            return Response(
                {"detail": f"connecteur inconnu : {connector}"}, status=status.HTTP_400_BAD_REQUEST
            )
        upload = request.FILES.get("file")
        if upload is None:
            return Response(
                {"detail": "fichier requis (champ « file »)."}, status=status.HTTP_400_BAD_REQUEST
            )
        force = str(request.data.get("force", "")).lower() in ("1", "true", "yes")
        try:
            batch, replayed = run_import(
                connector, upload.name, upload.read(), user=request.user, force=force
            )
        except ImportError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        serializer = ImportBatchSerializer(batch, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK if replayed else status.HTTP_201_CREATED)


class ImportBatchViewSet(viewsets.ReadOnlyModelViewSet):
    """Historique des lots + journal d'erreurs ligne à ligne."""

    permission_classes = [IsAuthenticated]
    serializer_class = ImportBatchSerializer

    def get_queryset(self):
        qs = ImportBatch.objects.prefetch_related("rows").select_related("created_by")
        connector = self.request.query_params.get("connector")
        batch_status = self.request.query_params.get("status")
        if connector:
            qs = qs.filter(connector=connector)
        if batch_status:
            qs = qs.filter(status=batch_status)
        return qs