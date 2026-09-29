from django.contrib import admin

from .models import DutyAssignment, DutyPortion, DutyRoster


@admin.register(DutyRoster)
class DutyRosterAdmin(admin.ModelAdmin):
    list_display = ("date", "user", "home_clinic", "status", "clinic")
    list_filter = ("status", "home_clinic", "clinic")
    date_hierarchy = "date"
    search_fields = ("user__username", "user__display_name")


@admin.register(DutyPortion)
class DutyPortionAdmin(admin.ModelAdmin):
    list_display = ("name", "clinic", "group", "pic_function", "people", "weekdays", "active", "sort_order")
    list_filter = ("clinic", "group", "active")


@admin.register(DutyAssignment)
class DutyAssignmentAdmin(admin.ModelAdmin):
    list_display = ("date", "clinic", "portion", "user", "source")
    list_filter = ("clinic", "source", "portion__group")
    date_hierarchy = "date"
