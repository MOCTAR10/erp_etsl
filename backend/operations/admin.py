from django.contrib import admin

from .models import (
    GammeOperatoire,
    GammeOperation,
    OrdreFabrication,
    PointageChantier,
    SituationTravaux,
)


@admin.register(GammeOperatoire)
class GammeAdmin(admin.ModelAdmin):
    list_display = ("code", "label", "status", "is_global_rental")
    list_filter = ("status", "is_global_rental")


@admin.register(GammeOperation)
class GammeOperationAdmin(admin.ModelAdmin):
    list_display = ("gamme", "sequence", "label", "poste", "planned_hours")


@admin.register(OrdreFabrication)
class OrdreFabricationAdmin(admin.ModelAdmin):
    list_display = ("code", "label", "affaire", "scope", "status", "planned_start")
    list_filter = ("status", "scope")


@admin.register(PointageChantier)
class PointageChantierAdmin(admin.ModelAdmin):
    list_display = ("code", "ordre", "worker_name", "date", "hours", "status")
    list_filter = ("status", "date")


@admin.register(SituationTravaux)
class SituationTravauxAdmin(admin.ModelAdmin):
    list_display = ("code", "label", "affaire", "amount", "progress", "status")
    list_filter = ("status",)