from django.contrib import admin

from .models import AccountMove, AccountMoveLine, FiscalYear, Journal, Period, Sequence


class PeriodInline(admin.TabularInline):
    model = Period
    extra = 0


@admin.register(FiscalYear)
class FiscalYearAdmin(admin.ModelAdmin):
    list_display = ("year", "start_date", "end_date", "status")
    list_filter = ("status",)
    inlines = [PeriodInline]


@admin.register(Period)
class PeriodAdmin(admin.ModelAdmin):
    list_display = ("fiscal_year", "number", "start_date", "end_date", "status")
    list_filter = ("status", "fiscal_year")


@admin.register(Journal)
class JournalAdmin(admin.ModelAdmin):
    list_display = ("code", "label", "journal_type", "is_active")
    list_filter = ("journal_type", "is_active")


@admin.register(Sequence)
class SequenceAdmin(admin.ModelAdmin):
    list_display = ("journal", "prefix", "padding", "next_number")


class AccountMoveLineInline(admin.TabularInline):
    model = AccountMoveLine
    extra = 0


@admin.register(AccountMove)
class AccountMoveAdmin(admin.ModelAdmin):
    list_display = ("number", "date", "journal", "label", "status", "source")
    list_filter = ("status", "journal", "source")
    search_fields = ("number", "reference", "label")
    inlines = [AccountMoveLineInline]


@admin.register(AccountMoveLine)
class AccountMoveLineAdmin(admin.ModelAdmin):
    list_display = ("move", "account", "partner", "debit", "credit")
    list_filter = ("account__account_class",)
