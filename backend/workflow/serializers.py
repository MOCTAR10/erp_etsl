from rest_framework import serializers


from config.serializers import ModelCleanMixin

from .models import Circuit, CircuitStep, Delegation, Notification, Task, TaskComment


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

    def validate_code(self, value):
        if self.instance is not None and value != self.instance.code:
            raise serializers.ValidationError("Le code d'un circuit ne se modifie pas (types de documents liés).")
        if self.instance is None and Circuit.objects.filter(code=value).exists():
            raise serializers.ValidationError("Ce code de circuit existe déjà.")
        return value

    def validate_max_days(self, value):
        if not 1 <= value <= 365:
            raise serializers.ValidationError("Délai attendu entre 1 et 365 jours.")
        return value


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
    # Nom affiché (nom complet, sinon fonction) et rôle de l'assigné : le kanban n'affiche jamais l'e-mail.
    assigned_to_name = serializers.CharField(source="assigned_to.nom_affiche", read_only=True, default=None)
    assigned_to_role = serializers.CharField(source="assigned_to.role", read_only=True, default=None)
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
            "assigned_to_name",
            "assigned_to_role",
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


class NotificationSerializer(serializers.ModelSerializer):
    document_title = serializers.CharField(source="task.document.title", read_only=True)
    step_name = serializers.CharField(source="task.step.name", read_only=True)

    class Meta:
        model = Notification
        fields = [
            "id",
            "subject",
            "message",
            "kind",
            "is_read",
            "task",
            "document_title",
            "step_name",
            "created_at",
        ]
        read_only_fields = fields


class DelegationSerializer(ModelCleanMixin, serializers.ModelSerializer):
    delegant_email = serializers.EmailField(source="delegant.email", read_only=True)
    delegataire_email = serializers.EmailField(source="delegataire.email", read_only=True)
    # Saisie par adresse e-mail : un utilisateur non admin n'a pas accès à l'annuaire des comptes.
    email_delegataire = serializers.EmailField(write_only=True, required=False)
    active = serializers.BooleanField(read_only=True)

    class Meta:
        model = Delegation
        fields = [
            "id", "code", "delegant", "delegant_email", "delegataire", "delegataire_email", "date_debut",
            "date_fin", "motif", "active", "annulee_le", "annulee_par", "created_by", "created_at", "email_delegataire",
        ]
        read_only_fields = ["id", "code", "delegant", "active", "annulee_le", "annulee_par", "created_by", "created_at"]
        extra_kwargs = {"delegataire": {"required": False}}

    def validate(self, attrs):
        from users.models import User

        email = attrs.pop("email_delegataire", None)
        if email:
            attrs["delegataire"] = User.objects.filter(email__iexact=email, is_active=True).first()
            if attrs["delegataire"] is None:
                raise serializers.ValidationError({"email_delegataire": "Aucun compte actif avec cette adresse."})
        if self.instance is None:
            if not attrs.get("delegataire"):
                raise serializers.ValidationError({"delegataire": "Délégataire obligatoire."})
            attrs["delegant"] = self.context["delegant"]
        return super().validate(attrs)
