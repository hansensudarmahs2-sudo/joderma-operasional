"""Jadwal istirahat, makan, dan ibadah (PRD 8.6)."""
from __future__ import annotations

from django.conf import settings
from django.db import models


class BreakType(models.TextChoices):
    ISTIRAHAT = "ISTIRAHAT", "Istirahat"
    MAKAN = "MAKAN", "Makan"
    IBADAH = "IBADAH", "Ibadah"
    LAINNYA = "LAINNYA", "Lainnya"


class BreakStatus(models.TextChoices):
    DIJADWALKAN = "DIJADWALKAN", "Dijadwalkan"
    BERJALAN = "BERJALAN", "Berjalan"
    SELESAI = "SELESAI", "Selesai"
    BATAL = "BATAL", "Batal"


class BreakSchedule(models.Model):
    clinic = models.ForeignKey("core.Clinic", on_delete=models.CASCADE, related_name="breaks")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="break_schedules"
    )
    date = models.DateField("tanggal")
    break_type = models.CharField("jenis", max_length=10, choices=BreakType.choices)
    start_at = models.DateTimeField("mulai")
    end_at = models.DateTimeField("selesai")
    location_note = models.CharField("lokasi/catatan", max_length=200, blank=True)
    status = models.CharField(max_length=12, choices=BreakStatus.choices, default=BreakStatus.DIJADWALKAN)
    staffing_override_reason = models.TextField("alasan override minimum staf", blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="breaks_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "jadwal istirahat"
        verbose_name_plural = "jadwal istirahat"
        ordering = ("date", "start_at")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_at__gt=models.F("start_at")),
                name="break_end_after_start",
            )
        ]
        indexes = [models.Index(fields=["date", "user"])]

    def __str__(self) -> str:
        return f"{self.user} · {self.get_break_type_display()} {self.start_at:%H:%M}-{self.end_at:%H:%M}"

    @property
    def duration_minutes(self) -> int:
        return int((self.end_at - self.start_at).total_seconds() // 60)
