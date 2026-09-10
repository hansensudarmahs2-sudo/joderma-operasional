"""Test antrean: nomor unik, keep number, event pembayaran, reorder (PRD 20.4)."""
import pytest
from django.core.exceptions import ValidationError

from audit.models import AuditAction, AuditEvent
from queueing.models import PaymentStatus, PaymentStatusEvent, QueueEntry, QueueStatus, VisitType
from queueing.services import (
    change_payment_status,
    change_queue_status,
    create_entry,
    keep_number_statuses,
    queue_summary,
    reorder,
)

pytestmark = pytest.mark.django_db


def _entry(day, user, name="Pasien Uji"):
    return create_entry(day, user=user, display_name=name, visit_type=VisitType.KONSULTASI)


def test_queue_numbers_unique_and_sequential(day, kasir):
    a = _entry(day, kasir, "A")
    b = _entry(day, kasir, "B")
    c = _entry(day, kasir, "C")
    assert [a.queue_no, b.queue_no, c.queue_no] == [1, 2, 3]
    assert QueueEntry.objects.filter(operational_day=day).count() == 3


def test_display_name_required(day, kasir):
    with pytest.raises(ValidationError):
        create_entry(day, user=kasir, display_name="  ", visit_type=VisitType.KONSULTASI)


def test_form_default_payment_matches_policy(client, clinic, day, kasir):
    """Regresi: default form harus 'Belum bayar', bukan opsi pertama enum."""
    from django.urls import reverse

    client.login(username="kasir", password="TestPassword123!")
    body = client.get(reverse("queueing:create")).content.decode()
    assert 'value="BELUM_BAYAR" selected' in body


def test_unknown_payment_status_rejected(day, kasir):
    with pytest.raises(ValidationError):
        create_entry(
            day, user=kasir, display_name="X", visit_type=VisitType.KONSULTASI,
            payment_status="TIDAK_ADA",
        )


def test_keep_number_rule(day, kasir, clinic):
    e = _entry(day, kasir)
    keep = keep_number_statuses(clinic)
    assert e.keeps_number(keep) is False
    change_payment_status(e, user=kasir, to_status=PaymentStatus.SUDAH_BAYAR)
    e.refresh_from_db()
    assert e.keeps_number(keep) is True


def test_payment_change_creates_event(day, kasir):
    e = _entry(day, kasir)
    change_payment_status(e, user=kasir, to_status=PaymentStatus.SUDAH_BAYAR, payment_ref="TRX-1")
    events = PaymentStatusEvent.objects.filter(queue_entry=e).order_by("occurred_at")
    assert events.count() == 2  # entri baru + perubahan
    last = events.last()
    assert last.to_status == PaymentStatus.SUDAH_BAYAR and last.actor == kasir


def test_refund_requires_reason(day, kasir):
    e = _entry(day, kasir)
    change_payment_status(e, user=kasir, to_status=PaymentStatus.SUDAH_BAYAR)
    with pytest.raises(ValidationError) as exc:
        change_payment_status(e, user=kasir, to_status=PaymentStatus.REFUND, reason="")
    assert "alasan" in " ".join(exc.value.messages).lower()
    change_payment_status(e, user=kasir, to_status=PaymentStatus.REFUND, reason="Pasien membatalkan")
    e.refresh_from_db()
    assert e.payment_status == PaymentStatus.REFUND


def test_dibebaskan_only_by_supervisor(day, kasir, supervisor):
    e = _entry(day, kasir)
    with pytest.raises(ValidationError) as exc:
        change_payment_status(
            e, user=kasir, to_status=PaymentStatus.DIBEBASKAN, reason="Karyawan"
        )
    assert "supervisor" in " ".join(exc.value.messages).lower()
    change_payment_status(
        e, user=supervisor, to_status=PaymentStatus.DIBEBASKAN, reason="Keluarga karyawan"
    )
    e.refresh_from_db()
    assert e.payment_status == PaymentStatus.DIBEBASKAN


def test_invalid_status_transition_blocked(day, kasir):
    e = _entry(day, kasir)
    with pytest.raises(ValidationError):
        change_queue_status(e, user=kasir, to_status=QueueStatus.SELESAI)


def test_no_show_requires_reason(day, kasir):
    e = _entry(day, kasir)
    change_queue_status(e, user=kasir, to_status=QueueStatus.CHECK_IN)
    change_queue_status(e, user=kasir, to_status=QueueStatus.MENUNGGU)
    with pytest.raises(ValidationError):
        change_queue_status(e, user=kasir, to_status=QueueStatus.NO_SHOW, reason="")
    change_queue_status(e, user=kasir, to_status=QueueStatus.NO_SHOW, reason="Tidak hadir 20 menit")
    e.refresh_from_db()
    assert e.queue_status == QueueStatus.NO_SHOW


def test_reorder_requires_reason_and_audits(day, kasir, supervisor):
    a = _entry(day, kasir, "A")
    b = _entry(day, kasir, "B")
    c = _entry(day, kasir, "C")
    with pytest.raises(ValidationError):
        reorder(c, user=supervisor, new_position=1, reason="")

    reorder(c, user=supervisor, new_position=1, reason="Pasien lansia didahulukan")
    positions = list(
        QueueEntry.objects.filter(operational_day=day).order_by("position").values_list("display_name", flat=True)
    )
    assert positions == ["C", "A", "B"]
    assert AuditEvent.objects.filter(entity_type="queueentry", action=AuditAction.OVERRIDE).exists()


def test_masked_name_hides_identity(day, kasir):
    e = create_entry(
        day, user=kasir, display_name="Budi Santoso", visit_type=VisitType.KONSULTASI
    )
    assert e.masked_name == "B*** S."
    e.alias = "B.S."
    assert e.masked_name == "B.S."


def test_queue_summary(day, kasir):
    a = _entry(day, kasir, "A")
    b = _entry(day, kasir, "B")
    change_payment_status(a, user=kasir, to_status=PaymentStatus.SUDAH_BAYAR)
    summary = queue_summary(day)
    assert summary["total"] == 2 and summary["sudah_bayar"] == 1
