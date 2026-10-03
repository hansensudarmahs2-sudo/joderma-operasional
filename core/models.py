"""Entitas inti: klinik, konfigurasi, hari operasional, action item, lampiran."""
from __future__ import annotations

import secrets
from datetime import date as date_cls

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Clinic(models.Model):
    name = models.CharField("nama", max_length=120)
    code = models.SlugField("kode", max_length=32, unique=True)
    address = models.TextField("alamat", blank=True)
    phone = models.CharField("nomor HP/WhatsApp", max_length=40, blank=True)
    timezone_name = models.CharField("zona waktu", max_length=64, default="Asia/Jakarta")
    open_time = models.TimeField("jam buka", default="12:00")
    close_time = models.TimeField("jam tutup", default="21:00")
    dpj_name = models.CharField(
        "dokter penanggung jawab (DPJ)", max_length=160, blank=True,
        help_text="Nama lengkap beserta gelar, mis. dr. Yohanes Widjaja, Sp.DVE.",
    )
    apj_name = models.CharField(
        "apoteker penanggung jawab (APJ)", max_length=160, blank=True,
        help_text="Nama lengkap beserta gelar.",
    )
    latitude = models.DecimalField("lintang", max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField("bujur", max_digits=9, decimal_places=6, null=True, blank=True)
    radius_m = models.PositiveIntegerField(
        "radius klinik (m)", default=150,
        help_text="Jejak dengan lokasi di dalam radius ini berlabel Kuat (tahap 3 paket E).",
    )
    active = models.BooleanField("aktif", default=True)

    class Meta:
        verbose_name = "klinik"
        verbose_name_plural = "klinik"
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class Holiday(models.Model):
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name="holidays")
    date = models.DateField("tanggal")
    description = models.CharField("keterangan", max_length=200, blank=True)

    class Meta:
        verbose_name = "hari libur"
        verbose_name_plural = "hari libur"
        constraints = [
            models.UniqueConstraint(fields=["clinic", "date"], name="uniq_clinic_holiday")
        ]
        ordering = ("-date",)

    def __str__(self) -> str:
        return f"{self.date} · {self.description}"


DEFAULT_CONFIG: dict[str, object] = {
    # Kas
    "cash.dual_control_enabled": True,
    "cash.track_change_fund_separately": True,
    "cash.denominations": [100000, 50000, 20000, 10000, 5000, 2000, 1000, 500, 200, 100],
    # Antrean
    "queue.keep_number_statuses": ["SUDAH_BAYAR", "DIBEBASKAN"],
    "queue.no_show_grace_minutes": 15,
    # Rotasi perawat
    "nurse.rotation_policy": "ROUND_ROBIN_PER_CONFIRMED_PROCEDURE",
    "nurse.skip_keeps_position": True,
    "nurse.cancel_before_start_restores_position": True,
    # Perawat yang total tally bulanannya >= N di bawah total terkecil rekan
    # didahulukan sampai tinggal 1 di bawah ("sampai total -1").
    "nurse.catch_up_gap": 2,
    # Istirahat
    "break.min_active_front_desk": 1,
    "break.min_active_nurse": 1,
    # SLA (jam)
    "sla.KRITIS.assign_hours": 1,
    "sla.KRITIS.resolve_hours": 8,
    "sla.TINGGI.assign_hours": 4,
    "sla.TINGGI.resolve_hours": 24,
    "sla.SEDANG.assign_hours": 24,
    "sla.SEDANG.resolve_hours": 72,
    "sla.RENDAH.assign_hours": 48,
    "sla.RENDAH.resolve_hours": 168,
    # Pembukaan
    "opening.reminder_minutes_before_open": 30,
    # Ringkasan/dashboard: task dianggap "mendesak" bila targetnya <= N jam lagi
    "dashboard.urgent_hours": 48,
    # KPI per staf (uji coba): butir Pembukaan dianggap tepat waktu bila selesai sebelum jam buka + N menit;
    # tanda "centang massal" bila >= N butir dicentang dalam N detik (hanya tanda, bukan pengurang).
    "kpi.open_tolerance_minutes": 15,
    "kpi.bulk_items": 5,
    "kpi.bulk_seconds": 60,
}


