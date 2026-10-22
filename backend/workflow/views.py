from django.core.exceptions import PermissionDenied, ValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from documents.audit import log_audit, request_ip
from documents.models import AuditLog, Document
from documents.services import can_write_document, visible_documents
from users.models import User

from django.db.models import Q
from django.utils import timezone

from .models import Circuit, Delegation, Notification, Task
from .serializers import (
    CircuitSerializer,
    CommentSerializer,
    DelegateSerializer,
    DelegationSerializer,
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


class CircuitViewSet(viewsets.ModelViewSet):
    """Circuits de validation (RF-29 à 31), modifiables à chaud (EX-G-02) par l'administrateur et la Direction
    Générale : libellé, délai, activation, étapes (ajout, modification, ordre, retrait d'une étape inutilisée).
    Les tâches en cours gardent leur étape ; les nouvelles soumissions suivent le circuit modifié."""

    serializer_class = CircuitSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = Circuit.objects.prefetch_related("steps")
        if not (self.action != "list" or self.request.query_params.get("tous") == "1" and _gere_circuits(self.request.user)):
            qs = qs.filter(is_active=True)
        return qs

    def get_permissions(self):
        perms = super().get_permissions()
        if self.request.method not in ("GET", "HEAD", "OPTIONS"):
            perms.append(_CanGererCircuits())
        return perms

    def perform_create(self, serializer):
        serializer.save()

    def _etape(self, circuit, request):
        from .models import CircuitStep

        try:
            return CircuitStep.objects.select_for_update(of=("self",)).get(circuit=circuit, pk=int(request.data.get("etape")))
        except (CircuitStep.DoesNotExist, TypeError, ValueError):
            raise DRFValidationError({"etape": "Étape inconnue pour ce circuit."})

    @staticmethod
    def _valider_etape(data, partiel=False):
        out = {}
        if not partiel or "name" in data:
            nom = str(data.get("name", "")).strip()
            if not nom:
                raise DRFValidationError({"name": "Nom de l'étape obligatoire."})
            out["name"] = nom[:120]
        if not partiel or "actor_role" in data:
            role = data.get("actor_role")
            if role not in User.Role.values:
                raise DRFValidationError({"actor_role": "Rôle inconnu."})
            out["actor_role"] = role
        if not partiel or "max_days" in data:
            try:
                jours = int(data.get("max_days", 1))
            except (TypeError, ValueError):
                raise DRFValidationError({"max_days": "Nombre de jours entier attendu."})
            if not 1 <= jours <= 365:
                raise DRFValidationError({"max_days": "Délai attendu entre 1 et 365 jours."})
            out["max_days"] = jours
        return out

    @action(detail=True, methods=["post"], url_path="ajouter-etape")
    def ajouter_etape(self, request, pk=None):
        from django.db import transaction
        from django.db.models import Max

        from .models import CircuitStep

        valeurs = self._valider_etape(request.data)
        with transaction.atomic():
            circuit = Circuit.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
            ordre = (circuit.steps.aggregate(m=Max("order"))["m"] or 0) + 1
            CircuitStep.objects.create(circuit=circuit, order=ordre, **valeurs)
        return Response(CircuitSerializer(Circuit.objects.prefetch_related("steps").get(pk=circuit.pk)).data, status=201)

    @action(detail=True, methods=["post"], url_path="modifier-etape")
    def modifier_etape(self, request, pk=None):
        from django.db import transaction

        valeurs = self._valider_etape(request.data, partiel=True)
        with transaction.atomic():
            circuit = Circuit.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
            etape = self._etape(circuit, request)
            for champ, valeur in valeurs.items():
                setattr(etape, champ, valeur)
            etape.save()
        return Response(CircuitSerializer(Circuit.objects.prefetch_related("steps").get(pk=circuit.pk)).data)

    @action(detail=True, methods=["post"], url_path="deplacer-etape")
    def deplacer_etape(self, request, pk=None):
        """`{"etape": id, "sens": "haut" | "bas"}` : échange l'ordre avec l'étape voisine."""
        from django.db import transaction

        sens = request.data.get("sens")
        if sens not in ("haut", "bas"):
            raise DRFValidationError({"sens": "« haut » ou « bas » attendu."})
        with transaction.atomic():
            circuit = Circuit.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
            etape = self._etape(circuit, request)
            voisins = circuit.steps.filter(order__lt=etape.order).order_by("-order") if sens == "haut" else \
                circuit.steps.filter(order__gt=etape.order).order_by("order")
            voisin = voisins.first()
            if voisin is not None:
                a, b = etape.order, voisin.order
                etape.order = 0
                etape.save(update_fields=["order"])
                voisin.order = a
                voisin.save(update_fields=["order"])
                etape.order = b
                etape.save(update_fields=["order"])
        return Response(CircuitSerializer(Circuit.objects.prefetch_related("steps").get(pk=circuit.pk)).data)

    @action(detail=True, methods=["post"], url_path="retirer-etape")
    def retirer_etape(self, request, pk=None):
        """Retire une étape jamais utilisée (une étape portée par des tâches reste : historique des circuits)."""
        from django.db import transaction

        with transaction.atomic():
            circuit = Circuit.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
            etape = self._etape(circuit, request)
            if etape.tasks.exists():
                raise DRFValidationError({"etape": "Étape déjà utilisée par des tâches : modifiez-la plutôt que la retirer."})
            if circuit.steps.count() <= 1:
                raise DRFValidationError({"etape": "Un circuit garde au moins une étape."})
            etape.delete()
        return Response(CircuitSerializer(Circuit.objects.prefetch_related("steps").get(pk=circuit.pk)).data)


CIRCUIT_ROLES = (User.Role.ADMIN, User.Role.PDG, User.Role.DGA)


def _gere_circuits(user):
    return bool(user and user.is_authenticated) and (user.is_staff or user.role in CIRCUIT_ROLES)


class _CanGererCircuits:
    message = "Modification des circuits réservée à l'administrateur et à la Direction Générale."

    def has_permission(self, request, view):
        return _gere_circuits(request.user)

    def has_object_permission(self, request, view, obj):
        return True


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
            # Ses tâches + celles des titulaires qui lui délèguent en ce moment (EX-G-02).
            delegants = Delegation.actives().filter(delegataire=user).values_list("delegant_id", flat=True)
            queryset = queryset.filter(Q(assigned_to=user) | Q(assigned_to_id__in=delegants))
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


class DelegationViewSet(viewsets.ModelViewSet):
    """Délégations temporaires (EX-G-02) : chacun délègue ses propres validations ; l'admin voit tout."""

    serializer_class = DelegationSerializer
    http_method_names = ["get", "post"]

    def _admin(self):
        user = self.request.user
        return user.is_staff or user.role == User.Role.ADMIN

    def get_queryset(self):
        qs = Delegation.objects.select_related("delegant", "delegataire")
        if not self._admin():
            user = self.request.user
            qs = qs.filter(Q(delegant=user) | Q(delegataire=user))
        if self.request.query_params.get("actives") == "1":
            jour = timezone.localdate()
            qs = qs.filter(annulee_le__isnull=True, date_debut__lte=jour, date_fin__gte=jour)
        return qs

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["delegant"] = self.request.user
        return context

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"])
    def annuler(self, request, pk=None):
        delegation = self.get_object()
        if delegation.delegant_id != request.user.id and not self._admin():
            raise PermissionDenied("Seul le titulaire ou l'administrateur annule une délégation.")
        if delegation.annulee_le:
            raise DRFValidationError("Délégation déjà annulée.")
        delegation.annuler(request.user)
        return Response(self.get_serializer(delegation).data)
