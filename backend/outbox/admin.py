from django.contrib import admin

from .models import OutboxEvent


@admin.register(OutboxEvent)
class OutboxEventAdmin(admin.ModelAdmin):
    list_display = ("topic", "status", "attempt_count", "created_at", "delivered_at")
    list_filter = ("status", "topic")
    readonly_fields = [f.name for f in OutboxEvent._meta.fields]