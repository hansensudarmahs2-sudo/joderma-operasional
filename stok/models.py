"""Modul Stok Apotek: data dari ekspor Omnicare dan parameter perhitungan.

Spesifikasi: `docs/stok-apotek.md`. Semua status, buffer, dan saran
dihitung saat halaman dibuka (`stok/hitung.py`), jadi tidak ada tabel hasil.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from core.models import Clinic


class JenisFile(models.TextChoices):
    DAFTAR_PRODUK = "DAFTAR_PRODUK", "Daftar Produk"
    TINGKAT_PERSEDIAAN = "TINGKAT_PERSEDIAAN", "Tingkat Persediaan"
    PERGERAKAN = "PERGERAKAN", "Ringkasan Pergerakan Stok"


class Produk(models.Model):
    """Satu produk Omnicare. Dua laporan lain dicocokkan lewat `kunci` (nama + dosis)."""

    omnicare_id = models.PositiveIntegerField("ID Omnicare", unique=True)
    nama = models.CharField(max_length=200)
    dosis = models.CharField(max_length=60, blank=True)
    kunci = models.CharField("kunci pencocokan", max_length=260, unique=True)
    generik = models.CharField("nama generik", max_length=200, blank=True)
    pabrikan = models.CharField(max_length=120, blank=True)
    kategori = models.CharField(max_length=80, blank=True)
    sediaan = models.CharField(max_length=60, blank=True)
    satuan = models.CharField(max_length=40, blank=True)
    harga_modal = models.FloatField(default=0)
    harga_jual = models.FloatField(default=0)
    min_omnicare = models.FloatField("MIN Omnicare", default=0)
    max_omnicare = models.FloatField("MAX Omnicare", default=0)
    non_stok = models.BooleanField("non-stok (racik/jasa)", default=False)
    aktif = models.BooleanField(default=True)
    diperbarui = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "produk"
        verbose_name_plural = "produk"
        ordering = ("nama",)

    def __str__(self) -> str:
        return f"{self.nama} {self.dosis}".strip()

    @property
    def produksi_sendiri(self) -> bool:
        return self.pabrikan.strip().lower() in {"dryn", "joderma"}


class ProdukAlias(models.Model):
    """Kunci lama bila nama produk diubah di Omnicare, agar riwayat tetap tersambung."""

    produk = models.ForeignKey(Produk, on_delete=models.CASCADE, related_name="alias")
    kunci = models.CharField(max_length=260, unique=True)

    class Meta:
        verbose_name = "alias produk"
        verbose_name_plural = "alias produk"

    def __str__(self) -> str:
        return self.kunci


class Unggahan(models.Model):
    jenis = models.CharField(max_length=24, choices=JenisFile.choices)
    clinic = models.ForeignKey(Clinic, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    tahun = models.PositiveSmallIntegerField(null=True, blank=True)
    bulan = models.PositiveSmallIntegerField(null=True, blank=True)
    tanggal = models.DateField("tanggal data", null=True, blank=True)
    judul = models.CharField("judul laporan", max_length=200, blank=True)
    nama_file = models.CharField(max_length=255)
    file = models.FileField(upload_to="stok/%Y/%m/")
    jumlah_baris = models.PositiveIntegerField(default=0)
    jumlah_cocok = models.PositiveIntegerField(default=0)
    peringatan = models.JSONField(default=list, blank=True)
    diunggah_oleh = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    waktu = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "unggahan Omnicare"
        verbose_name_plural = "unggahan Omnicare"
        ordering = ("-waktu", "-pk")

    def __str__(self) -> str:
        return f"{self.get_jenis_display()} · {self.nama_file}"


class PosisiStok(models.Model):
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name="+")
    produk = models.ForeignKey(Produk, on_delete=models.CASCADE, related_name="posisi")
    tanggal = models.DateField()
    stok = models.FloatField(default=0)
    nilai_modal = models.FloatField(default=0)
    unggahan = models.ForeignKey(Unggahan, on_delete=models.SET_NULL, null=True, related_name="+")

    class Meta:
        verbose_name = "posisi stok"
        verbose_name_plural = "posisi stok"
        constraints = [
            models.UniqueConstraint(fields=["clinic", "produk", "tanggal"], name="uniq_posisi_stok")
        ]


class PergerakanBulanan(models.Model):
    """Satu baris laporan pergerakan. Barang keluar bertanda minus, sama seperti Omnicare."""

    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name="+")
    produk = models.ForeignKey(Produk, on_delete=models.CASCADE, related_name="pergerakan")
    tahun = models.PositiveSmallIntegerField()
    bulan = models.PositiveSmallIntegerField()
    stok_awal = models.FloatField(default=0)
    diterima = models.FloatField(default=0)
    dijual = models.FloatField(default=0)
    dipakai = models.FloatField(default=0)
    fabrikasi = models.FloatField(default=0)
    retur_jual = models.FloatField(default=0)
    retur_beli = models.FloatField(default=0)
    rusak = models.FloatField(default=0)
    mutasi = models.FloatField(default=0)
    penyesuaian = models.FloatField(default=0)
    gabung = models.FloatField(default=0)
    stok_akhir = models.FloatField(default=0)
    unggahan = models.ForeignKey(Unggahan, on_delete=models.SET_NULL, null=True, related_name="+")

    class Meta:
        verbose_name = "pergerakan bulanan"
        verbose_name_plural = "pergerakan bulanan"
        constraints = [
            models.UniqueConstraint(fields=["clinic", "produk", "tahun", "bulan"], name="uniq_pergerakan")
        ]

    @property
    def pemakaian(self) -> float:
        return -(self.dijual + self.dipakai + self.retur_jual + min(self.fabrikasi, 0))


class StatusPeriode(models.Model):
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name="+")
    tahun = models.PositiveSmallIntegerField()
    bulan = models.PositiveSmallIntegerField()
    lengkap = models.BooleanField(default=False)
    hasil = models.JSONField("hasil uji", default=dict, blank=True)
    diduga_hilang = models.JSONField("produk diduga hilang", default=list, blank=True)
    selisih_stok = models.JSONField("selisih dengan tingkat persediaan", default=list, blank=True)
    jumlah_baris = models.PositiveIntegerField(default=0)
    diperbarui = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "status periode"
        verbose_name_plural = "status periode"
        ordering = ("clinic", "-tahun", "-bulan")
        constraints = [
            models.UniqueConstraint(fields=["clinic", "tahun", "bulan"], name="uniq_status_periode")
        ]

    def __str__(self) -> str:
        return f"{self.clinic} {self.bulan:02d}/{self.tahun}"


class Parameter(models.Model):
    """Satu baris. Nilai awal adalah asumsi PRD, diubah dari halaman Stok Apotek."""

    bulan_rata_rata = models.PositiveSmallIntegerField("jumlah bulan rata-rata", default=3)
    bulan_buffer = models.FloatField("bulan buffer", default=1)
    ambang_mendekati = models.FloatField("ambang mendekati buffer (desimal)", default=0.25)
    target_bulan = models.FloatField("target stok setelah order (bulan)", default=2)
    cadangan_bulan = models.FloatField("cadangan cabang pengirim (bulan)", default=2)
    diubah_oleh = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    diubah = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "parameter stok"
        verbose_name_plural = "parameter stok"

    @property
    def ambang_persen(self) -> int:
        return round(self.ambang_mendekati * 100)

    @classmethod
    def aktif(cls) -> "Parameter":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
