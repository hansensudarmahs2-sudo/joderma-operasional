from django.contrib import admin

from .models import OwnerRequest, OwnerRequestNote


@admin.register(OwnerRequest)
class OwnerRequestAdmin(admin.ModelAdmin):
    list_display = ("title", "target_date", "created_by", "created_at")
    readonly_fields = ("created_at", "updated_at")


@admin.register(OwnerRequestNote)
class OwnerRequestNoteAdmin(admin.ModelAdmin):
    list_display = ("request", "author", "created_at")
