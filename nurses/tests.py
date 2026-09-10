"""Test rotasi perawat: deterministik, ledger, skip/override (PRD 20.5)."""
import pytest
from django.core.exceptions import ValidationError

from core.models import ClinicConfig
from nurses.models import (
    Availability,
    CommissionTurnEvent,
    NurseRosterEntry,
    ProcedureStatus,
    TurnAction,
)
from nurses.services import (
    assign_procedure,
    cancel_procedure,
    complete_procedure,
    next_nurse,
    set_availability,
    set_roster,
    skip_nurse,
    start_procedure,
)

pytestmark = pytest.mark.django_db


def _roster(day, supervisor, nurses):
    return set_roster(day, supervisor=supervisor, nurse_ids=[n.pk for n in nurses])


def test_roster_produces_deterministic_order(day, supervisor, eligible_nurses):
    entries = _roster(day, supervisor, eligible_nurses)
    assert [e.position for e in entries] == [1, 2]
    assert next_nurse(day).nurse_id == eligible_nurses[0].pk


def test_empty_roster_rejected(day, supervisor):
    with pytest.raises(ValidationError):
        set_roster(day, supervisor=supervisor, nurse_ids=[])


def test_completed_procedure_moves_nurse_to_back(day, supervisor, eligible_nurses, kategori):
    _roster(day, supervisor, eligible_nurses)
    a, b = eligible_nurses

    assignment = assign_procedure(day, user=supervisor, category=kategori)
    assert assignment.nurse_id == a.pk

    complete_procedure(assignment, user=supervisor)
    assert next_nurse(day).nurse_id == b.pk
    entry_a = NurseRosterEntry.objects.get(operational_day=day, nurse=a)
    assert entry_a.position == 2 and entry_a.turns_taken == 1
    assert CommissionTurnEvent.objects.filter(action=TurnAction.TINDAKAN_SELESAI).exists()


def test_ineligible_nurse_requires_supervisor_override(day, supervisor, kasir, perawat, perawat_b, kategori):
    from nurses.models import NurseEligibility

    NurseEligibility.objects.create(nurse=perawat, category=kategori)
    _roster(day, supervisor, [perawat, perawat_b])

    with pytest.raises(ValidationError) as exc:
        assign_procedure(day, user=supervisor, category=kategori, nurse_id=perawat_b.pk)
    assert "override" in " ".join(exc.value.messages).lower()

    assignment = assign_procedure(
        day,
        user=supervisor,
        category=kategori,
        nurse_id=perawat_b.pk,
        override_reason="Perawat 1 sedang menangani pasien lain",
    )
    assert assignment.nurse_id == perawat_b.pk
    assert CommissionTurnEvent.objects.filter(action=TurnAction.TIDAK_ELIGIBLE).exists()


def test_non_supervisor_cannot_override(day, supervisor, kasir, eligible_nurses, kategori):
    _roster(day, supervisor, eligible_nurses)
    with pytest.raises(ValidationError) as exc:
        assign_procedure(
            day,
            user=kasir,
            category=kategori,
            nurse_id=eligible_nurses[1].pk,
            override_reason="alasan apapun",
        )
    assert "supervisor" in " ".join(exc.value.messages).lower()


def test_skip_keeps_position_by_default(day, supervisor, eligible_nurses, kategori):
    _roster(day, supervisor, eligible_nurses)
    entry = NurseRosterEntry.objects.get(operational_day=day, nurse=eligible_nurses[0])
    with pytest.raises(ValidationError):
        skip_nurse(entry, user=supervisor, reason="")
    skip_nurse(entry, user=supervisor, reason="Sedang menyiapkan ruang")
    entry.refresh_from_db()
    assert entry.position == 1
    assert CommissionTurnEvent.objects.filter(action=TurnAction.SKIP).exists()


def test_skip_moves_to_back_when_configured(clinic, day, supervisor, eligible_nurses):
    ClinicConfig.set(clinic, "nurse.skip_keeps_position", False)
    _roster(day, supervisor, eligible_nurses)
    entry = NurseRosterEntry.objects.get(operational_day=day, nurse=eligible_nurses[0])
    skip_nurse(entry, user=supervisor, reason="Tidak tersedia")
    entry.refresh_from_db()
    assert entry.position == 2


def test_cancel_before_start_restores_position(day, supervisor, eligible_nurses, kategori):
    _roster(day, supervisor, eligible_nurses)
    assignment = assign_procedure(day, user=supervisor, category=kategori)
    with pytest.raises(ValidationError):
        cancel_procedure(assignment, user=supervisor, reason="")
    cancel_procedure(assignment, user=supervisor, reason="Pasien membatalkan")
    assert next_nurse(day).nurse_id == eligible_nurses[0].pk
    assignment.refresh_from_db()
    assert assignment.status == ProcedureStatus.BATAL


def test_cancel_after_start_counts_as_turn(day, supervisor, eligible_nurses, kategori):
    _roster(day, supervisor, eligible_nurses)
    assignment = assign_procedure(day, user=supervisor, category=kategori)
    start_procedure(assignment, user=supervisor)
    cancel_procedure(assignment, user=supervisor, reason="Pasien tidak nyaman, dihentikan")
    entry = NurseRosterEntry.objects.get(operational_day=day, nurse=eligible_nurses[0])
    assert entry.position == 2 and entry.turns_taken == 1


def test_unavailable_nurse_is_skipped(day, supervisor, eligible_nurses, kategori):
    _roster(day, supervisor, eligible_nurses)
    entry = NurseRosterEntry.objects.get(operational_day=day, nurse=eligible_nurses[0])
    set_availability(entry, user=supervisor, availability=Availability.OFF_DUTY, reason="Pulang awal")
    assert next_nurse(day).nurse_id == eligible_nurses[1].pk


def test_ledger_explains_current_order(day, supervisor, eligible_nurses, kategori):
    _roster(day, supervisor, eligible_nurses)
    assignment = assign_procedure(day, user=supervisor, category=kategori)
    complete_procedure(assignment, user=supervisor)
    events = CommissionTurnEvent.objects.filter(operational_day=day).order_by("id")
    actions = [e.action for e in events]
    assert TurnAction.ROSTER_DIBUAT in actions
    assert TurnAction.TINDAKAN_DITUGASKAN in actions
    assert TurnAction.TINDAKAN_SELESAI in actions
    finish = events.filter(action=TurnAction.TINDAKAN_SELESAI).first()
    assert finish.position_before == 1 and finish.position_after == 2


def test_turn_event_is_append_only(day, supervisor, eligible_nurses):
    _roster(day, supervisor, eligible_nurses)
    event = CommissionTurnEvent.objects.first()
    event.reason = "diubah"
    with pytest.raises(RuntimeError):
        event.save()
