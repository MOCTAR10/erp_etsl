from django.contrib import admin

from .models import (
    Budget,
    BudgetLigne,
    BudgetRevision,
    ClotureGestion,
    ControleGestionSequence,
)


@admin.register(ControleGestionSequence)
class ControleGestionSequenceAdmin(admin.ModelAdmin):
    list_display = ("kind", "prefix", "padding", "next_number")
    list_editable = ("next_number",)


class BudgetLigneInline(admin.TabularInline):
    model = BudgetLigne
    extra = 0


class BudgetRevisionInline(admin.TabularInline):
    model = BudgetRevision
    extra = 0
    readonly_fields = ("code", "numero", "ancien_montant", "statut")


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ("code", "label", "type_budget", "fiscal_year", "montant", "statut")
    list_filter = ("type_budget", "statut", "fiscal_year")
    inlines = [BudgetLigneInline, BudgetRevisionInline]


@admin.register(BudgetRevision)
class BudgetRevisionAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "budget",
        "numero",
        "date_revision",
        "ancien_montant",
        "nouveau_montant",
        "statut",
    )
    list_filter = ("statut",)


@admin.register(ClotureGestion)
class ClotureGestionAdmin(admin.ModelAdmin):
    list_display = ("code", "period", "date_cloture", "statut", "conforme_j4")
    list_filter = ("statut",)