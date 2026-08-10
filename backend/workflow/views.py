from django.core.exceptions import PermissionDenied, ValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from documents.audit import log_audit, request_ip
from documents.models import AuditLog, Document
from documents.permissions import IsAdminOrStaff
from documents.services import can_write_document, visible_documents
from users.models import User

from .models import Circuit, Notification, Task
from .serializers import (
    CircuitSerializer,
    CommentSerializer,
    DelegateSerializer,
    NotificationSerializer,
    RejectSerializer,
    SubmitSerializer,
    TaskCommentSerializer,
    TaskSerializer,
)
from .services import (
    add_comment,
    complete_task,
    delegate_task,
    reject_task,
    start_circuit,
)


class CircuitViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Circuit.objects.prefetch_related("steps").filter(is_active=True)
    serializer_class = CircuitSerializer


class TaskViewSet(viewsets.ReadOnlyModelViewSet):
    """Tâches du workflow — tableau de bord des tâches en attente (RF-37)."""

    queryset = Task.objects.select_related(
        "document", "circuit", "step", "assigned_to"
    )
    serializer_class = TaskSerializer

    def get_queryset(self):
        user = self.request.user
        queryset = Task.objects.select_related(
            "document", "circuit", "step", "assigned_to"
        )
        # Visibilité : un utilisateur ne voit que ses tâches (ou tout si admin).
        if not (user.is_staff or user.role == User.Role.ADMIN):
            queryset = queryset.filter(assigned_to=user)
        # Un utilisateur ne voit pas les tâches de documents invisibles (RF-33).
        queryset = queryset.filter(
            document_id__in=visible_documents(user).values_list("id", flat=True)
        )

        params = self.request.query_params
        if status_param := params.get("status"):
            queryset = queryset.filter(status=status_param)
        if assigned_to := params.get("assigned_to"):
            queryset = queryset.filter(assigned_to_id=assigned_to)
        if document_id := params.get("document_id"):
            queryset = queryset.filter(document_id=document_id)
        return queryset

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Tableau de bord : tâches en attente par service (RF-37)."""
        if not (request.user.is_staff or request.user.role == User.Role.ADMIN):
            raise PermissionDenied("Réservé à l'administration.")
        pending = Task.objects.filter(status=Task.Status.PENDING)
        per_service = [
            {
                "role": code,
                "label": label,
                "pending": pending.filter(assigned_to__role=code).count(),
            }
            for code, label in User.Role.choices
        ]
        per_service = [s for s in per_service if s["pending"] > 0]
        return Response(
            {"total_pending": pending.count(), "per_service": per_service}
        )

    @action(detail=False, methods=["post"])
    def submit(self, request):
        """Soumission d'un document → démarre son circuit (RF-29 à 31)."""
        serializer = SubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document = Document.objects.filter(id=serializer.validated_data["document"]).first()
        if document is None:
            return Response(
                {"detail": "Document introuvable."}, status=status.HTTP_404_NOT_FOUND
            )
        if not can_write_document(request.user, document):
            raise PermissionDenied("Vous n'avez pas le droit de soumettre ce document.")
        try:
            task = start_circuit(document, request.user)
        except ValidationError as exc:
            return Response(
                {"detail": "; ".join(exc.messages) if exc.messages else str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        log_audit(
            request.user,
            AuditLog.Action.UPDATE,
            "document",
            document.id,
            {"submit": True, "circuit": task.circuit.code, "step": task.step.name},
            request_ip(request),
        )
        return Response(TaskSerializer(task).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        """Termine l'étape courante (avancement ou archivage, RF-40)."""
        task = self.get_object()
        try:
            next_task = complete_task(task, request.user)
        except ValidationError as exc:
            return Response(
                {"detail": "; ".join(exc.messages) if exc.messages else str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        log_audit(
            request.user,
            AuditLog.Action.UPDATE,
            "document",
            task.document_id,
            {"task_completed": task.step.name},
            request_ip(request),
        )
        if next_task is None:
            return Response(
                {"detail": "Circuit terminé, document archivé."},
                status=status.HTTP_200_OK,
            )
        return Response(TaskSerializer(next_task).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        """Rejet motivé → document rejeté (RF-39)."""
        task = self.get_object()
        serializer = RejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            document = reject_task(task, request.user, serializer.validated_data["reason"])
        except ValidationError as exc:
            return Response(
                {"detail": "; ".join(exc.messages) if exc.messages else str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        log_audit(
            request.user,
            AuditLog.Action.UPDATE,
            "document",
            document.id,
            {"rejected": True, "reason": serializer.validated_data["reason"]},
            request_ip(request),
        )
        return Response(
            {"detail": "Document rejeté.", "status": document.status}
        )

    @action(detail=True, methods=["post"])
    def delegate(self, request, pk=None):
        """Délégation / transfert de tâche (RF-36)."""
        task = self.get_object()
        serializer = DelegateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        to_user = User.objects.filter(id=serializer.validated_data["user"]).first()
        if to_user is None:
            return Response(
                {"detail": "Utilisateur introuvable."}, status=status.HTTP_404_NOT_FOUND
            )
        try:
            task = delegate_task(task, request.user, to_user)
        except ValidationError as exc:
            return Response(
                {"detail": "; ".join(exc.messages) if exc.messages else str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        log_audit(
            request.user,
            AuditLog.Action.UPDATE,
            "document",
            task.document_id,
            {"delegated": True, "to": to_user.email},
            request_ip(request),
        )
        return Response(TaskSerializer(task).data)

    @action(detail=True, methods=["get", "post"])
    def comments(self, request, pk=None):
        """Commentaires / annotations dans le circuit (RF-38)."""
        task = self.get_object()
        if request.method == "POST":
            serializer = CommentSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            comment = add_comment(task, request.user, serializer.validated_data["text"])
            return Response(
                TaskCommentSerializer(comment).data, status=status.HTTP_201_CREATED
            )
        return Response(
            TaskCommentSerializer(task.comments.select_related("author"), many=True).data
        )


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """Notifications de l'utilisateur connecté (RF-34/35/37)."""

    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).select_related(
            "task__document", "task__step"
        )

    @action(detail=True, methods=["post"])
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.save(update_fields=["is_read"])
        return Response(NotificationSerializer(notification).data)

    @action(detail=False, methods=["post"])
    def mark_all_read(self, request):
        updated = self.get_queryset().update(is_read=True)
        return Response({"updated": updated})
