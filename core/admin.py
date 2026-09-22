from django.contrib import admin

from .models import (
    ActionItem,
    Attachment,
    Clinic,
    ClinicConfig,
    Holiday,
    OperationalDay,
    TaskAssignment,
    TaskAudienceSnapshot,
    TaskEvent,
)

admin.site.site_header = "JoDerma Staff Ops — Administrasi"
admin.site.site_title = "JoDerma Staff Ops"
admin.site.index_title = "Konfigurasi dan data referensi"

admin.site.register(
    [
        Clinic,
        Holiday,
        ClinicConfig,
        OperationalDay,
        ActionItem,
        TaskAudienceSnapshot,
        TaskAssignment,
        TaskEvent,
        Attachment,
    ]
)
