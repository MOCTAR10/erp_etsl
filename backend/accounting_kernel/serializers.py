from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import AccountMove, AccountMoveLine, FiscalYear, Journal, Period, Sequence
from .services import period_for_date


class FiscalYearSerializer(serializers.ModelSerializer):
    class Meta:
        model = FiscalYear
        fields = ["id", "year", "start_date", "end_date", "status"]


class PeriodSerializer(serializers.ModelSerializer):
    fiscal_year_year = serializers.IntegerField(source="fiscal_year.year", read_only=True)
    is_open = serializers.BooleanField(read_only=True)

    class Meta:
        model = Period
        fields = [
            "id",
            "fiscal_year",
            "fiscal_year_year",
            "number",
            "start_date",
            "end_date",
            "status",
            "is_open",
        ]
        read_only_fields = ["id", "status"]


class JournalSerializer(serializers.ModelSerializer):
    journal_type_label = serializers.CharField(
        source="get_journal_type_display", read_only=True
    )

    class Meta:
        model = Journal
        fields = ["id", "code", "label", "journal_type", "journal_type_label", "is_active"]


class SequenceSerializer(serializers.ModelSerializer):
    journal_code = serializers.CharField(source="journal.code", read_only=True)

    class Meta:
        model = Sequence
        fields = ["id", "journal", "journal_code", "prefix", "padding", "next_number"]
        read_only_fields = ["id", "next_number"]


class AccountMoveLineSerializer(serializers.ModelSerializer):
    account_code = serializers.CharField(source="account.code", read_only=True)
    account_label = serializers.CharField(source="account.label", read_only=True)

    class Meta:
        model = AccountMoveLine
        fields = [
            "id",
            "account",
            "account_code",
            "account_label",
            "partner",
            "analytic_account",
            "label",
            "debit",
            "credit",
            "order",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        debit = attrs.get("debit", 0)
        credit = attrs.get("credit", 0)
        if debit and credit:
            raise serializers.ValidationError(
                "Une ligne ne peut être à la fois débit et crédit."
            )
        if not debit and not credit:
            raise serializers.ValidationError("Renseignez un débit ou un crédit.")
        return attrs


class AccountMoveSerializer(serializers.ModelSerializer):
    lines = AccountMoveLineSerializer(many=True)
    period = serializers.PrimaryKeyRelatedField(queryset=Period.objects.all(), required=False)
    total_debit = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    total_credit = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    journal_code = serializers.CharField(source="journal.code", read_only=True)

    class Meta:
        model = AccountMove
        fields = [
            "id",
            "journal",
            "journal_code",
            "period",
            "date",
            "number",
            "reference",
            "label",
            "status",
            "source",
            "source_ref",
            "reversed_by",
            "created_by",
            "posted_at",
            "created_at",
            "total_debit",
            "total_credit",
            "lines",
        ]
        read_only_fields = [
            "id",
            "number",
            "status",
            "reversed_by",
            "created_by",
            "posted_at",
            "created_at",
        ]

    def validate_lines(self, value):
        if len(value) < 2:
            raise serializers.ValidationError("Une écriture doit comporter au moins deux lignes.")
        return value

    def create(self, validated_data):
        lines_data = validated_data.pop("lines")
        if not validated_data.get("period"):
            try:
                validated_data["period"] = period_for_date(validated_data["date"])
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"date": exc.messages})
        move = AccountMove.objects.create(**validated_data)
        for index, line_data in enumerate(lines_data):
            line_data.setdefault("order", index)
            AccountMoveLine.objects.create(move=move, **line_data)
        return move
