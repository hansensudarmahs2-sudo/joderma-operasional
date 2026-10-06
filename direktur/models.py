"""Peran Direktur Operasional (Role.AOM): checklist audit berkala dan catatan.

Checklist Direktur adalah **uji petik**, bukan checklist pelaksana. Butirnya
(`AuditItem`) sengaja tidak memakai `checklists.ChecklistTemplate`, karena
template di sana diinstansiasi otomatis menjadi `ChecklistRun` pada setiap hari
operasional cabang — butir mingguan/bulanan akan ikut muncul setiap hari di
daftar checklist staf. Temuan dari uji petik memakai `core.ActionItem` yang
sudah ada (lewat `core.task_services.create_task`), sehingga tindak lanjutnya
berjalan di alur task yang sama dengan modul lain (Opsi B pada rencana fitur).
"""
from __future__ import annotations

import datetime as dt

from django.conf import settings
from django.db import models

from accounts.models import PicFunction


class Cadence(models.TextChoices):
    HARIAN = "HARIAN", "Harian"
    MINGGUAN = "MINGGUAN", "Mingguan"
    BULANAN = "BULANAN", "Bulanan"


def period_start(cadence: str, day: dt.date) -> dt.date:
    """Awal periode yang memuat `day`: hari itu, Senin minggu itu, atau tanggal 1."""
    if cadence == Cadence.MINGGUAN:
        return day - dt.timedelta(days=day.weekday())
    if cadence == Cadence.BULANAN:
        return day.replace(day=1)
    return day


class AuditItem(models.Model):
    """Satu butir checklist Direktur (baris "No | Cek | Yang dilihat | Bahan dari")."""

    code = models.SlugField("kode", max_length=60, unique=True)
    cadence = models.CharField("siklus", max_length=10, choices=Cadence.choices)
    number = models.PositiveSmallIntegerField("nomor")
    title = models.CharField("cek", max_length=120)
    description = models.TextField("yang dilihat")
    source_label = models.CharField("bahan dari", max_length=120, blank=True)
    pic_function = models.CharField(
        "fungsi PIC tindak lanjut",
        max_length=32,
        choices=PicFunction.choices,
        blank=True,
        default="",
        help_text="Penerima bawaan task temuan. Kosong berarti dipilih manual saat mencatat temuan.",
    )
    clinic_codes = models.JSONField(
        "berlaku untuk kode cabang",
        default=list,
        blank=True,
        help_text="Kosong berarti berlaku di semua cabang, mis. [\"citraland\"].",
    )
    active = models.BooleanField("aktif", default=True)
    sort_order = models.PositiveIntegerField("urutan", default=0)

    class Meta:
        verbose_name = "butir checklist Direktur"
        verbose_name_plural = "butir checklist Direktur"
        ordering = ("cadence", "sort_order", "number")

    def __str__(self) -> str:
        return f"{self.get_cadence_display()} {self.number}. {self.title}"

    def applies_to(self, clinic) -> bool:
        from core.services import clinic_key

        codes = list(self.clinic_codes or [])
        return not codes or clinic.code in codes or clinic_key(clinic) in codes

    def to_snapshot(self) -> dict:
        return {
            "id": self.pk,
            "code": self.code,
            "cadence": self.cadence,
            "number": self.number,
            "title": self.title,
            "description": self.description,
            "source_label": self.source_label,
            "points": [
                {"text": p.text, "evidence": p.evidence} for p in self.points.all()
            ],
        }


class AuditPoint(models.Model):
    """Rincian pemeriksaan satu butir ("Yang dicek | Bukti yang dilihat")."""

    item = models.ForeignKey(AuditItem, on_delete=models.CASCADE, related_name="points")
    text = models.CharField("yang dicek", max_length=300)
    evidence = models.CharField("bukti yang dilihat", max_length=300, blank=True)
    sort_order = models.PositiveIntegerField("urutan", default=0)

    class Meta:
        verbose_name = "rincian pemeriksaan"
        verbose_name_plural = "rincian pemeriksaan"
        ordering = ("sort_order", "id")

    def __str__(self) -> str:
        return self.text


