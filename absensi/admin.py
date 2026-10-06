"""Django admin untuk absensi.

Keputusan D4 ditegakkan di sini juga: yang boleh mengubah cap — dan karenanya skor dan
lembur seseorang — hanya Direktur Operasional, Direktur Utama, dan Owner. Admin sistem
boleh mengubah jadwal jaga, tetapi tidak boleh mengoreksi absen.

Sejak Tahap 4 koreksi sehari-hari dikerjakan dari halaman (`absensi:koreksi`, tombol
pada baris "Perlu dicek"), yang lebih aman untuk itu: ia meminta jam dinding pada hari
kerja lalu menghitung sendiri waktu mutlaknya, sedangkan di sini `occurred_at` diisi
langsung — pulang 00.28 untuk hari kerja tanggal 4 harus ditulis sebagai tanggal 5,
dan salah di situ tidak menghasilkan error, hanya angka yang keliru.

Admin tetap ada untuk yang tidak dilayani halaman itu: memindahkan pemilik satu ID
mesin, dan menghapus cap mesin (halaman hanya menghapus cap manual, karena cap mesin
adalah bukti apa yang dicatat alat).

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
