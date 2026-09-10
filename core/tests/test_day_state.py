"""Unit test state machine hari operasional (PRD 20.2)."""
import pytest
from django.core.exceptions import ValidationError

from audit.models import AuditAction, AuditEvent
from cash.services import get_or_create_session, save_count, submit_for_verification, verify
from cash.models import CashSessionType
from checklists.models import ChecklistResponse, ResponseResult
from checklists.services import record_response
from core.models import DayStatus, OperationalDay
from core.services import (
    close_day,
    get_or_create_day,
    mark_ready,
    open_day,
    reopen_day,
    start_closing,
)

pytestmark = pytest.mark.django_db


def _complete_checklist(day, user):
    for r in ChecklistResponse.objects.filter(run__operational_day=day):
        record_response(
            r,
            user=user,
            result=ResponseResult.OK,
            quantity=25 if r.input_type == "KUANTITAS" else None,
        )


def _record_cash(day, counter, verifier, session_type=CashSessionType.OPENING):
    session = get_or_create_session(day, session_type, user=counter)
    save_count(
        session,
        user=counter,
        quantities={100000: 5},
        expected_total=500000,
    )
    submit_for_verification(session, counter)
    verify(session, verifier=verifier)
    return session


def test_only_one_day_per_date(clinic, template, supervisor):
    day1, created1 = get_or_create_day(clinic, user=supervisor)
    day2, created2 = get_or_create_day(clinic, user=supervisor)
    assert created1 is True and created2 is False
    assert day1.pk == day2.pk
    assert OperationalDay.objects.filter(clinic=clinic, date=day1.date).count() == 1


def test_template_snapshot_copied_on_day_creation(day, template):
    responses = ChecklistResponse.objects.filter(run__operational_day=day)
    assert responses.count() == 3
    assert responses.filter(label="Sarung tangan", min_quantity=20).exists()


def test_template_change_does_not_affect_history(day, template, supervisor):
    template.items.filter(label="Item opsional").delete()
    template.items.create(label="Item baru", required=True, sort_order=9)
    labels = set(
        ChecklistResponse.objects.filter(run__operational_day=day).values_list("label", flat=True)
    )
    assert "Item opsional" in labels
    assert "Item baru" not in labels


def test_ready_blocked_when_required_items_pending(day, supervisor):
    with pytest.raises(ValidationError) as exc:
        mark_ready(day, supervisor)
    assert "item wajib" in " ".join(exc.value.messages).lower()


def test_ready_blocked_when_cash_not_recorded(day, supervisor, kasir):
    _complete_checklist(day, kasir)
    with pytest.raises(ValidationError) as exc:
        mark_ready(day, supervisor)
    assert "kas awal" in " ".join(exc.value.messages).lower()


def test_ready_succeeds_when_all_conditions_met(day, supervisor, kasir):
    _complete_checklist(day, kasir)
    _record_cash(day, kasir, supervisor)
    mark_ready(day, supervisor)
    day.refresh_from_db()
    assert day.status == DayStatus.READY


def test_ready_with_issues_requires_reason(day, supervisor):
    with pytest.raises(ValidationError):
        mark_ready(day, supervisor, with_issues=True, reason="")

    mark_ready(day, supervisor, with_issues=True, reason="AC ruang tunggu rusak, teknisi dipanggil")
    day.refresh_from_db()
    assert day.status == DayStatus.READY_WITH_ISSUES
    assert AuditEvent.objects.filter(
        entity_type="operationalday", action=AuditAction.OVERRIDE
    ).exists()


def test_close_requires_cash_or_override(day, supervisor, kasir):
    _complete_checklist(day, kasir)
    _record_cash(day, kasir, supervisor)
    mark_ready(day, supervisor)
    open_day(day, supervisor)
    start_closing(day, supervisor)

    with pytest.raises(ValidationError):
        close_day(day, supervisor)

    close_day(day, supervisor, override_reason="Kas akhir dicatat manual di buku, sistem sempat mati")
    day.refresh_from_db()
    assert day.status == DayStatus.CLOSED


def test_closed_day_is_read_only_and_reopen_requires_reason(day, supervisor, kasir):
    _complete_checklist(day, kasir)
    _record_cash(day, kasir, supervisor)
    mark_ready(day, supervisor)
    open_day(day, supervisor)
    start_closing(day, supervisor)
    close_day(day, supervisor, override_reason="Override uji")

    response = ChecklistResponse.objects.filter(run__operational_day=day).first()
    with pytest.raises(ValidationError):
        record_response(response, user=kasir, result=ResponseResult.RUSAK, note="test")

    with pytest.raises(ValidationError):
        reopen_day(day, supervisor, reason="")

    reopen_day(day, supervisor, reason="Koreksi catatan kas akhir")
    day.refresh_from_db()
    assert day.status == DayStatus.OPEN
    assert AuditEvent.objects.filter(action=AuditAction.REOPEN).exists()
