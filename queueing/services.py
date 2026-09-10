"""Service antrean: nomor unik, transisi status, payment event, reorder (PRD 8.4)."""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from audit.models import AuditAction
from audit.services import log_create, log_event, log_update, snapshot
from core.locking import assert_current_version
from core.models import ClinicConfig

from .models import (
    PaymentStatus,
    PaymentStatusEvent,
    QUEUE_TRANSITIONS,
    QueueEntry,
    QueueStatus,
    QueueStatusEvent,
    REASON_REQUIRED_STATUSES,
)

KEEP_NUMBER_DEFAULT = [PaymentStatus.SUDAH_BAYAR, PaymentStatus.DIBEBASKAN]


def keep_number_statuses(clinic) -> list[str]:
    return list(ClinicConfig.get(clinic, "queue.keep_number_statuses", KEEP_NUMBER_DEFAULT))


def next_queue_no(day) -> int:
    current = QueueEntry.objects.filter(operational_day=day).aggregate(m=Max("queue_no"))["m"]
    return (current or 0) + 1


@transaction.atomic
def create_entry(
    day,
    *,
    user,
    display_name: str,
    visit_type: str,
    patient_ref: str = "",
    alias: str = "",
    appointment_at=None,
    payment_status: str = PaymentStatus.BELUM_BAYAR,
    note: str = "",
) -> QueueEntry:
    day.assert_editable()
    display_name = (display_name or "").strip()
    if not display_name:
        raise ValidationError("Nama tampilan wajib diisi.")

    if payment_status not in dict(PaymentStatus.choices):
        raise ValidationError("Status pembayaran tidak dikenali.")

    queue_no = next_queue_no(day)
    entry = QueueEntry.objects.create(
        operational_day=day,
        queue_no=queue_no,
        position=queue_no,
        display_name=display_name,
        alias=(alias or "").strip(),
        patient_ref=(patient_ref or "").strip(),
        visit_type=visit_type,
        appointment_at=appointment_at,
        payment_status=payment_status,
        note=(note or "").strip(),
        created_by=user,
    )
    PaymentStatusEvent.objects.create(
        queue_entry=entry, from_status="", to_status=payment_status, actor=user, reason="Entri baru"
    )
    QueueStatusEvent.objects.create(
        queue_entry=entry, from_status="", to_status=entry.queue_status, actor=user
    )
    log_create(entry, actor=user, label=f"Antrean #{queue_no}")
    return entry


@transaction.atomic
def change_queue_status(
    entry: QueueEntry, *, user, to_status: str, reason: str = "", expected_version: int | None = None
) -> QueueEntry:
    entry.operational_day.assert_editable()
    assert_current_version(entry, expected_version)

    if to_status == entry.queue_status:
        return entry
    allowed = QUEUE_TRANSITIONS.get(entry.queue_status, set())
    if to_status not in allowed:
        raise ValidationError(
            f"Perubahan status dari {entry.get_queue_status_display()} tidak diizinkan."
        )
    reason = (reason or "").strip()
    if to_status in REASON_REQUIRED_STATUSES and not reason:
        raise ValidationError("Alasan wajib diisi untuk pembatalan atau no-show.")
    if entry.queue_status in {QueueStatus.BATAL, QueueStatus.NO_SHOW} and not reason:
        raise ValidationError("Alasan wajib diisi untuk mengaktifkan kembali entri.")

    before = snapshot(entry)
    from_status = entry.queue_status
    entry.queue_status = to_status
    if to_status == QueueStatus.CHECK_IN and entry.arrived_at is None:
        entry.arrived_at = timezone.now()
    entry.version += 1
    entry.save()
    QueueStatusEvent.objects.create(
        queue_entry=entry, from_status=from_status, to_status=to_status, actor=user, reason=reason
    )
    log_update(
        entry,
        before,
        actor=user,
        reason=reason,
        action=AuditAction.CANCEL if to_status == QueueStatus.BATAL else AuditAction.UPDATE,
    )
    return entry


