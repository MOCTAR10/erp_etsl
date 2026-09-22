from django.contrib import admin

from .models import (
    AffectationParc,
    DemandeMobilisation,
    EquipementParc,
    LectureCompteur,
    LocationGR,
    LogistiqueSequence,
)


@admin.register(LogistiqueSequence)
class LogistiqueSequenceAdmin(admin.ModelAdmin):
    list_display = ["kind", "prefix", "padding", "next_number"]


@admin.register(EquipementParc)
class EquipementParcAdmin(admin.ModelAdmin):
    list_display = [
        "code", "label", "categorie", "statut", "compteur_type", "compteur_value",
        "is_global_rental", "site",
    ]
    list_filter = ["categorie", "statut", "is_global_rental"]
    search_fields = ["code", "label", "registration"]


@admin.register(DemandeMobilisation)
class DemandeMobilisationAdmin(admin.ModelAdmin):
    list_display = ["code", "label", "departement", "date_debut", "date_fin", "statut"]
    list_filter = ["statut"]
    search_fields = ["code", "label", "departement"]


@admin.register(AffectationParc)
class AffectationParcAdmin(admin.ModelAdmin):
    list_display = ["code", "equipement", "affaire", "date_debut", "date_fin", "statut"]
    list_filter = ["statut"]
    search_fields = ["code", "equipement__code", "equipement__label"]


@admin.register(LocationGR)
class LocationGRAdmin(admin.ModelAdmin):
    list_display = [
        "code", "equipement", "partenaire", "affaire", "periodicite", "tarif",
        "montant_estime", "statut",
    ]
    list_filter = ["statut", "periodicite", "imputation_618"]
    search_fields = ["code", "equipement__code", "partenaire__name", "reference_bc"]


@admin.register(LectureCompteur)
class LectureCompteurAdmin(admin.ModelAdmin):
    list_display = ["code", "location", "date", "valeur", "type_lecture", "source"]
    list_filter = ["type_lecture", "source"]
    search_fields = ["code", "location__code"]