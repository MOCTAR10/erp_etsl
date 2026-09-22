from django.contrib import admin

from .models import Actif, Inspection, MaintenanceSequence, OrdreTravail


@admin.register(MaintenanceSequence)
class MaintenanceSequenceAdmin(admin.ModelAdmin):
    list_display = ["kind", "prefix", "padding", "next_number"]
    ordering = ["kind"]


@admin.register(Actif)
class ActifAdmin(admin.ModelAdmin):
    list_display = [
        "code", "designation", "categorie", "fabricant", "site", "statut",
        "compteur_type", "compteur_value", "is_global_rental",
    ]
    list_filter = ["categorie", "statut", "compteur_type", "is_global_rental"]
    search_fields = ["code", "designation", "numero_serie", "fabricant"]


@admin.register(OrdreTravail)
class OrdreTravailAdmin(admin.ModelAdmin):
    list_display = ["code", "actif", "type_ot", "priorite", "date_demande", "statut"]
    list_filter = ["type_ot", "priorite", "statut"]
    search_fields = ["code", "actif__code", "actif__designation", "description"]


@admin.register(Inspection)
class InspectionAdmin(admin.ModelAdmin):
    list_display = [
        "code", "actif", "type_inspection", "date_inspection", "prochaine_inspection",
        "resultat", "statut",
    ]
    list_filter = ["type_inspection", "resultat", "statut"]
    search_fields = ["code", "actif__code", "actif__designation", "constat"]