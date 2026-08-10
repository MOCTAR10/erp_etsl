from django.contrib.postgres.search import SearchQuery, SearchRank
from django.core.exceptions import PermissionDenied
from django.db.models import Count, F
from django.shortcuts import redirect
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .audit import log_audit, request_ip
from .models import (
    AuditLog,
    Document,
    DocumentType,
    Dossier,
    DocumentAccess,
    DossierAccess,
    Version,
)
from .permissions import (
    CanManageACL,
    DocumentPermission,
    DossierPermission,
    IsAdminOrStaff,
)
from .serializers import (
    AccessEntrySerializer,
    AuditLogSerializer,
    DocumentListSerializer,
    DocumentSerializer,
    DocumentTypeSerializer,
    DossierSerializer,
    NewVersionSerializer,
    VersionSerializer,
)
from .services import (
    WRITE_ROLES,
    can_manage_acl,
    can_write_dossier,
    is_admin_or_staff,
    visible_documents,
    visible_dossiers,
)


class DocumentTypeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DocumentType.objects.all()
    serializer_class = DocumentTypeSerializer


class DossierViewSet(viewsets.ModelViewSet):
    queryset = Dossier.objects.all()
    serializer_class = DossierSerializer
    permission_classes = [DossierPermission]
    http_method_names = ["get", "post", "patch", "delete"]

    def get_queryset(self):
        return visible_dossiers(self.request.user)

    def perform_create(self, serializer):
        user = self.request.user
        if not is_admin_or_staff(user) and user.role not in WRITE_ROLES:
            raise PermissionDenied(
                "Votre rôle ne permet pas de créer de dossier (matrice §3.3)."
            )
        dossier = serializer.save(created_by=user)
        log_audit(
            user,
            AuditLog.Action.CREATE,
            "dossier",
            dossier.id,
            {"name": dossier.name},
            request_ip(self.request),
        )

    def perform_update(self, serializer):
        before = {f: str(getattr(serializer.instance, f)) for f in serializer.validated_data}
        dossier = serializer.save()
        log_audit(
            self.request.user,
            AuditLog.Action.UPDATE,
            "dossier",
            dossier.id,
            {"changed": before},
            request_ip(self.request),
        )

    def perform_destroy(self, instance):
        log_audit(
            self.request.user,
            AuditLog.Action.DELETE,
            "dossier",
            instance.id,
            {"name": instance.name},
            request_ip(self.request),
        )
        instance.delete()

    @action(detail=True, methods=["get", "post", "delete"])
    def acl(self, request, pk=None):
        """Gestion des droits au niveau dossier (RF-58, héritage descendants)."""
        dossier = self.get_object()
        if not can_manage_acl(request.user, dossier=dossier):
            raise PermissionDenied("Seul l'admin ou le créateur du dossier gère ses droits.")
        if request.method == "GET":
            entries = [
                {
                    "user": a.user_id,
                    "user_email": a.user.email,
                    "permission": a.permission,
                }
                for a in dossier.acl.select_related("user").all()
            ]
            return Response(entries)
        serializer = AccessEntrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_id = serializer.validated_data["user"]
        if request.method == "DELETE":
            removed = dossier.acl.filter(user_id=user_id)
            if removed.exists():
                removed.delete()
                log_audit(
                    request.user,
                    AuditLog.Action.ACL_REVOKE,
                    "dossier",
                    dossier.id,
                    {"user": user_id},
                    request_ip(request),
                )
            return Response(status=status.HTTP_204_NO_CONTENT)
        permission = serializer.validated_data.get("permission", "read")
        DossierAccess.objects.update_or_create(
            dossier=dossier,
            user_id=user_id,
            defaults={"permission": permission, "granted_by": request.user},
        )
        log_audit(
            request.user,
            AuditLog.Action.ACL_GRANT,
            "dossier",
            dossier.id,
            {"user": user_id, "permission": permission},
            request_ip(request),
        )
        return Response(status=status.HTTP_200_OK)


