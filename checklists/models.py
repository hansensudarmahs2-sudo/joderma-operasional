"""Checklist pembukaan: template berversi + snapshot harian (PRD 8.2)."""
from __future__ import annotations

from django.conf import settings
from django.db import models


class ChecklistArea(models.TextChoices):
    AKSES_UMUM = "AKSES_UMUM", "Akses dan area umum"
    KOMPUTER_SISTEM = "KOMPUTER_SISTEM", "Komputer dan sistem"
    RUANG_KONSULTASI = "RUANG_KONSULTASI", "Ruang konsultasi"
    RUANG_TINDAKAN = "RUANG_TINDAKAN", "Ruang tindakan estetik"


class InputType(models.TextChoices):
    CEKLIS = "CEKLIS", "Ceklis"
    KUANTITAS = "KUANTITAS", "Jumlah (kuantitas)"


class ChecklistTemplate(models.Model):
    clinic = models.ForeignKey("core.Clinic", on_delete=models.CASCADE, related_name="templates")
    name = models.CharField("nama", max_length=150)
    area = models.CharField("area", max_length=24, choices=ChecklistArea.choices)
    version = models.PositiveIntegerField("versi", default=1)
    active = models.BooleanField("aktif", default=True)
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
                fields=["clinic", "area", "version"], name="uniq_template_area_version"
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_area_display()} v{self.version}"


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
    photo_required = models.BooleanField("foto wajib", default=False)
    sort_order = models.PositiveIntegerField(default=0)
    help_text = models.CharField("petunjuk", max_length=250, blank=True)

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
            "photo_required": self.photo_required,
            "sort_order": self.sort_order,
            "help_text": self.help_text,
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
                fields=["operational_day", "area"], name="uniq_run_day_area"
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_area_display()} · {self.operational_day.date}"


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
    photo_required = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    result = models.CharField(max_length=16, choices=ResponseResult.choices, default=ResponseResult.BELUM)
    quantity = models.PositiveIntegerField("jumlah aktual", null=True, blank=True)
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
