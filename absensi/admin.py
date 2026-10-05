"""Django admin untuk absensi.

Di sini koreksi cap dilakukan sampai Tahap 4 (alur koreksi dari halaman) dibangun,
jadi di sinilah keputusan D4 ditegakkan: yang boleh mengubah cap — dan karenanya
skor dan lembur seseorang — hanya Direktur Operasional, Direktur Utama, dan Owner.
Admin sistem boleh mengubah jadwal jaga, tetapi tidak boleh mengoreksi absen.

`AttendanceImport` sengaja tidak bisa diubah sama sekali: ia catatan apa yang pernah
diimpor, bukan data yang boleh dirapikan belakangan.
"""
from django.contrib import admin

from core.permissions import can_correct_absensi

from .models import AttendanceDevice, AttendanceImport, AttendancePunch


class KoreksiAbsensiMixin:
    """Tambah, ubah, dan hapus hanya untuk yang boleh mengoreksi absen (D4)."""

    def has_add_permission(self, request):
        return can_correct_absensi(request.user)

    def has_change_permission(self, request, obj=None):
        return can_correct_absensi(request.user)

    def has_delete_permission(self, request, obj=None):
        return can_correct_absensi(request.user)


@admin.register(AttendanceDevice)
class AttendanceDeviceAdmin(KoreksiAbsensiMixin, admin.ModelAdmin):
    # Mengubah pemilik satu ID memindahkan seluruh cap bulan itu ke orang lain, jadi
    # haknya sama dengan mengoreksi cap, bukan hak admin biasa.
    list_display = ("device_uid", "device_label", "user", "recording_only", "active", "note")
    list_filter = ("active", "recording_only")
    search_fields = ("device_uid", "device_label", "user__username", "user__display_name")


@admin.register(AttendanceImport)
class AttendanceImportAdmin(admin.ModelAdmin):
    list_display = (
        "file_name", "period_start", "period_end", "imported_at", "imported_by",
        "rows_read", "punches_created", "punches_skipped",
    )
    date_hierarchy = "imported_at"
    readonly_fields = tuple(f.name for f in AttendanceImport._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AttendancePunch)
class AttendancePunchAdmin(KoreksiAbsensiMixin, admin.ModelAdmin):
    list_display = ("shift_date", "user", "occurred_at", "kind", "source", "device", "note")
    list_filter = ("kind", "source")
    date_hierarchy = "shift_date"
    search_fields = ("user__username", "user__display_name")