@transaction.atomic
def change_payment_status(
    entry: QueueEntry, *, user, to_status: str, reason: str = "", payment_ref: str = ""
) -> QueueEntry:
    """Setiap perubahan pembayaran membentuk event historis (PRD 20.4)."""
    entry.operational_day.assert_editable()
    if to_status not in dict(PaymentStatus.choices):
        raise ValidationError("Status pembayaran tidak dikenali.")

    reason = (reason or "").strip()
    if to_status == PaymentStatus.REFUND and not reason:
        raise ValidationError("Alasan wajib diisi untuk refund.")
    if to_status == PaymentStatus.DIBEBASKAN:
        from core.permissions import is_owner, is_supervisor

        if not (is_supervisor(user) or is_owner(user)):
            raise ValidationError("Hanya supervisor yang dapat membebaskan biaya konsultasi.")
        if not reason:
            raise ValidationError("Alasan wajib diisi untuk pembebasan biaya.")

    before = snapshot(entry)
    from_status = entry.payment_status
    entry.payment_status = to_status
    if payment_ref:
        entry.payment_ref = payment_ref.strip()
    entry.version += 1
    entry.save()
    PaymentStatusEvent.objects.create(
        queue_entry=entry,
        from_status=from_status,
        to_status=to_status,
        actor=user,
        reason=reason,
        payment_ref=entry.payment_ref,
    )
    log_update(entry, before, actor=user, reason=reason, label=f"Pembayaran antrean #{entry.queue_no}")
    return entry


@transaction.atomic
def reorder(entry: QueueEntry, *, user, new_position: int, reason: str) -> QueueEntry:
    """Reorder manual wajib alasan dan tercatat sebagai override (PRD 20.4)."""
    if not reason.strip():
        raise ValidationError("Alasan wajib diisi untuk mengubah urutan antrean.")
    entry.operational_day.assert_editable()

    before = snapshot(entry)
    entries = list(
        QueueEntry.objects.select_for_update()
        .filter(operational_day=entry.operational_day)
        .order_by("position", "queue_no")
    )
    entries = [e for e in entries if e.pk != entry.pk]
    new_position = max(1, min(int(new_position), len(entries) + 1))
    entries.insert(new_position - 1, entry)
    for idx, e in enumerate(entries, start=1):
        if e.position != idx:
            e.position = idx
            e.save(update_fields=["position"])
    entry.refresh_from_db()
    log_update(entry, before, actor=user, reason=reason, action=AuditAction.OVERRIDE)
    return entry


@transaction.atomic
def set_priority(entry: QueueEntry, *, user, reason: str) -> QueueEntry:
    if not reason.strip():
        raise ValidationError("Alasan wajib diisi untuk menandai pasien prioritas.")
    before = snapshot(entry)
    entry.priority_flag = True
    entry.priority_reason = reason.strip()
    entry.version += 1
    entry.save()
    log_update(entry, before, actor=user, reason=reason, action=AuditAction.OVERRIDE)
    return entry


def queue_summary(day) -> dict:
    entries = QueueEntry.objects.filter(operational_day=day)
    keep = keep_number_statuses(day.clinic)
    return {
        "total": entries.count(),
        "sudah_bayar": entries.filter(payment_status__in=keep).count(),
        "menunggu": entries.filter(
            queue_status__in=[QueueStatus.MENUNGGU, QueueStatus.CHECK_IN, QueueStatus.DIPESAN]
        ).count(),
        "dilayani": entries.filter(
            queue_status__in=[QueueStatus.DIPANGGIL, QueueStatus.DILAYANI]
        ).count(),
        "selesai": entries.filter(queue_status=QueueStatus.SELESAI).count(),
        "batal": entries.filter(
            queue_status__in=[QueueStatus.BATAL, QueueStatus.NO_SHOW]
        ).count(),
    }
