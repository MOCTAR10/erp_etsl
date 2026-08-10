from rest_framework import serializers

from users.models import User

from .models import Circuit, CircuitStep, Task, TaskComment


class CircuitStepSerializer(serializers.ModelSerializer):
    actor_role_label = serializers.CharField(
        source="get_actor_role_display", read_only=True
    )

    class Meta:
        model = CircuitStep
        fields = [
            "id",
            "circuit",
            "order",
            "name",
            "actor_role",
            "actor_role_label",
            "max_days",
        ]


class CircuitSerializer(serializers.ModelSerializer):
    steps = CircuitStepSerializer(many=True, read_only=True)

    class Meta:
        model = Circuit
        fields = ["id", "code", "label", "max_days", "is_active", "steps"]


class TaskCommentSerializer(serializers.ModelSerializer):
    author_email = serializers.EmailField(source="author.email", read_only=True)

    class Meta:
        model = TaskComment
        fields = ["id", "author", "author_email", "text", "created_at"]
        read_only_fields = ["id", "author", "author_email", "created_at"]


class TaskSerializer(serializers.ModelSerializer):
    document_title = serializers.CharField(source="document.title", read_only=True)
    step_name = serializers.CharField(source="step.name", read_only=True)
    step_order = serializers.IntegerField(source="step.order", read_only=True)
    circuit_label = serializers.CharField(source="circuit.label", read_only=True)
    assigned_to_email = serializers.EmailField(source="assigned_to.email", read_only=True)
    comments_count = serializers.IntegerField(
        source="comments.count", read_only=True
    )

    class Meta:
        model = Task
        fields = [
            "id",
            "document",
            "document_title",
            "circuit",
            "circuit_label",
            "step",
            "step_name",
            "step_order",
            "assigned_to",
            "assigned_to_email",
            "status",
            "due_date",
            "completed_at",
            "created_at",
            "comments_count",
        ]
        read_only_fields = fields


class SubmitSerializer(serializers.Serializer):
    """Soumission d'un document au circuit (RF-29 à 31)."""

    document = serializers.UUIDField()


class RejectSerializer(serializers.Serializer):
    """Rejet motivé (RF-39)."""

    reason = serializers.CharField(required=True, allow_blank=False)


class DelegateSerializer(serializers.Serializer):
    """Délégation de tâche (RF-36)."""

    user = serializers.UUIDField()


class CommentSerializer(serializers.Serializer):
    """Commentaire dans le circuit (RF-38)."""

    text = serializers.CharField(required=True, allow_blank=False)
