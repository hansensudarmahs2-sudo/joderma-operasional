from django.contrib import admin

from .models import Laporan, LaporanUpdate, Masukan, MasukanPublication


@admin.register(Laporan)
class LaporanAdmin(admin.ModelAdmin):
    list_display = ("id", "clinic", "visibility", "status", "title", "created_by", "created_at")
    list_filter = ("clinic", "visibility", "status")


admin.site.register(LaporanUpdate)


@admin.register(Masukan)
class MasukanAdmin(admin.ModelAdmin):
    list_display = ("id", "clinic", "title", "created_by", "created_at", "archived_at")
    list_filter = ("clinic",)


admin.site.register(MasukanPublication)
