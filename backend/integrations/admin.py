from django.contrib import admin

from .models import BatchRow, ImportBatch


class BatchRowInline(admin.TabularInline):
    model = BatchRow
    fields = ("row_number", "status", "data", "error_message")
    readonly_fields = fields
    extra = 0


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = ("connector", "status", "filename", "total_rows", "created_rows", "updated_rows", "error_rows", "created_at")
    list_filter = ("connector", "status")
    search_fields = ("filename", "file_hash")
    readonly_fields = [f.name for f in ImportBatch._meta.fields]
    inlines = [BatchRowInline]


@admin.register(BatchRow)
class BatchRowAdmin(admin.ModelAdmin):
    list_display = ("batch", "row_number", "status", "error_message")
    list_filter = ("status", "batch__connector")