from django.contrib import admin

from .models import AuditCheck, AuditItem, AuditPoint, DirectorNote


class AuditPointInline(admin.TabularInline):
    model = AuditPoint
    extra = 0


@admin.register(AuditItem)
class AuditItemAdmin(admin.ModelAdmin):
    list_display = ("cadence", "number", "title", "source_label", "pic_function", "active")
    list_filter = ("cadence", "active")
    inlines = [AuditPointInline]


@admin.register(AuditCheck)
class AuditCheckAdmin(admin.ModelAdmin):
    list_display = ("period_start", "clinic", "item", "result", "direct", "checked_by")
    list_filter = ("result", "clinic", "item__cadence")
    readonly_fields = ("item_snapshot", "checked_at", "updated_at")


@admin.register(DirectorNote)
class DirectorNoteAdmin(admin.ModelAdmin):
    list_display = ("__str__", "author", "clinic", "source", "created_at", "archived_at")
    list_filter = ("source",)
