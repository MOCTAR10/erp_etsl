from django.contrib import admin

from .models import (
    ActionCorrective,
    ControleQualite,
    NonConformite,
    PvControle,
    QualificationSoudeur,
    QualiteSequence,
    Soudeur,
    WpsWpqr,
)


@admin.register(QualiteSequence)
class QualiteSequenceAdmin(admin.ModelAdmin):
    list_display = ["kind", "prefix", "padding", "next_number"]
    ordering = ["kind"]


@admin.register(Soudeur)
class SoudeurAdmin(admin.ModelAdmin):
    list_display = ["code", "nom", "prenoms", "matricule", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["code", "nom", "prenoms", "matricule"]


@admin.register(QualificationSoudeur)
class QualificationSoudeurAdmin(admin.ModelAdmin):
    list_display = [
        "code", "soudeur", "norme", "procede", "date_qualification",
        "date_validite", "statut",
    ]
    list_filter = ["norme", "procede", "statut"]
    search_fields = ["code", "soudeur__nom", "certificat"]


@admin.register(WpsWpqr)
class WpsWpqrAdmin(admin.ModelAdmin):
    list_display = ["code", "type", "procede", "materiau", "statut", "date_validation"]
    list_filter = ["type", "procede", "statut"]
    search_fields = ["code", "reference"]


@admin.register(ControleQualite)
class ControleQualiteAdmin(admin.ModelAdmin):
    list_display = [
        "code", "type_controle", "affaire", "ordre", "date_controle",
        "resultat", "statut",
    ]
    list_filter = ["type_controle", "organisme", "resultat", "statut"]
    search_fields = ["code", "organisme_libelle", "point_controle"]


@admin.register(NonConformite)
class NonConformiteAdmin(admin.ModelAdmin):
    list_display = ["code", "source", "gravite", "traitement", "statut", "date_decision"]
    list_filter = ["source", "gravite", "statut"]
    search_fields = ["code", "description"]


@admin.register(ActionCorrective)
class ActionCorrectiveAdmin(admin.ModelAdmin):
    list_display = ["code", "non_conformite", "type", "responsable", "echeance", "statut"]
    list_filter = ["type", "statut", "efficace"]
    search_fields = ["code", "description"]


@admin.register(PvControle)
class PvControleAdmin(admin.ModelAdmin):
    list_display = ["code", "intitule", "affaire", "date_pv", "statut", "resultat"]
    list_filter = ["statut", "resultat"]
    search_fields = ["code", "intitule", "reserve_motif"]