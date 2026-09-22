from django.contrib import admin

from .models import (
    ActionHse,
    BordereauDechet,
    Epi,
    EquipementAtex,
    EvaluationRisque,
    FormationSecurite,
    HseSequence,
    Incident,
    PermisTravail,
)


@admin.register(HseSequence)
class HseSequenceAdmin(admin.ModelAdmin):
    list_display = ["kind", "prefix", "padding", "next_number"]
    ordering = ["kind"]


@admin.register(PermisTravail)
class PermisTravailAdmin(admin.ModelAdmin):
    list_display = ["code", "type_permis", "emplacement", "date_debut", "date_fin", "statut"]
    list_filter = ["type_permis", "statut"]
    search_fields = ["code", "emplacement", "description"]


@admin.register(EvaluationRisque)
class EvaluationRisqueAdmin(admin.ModelAdmin):
    list_display = ["code", "lieux", "activite", "probabilite", "gravite", "statut"]
    list_filter = ["statut"]
    search_fields = ["code", "lieux", "activite", "description"]


@admin.register(EquipementAtex)
class EquipementAtexAdmin(admin.ModelAdmin):
    list_display = [
        "code", "designation", "zone_atex", "certificat",
        "date_expiration_certificat", "statut",
    ]
    list_filter = ["zone_atex", "statut"]
    search_fields = ["code", "designation", "certificat", "numero_serie"]


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ["code", "type_incident", "gravite", "date_evenement", "lieu", "statut"]
    list_filter = ["type_incident", "gravite", "statut", "archive"]
    search_fields = ["code", "lieu", "description"]


@admin.register(ActionHse)
class ActionHseAdmin(admin.ModelAdmin):
    list_display = ["code", "incident", "risque", "type", "responsable", "echeance", "statut"]
    list_filter = ["type", "statut"]
    search_fields = ["code", "description"]


@admin.register(FormationSecurite)
class FormationSecuriteAdmin(admin.ModelAdmin):
    list_display = ["code", "type_session", "theme", "formateur", "date_session", "statut"]
    list_filter = ["type_session", "statut"]
    search_fields = ["code", "theme", "formateur"]


@admin.register(Epi)
class EpiAdmin(admin.ModelAdmin):
    list_display = ["code", "type_epi", "designation", "beneficiaire", "date_dotation", "statut"]
    list_filter = ["type_epi", "statut"]
    search_fields = ["code", "designation", "taille"]


@admin.register(BordereauDechet)
class BordereauDechetAdmin(admin.ModelAdmin):
    list_display = ["code", "type_dechet", "quantite", "unite", "transporteur", "statut"]
    list_filter = ["type_dechet", "unite", "statut"]
    search_fields = ["code", "numero_bsd", "destination"]