class CheckResult(models.TextChoices):
    SESUAI = "SESUAI", "Sesuai"
    TEMUAN = "TEMUAN", "Ada temuan"
    TIDAK_BERLAKU = "TIDAK_BERLAKU", "Tidak berlaku"


class AuditCheck(models.Model):
    """Hasil cek satu butir, di satu cabang, untuk satu periode.

    Satu baris per (butir, cabang, awal periode). Ketiadaan baris untuk periode
    berjalan itulah yang ditampilkan sebagai "belum dicek" — sistem melaporkan
    ketiadaan catatan, bukan hanya catatan yang ada.
    """

    item = models.ForeignKey(AuditItem, on_delete=models.PROTECT, related_name="checks")
    clinic = models.ForeignKey("core.Clinic", on_delete=models.PROTECT, related_name="director_checks")
    period_start = models.DateField("awal periode")
    result = models.CharField("hasil", max_length=16, choices=CheckResult.choices)
    direct = models.BooleanField(
        "dicek langsung", default=False, help_text="Diperiksa sendiri di lapangan, bukan dari laporan PIC."
    )
    note = models.TextField("catatan", blank=True)
    item_snapshot = models.JSONField("snapshot butir", default=dict)
    finding = models.ForeignKey(
        "core.ActionItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="director_checks",
        verbose_name="task temuan",
    )
    checked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="director_checks"
    )
    checked_at = models.DateTimeField("dicek pada", auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "cek Direktur"
        verbose_name_plural = "cek Direktur"
        ordering = ("-period_start", "item__sort_order")
        constraints = [
            models.UniqueConstraint(
                fields=["item", "clinic", "period_start"], name="uniq_director_check_period"
            )
        ]

    def __str__(self) -> str:
        return f"{self.item} · {self.clinic.code} · {self.period_start}"


class NoteSource(models.TextChoices):
    MANUAL = "MANUAL", "Ditulis langsung"
    PASTE_WA = "PASTE_WA", "Tempelan WhatsApp"


class DirectorNote(models.Model):
    """Catatan bebas Direktur. Dapat dijadikan task; diarsipkan manual, tidak dihapus."""

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="director_notes"
    )
    clinic = models.ForeignKey(
        "core.Clinic",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="director_notes",
        help_text="Kosong untuk catatan lintas cabang.",
    )
    body = models.TextField("isi")
    source = models.CharField("sumber", max_length=10, choices=NoteSource.choices, default=NoteSource.MANUAL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    converted_task = models.ForeignKey(
        "core.ActionItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_notes",
        verbose_name="dijadikan task",
    )
    converted_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "catatan Direktur"
        verbose_name_plural = "catatan Direktur"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        first = self.body.strip().splitlines()[0] if self.body.strip() else ""
        return first[:80]

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None


class DecisionStatus(models.TextChoices):
    MENUNGGU = "MENUNGGU", "Menunggu keputusan"
    DITETAPKAN = "DITETAPKAN", "Ditetapkan"
    DIBATALKAN = "DIBATALKAN", "Dibatalkan"


class Decider(models.TextChoices):
    RAPAT_BERSAMA = "RAPAT_BERSAMA", "Rapat bersama (Kamis)"
    OWNER = "OWNER", "Owner"
    DIRUT = "DIRUT", "Direktur Utama"
    DIREKTUR_OPERASIONAL = "DIREKTUR_OPERASIONAL", "Direktur Operasional"
    PJ_PELAYANAN = "PJ_PELAYANAN", "Penanggung Jawab Pelayanan"
    LAINNYA = "LAINNYA", "Lainnya"


class Verdict(models.TextChoices):
    """Jawaban Owner atas permintaan keputusan Direktur Operasional (7 Okt 2026)."""

    SETUJU = "SETUJU", "Disetujui"
    TOLAK = "TOLAK", "Ditolak"


class Decision(models.Model):
    """Register keputusan: yang masih menggantung dan kebijakan yang sudah ditetapkan.

    Ditulis Direktur Operasional; dibaca Owner di Ringkasan tanpa perlu bertanya.
    Tidak pernah dihapus — dibatalkan dengan alasan.
    """

    clinic = models.ForeignKey(
        "core.Clinic",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="director_decisions",
        help_text="Kosong untuk keputusan lintas cabang.",
    )
    reference = models.CharField("nomor rujukan", max_length=30, blank=True, help_text="Mis. KP-188.")
    title = models.CharField("perkara", max_length=200)
    background = models.TextField("latar / pertanyaan", blank=True)
    decider = models.CharField("diputuskan oleh", max_length=24, choices=Decider.choices)
    needed_by = models.DateField("perlu diputuskan sebelum", null=True, blank=True)
    status = models.CharField(max_length=12, choices=DecisionStatus.choices, default=DecisionStatus.MENUNGGU)
    decision_text = models.TextField("isi keputusan", blank=True)
    is_policy = models.BooleanField(
        "kebijakan berlaku", default=False, help_text="Keputusan ini menjadi aturan yang berlaku bagi staf."
    )
    decided_on = models.DateField("tanggal ditetapkan", null=True, blank=True)
    verdict = models.CharField("jawaban Owner", max_length=10, choices=Verdict.choices, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        help_text="Owner yang memutuskan lewat halaman Owner (7 Okt 2026).",
    )
    waiting_tasks = models.ManyToManyField(
        "core.ActionItem",
        blank=True,
        related_name="waiting_decisions",
        verbose_name="task yang menunggu keputusan ini",
        help_text="Tenggat task ini dibekukan selama keputusan belum diambil (K-015).",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="director_decisions"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "keputusan"
        verbose_name_plural = "keputusan"
        ordering = ("status", "needed_by", "-created_at")

    def __str__(self) -> str:
        prefix = f"{self.reference} · " if self.reference else ""
        return f"{prefix}{self.title}"

    def is_overdue(self, today: dt.date) -> bool:
        return bool(self.status == DecisionStatus.MENUNGGU and self.needed_by and self.needed_by < today)


class DailySummary(models.Model):
    """Summary of the day dari Direktur Operasional untuk Owner, satu per tanggal.

    Disusun dari tombol "Simpan dan kirim summary ke Owner" di Checklist Direktur. Bisa
    dikirim ulang di hari yang sama; Owner melihat versi terakhir beserta jamnya.

    `content` berbentuk ``{"sections": [{"title": str, "empty": str,
    "items": [{"text": str, "meta": str, "tone": "ok"|"warn"|"err"|""}]}]}`` supaya
    halaman Owner cukup menampilkan apa adanya.
    """

    date = models.DateField("tanggal", unique=True)
    note = models.TextField("catatan Direktur", blank=True)
    content = models.JSONField("isi", default=dict)
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="daily_summaries"
    )
    first_sent_at = models.DateTimeField("pertama dikirim", auto_now_add=True)
    sent_at = models.DateTimeField("terakhir dikirim")
    send_count = models.PositiveSmallIntegerField("berapa kali dikirim", default=1)

    class Meta:
        verbose_name = "summary harian"
        verbose_name_plural = "summary harian"
        ordering = ("-date",)

    def __str__(self) -> str:
        return f"Summary {self.date:%d/%m/%Y}"

    @property
    def sections(self) -> list[dict]:
        return list((self.content or {}).get("sections") or [])


class DailySummaryRead(models.Model):
    """Kapan seorang Owner terakhir membuka summary satu tanggal (7 Okt 2026)."""

    summary = models.ForeignKey(DailySummary, on_delete=models.CASCADE, related_name="reads")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    read_at = models.DateTimeField("terakhir dibuka")

    class Meta:
        verbose_name = "tanda baca summary"
        verbose_name_plural = "tanda baca summary"
        constraints = [models.UniqueConstraint(fields=["summary", "user"], name="uniq_summary_read")]


class DailySummaryNote(models.Model):
    """Tanggapan Owner ↔ Direktur pada summary satu tanggal. Tidak diubah atau dihapus (7 Okt 2026)."""

    summary = models.ForeignKey(DailySummary, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    body = models.TextField("tanggapan")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "tanggapan summary"
        verbose_name_plural = "tanggapan summary"
        ordering = ("created_at",)

    def __str__(self) -> str:
        return self.body[:80]
