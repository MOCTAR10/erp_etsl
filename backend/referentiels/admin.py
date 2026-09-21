from django.contrib import admin

from .models import (
    Account,
    AnalyticAccount,
    AnalyticAxis,
    Annexe,
    Article,
    Currency,
    Partner,
    UnitOfMeasure,
)


@admin.register(Annexe)
class AnnexeAdmin(admin.ModelAdmin):
    list_display = ("code", "label", "kind", "domain", "is_active")
    list_filter = ("kind", "domain", "is_active")
    search_fields = ("code", "label")
    ordering = ("domain", "kind", "code")


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ("code", "label", "symbol", "decimals", "is_active")
    search_fields = ("code", "label")


@admin.register(UnitOfMeasure)
class UnitOfMeasureAdmin(admin.ModelAdmin):
    list_display = ("code", "label", "is_active")
    search_fields = ("code", "label")


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("code", "label", "account_class", "account_type", "is_active")
    list_filter = ("account_class", "account_type", "is_active")
    search_fields = ("code", "label")


@admin.register(Partner)
class PartnerAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "kind", "is_global_rental", "is_active")
    list_filter = ("kind", "is_global_rental", "is_active")
    search_fields = ("code", "name", "tax_id")


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ("code", "label", "article_type", "unit", "is_stockable", "is_active")
    list_filter = ("article_type", "is_stockable", "is_active")
    search_fields = ("code", "label")


@admin.register(AnalyticAxis)
class AnalyticAxisAdmin(admin.ModelAdmin):
    list_display = ("code", "label", "axis_type", "is_active")
    list_filter = ("axis_type", "is_active")


@admin.register(AnalyticAccount)
class AnalyticAccountAdmin(admin.ModelAdmin):
    list_display = ("axis", "code", "label", "is_active")
    list_filter = ("axis", "is_active")
    search_fields = ("code", "label")
