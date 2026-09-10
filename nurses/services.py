"""Rotasi giliran perawat: round-robin deterministik + ledger event (PRD 8.5, 20.5)."""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from audit.models import AuditAction
from audit.services import log_event, log_update, snapshot
from core.models import ClinicConfig

from .models import (
    Availability,
    CommissionTurnEvent,
    NurseEligibility,
    NurseRosterEntry,
    ProcedureAssignment,
    ProcedureCategory,
    ProcedureStatus,
    TurnAction,
)


def rotation_policy(clinic) -> dict:
    return {
        "policy": ClinicConfig.get(clinic, "nurse.rotation_policy"),
        "skip_keeps_position": bool(ClinicConfig.get(clinic, "nurse.skip_keeps_position")),
        "cancel_before_start_restores_position": bool(
            ClinicConfig.get(clinic, "nurse.cancel_before_start_restores_position")
        ),
    }


@transaction.atomic
def set_roster(day, *, supervisor, nurse_ids: list[int], reason: str = "") -> list[NurseRosterEntry]:
    """Roster aktif menghasilkan urutan awal deterministik (urut sesuai input)."""
    day.assert_editable()
    if not nurse_ids:
        raise ValidationError("Pilih minimal satu perawat untuk roster hari ini.")

    existing = {r.nurse_id: r for r in NurseRosterEntry.objects.filter(operational_day=day)}
    entries: list[NurseRosterEntry] = []
    for idx, nurse_id in enumerate(nurse_ids, start=1):
        nurse_id = int(nurse_id)
        entry = existing.pop(nurse_id, None)
        if entry is None:
            entry = NurseRosterEntry.objects.create(
                operational_day=day, nurse_id=nurse_id, position=idx
            )
            CommissionTurnEvent.objects.create(
                operational_day=day,
                roster_entry=entry,
                nurse_id=nurse_id,
                action=TurnAction.ROSTER_DIBUAT,
                position_after=idx,
                actor=supervisor,
                reason=reason,
            )
        elif entry.position != idx:
            before_pos = entry.position
            entry.position = idx
            entry.save(update_fields=["position"])
            CommissionTurnEvent.objects.create(
                operational_day=day,
                roster_entry=entry,
                nurse_id=nurse_id,
                action=TurnAction.OVERRIDE,
                position_before=before_pos,
                position_after=idx,
                actor=supervisor,
                reason=reason or "Penyusunan ulang roster",
            )
        entries.append(entry)

    for leftover in existing.values():
        leftover.availability = Availability.OFF_DUTY
        leftover.save(update_fields=["availability"])

    log_event(
        action=AuditAction.UPDATE,
        entity_type="nurseroster",
        entity_id=day.pk,
        entity_label=f"Roster {day.date}",
        actor=supervisor,
        after={"nurse_ids": [int(n) for n in nurse_ids]},
        reason=reason,
    )
    return entries


def is_eligible(nurse_id: int, category: ProcedureCategory) -> bool:
    return NurseEligibility.objects.filter(
        nurse_id=nurse_id, category=category, active=True
    ).exists()


def next_nurse(day, category: ProcedureCategory | None = None) -> NurseRosterEntry | None:
    """Perawat berikutnya: posisi terkecil, tersedia, dan eligible bila kategori diberikan."""
    qs = NurseRosterEntry.objects.filter(
        operational_day=day, availability=Availability.TERSEDIA
    ).order_by("position", "id")
    for entry in qs:
        if category is None or is_eligible(entry.nurse_id, category):
            return entry
    return None


def _move_to_back(day, entry: NurseRosterEntry) -> tuple[int, int]:
    """Pindahkan perawat ke belakang antrean; kembalikan (posisi lama, posisi baru)."""
    others = list(
        NurseRosterEntry.objects.select_for_update()
        .filter(operational_day=day)
        .exclude(pk=entry.pk)
        .order_by("position", "id")
    )
    before_pos = entry.position
    for idx, other in enumerate(others, start=1):
        if other.position != idx:
            other.position = idx
            other.save(update_fields=["position"])
    entry.position = len(others) + 1
    entry.save(update_fields=["position"])
    return before_pos, entry.position


def _move_to_front(day, entry: NurseRosterEntry) -> tuple[int, int]:
    others = list(
        NurseRosterEntry.objects.select_for_update()
        .filter(operational_day=day)
        .exclude(pk=entry.pk)
        .order_by("position", "id")
    )
    before_pos = entry.position
    entry.position = 1
    entry.save(update_fields=["position"])
    for idx, other in enumerate(others, start=2):
        if other.position != idx:
            other.position = idx
            other.save(update_fields=["position"])
    return before_pos, 1


