from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import OutboxEvent
from .serializers import OutboxEventSerializer


class OutboxEventViewSet(viewsets.ReadOnlyModelViewSet):
    """Événements outbox (suivi inter-modules) — lecture authentifiée."""

    permission_classes = [IsAuthenticated]
    serializer_class = OutboxEventSerializer

    def get_queryset(self):
        qs = OutboxEvent.objects.all()
        topic = self.request.query_params.get("topic")
        status = self.request.query_params.get("status")
        if topic:
            qs = qs.filter(topic=topic)
        if status:
            qs = qs.filter(status=status)
        return qs