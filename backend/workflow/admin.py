from django.contrib import admin

from .models import Circuit, CircuitStep, Task, TaskComment


class CircuitStepInline(admin.TabularInline):
    model = CircuitStep
    extra = 0


@admin.register(Circuit)
class CircuitAdmin(admin.ModelAdmin):
    list_display = ["code", "label", "max_days", "is_active"]
    inlines = [CircuitStepInline]


@admin.register(CircuitStep)
class CircuitStepAdmin(admin.ModelAdmin):
    list_display = ["circuit", "order", "name", "actor_role", "max_days"]
    list_filter = ["circuit", "actor_role"]
    ordering = ["circuit", "order"]


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ["document", "circuit", "step", "assigned_to", "status", "due_date"]
    list_filter = ["status", "circuit"]
    search_fields = ["document__title", "assigned_to__email"]


@admin.register(TaskComment)
class TaskCommentAdmin(admin.ModelAdmin):
    list_display = ["task", "author", "created_at"]
    search_fields = ["text", "author__email"]
