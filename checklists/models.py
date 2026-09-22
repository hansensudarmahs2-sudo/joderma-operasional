"""Checklist pembukaan: template berversi + snapshot harian (PRD 8.2)."""
from __future__ import annotations

from django.conf import settings
from django.db import models

from accounts.models import PicFunction, Role
from core.models import TaskAssignmentMode


class ChecklistArea(models.TextChoices):
    AKSES_UMUM = "AKSES_UMUM", "Akses dan area umum"
    KOMPUTER_SISTEM = "KOMPUTER_SISTEM", "Komputer dan sistem"
    RUANG_KONSULTASI = "RUANG_KONSULTASI", "Ruang konsultasi"
    RUANG_TINDAKAN = "RUANG_TINDAKAN", "Ruang tindakan estetik"


class ChecklistSession(models.TextChoices):
    """Sesi checklist harian (PRD 8.1)."""

    OPENING = "OPENING", "Pembukaan"
    CLOSING = "CLOSING", "Penutupan"
    ANYTIME = "ANYTIME", "Kapan saja"


class InputType(models.TextChoices):
    CEKLIS = "CEKLIS", "Ceklis"
    KUANTITAS = "KUANTITAS", "Jumlah (kuantitas)"
    PILIHAN = "PILIHAN", "Pilihan"


