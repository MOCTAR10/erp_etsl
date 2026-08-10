from django.core.exceptions import PermissionDenied
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Document, DocumentType, Dossier, Version
from .permissions import DocumentPermission, DossierPermission
from .serializers import (
    DocumentListSerializer,
    DocumentSerializer,
    DocumentTypeSerializer,
    DossierSerializer,
    NewVersionSerializer,
    VersionSerializer,
)


class DocumentTypeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DocumentType.objects.all()
    serializer_class = DocumentTypeSerializer


class DossierViewSet(viewsets.ModelViewSet):
    queryset = Dossier.objects.all()
    serializer_class = DossierSerializer
    permission_classes = [DossierPermission]
    http_method_names = ["get", "post", "patch", "delete"]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class DocumentViewSet(viewsets.ModelViewSet):
    queryset = Document.objects.select_related(
        "current_version", "type", "dossier", "created_by"
    )
    permission_classes = [DocumentPermission]
    http_method_names = ["get", "post", "patch", "delete"]

    def get_serializer_class(self):
        if self.action == "list":
            return DocumentListSerializer
        return DocumentSerializer

    def perform_create(self, serializer):
        # created_by est posé dans DocumentSerializer.create (via le contexte).
        serializer.save()

    @action(detail=True, methods=["post"])
    def new_version(self, request, pk=None):
        """Ajoute une version (RF-42) — verrouillé tant que check-out (RF-44)."""
        document = self.get_object()
        serializer = NewVersionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if document.is_checked_out and document.checked_out_by_id != request.user.id:
            raise PermissionDenied(
                "Document verrouillé (check-out) par un autre utilisateur (RF-44)."
            )

        uploaded = serializer.validated_data["file"]
        from .serializers import compute_sha256

        sha256 = compute_sha256(uploaded)
        last = document.versions.order_by("-number").first()
        version = Version.objects.create(
            document=document,
            number=(last.number + 1) if last else 1,
            file=uploaded,
            sha256=sha256,
            size=uploaded.size,
            original_filename=uploaded.name,
            note=serializer.validated_data.get("note", ""),
            created_by=request.user,
        )
        document.current_version = version
        document.sha256 = sha256
        document.save(update_fields=["current_version", "sha256"])
        return Response(VersionSerializer(version).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def rollback(self, request, pk=None):
        """Restaure une version antérieure comme version courante (RF-43)."""
        document = self.get_object()
        version_id = request.data.get("version_id")
        version = document.versions.filter(id=version_id).first()
        if version is None:
            return Response(
                {"detail": "Version introuvable pour ce document."},
                status=status.HTTP_404_NOT_FOUND,
            )
        document.current_version = version
        document.sha256 = version.sha256
        document.save(update_fields=["current_version", "sha256"])
        return Response(VersionSerializer(version).data)

    @action(detail=True, methods=["post"])
    def checkout(self, request, pk=None):
        """Verrouille le document pour édition exclusive (RF-44)."""
        document = self.get_object()
        if document.is_checked_out:
            return Response(
                {"detail": "Document déjà verrouillé."},
                status=status.HTTP_409_CONFLICT,
            )
        document.checked_out_by = request.user
        document.checked_out_at = timezone.now()
        document.save(update_fields=["checked_out_by", "checked_out_at"])
        return Response(DocumentSerializer(document, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def checkin(self, request, pk=None):
        """Libère le verrou (RF-44)."""
        document = self.get_object()
        if not document.is_checked_out:
            return Response(
                {"detail": "Le document n'est pas verrouillé."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if document.checked_out_by_id != request.user.id and not request.user.is_staff:
            raise PermissionDenied("Seul le titulaire du verrou peut faire le check-in.")
        document.checked_out_by = None
        document.checked_out_at = None
        document.save(update_fields=["checked_out_by", "checked_out_at"])
        return Response(DocumentSerializer(document, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["get"])
    def versions(self, request, pk=None):
        """Historique des versions (RF-43)."""
        document = self.get_object()
        return Response(
            VersionSerializer(document.versions.all(), many=True).data
        )
