from django.contrib import admin

from .models import (
    ArticleStock,
    CertificatMatiere,
    Depot,
    Inventaire,
    InventaireLigne,
    LotMatiere,
    MouvementStock,
    StockQuant,
    StocksSequence,
)


@admin.register(StocksSequence)
class StocksSequenceAdmin(admin.ModelAdmin):
    list_display = ("kind", "prefix", "padding", "next_number")
    search_fields = ("kind", "prefix")
    ordering = ("kind",)


@admin.register(Depot)
class DepotAdmin(admin.ModelAdmin):
    list_display = ("code", "label", "site", "responsable", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "label", "site")


@admin.register(ArticleStock)
class ArticleStockAdmin(admin.ModelAdmin):
    list_display = ("article", "methode", "seuil_minimal", "gestion_lots", "is_active")
    list_filter = ("methode", "gestion_lots", "is_active")
    autocomplete_fields = ("article",)


@admin.register(LotMatiere)
class LotMatiereAdmin(admin.ModelAdmin):
    list_display = (
        "code", "article", "numero_lot", "date_reception",
        "quantite_initiale", "quantite_restante", "statut",
    )
    list_filter = ("statut",)
    search_fields = ("code", "numero_lot", "article__label")


@admin.register(CertificatMatiere)
class CertificatMatiereAdmin(admin.ModelAdmin):
    list_display = ("code", "lot", "type", "numero_certificat", "conforme")
    list_filter = ("type", "conforme")
    search_fields = ("code", "numero_certificat", "lot__code")


@admin.register(StockQuant)
class StockQuantAdmin(admin.ModelAdmin):
    list_display = ("depot", "article", "lot", "quantity", "stock_value")
    search_fields = ("depot__code", "article__label")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MouvementStock)
class MouvementStockAdmin(admin.ModelAdmin):
    list_display = (
        "code", "date", "type_mouvement", "article", "quantite",
        "prix_unitaire", "source", "destination", "lot", "executed"
    )
    list_filter = ("type_mouvement", "executed", "date")
    search_fields = ("code", "document_reference", "article__label")


class InventaireLigneInline(admin.TabularInline):
    model = InventaireLigne
    extra = 0


@admin.register(Inventaire)
class InventaireAdmin(admin.ModelAdmin):
    list_display = ("code", "depot", "date", "statut", "responsable")
    list_filter = ("statut", "date")
    inlines = [InventaireLigneInline]