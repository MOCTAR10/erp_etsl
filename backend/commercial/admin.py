from django.contrib import admin

from .models import (
    Affaire,
    ClientProfile,
    Contract,
    ContractService,
    Estimate,
    EstimateLine,
    EstimateOption,
    Milestone,
    Opportunity,
    SoumissionEvent,
    TenderReview,
)


@admin.register(ClientProfile)
class ClientProfileAdmin(admin.ModelAdmin):
    list_display = ("partner", "segment", "scoring", "origin", "is_active")
    list_filter = ("segment", "origin")


@admin.register(Opportunity)
class OpportunityAdmin(admin.ModelAdmin):
    list_display = ("code", "subject", "client", "stage", "amount", "probability", "owner")
    list_filter = ("stage", "origin")


@admin.register(Estimate)
class EstimateAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "client", "status", "total", "valid_until")
    list_filter = ("status", "is_global_rental")


@admin.register(EstimateOption)
class EstimateOptionAdmin(admin.ModelAdmin):
    list_display = ("label", "estimate", "amount", "is_selected")


@admin.register(EstimateLine)
class EstimateLineAdmin(admin.ModelAdmin):
    list_display = ("label", "estimate", "quantity", "unit_price", "price_total")


@admin.register(TenderReview)
class TenderReviewAdmin(admin.ModelAdmin):
    list_display = ("tender_ref", "client", "bid_deadline", "review_status")
    list_filter = ("review_status",)


@admin.register(Affaire)
class AffaireAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "client", "affaire_type", "status", "contract_amount")
    list_filter = ("status", "affaire_type")


@admin.register(Milestone)
class MilestoneAdmin(admin.ModelAdmin):
    list_display = ("code", "label", "affaire", "planned_date", "status")
    list_filter = ("status",)


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ("code", "client", "profile", "start_date", "end_date", "status")
    list_filter = ("profile", "status")


@admin.register(ContractService)
class ContractServiceAdmin(admin.ModelAdmin):
    list_display = ("label", "contract", "kind", "price", "frequency")


@admin.register(SoumissionEvent)
class SoumissionEventAdmin(admin.ModelAdmin):
    list_display = ("kind", "happened_at", "client", "opportunity", "author")
    list_filter = ("kind",)