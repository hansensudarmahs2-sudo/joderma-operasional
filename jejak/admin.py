from django.contrib import admin

from .models import KnownDevice, PresenceStamp


@admin.register(KnownDevice)
class KnownDeviceAdmin(admin.ModelAdmin):
    list_display = ("name", "ip_address", "clinic", "is_clinic_device")


@admin.register(PresenceStamp)
class PresenceStampAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "event", "clinic", "confidence", "ip_address", "distance_m")
    list_filter = ("event", "confidence", "clinic")
