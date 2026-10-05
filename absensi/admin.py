from django.contrib import admin

from .models import AttendanceDevice, AttendanceImport, AttendancePunch


@admin.register(AttendanceDevice)
class AttendanceDeviceAdmin(admin.ModelAdmin):
    list_display = ("device_uid", "device_label", "user", "active", "note")
    list_filter = ("active",)
    search_fields = ("device_uid", "device_label", "user__username", "user__display_name")


@admin.register(AttendanceImport)
class AttendanceImportAdmin(admin.ModelAdmin):
    list_display = (
        "file_name", "period_start", "period_end", "imported_at", "imported_by",
        "rows_read", "punches_created", "punches_skipped",
    )
    date_hierarchy = "imported_at"
    readonly_fields = tuple(f.name for f in AttendanceImport._meta.fields)


@admin.register(AttendancePunch)
class AttendancePunchAdmin(admin.ModelAdmin):
    list_display = ("shift_date", "user", "occurred_at", "kind", "source", "device", "note")
    list_filter = ("kind", "source")
    date_hierarchy = "shift_date"
    search_fields = ("user__username", "user__display_name")