class ChecklistTemplate(models.Model):
    clinic = models.ForeignKey("core.Clinic", on_delete=models.CASCADE, related_name="templates")
    name = models.CharField("nama", max_length=150)
    area = models.CharField("area", max_length=24, choices=ChecklistArea.choices)
    session = models.CharField(
        "sesi",
        max_length=12,
        choices=ChecklistSession.choices,
        default=ChecklistSession.OPENING,
    )
    version = models.PositiveIntegerField("versi", default=1)
    audience_key = models.CharField(
        "kunci target", max_length=40, blank=True, default="",
        help_text="Kunci unik template per peran/fungsi; kosong untuk template lama.",
    )
    active = models.BooleanField("aktif", default=True)
    # Target opsional fungsi PIC dan/atau role/tier (PRD 8.1). Kosong berarti
    # tidak ditargetkan otomatis ke siapa pun; tindak lanjut memakai penerima
    # checklist sebagai fallback (lihat services.resolve_template_audience).
    target_pic_function = models.CharField(
        "fungsi PIC target",
        max_length=32,
        choices=PicFunction.choices,
        blank=True,
        default="",
    )
    target_role = models.CharField(
        "role/tier target",
        max_length=20,
        choices=Role.choices,
        blank=True,
        default="",
    )
    target_roles = models.JSONField(
        "role target", default=list, blank=True,
        help_text="Daftar role yang dapat melihat/mengisi run checklist.",
    )
    assignment_mode = models.CharField(
        "mode assignment",
        max_length=12,
        choices=TaskAssignmentMode.choices,
        default=TaskAssignmentMode.INDIVIDUAL,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        verbose_name = "template checklist"
        verbose_name_plural = "template checklist"
        ordering = ("area", "-version")
        constraints = [
            models.UniqueConstraint(
                fields=["clinic", "area", "session", "version", "audience_key"],
                name="uniq_template_area_session_version_audience",
            )
        ]

    def __str__(self) -> str:
        suffix = f" · {self.audience_key}" if self.audience_key else ""
        return f"{self.get_area_display()} · {self.get_session_display()} v{self.version}{suffix}"


class ChecklistTemplateItem(models.Model):
    template = models.ForeignKey(
        ChecklistTemplate, on_delete=models.CASCADE, related_name="items"
    )
    label = models.CharField("item", max_length=200)
    category = models.CharField("kategori", max_length=100, blank=True)
    required = models.BooleanField("wajib", default=True)
    input_type = models.CharField(max_length=12, choices=InputType.choices, default=InputType.CEKLIS)
    unit = models.CharField("satuan", max_length=30, blank=True)
    min_quantity = models.PositiveIntegerField("jumlah minimum", null=True, blank=True)
    options = models.JSONField("opsi pilihan", default=list, blank=True)
    photo_required = models.BooleanField("foto wajib", default=False)
    sort_order = models.PositiveIntegerField(default=0)
    help_text = models.CharField("petunjuk", max_length=250, blank=True)
    performer_roles = models.JSONField("role pelaksana", default=list, blank=True)
    verifier_roles = models.JSONField("role verifikator", default=list, blank=True)

    class Meta:
        verbose_name = "item template"
        verbose_name_plural = "item template"
        ordering = ("sort_order", "id")

    def __str__(self) -> str:
        return self.label

    def to_snapshot(self) -> dict:
        return {
            "id": self.pk,
            "label": self.label,
            "category": self.category,
            "required": self.required,
            "input_type": self.input_type,
            "unit": self.unit,
            "min_quantity": self.min_quantity,
            "options": list(self.options or []),
            "photo_required": self.photo_required,
            "sort_order": self.sort_order,
            "help_text": self.help_text,
            "performer_roles": list(self.performer_roles or []),
            "verifier_roles": list(self.verifier_roles or []),
        }


class RunStatus(models.TextChoices):
    BERJALAN = "BERJALAN", "Berjalan"
    SELESAI = "SELESAI", "Selesai"
    DITERIMA_DENGAN_CATATAN = "DITERIMA_DENGAN_CATATAN", "Diterima dengan catatan"


class ChecklistRun(models.Model):
    """Instance harian: template disalin sebagai snapshot (PRD 5, 20.2)."""

    operational_day = models.ForeignKey(
        "core.OperationalDay", on_delete=models.CASCADE, related_name="checklist_runs"
    )
    template = models.ForeignKey(ChecklistTemplate, on_delete=models.PROTECT)
    area = models.CharField(max_length=24, choices=ChecklistArea.choices)
    session = models.CharField(
        "sesi", max_length=12, choices=ChecklistSession.choices, default=ChecklistSession.OPENING
    )
    template_snapshot = models.JSONField()
    status = models.CharField(max_length=26, choices=RunStatus.choices, default=RunStatus.BERJALAN)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="checklist_reviews",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    exception_reason = models.TextField("alasan pengecualian", blank=True)

    class Meta:
        verbose_name = "checklist harian"
        verbose_name_plural = "checklist harian"
        ordering = ("area",)
        constraints = [
            models.UniqueConstraint(
                fields=["operational_day", "template"], name="uniq_run_day_template"
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_area_display()} · {self.get_session_display()} · {self.operational_day.date}"


class ResponseResult(models.TextChoices):
    BELUM = "BELUM", "Belum dicek"
    OK = "OK", "OK"
    TIDAK_LENGKAP = "TIDAK_LENGKAP", "Tidak lengkap"
    RUSAK = "RUSAK", "Rusak"
    TIDAK_BERLAKU = "TIDAK_BERLAKU", "Tidak berlaku"


PROBLEM_RESULTS = {ResponseResult.TIDAK_LENGKAP, ResponseResult.RUSAK}


class ChecklistResponse(models.Model):
    run = models.ForeignKey(ChecklistRun, on_delete=models.CASCADE, related_name="responses")
    item_snapshot = models.JSONField()
    label = models.CharField(max_length=200)
    category = models.CharField(max_length=100, blank=True)
    required = models.BooleanField(default=True)
    input_type = models.CharField(max_length=12, choices=InputType.choices, default=InputType.CEKLIS)
    unit = models.CharField(max_length=30, blank=True)
    min_quantity = models.PositiveIntegerField(null=True, blank=True)
    options = models.JSONField(default=list, blank=True)
    photo_required = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    performer_roles = models.JSONField(default=list, blank=True)
    verifier_roles = models.JSONField(default=list, blank=True)

    result = models.CharField(max_length=16, choices=ResponseResult.choices, default=ResponseResult.BELUM)
    quantity = models.PositiveIntegerField("jumlah aktual", null=True, blank=True)
    selection = models.CharField("pilihan", max_length=80, blank=True)
    note = models.TextField("catatan", blank=True)
    checked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="checklist_responses",
    )
    checked_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "respons checklist"
        verbose_name_plural = "respons checklist"
        ordering = ("sort_order", "id")

    def __str__(self) -> str:
        return f"{self.label}: {self.get_result_display()}"

    @property
    def is_problem(self) -> bool:
        return self.result in PROBLEM_RESULTS

    @property
    def below_minimum(self) -> bool:
        return bool(
            self.input_type == InputType.KUANTITAS
            and self.min_quantity is not None
            and self.quantity is not None
            and self.quantity < self.min_quantity
        )


class ChecklistFollowup(models.Model):
    """Penanda idempotensi task tindak lanjut dari respons bermasalah (PRD 8.1).

    Satu `ChecklistResponse` bermasalah hanya boleh menghasilkan satu
    `ActionItem`/`TaskAssignment` tindak lanjut walau proses pembuatannya
    dipicu ulang (double submit, retry).
    """

    response = models.OneToOneField(
        ChecklistResponse, on_delete=models.CASCADE, related_name="followup"
    )
    action_item = models.ForeignKey(
        "core.ActionItem", on_delete=models.CASCADE, related_name="checklist_followups"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="checklist_followups_created",
    )

    class Meta:
        verbose_name = "tindak lanjut checklist"
        verbose_name_plural = "tindak lanjut checklist"

    def __str__(self) -> str:
        return f"Tindak lanjut #{self.response_id} -> {self.action_item}"
