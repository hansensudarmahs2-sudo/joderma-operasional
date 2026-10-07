from django.contrib import admin

from .models import Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "leader", "target_date", "created_by", "created_at")
    list_filter = ("status",)
    readonly_fields = ("created_at", "updated_at")
