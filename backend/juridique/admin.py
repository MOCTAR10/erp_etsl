from django.contrib import admin

from .models import (
    Assurance,
    Caution,
    Contentieux,
    Convention,
    Courrier,
    DossierGlobalRental,
    JuridiqueSequence,
    Reunion,
)


@admin.register(JuridiqueSequence)
class JuridiqueSequenceAdmin(admin.ModelAdmin):
    list_display = ("kind", "prefix", "padding", "next_number")
    list_editable = ("next_number",)


@admin.register(Courrier)
class CourrierAdmin(admin.ModelAdmin):
    list_display = ("code", "sens", "type", "objet", "tiers", "date_courrier", "statut")
    list_filter = ("sens", "type", "statut")


@admin.register(Convention)
class ConventionAdmin(admin.ModelAdmin):
    list_display = ("code", "type", "titre", "partenaire", "date_fin", "statut")
    list_filter = ("type", "statut")


@admin.register(Contentieux)
class ContentieuxAdmin(admin.ModelAdmin):
    list_display = ("code", "nature", "objet", "partie_adverse", "statut", "phase")
    list_filter = ("nature", "statut", "phase")


@admin.register(Caution)
class CautionAdmin(admin.ModelAdmin):
    list_display = ("code", "type", "beneficiaire", "montant", "date_echeance", "statut")
    list_filter = ("type", "statut")


@admin.register(Assurance)
class AssuranceAdmin(admin.ModelAdmin):
    list_display = ("code", "type", "assureur", "numero_police", "date_echeance", "statut")
    list_filter = ("type", "statut")


@admin.register(Reunion)
class ReunionAdmin(admin.ModelAdmin):
    list_display = ("code", "type", "objet", "date_reunion", "statut")
    list_filter = ("type", "statut")


@admin.register(DossierGlobalRental)
class DossierGlobalRentalAdmin(admin.ModelAdmin):
    list_display = ("code", "partenaire_gr", "objet", "signe_618", "date_fin", "statut")
    list_filter = ("statut", "signe_618")