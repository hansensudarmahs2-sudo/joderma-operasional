"""Test kas: kalkulasi pecahan, selisih, dual-control, koreksi (PRD 20.3)."""
import pytest
from django.core.exceptions import ValidationError

from audit.models import AuditAction, AuditEvent
from cash.models import CashSessionType, CashStatus, VerificationResult
from cash.services import (
    correct_after_verification,
    get_or_create_session,
    save_count,
    submit_for_verification,
    verify,
)
from core.models import ClinicConfig

pytestmark = pytest.mark.django_db


def _session(day, user):
    return get_or_create_session(day, CashSessionType.OPENING, user=user)


def test_denomination_total_is_correct(day, kasir):
    s = _session(day, kasir)
    save_count(s, user=kasir, quantities={100000: 3, 50000: 2, 20000: 1}, expected_total=420000)
    s.refresh_from_db()
    assert s.actual_total == 3 * 100000 + 2 * 50000 + 20000 == 420000
    assert s.variance == 0
    assert s.status == CashStatus.DRAFT


def test_negative_quantity_rejected(day, kasir):
    s = _session(day, kasir)
    with pytest.raises(ValidationError) as exc:
        save_count(s, user=kasir, quantities={100000: -1}, expected_total=0)
    assert "negatif" in " ".join(exc.value.messages).lower()


def test_variance_computed_and_note_required(day, kasir):
    s = _session(day, kasir)
    with pytest.raises(ValidationError) as exc:
        save_count(s, user=kasir, quantities={100000: 4}, expected_total=500000)
    assert "catatan" in " ".join(exc.value.messages).lower()

    save_count(
        s, user=kasir, quantities={100000: 4}, expected_total=500000, note="Kurang 1 lembar 100rb"
    )
    s.refresh_from_db()
    assert s.variance == -100000


def test_dual_control_blocks_self_verification(day, kasir):
    s = _session(day, kasir)
    save_count(s, user=kasir, quantities={100000: 5}, expected_total=500000)
    submit_for_verification(s, kasir)
    with pytest.raises(ValidationError) as exc:
        verify(s, verifier=kasir)
    assert "dual-control" in " ".join(exc.value.messages).lower()


def test_second_person_can_verify(day, kasir, supervisor):
    s = _session(day, kasir)
    save_count(s, user=kasir, quantities={100000: 5}, expected_total=500000)
    submit_for_verification(s, kasir)
    verify(s, verifier=supervisor, recounted_total=500000)
    s.refresh_from_db()
    assert s.status == CashStatus.SESUAI
    assert AuditEvent.objects.filter(entity_type="cashsession", action=AuditAction.VERIFY).exists()


def test_recount_mismatch_rejected(day, kasir, supervisor):
    s = _session(day, kasir)
    save_count(s, user=kasir, quantities={100000: 5}, expected_total=500000)
    submit_for_verification(s, kasir)
    with pytest.raises(ValidationError) as exc:
        verify(s, verifier=supervisor, recounted_total=450000)
    assert "hitung ulang" in " ".join(exc.value.messages).lower()


def test_variance_result_marks_selisih(day, kasir, supervisor):
    s = _session(day, kasir)
    save_count(s, user=kasir, quantities={100000: 4}, expected_total=500000, note="selisih")
    submit_for_verification(s, kasir)
    verify(s, verifier=supervisor, note="Dicatat, dicek ulang sore")
    s.refresh_from_db()
    assert s.status == CashStatus.SELISIH


def test_dual_control_can_be_disabled_by_config(clinic, day, kasir):
    ClinicConfig.set(clinic, "cash.dual_control_enabled", False)
    s = _session(day, kasir)
    save_count(s, user=kasir, quantities={50000: 2}, expected_total=100000)
    submit_for_verification(s, kasir)
    verify(s, verifier=kasir)
    s.refresh_from_db()
    assert s.status == CashStatus.SESUAI


def test_front_desk_can_be_second_counter(day, supervisor, kasir):
    """Regresi: bila hanya supervisor yang boleh verifikasi dan supervisor pula
    yang menghitung, dual-control membuat kas tidak pernah dapat diverifikasi."""
    from core.permissions import can_correct_cash, can_verify_cash

    assert can_verify_cash(kasir) is True
    assert can_correct_cash(kasir) is False  # koreksi tetap hanya supervisor

    s = _session(day, supervisor)
    save_count(s, user=supervisor, quantities={100000: 5}, expected_total=500000)
    submit_for_verification(s, supervisor)
    verify(s, verifier=kasir, recounted_total=500000)
    s.refresh_from_db()
    assert s.status == CashStatus.SESUAI


def test_correction_after_verification_requires_reason_and_keeps_history(day, kasir, supervisor):
    s = _session(day, kasir)
    save_count(s, user=kasir, quantities={100000: 5}, expected_total=500000)
    submit_for_verification(s, kasir)
    verify(s, verifier=supervisor)

    with pytest.raises(ValidationError):
        save_count(s, user=kasir, quantities={100000: 6}, expected_total=500000, note="x")

    with pytest.raises(ValidationError):
        correct_after_verification(
            s, supervisor=supervisor, quantities={100000: 6}, expected_total=600000, reason=""
        )

    correct_after_verification(
        s,
        supervisor=supervisor,
        quantities={100000: 6},
        expected_total=600000,
        reason="Satu lembar terselip di laci kedua",
    )
    s.refresh_from_db()
    assert s.actual_total == 600000
    assert s.status == CashStatus.MENUNGGU_VERIFIKASI

    override = AuditEvent.objects.filter(
        entity_type="cashsession", action=AuditAction.OVERRIDE
    ).first()
    assert override is not None
    assert override.before_json["actual_total"] == 500000
    assert override.after_json["actual_total"] == 600000
