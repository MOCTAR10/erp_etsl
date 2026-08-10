from django.contrib import admin

from .models import (
    AuditLog,
    Document,
    DocumentType,
    Dossier,
    DocumentAccess,
    DossierAccess,
    Version,
)


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


@admin.register(DocumentAccess)
class DocumentAccessAdmin(admin.ModelAdmin):
    list_display = ["document", "user", "permission", "granted_by", "created_at"]
    list_filter = ["permission"]
    search_fields = ["user__email", "document__title"]


@admin.register(DossierAccess)
class DossierAccessAdmin(admin.ModelAdmin):
    list_display = ["dossier", "user", "permission", "granted_by", "created_at"]
    list_filter = ["permission"]
    search_fields = ["user__email", "dossier__name"]


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["created_at", "user", "action", "object_type", "object_id", "ip_address"]
    list_filter = ["action", "object_type"]
    search_fields = ["object_id", "user__email"]
    readonly_fields = ["id", "created_at"]
    date_hierarchy = "created_at"
