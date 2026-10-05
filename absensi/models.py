"""Cap jam kerja staf: satu baris per cap, waktunya mutlak.

Modul ini hanya menyimpan *kapan* seseorang mengecap. Ia tidak tahu jam shift, tidak
menghitung terlambat atau lembur, dan tidak membaca jadwal jaga. Itu urusan lapisan
perhitungan, yang mengambil shift dari `jadwal.DutyRoster` hari itu lalu
`core.Clinic.open_time`/`close_time` cabang tempat orang itu bertugas.

Dua hal yang dipisahkan sengaja:

``shift_date`` vs ``occurred_at``
    Cap pulang bisa jatuh setelah tengah malam. Mesin sidik jari sudah menaruhnya di
    baris tanggal shift (pulang 00.28 tercatat di baris tanggal 4, bukan tanggal 5),
    dan kami mempertahankan itu: ``shift_date`` adalah hari kerjanya, ``occurred_at``
    adalah detik sebenarnya. Menghitung lembur dari ``occurred_at`` membuat 00.28
    menjadi +148 menit, bukan -1292 menit.

``jenis`` boleh belum pasti
    Bila satu hari cuma punya satu cap, importer tidak menebak apakah itu masuk atau
    keluar; ia menandainya ``TIDAK_PASTI``. Yang punya jadwal adalah lapisan
    perhitungan, jadi di sanalah tafsirannya diputuskan dan dilaporkan sebagai
    pengecualian, bukan disembunyikan sebagai angka nol.

Rencana lanjutan (belum dibangun): cap lewat aplikasi dengan foto selfie dan lokasi
sesaat. `SumberCap` sudah menyediakan tempatnya dan `core.Clinic` sudah punya
lintang/bujur/radius; lihat `docs/ABSENSI_RENCANA.md`.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models


class SumberCap(models.TextChoices):
    FINGERPRINT = "FINGERPRINT", "Mesin sidik jari"
    MANUAL = "MANUAL", "Koreksi manual"


class JenisCap(models.TextChoices):
    MASUK = "MASUK", "Masuk"
    KELUAR = "KELUAR", "Keluar"
    TIDAK_PASTI = "TIDAK_PASTI", "Belum pasti masuk atau keluar"


class AttendanceDevice(models.Model):
    """ID di mesin sidik jari dan pemiliknya.

    Mesin memakai nomor, bukan username, dan ejaan namanya kerap berbeda dari sistem
    (mis. "Heny" vs user `heni`, "Agustin" vs user `nanda`). Nomor itulah kuncinya;
    `device_label` disimpan apa adanya supaya importer bisa memperingatkan bila nama
    pada file tidak lagi cocok dengan pemetaan ini.
    """

    device_uid = models.CharField("ID di mesin", max_length=20, unique=True)
    device_label = models.CharField(
        "nama di mesin", max_length=120, blank=True,
        help_text="Ejaan nama persis seperti tercetak di ekspor mesin.",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="attendance_devices",
        verbose_name="staf",
    )
    active = models.BooleanField("aktif", default=True)
    recording_only = models.BooleanField(
        "rekam saja, tanpa penilaian", default=False,
        help_text="Capnya disimpan dan bisa dilihat, tetapi tidak masuk papan skor dan "
                  "tidak menghasilkan daftar pengecualian. Untuk staf di luar skema shift dua cabang.",
    )
    note = models.CharField("catatan", max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "ID mesin absensi"
        verbose_name_plural = "ID mesin absensi"
        ordering = ("device_uid",)

    def __str__(self) -> str:
        return f"{self.device_uid} · {self.device_label or self.user}"


class AttendanceImport(models.Model):
    """Satu berkas ekspor mesin yang pernah diimpor.

    Disimpan supaya impor ulang berkas yang sama tidak menggandakan cap, dan supaya
    peringatan parser (ID tak dikenal, sel berisi teks, baris cap tunggal) tetap bisa
    dibaca setelah impor selesai.
    """

    file_name = models.CharField("nama berkas", max_length=255)
    checksum = models.CharField("sidik berkas", max_length=64, db_index=True)
    period_start = models.DateField("periode mulai", null=True, blank=True)
    period_end = models.DateField("periode selesai", null=True, blank=True)
    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        verbose_name="diimpor oleh",
    )
    imported_at = models.DateTimeField(auto_now_add=True, db_index=True)
    rows_read = models.PositiveIntegerField("baris hari terbaca", default=0)
    punches_created = models.PositiveIntegerField("cap baru", default=0)
    punches_skipped = models.PositiveIntegerField("cap sudah ada", default=0)
    warnings = models.JSONField("peringatan", default=list, blank=True)

    class Meta:
        verbose_name = "impor absensi"
        verbose_name_plural = "impor absensi"
        ordering = ("-imported_at",)

    def __str__(self) -> str:
        return f"{self.file_name} ({self.imported_at:%Y-%m-%d})"


class AttendancePunch(models.Model):
    """Satu cap. ``occurred_at`` mutlak, ``shift_date`` hari kerjanya."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="attendance_punches",
        verbose_name="staf",
    )
    shift_date = models.DateField("tanggal shift", db_index=True)
    occurred_at = models.DateTimeField("waktu cap")
    kind = models.CharField("jenis", max_length=12, choices=JenisCap.choices)
    source = models.CharField(
        "sumber", max_length=12, choices=SumberCap.choices, default=SumberCap.FINGERPRINT
    )
    device = models.ForeignKey(
        AttendanceDevice, on_delete=models.SET_NULL, null=True, blank=True, related_name="punches",
        verbose_name="ID mesin",
    )
    import_batch = models.ForeignKey(
        AttendanceImport, on_delete=models.SET_NULL, null=True, blank=True, related_name="punches",
        verbose_name="berkas impor",
    )
    note = models.CharField("catatan", max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "cap absensi"
        verbose_name_plural = "cap absensi"
        ordering = ("shift_date", "occurred_at")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "occurred_at"], name="uniq_punch_user_waktu"
            )
        ]
        indexes = [models.Index(fields=["user", "shift_date"])]

    def __str__(self) -> str:
        return f"{self.user} {self.shift_date} {self.get_kind_display()}"
