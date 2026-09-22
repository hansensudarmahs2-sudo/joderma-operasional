from django.contrib import admin

from .models import ChecklistFollowup, ChecklistResponse, ChecklistRun, ChecklistTemplate, ChecklistTemplateItem


class ItemInline(admin.TabularInline):
    model = ChecklistTemplateItem
    extra = 3


@admin.register(ChecklistTemplate)
class TemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "area", "session", "audience_key", "version", "active")
    list_filter = ("area", "session", "active")
    inlines = [ItemInline]


@admin.register(ChecklistTemplateItem)
class TemplateItemAdmin(admin.ModelAdmin):
    list_display = ("label", "template", "input_type", "performer_roles", "verifier_roles")


admin.site.register([ChecklistRun, ChecklistResponse, ChecklistFollowup])
