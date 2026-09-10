"""Antrean pasien dan status pembayaran konsultasi (PRD 8.4).

Minimum necessary data: TIDAK menyimpan diagnosis, foto klinis, atau catatan medis.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models


class VisitType(models.TextChoices):
    KONSULTASI = "KONSULTASI", "Konsultasi"
    TINDAKAN = "TINDAKAN", "Tindakan"
    KONTROL = "KONTROL", "Kontrol"
    LAINNYA = "LAINNYA", "Lainnya"


class PaymentStatus(models.TextChoices):
    BELUM_PERLU = "BELUM_PERLU", "Belum perlu"
    BELUM_BAYAR = "BELUM_BAYAR", "Belum bayar"
    SUDAH_BAYAR = "SUDAH_BAYAR", "Sudah bayar"
    DIBEBASKAN = "DIBEBASKAN", "Dibebaskan"
    REFUND = "REFUND", "Refund"


class QueueStatus(models.TextChoices):
    DIPESAN = "DIPESAN", "Dipesan"
    CHECK_IN = "CHECK_IN", "Check-in"
    MENUNGGU = "MENUNGGU", "Menunggu"
    DIPANGGIL = "DIPANGGIL", "Dipanggil"
    DILAYANI = "DILAYANI", "Dilayani"
    SELESAI = "SELESAI", "Selesai"
    BATAL = "BATAL", "Batal"
    NO_SHOW = "NO_SHOW", "No-show"


ACTIVE_QUEUE_STATUSES = {
    QueueStatus.DIPESAN,
    QueueStatus.CHECK_IN,
    QueueStatus.MENUNGGU,
    QueueStatus.DIPANGGIL,
    QueueStatus.DILAYANI,
}

# Transisi status antrean yang diizinkan
QUEUE_TRANSITIONS: dict[str, set[str]] = {
    QueueStatus.DIPESAN: {QueueStatus.CHECK_IN, QueueStatus.BATAL, QueueStatus.NO_SHOW},
    QueueStatus.CHECK_IN: {QueueStatus.MENUNGGU, QueueStatus.BATAL, QueueStatus.NO_SHOW},
    QueueStatus.MENUNGGU: {QueueStatus.DIPANGGIL, QueueStatus.BATAL, QueueStatus.NO_SHOW},
    QueueStatus.DIPANGGIL: {
        QueueStatus.DILAYANI,
        QueueStatus.MENUNGGU,
        QueueStatus.NO_SHOW,
        QueueStatus.BATAL,
    },
    QueueStatus.DILAYANI: {QueueStatus.SELESAI, QueueStatus.BATAL},
    QueueStatus.SELESAI: set(),
    QueueStatus.BATAL: {QueueStatus.MENUNGGU},
    QueueStatus.NO_SHOW: {QueueStatus.MENUNGGU},
}

REASON_REQUIRED_STATUSES = {QueueStatus.BATAL, QueueStatus.NO_SHOW}


class QueueEntry(models.Model):
    operational_day = models.ForeignKey(
        "core.OperationalDay", on_delete=models.CASCADE, related_name="queue_entries"
    )
    queue_no = models.PositiveIntegerField("nomor antrean")
    patient_ref = models.CharField("ID pasien internal", max_length=40, blank=True)
    display_name = models.CharField("nama tampilan", max_length=120)
    alias = models.CharField("inisial/alias", max_length=20, blank=True)
    appointment_at = models.DateTimeField("waktu appointment", null=True, blank=True)
    arrived_at = models.DateTimeField("waktu kedatangan", null=True, blank=True)
    visit_type = models.CharField(max_length=12, choices=VisitType.choices, default=VisitType.KONSULTASI)
    payment_status = models.CharField(
        "status pembayaran konsultasi",
        max_length=12,
        choices=PaymentStatus.choices,
        default=PaymentStatus.BELUM_BAYAR,
    )
    payment_ref = models.CharField("referensi pembayaran internal", max_length=60, blank=True)
    queue_status = models.CharField(
        max_length=10, choices=QueueStatus.choices, default=QueueStatus.DIPESAN
    )
    position = models.PositiveIntegerField("urutan tampil", default=0)
    priority_flag = models.BooleanField("prioritas disetujui", default=False)
    priority_reason = models.CharField(max_length=200, blank=True)
    note = models.CharField("catatan operasional", max_length=250, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="queue_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "entri antrean"
        verbose_name_plural = "entri antrean"
        ordering = ("position", "queue_no")
        constraints = [
            models.UniqueConstraint(
                fields=["operational_day", "queue_no"], name="uniq_queue_day_number"
            )
        ]

    def __str__(self) -> str:
        return f"#{self.queue_no} {self.display_name}"

    @property
    def masked_name(self) -> str:
        """Nama disamarkan untuk layar bersama (PRD 13.3, 15.2)."""
        if self.alias:
            return self.alias
        parts = [p for p in str(self.display_name).split() if p]
        if not parts:
            return "—"
        first = parts[0]
        head = first[0].upper() + ("*" * max(len(first) - 1, 1))
        tail = f" {parts[-1][0].upper()}." if len(parts) > 1 else ""
        return head + tail

    def keeps_number(self, keep_statuses: list[str]) -> bool:
        return self.payment_status in keep_statuses

    @property
    def is_active(self) -> bool:
        return self.queue_status in ACTIVE_QUEUE_STATUSES


class PaymentStatusEvent(models.Model):
    """Riwayat perubahan pembayaran; append-only (PRD 20.4)."""

    queue_entry = models.ForeignKey(
        QueueEntry, on_delete=models.CASCADE, related_name="payment_events"
    )
    from_status = models.CharField(max_length=12, choices=PaymentStatus.choices, blank=True)
    to_status = models.CharField(max_length=12, choices=PaymentStatus.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="payment_events"
    )
    reason = models.CharField(max_length=250, blank=True)
    payment_ref = models.CharField(max_length=60, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "event pembayaran"
        verbose_name_plural = "event pembayaran"
        ordering = ("-occurred_at",)

    def __str__(self) -> str:
        return f"{self.queue_entry} {self.from_status}→{self.to_status}"


class QueueStatusEvent(models.Model):
    queue_entry = models.ForeignKey(
        QueueEntry, on_delete=models.CASCADE, related_name="status_events"
    )
    from_status = models.CharField(max_length=10, blank=True)
    to_status = models.CharField(max_length=10)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="queue_status_events"
    )
    reason = models.CharField(max_length=250, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-occurred_at",)