@transaction.atomic
def assign_procedure(
    day,
    *,
    user,
    category: ProcedureCategory,
    nurse_id: int | None = None,
    queue_entry=None,
    note: str = "",
    override_reason: str = "",
) -> ProcedureAssignment:
    """Tugaskan tindakan berkomisi. Nurse lain dari giliran = override wajib alasan."""
    day.assert_editable()
    from core.permissions import is_supervisor

    suggested = next_nurse(day, category)
    if nurse_id is None:
        if suggested is None:
            raise ValidationError(
                "Tidak ada perawat tersedia yang eligible untuk kategori tindakan ini."
            )
        roster_entry = suggested
        nurse_id = roster_entry.nurse_id
    else:
        nurse_id = int(nurse_id)
        roster_entry = NurseRosterEntry.objects.filter(
            operational_day=day, nurse_id=nurse_id
        ).first()
        if roster_entry is None:
            raise ValidationError("Perawat tidak berada dalam roster hari ini.")

    is_override = suggested is None or roster_entry.pk != suggested.pk
    eligible = is_eligible(nurse_id, category)

    if (is_override or not eligible) and not override_reason.strip():
        raise ValidationError(
            "Memilih perawat di luar giliran atau tanpa eligibility memerlukan alasan override supervisor."
        )
    if (is_override or not eligible) and not is_supervisor(user):
        raise ValidationError("Hanya supervisor yang dapat melakukan override giliran perawat.")

    assignment = ProcedureAssignment.objects.create(
        operational_day=day,
        queue_entry=queue_entry,
        category=category,
        nurse_id=nurse_id,
        note=(note or "").strip(),
        override_reason=override_reason.strip(),
        assigned_by=user,
    )
    CommissionTurnEvent.objects.create(
        operational_day=day,
        roster_entry=roster_entry,
        nurse_id=nurse_id,
        queue_entry=queue_entry,
        procedure_category=category,
        action=TurnAction.OVERRIDE if (is_override or not eligible) else TurnAction.TINDAKAN_DITUGASKAN,
        reason=override_reason,
        position_before=roster_entry.position,
        actor=user,
    )
    if not eligible:
        CommissionTurnEvent.objects.create(
            operational_day=day,
            roster_entry=roster_entry,
            nurse_id=nurse_id,
            procedure_category=category,
            action=TurnAction.TIDAK_ELIGIBLE,
            reason=override_reason,
            actor=user,
        )
    log_event(
        action=AuditAction.OVERRIDE if (is_override or not eligible) else AuditAction.CREATE,
        entity_type="procedureassignment",
        entity_id=assignment.pk,
        entity_label=str(assignment),
        actor=user,
        after=snapshot(assignment),
        reason=override_reason,
    )
    if is_override or not eligible:
        from notifications.services import notify_role

        notify_role(
            day.clinic,
            "SUPERVISOR",
            type_code="NURSE_OVERRIDE",
            title="Override urutan perawat",
            body=f"{assignment.nurse} ditugaskan di luar giliran untuk {category}.",
            entity_ref=f"procedureassignment#{assignment.pk}",
            url_name="nurses:board",
        )
    return assignment


@transaction.atomic
def start_procedure(assignment: ProcedureAssignment, *, user) -> ProcedureAssignment:
    if assignment.status != ProcedureStatus.DITUGASKAN:
        raise ValidationError("Tindakan tidak dalam status ditugaskan.")
    before = snapshot(assignment)
    assignment.status = ProcedureStatus.DIMULAI
    assignment.started_at = timezone.now()
    assignment.version += 1
    assignment.save()
    CommissionTurnEvent.objects.create(
        operational_day=assignment.operational_day,
        nurse_id=assignment.nurse_id,
        queue_entry=assignment.queue_entry,
        procedure_category=assignment.category,
        action=TurnAction.TINDAKAN_DIMULAI,
        actor=user,
    )
    log_update(assignment, before, actor=user)
    return assignment


