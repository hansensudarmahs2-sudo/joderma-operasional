"""Engine issue terpadu: komplain, masukan/saran, kerusakan (PRD 8.7–8.9)."""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import Priority


class IssueType(models.TextChoices):
    KOMPLAIN = "KOMPLAIN", "Komplain"
    MASUKAN = "MASUKAN", "Masukan/saran"
    KERUSAKAN = "KERUSAKAN", "Kerusakan"


NUMBER_PREFIX = {
    IssueType.KOMPLAIN: "CMP",
    IssueType.MASUKAN: "SUG",
    IssueType.KERUSAKAN: "DMG",
}


class IssueStatus(models.TextChoices):
    # Umum
    BARU = "BARU", "Baru"
    DITINJAU = "DITINJAU", "Ditinjau"
    DITUGASKAN = "DITUGASKAN", "Ditugaskan"
    DALAM_PROSES = "DALAM_PROSES", "Dalam proses"
    MENUNGGU_PIHAK_LAIN = "MENUNGGU_PIHAK_LAIN", "Menunggu pihak lain"
    SELESAI = "SELESAI", "Selesai"
    DIVERIFIKASI = "DIVERIFIKASI", "Diverifikasi"
    DITUTUP = "DITUTUP", "Ditutup"
    # Khusus masukan
    DIPERTIMBANGKAN = "DIPERTIMBANGKAN", "Dipertimbangkan"
    DIRENCANAKAN = "DIRENCANAKAN", "Direncanakan"
    DITERAPKAN = "DITERAPKAN", "Diterapkan"
    DITOLAK = "DITOLAK", "Ditolak"
    # Khusus kerusakan
    DITRIASE = "DITRIASE", "Ditriase"
    DALAM_PERBAIKAN = "DALAM_PERBAIKAN", "Dalam perbaikan"
    MENUNGGU_VENDOR = "MENUNGGU_VENDOR", "Menunggu vendor/komponen"


WORKFLOWS: dict[str, dict[str, set[str]]] = {
    IssueType.KOMPLAIN: {
        IssueStatus.BARU: {IssueStatus.DITINJAU},
        IssueStatus.DITINJAU: {IssueStatus.DITUGASKAN, IssueStatus.SELESAI},
        IssueStatus.DITUGASKAN: {IssueStatus.DALAM_PROSES, IssueStatus.MENUNGGU_PIHAK_LAIN},
        IssueStatus.DALAM_PROSES: {IssueStatus.MENUNGGU_PIHAK_LAIN, IssueStatus.SELESAI},
        IssueStatus.MENUNGGU_PIHAK_LAIN: {IssueStatus.DALAM_PROSES, IssueStatus.SELESAI},
        IssueStatus.SELESAI: {IssueStatus.DITUTUP, IssueStatus.DALAM_PROSES},
        IssueStatus.DITUTUP: set(),
    },
    IssueType.MASUKAN: {
        IssueStatus.BARU: {IssueStatus.DIPERTIMBANGKAN, IssueStatus.DITOLAK},
        IssueStatus.DIPERTIMBANGKAN: {
            IssueStatus.DIRENCANAKAN,
            IssueStatus.DITOLAK,
            IssueStatus.DITUTUP,
        },
        IssueStatus.DIRENCANAKAN: {IssueStatus.DITERAPKAN, IssueStatus.DITUTUP},
        IssueStatus.DITERAPKAN: {IssueStatus.DITUTUP},
        IssueStatus.DITOLAK: {IssueStatus.DITUTUP},
        IssueStatus.DITUTUP: set(),
    },
    IssueType.KERUSAKAN: {
        IssueStatus.BARU: {IssueStatus.DITRIASE},
        IssueStatus.DITRIASE: {IssueStatus.DITUGASKAN},
        IssueStatus.DITUGASKAN: {IssueStatus.DALAM_PERBAIKAN, IssueStatus.MENUNGGU_VENDOR},
        IssueStatus.DALAM_PERBAIKAN: {IssueStatus.MENUNGGU_VENDOR, IssueStatus.SELESAI},
        IssueStatus.MENUNGGU_VENDOR: {IssueStatus.DALAM_PERBAIKAN, IssueStatus.SELESAI},
        IssueStatus.SELESAI: {IssueStatus.DIVERIFIKASI, IssueStatus.DALAM_PERBAIKAN},
        IssueStatus.DIVERIFIKASI: {IssueStatus.DITUTUP},
        IssueStatus.DITUTUP: set(),
    },
}

OPEN_STATUSES = {
    IssueStatus.BARU,
    IssueStatus.DITINJAU,
    IssueStatus.DITUGASKAN,
    IssueStatus.DALAM_PROSES,
    IssueStatus.MENUNGGU_PIHAK_LAIN,
    IssueStatus.DIPERTIMBANGKAN,
    IssueStatus.DIRENCANAKAN,
    IssueStatus.DITRIASE,
    IssueStatus.DALAM_PERBAIKAN,
    IssueStatus.MENUNGGU_VENDOR,
}

REASON_REQUIRED_STATUSES = {IssueStatus.DITOLAK, IssueStatus.DITUTUP}


class ReporterSource(models.TextChoices):
    PASIEN = "PASIEN", "Pasien"
    KELUARGA = "KELUARGA", "Keluarga pasien"
    STAF = "STAF", "Staf"
    LAINNYA = "LAINNYA", "Lainnya"


class Channel(models.TextChoices):
    LANGSUNG = "LANGSUNG", "Langsung"
    TELEPON = "TELEPON", "Telepon"
    CHAT = "CHAT", "Chat"
    FORMULIR = "FORMULIR", "Formulir"
    LAINNYA = "LAINNYA", "Lainnya"


