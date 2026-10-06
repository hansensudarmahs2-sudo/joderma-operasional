from django.contrib import admin

from .models import Parameter, PergerakanBulanan, PosisiStok, Produk, StatusPeriode, Unggahan


@admin.register(Produk)
class ProdukAdmin(admin.ModelAdmin):
    list_display = ("nama", "dosis", "kategori", "produksi_sendiri", "non_stok", "aktif")
    search_fields = ("nama", "kunci")
    list_filter = ("produksi_sendiri", "non_stok", "aktif")


@admin.register(Unggahan)
class UnggahanAdmin(admin.ModelAdmin):
    list_display = ("waktu", "jenis", "clinic", "tahun", "bulan", "tanggal", "jumlah_baris", "diunggah_oleh")
    list_filter = ("jenis", "clinic")


@admin.register(StatusPeriode)
class StatusPeriodeAdmin(admin.ModelAdmin):
    list_display = ("clinic", "tahun", "bulan", "lengkap", "jumlah_baris", "diperbarui")


admin.site.register(PosisiStok)
admin.site.register(PergerakanBulanan)
admin.site.register(Parameter)
