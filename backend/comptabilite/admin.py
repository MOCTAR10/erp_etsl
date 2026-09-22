from django.contrib import admin

from .models import (
    CompteBancaire,
    ComptabiliteSequence,
    ControleInterne,
    DeclarationTva,
    Engagement,
    LigneRapprochement,
    LigneReleve,
    Paiement,
    RapprochementBancaire,
    ReleveBancaire,
    TauxTva,
)


@admin.register(ComptabiliteSequence)
class ComptabiliteSequenceAdmin(admin.ModelAdmin):
    list_display = ("kind", "prefix", "padding", "next_number")
    list_editable = ("next_number",)


@admin.register(TauxTva)
class TauxTvaAdmin(admin.ModelAdmin):
    list_display = ("code", "label", "taux", "is_default", "is_active")
    list_filter = ("is_active", "is_default")


@admin.register(CompteBancaire)
class CompteBancaireAdmin(admin.ModelAdmin):
    list_display = ("code", "label", "banque", "is_active")
    list_filter = ("is_active",)


class LigneReleveInline(admin.TabularInline):
    model = LigneReleve
    extra = 0


@admin.register(ReleveBancaire)
class ReleveBancaireAdmin(admin.ModelAdmin):
    list_display = ("code", "compte_bancaire", "date_debut", "date_fin", "statut", "source")
    list_filter = ("statut", "source")
    inlines = [LigneReleveInline]


class LigneRapprochementInline(admin.TabularInline):
    model = LigneRapprochement
    extra = 0


@admin.register(RapprochementBancaire)
class RapprochementBancaireAdmin(admin.ModelAdmin):
    list_display = ("code", "compte_bancaire", "date", "statut")
    list_filter = ("statut",)
    inlines = [LigneRapprochementInline]


@admin.register(Engagement)
class EngagementAdmin(admin.ModelAdmin):
    list_display = ("code", "objet", "montant", "statut", "demande_par")
    list_filter = ("statut",)


@admin.register(Paiement)
class PaiementAdmin(admin.ModelAdmin):
    list_display = ("code", "sens", "mode", "montant", "date", "statut", "move")
    list_filter = ("statut", "sens", "mode")


@admin.register(DeclarationTva)
class DeclarationTvaAdmin(admin.ModelAdmin):
    list_display = ("code", "mois", "taux_tva", "net_a_payer", "statut")
    list_filter = ("statut",)


@admin.register(ControleInterne)
class ControleInterneAdmin(admin.ModelAdmin):
    list_display = ("code", "libelle", "reference_procedure", "statut", "date_prevue")
    list_filter = ("statut",)