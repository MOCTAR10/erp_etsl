from django.contrib import admin

from .models import Document, DocumentType, Dossier, Version


@admin.register(DocumentType)
class DocumentTypeAdmin(admin.ModelAdmin):
    list_display = ["label", "code", "retention_years", "is_restricted_rh"]
    search_fields = ["label", "code"]


@admin.register(Dossier)
class DossierAdmin(admin.ModelAdmin):
    list_display = ["name", "parent", "created_at"]
    search_fields = ["name"]


class VersionInline(admin.TabularInline):
    model = Version
    extra = 0
    readonly_fields = ["id", "number", "file", "sha256", "size", "original_filename", "created_at"]
    can_delete = False


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ["title", "status", "type", "dossier", "counterparty", "sha256", "created_at"]
    list_filter = ["status", "type"]
    search_fields = ["title", "counterparty", "project", "reference", "sha256"]
    readonly_fields = ["id", "sha256", "current_version", "created_at", "updated_at"]
    inlines = [VersionInline]
