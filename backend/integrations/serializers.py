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


class GabaritImportSerializer(serializers.ModelSerializer):
    est_provisoire = serializers.BooleanField(read_only=True)

    class Meta:
        from .models import GabaritImport

        model = GabaritImport
        fields = [
            "id", "code", "label", "separateur", "encodage", "format_date", "separateur_decimal", "colonnes",
            "statut_valeur", "est_provisoire", "confirme_par", "confirme_le", "updated_at",
        ]
        read_only_fields = ["id", "statut_valeur", "est_provisoire", "confirme_par", "confirme_le", "updated_at"]

    def validate_encodage(self, value):
        import codecs

        try:
            codecs.lookup(value)
        except LookupError:
            raise serializers.ValidationError("Encodage inconnu (ex. cp1252, utf-8, latin-1).")
        return value

    def validate_format_date(self, value):
        from datetime import date

        try:
            date(2026, 1, 31).strftime(value)
        except ValueError:
            raise serializers.ValidationError("Format de date invalide (ex. %d/%m/%Y).")
        if "%d" not in value or "%m" not in value or not ("%Y" in value or "%y" in value):
            raise serializers.ValidationError("Le format doit contenir le jour, le mois et l'année.")
        return value

    def validate_colonnes(self, value):
        from .gabarits import CHAMPS_SAGE

        if not isinstance(value, dict) or any(not isinstance(v, str) for v in value.values()):
            raise serializers.ValidationError("Objet attendu : {champ ERP : nom de colonne}.")
        inconnus = sorted(set(value) - set(CHAMPS_SAGE))
        if inconnus:
            raise serializers.ValidationError(f"Champ(s) inconnu(s) : {', '.join(inconnus)}.")
        return value

    def update(self, instance, validated_data):
        # Toute modification repasse le gabarit en provisoire jusqu'à nouvelle confirmation.
        instance.statut_valeur = instance.StatutValeur.PROVISOIRE
        instance.confirme_par = None
        instance.confirme_le = None
        return super().update(instance, validated_data)
