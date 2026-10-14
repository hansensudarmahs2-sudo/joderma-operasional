"""Pengingat Harian Direktur Operasional (kebutuhan: docs/KEBUTUHAN_PENGINGAT_HARIAN_DO.md, 14 Okt 2026).

Materi (alur, SOP, standar, kebijakan) bergilir otomatis menurut kelasnya. Setiap hari kerja DO
mendapat kartu berisi butir yang perlu diingatkan ke tim beserta teks WA siap salin. Aplikasi tidak
mengirim apa pun ke staf; DO yang mengirim, aplikasi menyiapkan dan mencatat.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models


class Jenis(models.TextChoices):
    ALUR = "alur", "Alur"
    SOP = "sop", "SOP"
    STANDAR = "standar", "Standar"
    KEBIJAKAN = "kebijakan", "Kebijakan"


class Kelas(models.TextChoices):
    A = "A", "A · mingguan"
    B = "B", "B · dua mingguan"
    C = "C", "C · bulanan"


# Sasaran peran: label tetap (bukan `accounts.Role`), karena kelompoknya mengikuti cara DO
# menyapa tim (mis. "Piket", "Petugas online"), bukan hak akses di aplikasi.
SASARAN = (
    "Semua staf",
    "Meja depan",
    "Petugas online",
    "Kasir",
    "Perawat",
    "Koordinator shift",
    "Piket",
    "Apotek",
    "Dokter",
)


class Saluran(models.TextChoices):
    GRUP_WA = "GRUP_WA", "Grup WA"
    BRIEFING = "BRIEFING", "Briefing"
    LANGSUNG = "LANGSUNG", "Langsung"


class Materi(models.Model):
    kode = models.CharField("kode", max_length=20, unique=True)
    judul = models.CharField("judul", max_length=200)
    jenis = models.CharField("jenis", max_length=12, choices=Jenis.choices, default=Jenis.ALUR)
    sasaran = models.JSONField("sasaran peran", default=list)
    clinic = models.ForeignKey(
        "core.Clinic", on_delete=models.PROTECT, null=True, blank=True, related_name="+",
        verbose_name="cabang", help_text="Kosong = kedua cabang.",
    )
    kelas = models.CharField("kelas", max_length=1, choices=Kelas.choices, default=Kelas.B)
    poin = models.JSONField("poin kunci", default=list)
    teks_wa = models.TextField("teks WA", blank=True, help_text="{cabang} diganti nama cabang.")
    rujukan = models.CharField("rujukan", max_length=300, blank=True)
    kebijakan = models.ForeignKey(
        "direktur.Decision", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        verbose_name="kebijakan", help_text="Untuk jenis kebijakan: isinya ditampilkan dari record aslinya.",
    )
    aktif = models.BooleanField("aktif", default=True)
    tanggal_sosialisasi = models.DateField("tanggal sosialisasi", null=True, blank=True)
    catatan = models.TextField("catatan", blank=True)
    urutan = models.PositiveIntegerField("urutan prioritas", default=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "materi pengingat"
        verbose_name_plural = "materi pengingat"
        ordering = ("urutan", "kode")

    def __str__(self) -> str:
        return f"{self.kode} {self.judul}"


class Diingatkan(models.Model):
    """Log "Sudah diingatkan". `clinic` kosong = kedua cabang."""

    materi = models.ForeignKey(Materi, on_delete=models.PROTECT, related_name="log")
    tanggal = models.DateField("tanggal")
    clinic = models.ForeignKey("core.Clinic", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    saluran = models.CharField("saluran", max_length=10, choices=Saluran.choices)
    catatan = models.TextField("catatan", blank=True)
    oleh = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "log pengingat"
        verbose_name_plural = "log pengingat"
        ordering = ("-tanggal", "-id")


class Sebab(models.TextChoices):
    TUNDA = "TUNDA", "Ditunda"
    TEMUAN = "TEMUAN", "Karena temuan"
    ULANGAN = "ULANGAN", "Ulangan materi baru"


class Paksa(models.Model):
    """Butir yang dipaksa muncul pada `tanggal` di luar kuota. Tetap tertunda (dan muncul lagi)
    sampai butirnya ditangani di kartu: `selesai_pada` diisi saat itu."""

    materi = models.ForeignKey(Materi, on_delete=models.CASCADE, related_name="paksa")
    tanggal = models.DateField("tanggal muncul")
    sebab = models.CharField("sebab", max_length=8, choices=Sebab.choices)
    selesai_pada = models.DateField("ditangani pada", null=True, blank=True)
    dibuat_oleh = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "butir paksa"
        verbose_name_plural = "butir paksa"
        ordering = ("tanggal", "id")


class Kartu(models.Model):
    """Kartu "Pengingat hari ini": dibentuk sekali per hari kerja lalu dikunci."""

    tanggal = models.DateField("tanggal", unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "kartu pengingat"
        verbose_name_plural = "kartu pengingat"
        ordering = ("-tanggal",)


class Status(models.TextChoices):
    TERBUKA = "TERBUKA", "Belum"
    DIINGATKAN = "DIINGATKAN", "Sudah diingatkan"
    DITUNDA = "DITUNDA", "Ditunda ke besok"
    DILEWATI = "DILEWATI", "Dilewati"


class Butir(models.Model):
    kartu = models.ForeignKey(Kartu, on_delete=models.CASCADE, related_name="butir")
    materi = models.ForeignKey(Materi, on_delete=models.PROTECT, related_name="+")
    paksa = models.ForeignKey(Paksa, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    status = models.CharField("status", max_length=10, choices=Status.choices, default=Status.TERBUKA)
    alasan = models.TextField("alasan", blank=True)
    ditangani_oleh = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name="+")
    ditangani_pada = models.DateTimeField(null=True, blank=True)
    urutan = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "butir kartu"
        verbose_name_plural = "butir kartu"
        ordering = ("urutan", "id")
        constraints = [models.UniqueConstraint(fields=("kartu", "materi"), name="pengingat_butir_unik")]


class Pengaturan(models.Model):
    """Satu baris (pk=1). Hari kerja: 0 = Senin … 6 = Minggu."""

    hari_kerja = models.JSONField("hari kerja", default=list)
    kuota = models.PositiveSmallIntegerField("butir per hari", default=2)
    interval_a = models.PositiveSmallIntegerField("interval kelas A (hari)", default=7)
    interval_b = models.PositiveSmallIntegerField("interval kelas B (hari)", default=14)
    interval_c = models.PositiveSmallIntegerField("interval kelas C (hari)", default=28)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "pengaturan pengingat"
        verbose_name_plural = "pengaturan pengingat"

    @classmethod
    def get(cls) -> "Pengaturan":
        obj, _ = cls.objects.get_or_create(pk=1, defaults={"hari_kerja": [0, 1, 2, 3, 4, 5]})
        return obj

    def interval(self, kelas: str) -> int:
        return {"A": self.interval_a, "B": self.interval_b, "C": self.interval_c}[kelas]
