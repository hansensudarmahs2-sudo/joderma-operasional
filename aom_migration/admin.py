from django.contrib import admin

from .models import LegacyActor, LegacyArchive, LegacyIdMap, LegacyImportBatch


@admin.register(LegacyImportBatch)
class LegacyImportBatchAdmin(admin.ModelAdmin):
    list_display = ("name", "source_label", "imported_at", "manifest_checksum")
    readonly_fields = ("imported_at",)


@admin.register(LegacyIdMap)
class LegacyIdMapAdmin(admin.ModelAdmin):
    list_display = ("source_model", "legacy_id", "target_model", "target_id", "batch")
    list_filter = ("source_model", "target_model")
    search_fields = ("legacy_id",)


@admin.register(LegacyActor)
class LegacyActorAdmin(admin.ModelAdmin):
    list_display = ("label", "mapped_user")
    search_fields = ("label",)


@admin.register(LegacyArchive)
class LegacyArchiveAdmin(admin.ModelAdmin):
    list_display = ("source_model", "legacy_id", "batch", "imported_at")
    list_filter = ("source_model",)
    search_fields = ("legacy_id",)
