from rest_framework import serializers

from .models import BatchRow, ImportBatch


class BatchRowSerializer(serializers.ModelSerializer):
    class Meta:
        model = BatchRow
        fields = ["id", "row_number", "status", "data", "error_message", "created_at"]


class ImportBatchSerializer(serializers.ModelSerializer):
    connector_label = serializers.CharField(source="get_connector_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    rows = BatchRowSerializer(many=True, read_only=True)
    created_by_email = serializers.EmailField(source="created_by.email", read_only=True, default=None)

    class Meta:
        model = ImportBatch
        fields = [
            "id",
            "connector",
            "connector_label",
            "status",
            "status_label",
            "filename",
            "file_hash",
            "total_rows",
            "created_rows",
            "updated_rows",
            "error_rows",
            "error_message",
            "started_at",
            "finished_at",
            "created_by",
            "created_by_email",
            "created_at",
            "rows",
        ]
        read_only_fields = fields