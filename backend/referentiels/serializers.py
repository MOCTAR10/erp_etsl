from rest_framework import serializers

from .models import (
    Account,
    AnalyticAccount,
    AnalyticAxis,
    Annexe,
    Article,
    Currency,
    Partner,
    Site,
    UnitOfMeasure,
)


class AnnexeSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    domain_label = serializers.CharField(source="get_domain_display", read_only=True)

    class Meta:
        model = Annexe
        fields = [
            "id",
            "code",
            "label",
            "kind",
            "kind_label",
            "domain",
            "domain_label",
            "description",
            "source_ref",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class CurrencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Currency
        fields = ["id", "code", "label", "symbol", "decimals", "is_active"]


class UnitOfMeasureSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnitOfMeasure
        fields = ["id", "code", "label", "is_active"]


class AccountSerializer(serializers.ModelSerializer):
    account_class_label = serializers.CharField(
        source="get_account_class_display", read_only=True
    )
    account_type_label = serializers.CharField(
        source="get_account_type_display", read_only=True
    )

    class Meta:
        model = Account
        fields = [
            "id",
            "code",
            "label",
            "account_class",
            "account_class_label",
            "account_type",
            "account_type_label",
            "parent",
            "reconcile",
            "is_active",
        ]


class PartnerSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    currency_code = serializers.CharField(source="currency.code", read_only=True, default=None)

    class Meta:
        model = Partner
        fields = [
            "id",
            "code",
            "name",
            "kind",
            "kind_label",
            "tax_id",
            "phone",
            "email",
            "address",
            "currency",
            "currency_code",
            "is_global_rental",
            "agree_qualite_jusqu",
            "agree_hse_jusqu",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ArticleSerializer(serializers.ModelSerializer):
    article_type_label = serializers.CharField(
        source="get_article_type_display", read_only=True
    )
    unit_code = serializers.CharField(source="unit.code", read_only=True, default=None)

    class Meta:
        model = Article
        fields = [
            "id",
            "code",
            "label",
            "article_type",
            "article_type_label",
            "unit",
            "unit_code",
            "purchase_price",
            "sale_price",
            "account",
            "is_stockable",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class AnalyticAxisSerializer(serializers.ModelSerializer):
    axis_type_label = serializers.CharField(source="get_axis_type_display", read_only=True)

    class Meta:
        model = AnalyticAxis
        fields = [
            "id",
            "code",
            "label",
            "axis_type",
            "axis_type_label",
            "parent",
            "is_active",
        ]


class AnalyticAccountSerializer(serializers.ModelSerializer):
    axis_code = serializers.CharField(source="axis.code", read_only=True)

    class Meta:
        model = AnalyticAccount
        fields = ["id", "axis", "axis_code", "code", "label", "is_active"]


class SiteSerializer(serializers.ModelSerializer):
    type_site_label = serializers.CharField(source="get_type_site_display", read_only=True)
    est_provisoire = serializers.BooleanField(read_only=True)
    confirme_par_email = serializers.CharField(source="confirme_par.email", read_only=True, default=None)

    class Meta:
        model = Site
        fields = [
            "id", "code", "libelle", "type_site", "type_site_label", "ville", "alias", "actif",
            "statut_valeur", "est_provisoire", "confirme_par_email", "confirme_le", "created_at",
        ]
        read_only_fields = ["statut_valeur", "confirme_le", "created_at"]

    def validate_code(self, value):
        code = value.strip().upper()
        qs = Site.objects.filter(code__iexact=code)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Ce code de site existe déjà.")
        return code
