"""API des intégrations par fichiers (H-04) — upload idempotent + journal des lots."""

from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .importers import ImportError, run_import
from .models import ImportBatch
from accounting_kernel.permissions import CanPostAccounting
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

    # Un import écrit dans la comptabilité (connecteur GL) : cercle comptable uniquement.
    permission_classes = [CanPostAccounting]

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

    permission_classes = [CanPostAccounting]
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


class OpeningBalanceView(APIView):
    """POST multipart : `file` (CSV compte,debit,credit[,libelle]), `date` (1er jour de l'exercice), `total_debit` (contrôle SAGE)."""

    permission_classes = [CanPostAccounting]

    @extend_schema(request=OpenApiTypes.OBJECT, responses={201: OpenApiTypes.OBJECT, 200: OpenApiTypes.OBJECT})
    def post(self, request):
        from django.core.exceptions import ValidationError as DjangoValidationError

        from .opening import OpeningConflict, import_opening_balance

        upload = request.FILES.get("file")
        if upload is None:
            return Response({"detail": "fichier requis (champ « file »)."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            move, replayed = import_opening_balance(
                upload.read(), request.data.get("date"), request.user, request.data.get("total_debit")
            )
        except OpeningConflict as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except DjangoValidationError as exc:
            return Response({"detail": " ".join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {"move": str(move.pk), "number": move.number, "reference": move.reference,
             "total_debit": str(move.total_debit), "total_credit": str(move.total_credit), "lines": move.lines.count()},
            status=status.HTTP_200_OK if replayed else status.HTTP_201_CREATED,
        )
