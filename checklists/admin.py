from django.contrib import admin

from .models import ChecklistResponse, ChecklistRun, ChecklistTemplate, ChecklistTemplateItem


class ItemInline(admin.TabularInline):
    model = ChecklistTemplateItem
    extra = 3


@admin.register(ChecklistTemplate)
class TemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "area", "version", "active")
    list_filter = ("area", "active")
    inlines = [ItemInline]


admin.site.register([ChecklistRun, ChecklistResponse])