class ClinicConfig(models.Model):
    """Konfigurasi kebijakan yang terlihat di halaman Admin (PRD 8.5)."""

    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name="configs")
    key = models.CharField("kunci", max_length=100)
    value = models.JSONField("nilai")
    description = models.CharField("keterangan", max_length=300, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        verbose_name = "konfigurasi klinik"
        verbose_name_plural = "konfigurasi klinik"
        constraints = [
            models.UniqueConstraint(fields=["clinic", "key"], name="uniq_clinic_config_key")
        ]
        ordering = ("key",)

    def __str__(self) -> str:
        return f"{self.key} = {self.value}"

    @classmethod
    def get(cls, clinic: Clinic, key: str, default=None):
        row = cls.objects.filter(clinic=clinic, key=key).first()
        if row is not None:
            return row.value
        if key in DEFAULT_CONFIG:
            return DEFAULT_CONFIG[key]
        return default

    @classmethod
    def set(cls, clinic: Clinic, key: str, value, user=None):
        obj, _ = cls.objects.update_or_create(
            clinic=clinic, key=key, defaults={"value": value, "updated_by": user}
        )
        return obj


class DayStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    OPENING_IN_PROGRESS = "OPENING_IN_PROGRESS", "Pembukaan berjalan"
    READY = "READY", "Siap"
    READY_WITH_ISSUES = "READY_WITH_ISSUES", "Siap dengan catatan"
    OPEN = "OPEN", "Buka"
    CLOSING = "CLOSING", "Penutupan"
    CLOSED = "CLOSED", "Tutup"


EDITABLE_DAY_STATUSES = {
    DayStatus.DRAFT,
    DayStatus.OPENING_IN_PROGRESS,
    DayStatus.READY,
    DayStatus.READY_WITH_ISSUES,
    DayStatus.OPEN,
    DayStatus.CLOSING,
}


class OperationalDay(models.Model):
    """Satu sesi hari operasional per cabang per tanggal (PRD 7)."""

    clinic = models.ForeignKey(Clinic, on_delete=models.PROTECT, related_name="operational_days")
    date = models.DateField("tanggal operasional")
    shift = models.CharField("shift", max_length=40, blank=True, default="")
    status = models.CharField(max_length=24, choices=DayStatus.choices, default=DayStatus.DRAFT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="days_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="days_opened",
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="days_closed",
    )
    ready_exception_reason = models.TextField("alasan siap dengan catatan", blank=True)
    close_override_reason = models.TextField("alasan override penutupan", blank=True)
    reopen_reason = models.TextField("alasan buka kembali", blank=True)
    version = models.PositiveIntegerField(default=1)  # optimistic locking

    class Meta:
        verbose_name = "hari operasional"
        verbose_name_plural = "hari operasional"
        constraints = [
            models.UniqueConstraint(fields=["clinic", "date"], name="uniq_clinic_operational_date")
        ]
        ordering = ("-date",)

    def __str__(self) -> str:
        return f"{self.clinic.code} {self.date} ({self.get_status_display()})"

    @property
    def is_closed(self) -> bool:
        return self.status == DayStatus.CLOSED

    @property
    def is_editable(self) -> bool:
        return self.status in EDITABLE_DAY_STATUSES

    def assert_editable(self):
        if not self.is_editable:
            raise ValidationError(
                "Hari operasional sudah ditutup. Supervisor harus membuka kembali dengan alasan "
                "sebelum data dapat diubah."
            )

    @classmethod
    def today_for(cls, clinic: Clinic) -> "OperationalDay | None":
        return cls.objects.filter(clinic=clinic, date=local_today()).first()


def local_today() -> date_cls:
    return timezone.localtime(timezone.now()).date()


class Priority(models.TextChoices):
    RENDAH = "RENDAH", "Rendah"
    SEDANG = "SEDANG", "Sedang"
    TINGGI = "TINGGI", "Tinggi"
    KRITIS = "KRITIS", "Kritis"


class ActionItemStatus(models.TextChoices):
    BARU = "BARU", "Baru"
    DIKERJAKAN = "DIKERJAKAN", "Dikerjakan"
    SELESAI = "SELESAI", "Selesai"
    BATAL = "BATAL", "Batal"


class TaskAssignmentMode(models.TextChoices):
    INDIVIDUAL = "INDIVIDUAL", "Individual"
    BERSAMA = "BERSAMA", "Bersama"


class ReviewBy(models.TextChoices):
    DIREKTUR = "DIREKTUR", "Direktur Operasional"
    DIRUT = "DIRUT", "Direktur Utama / Owner"


class ActionItem(models.Model):
    """Tindak lanjut lintas modul (PRD 9.1)."""

    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name="action_items")
    title = models.CharField("judul", max_length=200)
    description = models.TextField("uraian", blank=True)
    source_type = models.CharField("modul sumber", max_length=40)
    source_id = models.PositiveIntegerField("id sumber", null=True, blank=True)
    source_label = models.CharField("label sumber", max_length=120, blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="action_items",
    )
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.SEDANG)
    status = models.CharField(
        max_length=12, choices=ActionItemStatus.choices, default=ActionItemStatus.BARU
    )
    assignment_mode = models.CharField(
        max_length=12, choices=TaskAssignmentMode.choices, default=TaskAssignmentMode.INDIVIDUAL
    )
    due_at = models.DateTimeField("target waktu", null=True, blank=True)
    progress_note = models.TextField("catatan progres", blank=True)
    review_by = models.CharField(
        "pemeriksa", max_length=10, choices=ReviewBy.choices, default=ReviewBy.DIREKTUR,
        help_text="Siapa yang memverifikasi. Task yang dikerjakan Direktur Operasional sendiri selalu "
        "diperiksa Direktur Utama / Owner (lihat effective_review_by).",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="action_items_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Fase 6 (migration rehearsal): penanda task hasil import dari AOM
    # standalone legacy. Additive, nullable/default aman untuk baris lama.
    imported_legacy = models.BooleanField("hasil import legacy", default=False)
    legacy_source_id = models.CharField(
        "ID sumber legacy", max_length=64, blank=True, default=""
    )
    legacy_completed_at = models.DateTimeField(
        "waktu selesai asli (legacy)", null=True, blank=True
    )

    class Meta:
        verbose_name = "action item"
        verbose_name_plural = "action item"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return self.title

    @property
    def effective_review_by(self) -> str:
        """Pemeriksa yang berlaku: Dirut/Owner bila salah satu penerima aktif adalah Direktur Operasional.

        Aturan tambahan matriks wewenang (Okt 2026): pekerjaan Direktur Operasional sendiri
        diverifikasi Direktur Utama. Dihitung, bukan disimpan, supaya data lama tidak perlu diubah.
        """
        if self.review_by == ReviewBy.DIRUT:
            return ReviewBy.DIRUT
        from accounts.models import Role, UserRole

        active = [a for a in self.task_assignments.all() if a.status != TaskAssignmentStatus.CANCELLED]
        ids = {a.assignee_id for a in active} | {a.claimed_by_id for a in active if a.claimed_by_id}
        if ids and UserRole.objects.filter(user_id__in=ids, role=Role.AOM).exists():
            return ReviewBy.DIRUT
        return ReviewBy.DIREKTUR

    @property
    def reviewed_by_dirut(self) -> bool:
        return self.effective_review_by == ReviewBy.DIRUT

    @property
    def on_hold(self) -> bool:
        """Ditahan karena menunggu keputusan (Keputusan.waiting_tasks) yang belum diambil (K-015)."""
        if not self.pk:
            return False
        cached = getattr(self, "_prefetched_objects_cache", {}).get("waiting_decisions")
        if cached is not None:
            return any(d.status == "MENUNGGU" for d in cached)
        return self.waiting_decisions.filter(status="MENUNGGU").exists()

    @property
    def is_overdue(self) -> bool:
        # Tenggat dibekukan selama task menunggu keputusan bersama.
        return bool(
            self.due_at
            and self.status in {ActionItemStatus.BARU, ActionItemStatus.DIKERJAKAN}
            and self.due_at < timezone.now()
            and not self.on_hold
        )


class TaskAudienceType(models.TextChoices):
    USER = "USER", "Satu user"
    USERS = "USERS", "Beberapa user"
    PIC_FUNCTION = "PIC_FUNCTION", "Fungsi PIC"
    ROLE = "ROLE", "Tier/role cabang"
    CLINIC = "CLINIC", "Seluruh staf cabang"


class TaskAudienceSnapshot(models.Model):
    """Snapshot target penerima saat task dikirim."""

    action_item = models.OneToOneField(
        ActionItem, on_delete=models.CASCADE, related_name="audience_snapshot"
    )
    audience_type = models.CharField(max_length=24, choices=TaskAudienceType.choices)
    criteria = models.JSONField(default=dict, blank=True)
    recipients = models.JSONField(default=list, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="task_audience_snapshots",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "snapshot penerima task"
        verbose_name_plural = "snapshot penerima task"

    def __str__(self) -> str:
        return f"{self.action_item} · {self.audience_type}"


class TaskAssignmentStatus(models.TextChoices):
    OPEN = "OPEN", "Terbuka"
    IN_PROGRESS = "IN_PROGRESS", "Dikerjakan"
    SUBMITTED = "SUBMITTED", "Diajukan selesai"
    REVISION_REQUIRED = "REVISION_REQUIRED", "Perlu revisi"
    CONFIRMED = "CONFIRMED", "Dikonfirmasi"
    CANCELLED = "CANCELLED", "Dibatalkan"


class TaskAssignment(models.Model):
    action_item = models.ForeignKey(
        ActionItem, on_delete=models.CASCADE, related_name="task_assignments"
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="task_assignments"
    )
    status = models.CharField(
        max_length=24, choices=TaskAssignmentStatus.choices, default=TaskAssignmentStatus.OPEN
    )
    claimed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="claimed_task_assignments",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_task_assignments",
    )
    revision_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "assignment task"
        verbose_name_plural = "assignment task"
        ordering = ("action_item", "assignee__username")
        constraints = [
            models.UniqueConstraint(
                fields=["action_item", "assignee"], name="uniq_task_assignment_recipient"
            )
        ]

    def __str__(self) -> str:
        return f"{self.action_item} · {self.assignee}"


class TaskEventType(models.TextChoices):
    SENT = "SENT", "Dikirim"
    CLAIMED = "CLAIMED", "Diambil"
    SUBMITTED = "SUBMITTED", "Diajukan selesai"
    CONFIRMED = "CONFIRMED", "Dikonfirmasi"
    REVISION_REQUESTED = "REVISION_REQUESTED", "Diminta revisi"
    CANCELLED = "CANCELLED", "Dibatalkan"
    COMMENT = "COMMENT", "Komentar"
    PROGRESS = "PROGRESS", "Laporan progres"


class TaskEvent(models.Model):
    action_item = models.ForeignKey(ActionItem, on_delete=models.CASCADE, related_name="task_events")
    assignment = models.ForeignKey(
        TaskAssignment,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="events",
    )
    event_type = models.CharField(max_length=24, choices=TaskEventType.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="task_events",
    )
    note = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "event task"
        verbose_name_plural = "event task"
        ordering = ("created_at", "id")

def attachment_upload_to(instance: "Attachment", filename: str) -> str:
    """Nama file diacak; nama asli disimpan sebagai metadata (PRD 9.3)."""
    return f"{instance.entity_type}/{timezone.now():%Y/%m}/{secrets.token_hex(16)}"


class Attachment(models.Model):
    entity_type = models.CharField(max_length=40, db_index=True)
    entity_id = models.PositiveIntegerField(db_index=True)
    file = models.FileField(upload_to=attachment_upload_to, max_length=255)
    original_name = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=100)
    size_bytes = models.PositiveIntegerField()
    sensitive = models.BooleanField(default=False)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="attachments"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "lampiran"
        verbose_name_plural = "lampiran"
        ordering = ("-uploaded_at",)
        indexes = [models.Index(fields=["entity_type", "entity_id"])]

    def __str__(self) -> str:
        return self.original_name

    @property
    def size_display(self) -> str:
        kb = self.size_bytes / 1024
        return f"{kb:.0f} KB" if kb < 1024 else f"{kb / 1024:.1f} MB"
