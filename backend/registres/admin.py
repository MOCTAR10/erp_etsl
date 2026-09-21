from django.contrib import admin

from .models import Registre, RegistreEntry


class RegistreEntryInline(admin.TabularInline):
    model = RegistreEntry
    extra = 0


@admin.register(Registre)
class RegistreAdmin(admin.ModelAdmin):
    list_display = ("label", "kind", "year", "is_active")
    list_filter = ("kind", "year", "is_active")
    search_fields = ("label",)
    inlines = [RegistreEntryInline]


@admin.register(RegistreEntry)
class RegistreEntryAdmin(admin.ModelAdmin):
    list_display = ("registre", "number", "entry_date")
    list_filter = ("registre__kind", "entry_date")
    search_fields = ("number",)