@transaction.atomic
def complete_procedure(assignment: ProcedureAssignment, *, user) -> ProcedureAssignment:
    """Tindakan selesai dikonfirmasi -> perawat pindah ke belakang antrean."""
    if assignment.status in {ProcedureStatus.SELESAI, ProcedureStatus.BATAL}:
        raise ValidationError("Tindakan sudah final.")
    day = assignment.operational_day
    day.assert_editable()

    before = snapshot(assignment)
    assignment.status = ProcedureStatus.SELESAI
    assignment.finished_at = timezone.now()
    assignment.version += 1
    assignment.save()

    roster_entry = NurseRosterEntry.objects.filter(
        operational_day=day, nurse_id=assignment.nurse_id
    ).first()
    pos_before = pos_after = None
    if roster_entry:
        pos_before, pos_after = _move_to_back(day, roster_entry)
        roster_entry.turns_taken += 1
        roster_entry.save(update_fields=["turns_taken"])

    CommissionTurnEvent.objects.create(
        operational_day=day,
        roster_entry=roster_entry,
        nurse_id=assignment.nurse_id,
        queue_entry=assignment.queue_entry,
        procedure_category=assignment.category,
        action=TurnAction.TINDAKAN_SELESAI,
        position_before=pos_before,
        position_after=pos_after,
        actor=user,
    )
    log_update(assignment, before, actor=user)
    return assignment


@transaction.atomic
def cancel_procedure(assignment: ProcedureAssignment, *, user, reason: str) -> ProcedureAssignment:
    """Batal sebelum dimulai mengembalikan posisi; setelah dimulai dihitung terpakai."""
    if not reason.strip():
        raise ValidationError("Alasan wajib diisi untuk membatalkan tindakan.")
    day = assignment.operational_day
    day.assert_editable()
    policy = rotation_policy(day.clinic)

    before = snapshot(assignment)
    started = assignment.status == ProcedureStatus.DIMULAI
    assignment.status = ProcedureStatus.BATAL
    assignment.version += 1
    assignment.save()

    roster_entry = NurseRosterEntry.objects.filter(
        operational_day=day, nurse_id=assignment.nurse_id
    ).first()
    pos_before = pos_after = None
    if roster_entry and started:
        pos_before, pos_after = _move_to_back(day, roster_entry)
        roster_entry.turns_taken += 1
        roster_entry.save(update_fields=["turns_taken"])
    elif roster_entry and policy["cancel_before_start_restores_position"]:
        pos_before, pos_after = _move_to_front(day, roster_entry)

    CommissionTurnEvent.objects.create(
        operational_day=day,
        roster_entry=roster_entry,
        nurse_id=assignment.nurse_id,
        queue_entry=assignment.queue_entry,
        procedure_category=assignment.category,
        action=TurnAction.TINDAKAN_BATAL,
        reason=reason,
        position_before=pos_before,
        position_after=pos_after,
        actor=user,
    )
    log_update(assignment, before, actor=user, reason=reason, action=AuditAction.CANCEL)
    return assignment


@transaction.atomic
def skip_nurse(roster_entry: NurseRosterEntry, *, user, reason: str) -> NurseRosterEntry:
    """Skip sementara: default perawat tetap pada posisinya (config)."""
    if not reason.strip():
        raise ValidationError("Alasan wajib diisi untuk skip perawat.")
    day = roster_entry.operational_day
    day.assert_editable()
    policy = rotation_policy(day.clinic)

    before = snapshot(roster_entry)
    pos_before = roster_entry.position
    pos_after = pos_before
    if not policy["skip_keeps_position"]:
        pos_before, pos_after = _move_to_back(day, roster_entry)

    CommissionTurnEvent.objects.create(
        operational_day=day,
        roster_entry=roster_entry,
        nurse_id=roster_entry.nurse_id,
        action=TurnAction.SKIP,
        reason=reason,
        position_before=pos_before,
        position_after=pos_after,
        actor=user,
    )
    log_update(roster_entry, before, actor=user, reason=reason, action=AuditAction.OVERRIDE)
    return roster_entry


@transaction.atomic
def set_availability(
    roster_entry: NurseRosterEntry, *, user, availability: str, reason: str = ""
) -> NurseRosterEntry:
    if availability not in dict(Availability.choices):
        raise ValidationError("Status ketersediaan tidak dikenali.")
    before = snapshot(roster_entry)
    roster_entry.availability = availability
    roster_entry.version += 1
    roster_entry.save()
    CommissionTurnEvent.objects.create(
        operational_day=roster_entry.operational_day,
        roster_entry=roster_entry,
        nurse_id=roster_entry.nurse_id,
        action=TurnAction.AVAILABILITY_BERUBAH,
        reason=reason,
        actor=user,
    )
    log_update(roster_entry, before, actor=user, reason=reason)
    return roster_entry
