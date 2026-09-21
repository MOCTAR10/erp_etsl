from rest_framework import serializers

from .models import OutboxEvent


class OutboxEventSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = OutboxEvent
        fields = [
            "id",
            "topic",
            "payload",
            "status",
            "status_label",
            "attempt_count",
            "error_message",
            "created_at",
            "delivered_at",
        ]
        read_only_fields = fields