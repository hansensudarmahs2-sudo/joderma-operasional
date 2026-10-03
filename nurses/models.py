"""Roster perawat dan ledger giliran tindakan berkomisi (PRD 8.5)."""
from __future__ import annotations

from django.conf import settings
from django.db import models


class ProcedureCategory(models.Model):
    clinic = models.ForeignKey(
        "core.Clinic", on_delete=models.CASCADE, related_name="procedure_categories"
    )
    code = models.SlugField("kode", max_length=40)
    name = models.CharField("nama kategori tindakan", max_length=120)
    commissioned = models.BooleanField("berkomisi", default=True)
    active = models.BooleanField("aktif", default=True)

    class Meta:
        verbose_name = "kategori tindakan"
        verbose_name_plural = "kategori tindakan"
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(fields=["clinic", "code"], name="uniq_procedure_code")
        ]

    def __str__(self) -> str:
        return self.name


class NurseEligibility(models.Model):
    """Kompetensi/otorisasi perawat per kategori tindakan."""

    nurse = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="eligibilities"
    )
    category = models.ForeignKey(
        ProcedureCategory, on_delete=models.CASCADE, related_name="eligible_nurses"
    )
    active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "eligibility perawat"
        verbose_name_plural = "eligibility perawat"
        constraints = [
            models.UniqueConstraint(fields=["nurse", "category"], name="uniq_nurse_category")
        ]

    def __str__(self) -> str:
        return f"{self.nurse} · {self.category}"


class Availability(models.TextChoices):
    TERSEDIA = "TERSEDIA", "Tersedia"
    MENANGANI = "MENANGANI", "Sedang menangani"
    ISTIRAHAT = "ISTIRAHAT", "Istirahat"
    OFF_DUTY = "OFF_DUTY", "Pulang/off"


class NurseRosterEntry(models.Model):
    operational_day = models.ForeignKey(
        "core.OperationalDay", on_delete=models.CASCADE, related_name="nurse_roster"
    )
    nurse = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="roster_entries"
    )
    position = models.PositiveIntegerField("posisi antrean giliran", default=0)
    availability = models.CharField(
        max_length=10, choices=Availability.choices, default=Availability.TERSEDIA
    )
    turns_taken = models.PositiveIntegerField("giliran terpakai", default=0)
    note = models.CharField(max_length=200, blank=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "roster perawat"
        verbose_name_plural = "roster perawat"
        ordering = ("position", "id")
        constraints = [
            models.UniqueConstraint(
                fields=["operational_day", "nurse"], name="uniq_roster_day_nurse"
            )
        ]

    def __str__(self) -> str:
        return f"{self.position}. {self.nurse}"

    @property
    def is_available(self) -> bool:
        return self.availability == Availability.TERSEDIA


class TurnAction(models.TextChoices):
    ROSTER_DIBUAT = "ROSTER_DIBUAT", "Roster dibuat"
    TINDAKAN_DITUGASKAN = "TINDAKAN_DITUGASKAN", "Tindakan ditugaskan"
    TINDAKAN_DIMULAI = "TINDAKAN_DIMULAI", "Tindakan dimulai"
    TINDAKAN_SELESAI = "TINDAKAN_SELESAI", "Tindakan selesai (giliran terpakai)"
    TINDAKAN_BATAL = "TINDAKAN_BATAL", "Tindakan batal"
    SKIP = "SKIP", "Skip sementara"
    OVERRIDE = "OVERRIDE", "Override supervisor"
    TIDAK_ELIGIBLE = "TIDAK_ELIGIBLE", "Dilewati: tidak eligible"
    AVAILABILITY_BERUBAH = "AVAILABILITY_BERUBAH", "Ketersediaan berubah"
    PASIEN_DISERAHKAN = "PASIEN_DISERAHKAN", "Pasien diserahkan"
    URUTAN_DIUBAH = "URUTAN_DIUBAH", "Urutan papan diubah"


class CommissionTurnEvent(models.Model):
    """Ledger append-only: riwayat menjelaskan mengapa urutan terbentuk (PRD 20.5)."""

    operational_day = models.ForeignKey(
        "core.OperationalDay", on_delete=models.CASCADE, related_name="turn_events"
    )
    roster_entry = models.ForeignKey(
        NurseRosterEntry, on_delete=models.SET_NULL, null=True, blank=True, related_name="turn_events"
    )
    nurse = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="turn_events",
    )
    queue_entry = models.ForeignKey(
        "queueing.QueueEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="turn_events",
    )
    procedure_category = models.ForeignKey(
        ProcedureCategory, on_delete=models.SET_NULL, null=True, blank=True
    )
    action = models.CharField(max_length=22, choices=TurnAction.choices)
    reason = models.TextField(blank=True)
    position_before = models.PositiveIntegerField(null=True, blank=True)
    position_after = models.PositiveIntegerField(null=True, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="turn_events_created",
    )
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "event giliran"
        verbose_name_plural = "event giliran"
        ordering = ("-occurred_at", "-id")

    def __str__(self) -> str:
        return f"{self.get_action_display()} · {self.nurse}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise RuntimeError("CommissionTurnEvent bersifat append-only.")
        return super().save(*args, **kwargs)


class ProcedureStatus(models.TextChoices):
    DITUGASKAN = "DITUGASKAN", "Ditugaskan"
    DIMULAI = "DIMULAI", "Dimulai"
    SELESAI = "SELESAI", "Selesai"
    BATAL = "BATAL", "Batal"


class ProcedureAssignment(models.Model):
    """Tindakan berkomisi yang ditugaskan ke perawat."""

    operational_day = models.ForeignKey(
        "core.OperationalDay", on_delete=models.CASCADE, related_name="procedures"
    )
    queue_entry = models.ForeignKey(
        "queueing.QueueEntry", on_delete=models.SET_NULL, null=True, blank=True, related_name="procedures"
    )
    category = models.ForeignKey(ProcedureCategory, on_delete=models.PROTECT)
    nurse = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="procedures"
    )
    status = models.CharField(
        max_length=12, choices=ProcedureStatus.choices, default=ProcedureStatus.DITUGASKAN
    )
    note = models.CharField(max_length=250, blank=True)
    override_reason = models.TextField(blank=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="procedures_assigned",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "tindakan berkomisi"
        verbose_name_plural = "tindakan berkomisi"
        ordering = ("-assigned_at",)

    def __str__(self) -> str:
        return f"{self.category} · {self.nurse} ({self.get_status_display()})"


class NurseActionTally(models.Model):
    """Catatan tally tindakan untuk rekonsiliasi dengan Omnicare."""

    operational_day = models.ForeignKey("core.OperationalDay", on_delete=models.CASCADE, related_name="nurse_tallies")
    nurse = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="nurse_tallies")
    rm_number = models.CharField("nomor RM", max_length=32)
    patient_name = models.CharField("nama pasien", max_length=120)
    action_name = models.CharField("tindakan", max_length=160)
    tally = models.PositiveIntegerField("jumlah", default=1)
    entered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="nurse_tallies_entered")
    created_at = models.DateTimeField(auto_now_add=True)
    # Koreksi oleh Koordinator Shift / Direktur Operasional (riwayat lengkap ada di audit log).
    corrected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    corrected_at = models.DateTimeField(null=True, blank=True)
    correction_reason = models.CharField("alasan koreksi", max_length=250, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")

    def __str__(self) -> str:
        return f"{self.rm_number} · {self.patient_name} · {self.action_name}"