class DamageCategory(models.TextChoices):
    FASILITAS = "FASILITAS", "Fasilitas"
    ALAT_MEDIS = "ALAT_MEDIS", "Alat medis"
    IT = "IT", "IT"
    LISTRIK = "LISTRIK", "Listrik"
    AIR = "AIR", "Air"
    FURNITUR = "FURNITUR", "Furnitur"
    KESELAMATAN = "KESELAMATAN", "Keselamatan"
    LAINNYA = "LAINNYA", "Lainnya"


class ImpactLevel(models.TextChoices):
    NORMAL = "NORMAL", "Tetap dapat digunakan"
    TERBATAS = "TERBATAS", "Penggunaan terbatas"
    TIDAK_DAPAT = "TIDAK_DAPAT", "Tidak dapat digunakan"
    RISIKO_KESELAMATAN = "RISIKO_KESELAMATAN", "Risiko keselamatan"


class Asset(models.Model):
    clinic = models.ForeignKey("core.Clinic", on_delete=models.CASCADE, related_name="assets")
    code = models.CharField("kode", max_length=40)
    name = models.CharField("nama", max_length=150)
    category = models.CharField(max_length=20, choices=DamageCategory.choices, blank=True)
    location = models.CharField("lokasi", max_length=150, blank=True)
    do_not_use = models.BooleanField("jangan digunakan", default=False)
    do_not_use_reason = models.CharField(max_length=200, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "aset"
        verbose_name_plural = "aset"
        ordering = ("name",)
        constraints = [models.UniqueConstraint(fields=["clinic", "code"], name="uniq_asset_code")]

    def __str__(self) -> str:
        return f"{self.code} · {self.name}"


class Issue(models.Model):
    clinic = models.ForeignKey("core.Clinic", on_delete=models.CASCADE, related_name="issues")
    issue_type = models.CharField("tipe", max_length=10, choices=IssueType.choices, db_index=True)
    number = models.CharField("nomor", max_length=30, unique=True)
    title = models.CharField("ringkasan", max_length=200)
    description = models.TextField("uraian", blank=True)
    category = models.CharField("kategori", max_length=60, blank=True)
    severity = models.CharField("tingkat", max_length=10, choices=Priority.choices, default=Priority.SEDANG)
    status = models.CharField(max_length=20, choices=IssueStatus.choices, default=IssueStatus.BARU, db_index=True)
    is_restricted = models.BooleanField("terbatas", default=False)
    is_anonymous = models.BooleanField("anonim terhadap staf biasa", default=False)

    # Komplain
    reporter_source = models.CharField(max_length=10, choices=ReporterSource.choices, blank=True)
    reporter_contact = models.CharField("kontak pelapor", max_length=120, blank=True)
    channel = models.CharField(max_length=10, choices=Channel.choices, blank=True)
    occurred_at = models.DateTimeField("waktu kejadian", null=True, blank=True)
    followup_preference = models.CharField("preferensi tindak lanjut", max_length=200, blank=True)

    # Masukan
    benefit = models.TextField("manfaat/dampak", blank=True)

    # Kerusakan
    location = models.CharField("lokasi", max_length=150, blank=True)
    asset = models.ForeignKey(Asset, on_delete=models.SET_NULL, null=True, blank=True, related_name="issues")
    impact = models.CharField(max_length=20, choices=ImpactLevel.choices, blank=True)
    repair_action = models.TextField("tindakan perbaikan", blank=True)
    repaired_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="issues_verified"
    )
    verified_at = models.DateTimeField(null=True, blank=True)

    resolution_summary = models.TextField("ringkasan penyelesaian", blank=True)
    closed_reason = models.TextField("alasan penutupan/penolakan", blank=True)
    duplicate_of = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="duplicates"
    )
    source_ref = models.CharField(max_length=60, blank=True)

    due_at = models.DateTimeField("target selesai", null=True, blank=True)
    assign_due_at = models.DateTimeField("target penugasan", null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="issues_created"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "catatan issue"
        verbose_name_plural = "catatan issue"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["issue_type", "status"])]

    def __str__(self) -> str:
        return f"{self.number} · {self.title}"

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES

    @property
    def is_overdue(self) -> bool:
        return bool(self.due_at and self.is_open and self.due_at < timezone.now())

    @property
    def current_assignee(self):
        assignment = self.assignments.filter(active=True).select_related("assignee").first()
        return assignment.assignee if assignment else None

    def allowed_next_statuses(self) -> set[str]:
        return WORKFLOWS.get(self.issue_type, {}).get(self.status, set())


class IssueAssignment(models.Model):
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name="assignments")
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="issue_assignments"
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="issues_assigned"
    )
    due_at = models.DateTimeField(null=True, blank=True)
    active = models.BooleanField(default=True)
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "penugasan issue"
        verbose_name_plural = "penugasan issue"
        ordering = ("-assigned_at",)

    def __str__(self) -> str:
        return f"{self.issue.number} → {self.assignee}"


class IssueUpdate(models.Model):
    """Timeline; catatan tidak pernah dihapus dari UI (PRD 8.7)."""

    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name="updates")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="issue_updates"
    )
    from_status = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=20, blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "riwayat issue"
        verbose_name_plural = "riwayat issue"
        ordering = ("created_at", "id")

    def __str__(self) -> str:
        return f"{self.issue.number} {self.status}"

    @property
    def status_label(self) -> str:
        return IssueStatus(self.status).label if self.status in IssueStatus.values else self.status

    @property
    def from_status_label(self) -> str:
        return IssueStatus(self.from_status).label if self.from_status in IssueStatus.values else self.from_status
