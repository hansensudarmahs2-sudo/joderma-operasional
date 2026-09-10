"""Kas: modal, kembalian, hitung pecahan, dual verification (PRD 8.3)."""
from __future__ import annotations

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class CashSessionType(models.TextChoices):
    OPENING = "OPENING", "Kas awal"
    CLOSING = "CLOSING", "Kas akhir"


class CashStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    MENUNGGU_VERIFIKASI = "MENUNGGU_VERIFIKASI", "Menunggu verifikasi"
    SESUAI = "SESUAI", "Sesuai"
    SELISIH = "SELISIH", "Selisih"
    DISETUJUI_DENGAN_CATATAN = "DISETUJUI_DENGAN_CATATAN", "Disetujui dengan catatan"


class CashSession(models.Model):
    operational_day = models.ForeignKey(
        "core.OperationalDay", on_delete=models.CASCADE, related_name="cash_sessions"
    )
    session_type = models.CharField("jenis", max_length=10, choices=CashSessionType.choices)
    shift = models.CharField("shift", max_length=40, blank=True)

    expected_total = models.BigIntegerField("jumlah diharapkan (Rp)", default=0)
    actual_total = models.BigIntegerField("jumlah aktual (Rp)", default=0)
    change_fund_total = models.BigIntegerField("uang kembalian (Rp)", default=0)
    other_funds_total = models.BigIntegerField("dana kas lain (Rp)", default=0)
    variance = models.BigIntegerField("selisih (Rp)", default=0)

    status = models.CharField(max_length=26, choices=CashStatus.choices, default=CashStatus.DRAFT)
    note = models.TextField("catatan", blank=True)

    counted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="cash_counts",
    )
    counted_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    correction_reason = models.TextField("alasan koreksi", blank=True)
    corrected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cash_corrections",
    )
    version = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "sesi kas"
        verbose_name_plural = "sesi kas"
        ordering = ("operational_day", "session_type")
        constraints = [
            models.UniqueConstraint(
                fields=["operational_day", "session_type", "shift"],
                name="uniq_cash_day_type_shift",
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_session_type_display()} {self.operational_day.date}"

    def recompute(self) -> None:
        self.actual_total = sum(d.subtotal for d in self.denominations.all())
        self.variance = self.actual_total - self.expected_total

    @property
    def is_verified(self) -> bool:
        return self.status in {
            CashStatus.SESUAI,
            CashStatus.SELISIH,
            CashStatus.DISETUJUI_DENGAN_CATATAN,
        }

    @property
    def is_editable_by_counter(self) -> bool:
        return self.status in {CashStatus.DRAFT, CashStatus.MENUNGGU_VERIFIKASI}


class CashDenominationCount(models.Model):
    cash_session = models.ForeignKey(
        CashSession, on_delete=models.CASCADE, related_name="denominations"
    )
    denomination = models.PositiveIntegerField("pecahan (Rp)")
    quantity = models.PositiveIntegerField("jumlah", default=0, validators=[MinValueValidator(0)])

    class Meta:
        verbose_name = "rincian pecahan"
        verbose_name_plural = "rincian pecahan"
        ordering = ("-denomination",)
        constraints = [
            models.UniqueConstraint(
                fields=["cash_session", "denomination"], name="uniq_cash_denomination"
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gte=0), name="cash_quantity_non_negative"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.denomination} x {self.quantity}"

    @property
    def subtotal(self) -> int:
        return int(self.denomination) * int(self.quantity)


class VerificationResult(models.TextChoices):
    SESUAI = "SESUAI", "Sesuai"
    SELISIH = "SELISIH", "Selisih"
    DISETUJUI_DENGAN_CATATAN = "DISETUJUI_DENGAN_CATATAN", "Disetujui dengan catatan"
    DITOLAK = "DITOLAK", "Ditolak / hitung ulang"


class CashVerification(models.Model):
    cash_session = models.ForeignKey(
        CashSession, on_delete=models.CASCADE, related_name="verifications"
    )
    verifier = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="cash_verifications"
    )
    recounted_total = models.BigIntegerField("total hitung ulang (Rp)", null=True, blank=True)
    result = models.CharField(max_length=26, choices=VerificationResult.choices)
    note = models.TextField("catatan", blank=True)
    verified_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "verifikasi kas"
        verbose_name_plural = "verifikasi kas"
        ordering = ("-verified_at",)

    def __str__(self) -> str:
        return f"{self.cash_session} · {self.get_result_display()}"
