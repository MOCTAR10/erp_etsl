from rest_framework import serializers

from .models import Registre, RegistreEntry


class RegistreSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    entries_count = serializers.IntegerField(source="entries.count", read_only=True)

    class Meta:
        model = Registre
        fields = [
            "id",
            "kind",
            "kind_label",
            "label",
            "year",
            "annexe",
            "is_active",
            "entries_count",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class RegistreEntrySerializer(serializers.ModelSerializer):
    document_title = serializers.CharField(source="document.title", read_only=True, default=None)

    class Meta:
        model = RegistreEntry
        fields = [
            "id",
            "registre",
            "number",
            "entry_date",
            "data",
            "document",
            "document_title",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "number", "created_by", "created_at", "updated_at"]