class DocumentViewSet(viewsets.ModelViewSet):
    queryset = Document.objects.select_related(
        "current_version", "type", "dossier", "created_by"
    )
    permission_classes = [DocumentPermission]
    http_method_names = ["get", "post", "patch", "delete"]

    def get_queryset(self):
        queryset = visible_documents(self.request.user)

        # Filtres facettes (RF-23/26) : type, statut, dossier, année.
        params = self.request.query_params
        if doc_type := params.get("type"):
            queryset = queryset.filter(type_id=doc_type)
        if doc_status := params.get("status"):
            queryset = queryset.filter(status=doc_status)
        if dossier := params.get("dossier"):
            queryset = queryset.filter(dossier_id=dossier)
        if year := params.get("year"):
            queryset = queryset.filter(document_date__year=year)

        # Recherche full-text (RF-23/26/27) : classée par pertinence.
        if search := params.get("search"):
            query = SearchQuery(search, config="french")
            queryset = (
                queryset.annotate(rank=SearchRank(F("search_vector"), query))
                .filter(search_vector=query)
                .order_by("-rank", "-created_at")
            )
        return queryset

    @action(detail=False, methods=["get"])
    def facets(self, request):
        """Compteurs par statut, type et année sur la sélection (RF-23/26)."""
        base = self.get_queryset()
        return Response(
            {
                "total": base.count(),
                "by_status": dict(
                    base.values_list("status").annotate(count=Count("id")).order_by()
                ),
                "by_type": list(
                    base.values("type__label")
                    .annotate(count=Count("id"))
                    .order_by("-count")
                ),
                "by_year": dict(
                    base.filter(document_date__isnull=False)
                    .values_list("document_date__year")
                    .annotate(count=Count("id"))
                    .order_by("-document_date__year")
                ),
            }
        )

    def get_serializer_class(self):
        if self.action == "list":
            return DocumentListSerializer
        return DocumentSerializer

    def perform_create(self, serializer):
        user = self.request.user
        # Matrice §3.3 : création réservée aux rôles à écriture, sauf droit dossier (RF-58).
        if not is_admin_or_staff(user) and user.role not in WRITE_ROLES:
            dossier = serializer.validated_data.get("dossier")
            if not (dossier and can_write_dossier(user, dossier)):
                raise PermissionDenied(
                    "Votre rôle ne permet pas de créer de document (matrice §3.3)."
                )
        # RF-33 : seul l'admin peut créer un document de type restreint (paie).
        doc_type = serializer.validated_data.get("type")
        if doc_type and doc_type.is_restricted_rh and not is_admin_or_staff(user):
            raise PermissionDenied(
                "Les documents de type restreint (paie) sont réservés à l'administration (RF-33)."
            )
        # created_by est posé dans DocumentSerializer.create (via le contexte).
        document = serializer.save()
        log_audit(
            user,
            AuditLog.Action.CREATE,
            "document",
            document.id,
            {"title": document.title, "version": 1},
            request_ip(self.request),
        )

    def perform_update(self, serializer):
        before = {f: str(getattr(serializer.instance, f)) for f in serializer.validated_data if f != "file"}
        document = serializer.save()
        log_audit(
            self.request.user,
            AuditLog.Action.UPDATE,
            "document",
            document.id,
            {"changed": before},
            request_ip(self.request),
        )

    def perform_destroy(self, instance):
        log_audit(
            self.request.user,
            AuditLog.Action.DELETE,
            "document",
            instance.id,
            {"title": instance.title},
            request_ip(self.request),
        )
        instance.delete()

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        """Téléchargement tracé (RF-64) — redirige vers l'objet MinIO."""
        document = self.get_object()
        if document.current_version_id is None:
            return Response(
                {"detail": "Le document n'a pas de version courante."},
                status=status.HTTP_404_NOT_FOUND,
            )
        log_audit(
            request.user,
            AuditLog.Action.DOWNLOAD,
            "document",
            document.id,
            {"version": document.current_version.number, "filename": document.current_version.original_filename},
            request_ip(request),
        )
        return redirect(document.current_version.file.url)

    @action(detail=True, methods=["get"])
    def verify(self, request, pk=None):
        """Vérifie l'intégrité du fichier stocké (SHA-256, RF-67)."""
        from .serializers import compute_sha256

        document = self.get_object()
        if document.current_version_id is None:
            return Response(
                {"detail": "Le document n'a pas de version courante."},
                status=status.HTTP_404_NOT_FOUND,
            )
        version = document.current_version
        try:
            actual = compute_sha256(version.file)
        except Exception as exc:
            return Response(
                {"detail": f"Lecture du fichier impossible : {exc}"},
                status=status.HTTP_409_CONFLICT,
            )
        ok = actual == version.sha256
        log_audit(
            request.user,
            AuditLog.Action.UPDATE,
            "document",
            document.id,
            {"integrity_verified": ok},
            request_ip(request),
        )
        return Response(
            {"ok": ok, "expected_sha256": version.sha256, "actual_sha256": actual}
        )

    @action(detail=True, methods=["get", "post", "delete"])
    def acl(self, request, pk=None):
        """Gestion des droits au niveau document (RF-57)."""
        document = self.get_object()
        if not can_manage_acl(request.user, document=document):
            raise PermissionDenied("Seul l'admin ou le créateur du document gère ses droits.")
        if request.method == "GET":
            entries = [
                {
                    "user": a.user_id,
                    "user_email": a.user.email,
                    "permission": a.permission,
                }
                for a in document.acl.select_related("user").all()
            ]
            return Response(entries)
        serializer = AccessEntrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_id = serializer.validated_data["user"]
        if request.method == "DELETE":
            removed = document.acl.filter(user_id=user_id)
            if removed.exists():
                removed.delete()
                log_audit(
                    request.user,
                    AuditLog.Action.ACL_REVOKE,
                    "document",
                    document.id,
                    {"user": user_id},
                    request_ip(request),
                )
            return Response(status=status.HTTP_204_NO_CONTENT)
        permission = serializer.validated_data.get("permission", "read")
        DocumentAccess.objects.update_or_create(
            document=document,
            user_id=user_id,
            defaults={"permission": permission, "granted_by": request.user},
        )
        log_audit(
            request.user,
            AuditLog.Action.ACL_GRANT,
            "document",
            document.id,
            {"user": user_id, "permission": permission},
            request_ip(request),
        )
        return Response(status=status.HTTP_200_OK)

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
        log_audit(
            request.user,
            AuditLog.Action.UPDATE,
            "document",
            document.id,
            {"new_version": version.number, "note": version.note},
            request_ip(request),
        )
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
        log_audit(
            request.user,
            AuditLog.Action.UPDATE,
            "document",
            document.id,
            {"rollback_version": version.number},
            request_ip(request),
        )
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
        log_audit(
            request.user,
            AuditLog.Action.UPDATE,
            "document",
            document.id,
            {"checkout": True},
            request_ip(request),
        )
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
        log_audit(
            request.user,
            AuditLog.Action.UPDATE,
            "document",
            document.id,
            {"checkout": False},
            request_ip(request),
        )
        return Response(DocumentSerializer(document, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["get"])
    def versions(self, request, pk=None):
        """Historique des versions (RF-43)."""
        document = self.get_object()
        return Response(
            VersionSerializer(document.versions.all(), many=True).data
        )


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Piste d'audit (RF-63 à 65) — consultation réservée à l'administration."""

    serializer_class = AuditLogSerializer
    permission_classes = [IsAdminOrStaff]

    def get_queryset(self):
        params = self.request.query_params
        queryset = AuditLog.objects.select_related("user").all()
        if object_type := params.get("object_type"):
            queryset = queryset.filter(object_type=object_type)
        if object_id := params.get("object_id"):
            queryset = queryset.filter(object_id=object_id)
        if action := params.get("action"):
            queryset = queryset.filter(action=action)
        if user_id := params.get("user"):
            queryset = queryset.filter(user_id=user_id)
        return queryset
