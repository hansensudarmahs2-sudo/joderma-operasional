"""Rotasi giliran perawat: round-robin deterministik + ledger event (PRD 8.5, 20.5)."""
from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from audit.models import AuditAction
from audit.services import log_event, log_update, snapshot
from core.models import ClinicConfig

from .models import (
    Availability,
    CommissionTurnEvent,
    NurseActionTally,
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


def month_bounds(date):
    import calendar

    return date.replace(day=1), date.replace(day=calendar.monthrange(date.year, date.month)[1])


def monthly_tally(nurse_ids, date) -> dict[int, int]:
    """Total tally bulan berjalan per perawat, sampai `date`, digabung semua cabang.

    Satu tindakan = satu tally (kolom `tally` pada catatan tally). Total bulanan
    dimulai dari nol setiap tanggal 1.
    """
    from django.db.models import Sum

    start, _ = month_bounds(date)
    rows = (
        NurseActionTally.objects.filter(
            nurse_id__in=list(nurse_ids),
            operational_day__date__gte=start,
            operational_day__date__lte=date,
        )
        .values("nurse_id")
        .annotate(total=Sum("tally"))
    )
    totals = {nid: 0 for nid in nurse_ids}
    for r in rows:
        totals[r["nurse_id"]] = r["total"] or 0
    return totals


def daily_tally(day) -> dict[int, int]:
    from django.db.models import Sum

    return {
        r["nurse_id"]: r["total"] or 0
        for r in NurseActionTally.objects.filter(operational_day=day)
        .values("nurse_id")
        .annotate(total=Sum("tally"))
    }


def catch_up_gap(clinic) -> int:
    return int(ClinicConfig.get(clinic, "nurse.catch_up_gap", 2) or 2)


def on_leave_this_month(nurse_ids, date) -> set[int]:
    """Perawat yang punya hari cuti di bulan berjalan sampai `date` (jadwal jaga)."""
    from jadwal.models import DutyRoster, DutyStatus

    start, _ = month_bounds(date)
    return set(
        DutyRoster.objects.filter(
            user_id__in=list(nurse_ids), status=DutyStatus.CUTI, date__gte=start, date__lte=date
        ).values_list("user_id", flat=True)
    )


def rotation_board(day, category: ProcedureCategory | None = None) -> dict:
    """Urutan giliran hari ini beserta alasannya.

    Aturan (ketetapan product owner 30 Sep 2026):
    1. Giliran ditentukan per pasien; tally dicatat per tindakan saat selesai.
       Total bulanan digabung dua cabang dan mulai dari nol tiap tanggal 1.
    2. Yang paling sedikit didahulukan. Perawat yang totalnya paling sedikit
       `gap` (bawaan 2) di bawah total terkecil rekan yang bertugas mendapat
       pasien berturut-turut sampai tinggal satu di bawah rekan itu ("-1").
       Off (termasuk tukar libur karena masuk Minggu/hari raya) tetap dihitung.
    3. Sesudah itu giliran kembali mengikuti urutan papan. Urutan papan awal
       hari disusun dari total bulanan terkecil; Koordinator Shift dapat
       menggesernya. Yang baru mencatat tally pindah ke belakang.
    4. Perawat yang mengajukan cuti di bulan itu tidak mendapat keistimewaan
       mengejar (butir 2); ia tetap mendapat tempat di papan seperti biasa.
    5. Yang sedang menangani, istirahat, atau off tidak diberi pasien.
    """
    entries = list(
        NurseRosterEntry.objects.filter(operational_day=day).select_related("nurse").order_by("position", "id")
    )
    on_duty = [e for e in entries if e.availability != Availability.OFF_DUTY]
    counts = monthly_tally([e.nurse_id for e in entries], day.date)
    today = daily_tally(day)
    gap = catch_up_gap(day.clinic)
    on_leave = on_leave_this_month([e.nurse_id for e in entries], day.date)

    def lagging(entry) -> int:
        if entry.nurse_id in on_leave:
            return 0
        others = [counts[o.nurse_id] for o in on_duty if o.pk != entry.pk]
        if not others:
            return 0
        behind = min(others) - counts[entry.nurse_id]
        return behind if behind >= gap else 0

    available = [
        e for e in entries
        if e.availability == Availability.TERSEDIA and (category is None or is_eligible(e.nurse_id, category))
    ]
    chasing = sorted((e for e in available if lagging(e)), key=lambda e: (counts[e.nurse_id], e.position, e.pk))
    if chasing:
        pick = chasing[0]
        reason = f"mengejar: {lagging(pick)} di bawah total terkecil rekan"
    elif available:
        pick = available[0]
        reason = "urutan papan"
    else:
        pick, reason = None, ""
    rows = [
        {
            "entry": e,
            "month": counts[e.nurse_id],
            "today": today.get(e.nurse_id, 0),
            "lagging": lagging(e) if e.availability != Availability.OFF_DUTY else 0,
            "is_next": pick is not None and e.pk == pick.pk,
            "on_leave": e.nurse_id in on_leave,
        }
        for e in entries
    ]
    return {"rows": rows, "next": pick, "reason": reason, "gap": gap}


def next_nurse(day, category: ProcedureCategory | None = None) -> NurseRosterEntry | None:
    """Perawat berikutnya menurut `rotation_board`."""
    return rotation_board(day, category)["next"]


@transaction.atomic
def sync_roster_with_duty(day, *, actor=None) -> dict:
    """Roster giliran hari ini mengikuti jadwal jaga.

    Perawat (peran PERAWAT) yang bertugas di cabang ini — termasuk perbantuan dari
    cabang lain — masuk roster; yang off, cuti, atau sedang di cabang lain ditandai
    Pulang/off sehingga tidak diberi tally. Urutan awal: total bulanan terkecil
    lebih dulu, lalu nama. Tidak mengubah apa pun bila jadwal hari itu belum diisi.
    """
    from accounts.models import Role
    from jadwal.services import has_roster, staff_on_duty

    if not has_roster(day.clinic, day.date):
        return {"added": 0, "off": 0, "synced": False}
    nurses = [u for u in staff_on_duty(day.clinic, day.date) if Role.PERAWAT in u.role_codes()]
    wanted = {u.pk for u in nurses}
    existing = {e.nurse_id: e for e in NurseRosterEntry.objects.select_for_update().filter(operational_day=day)}
    counts = monthly_tally(list(wanted | set(existing)), day.date)
    added = off = 0
    next_pos = max([e.position for e in existing.values()] or [0])
    for u in sorted(nurses, key=lambda u: (counts[u.pk], (u.display_name or u.username).lower())):
        entry = existing.get(u.pk)
        if entry is None:
            next_pos += 1
            entry = NurseRosterEntry.objects.create(operational_day=day, nurse=u, position=next_pos)
            CommissionTurnEvent.objects.create(
                operational_day=day, roster_entry=entry, nurse=u, action=TurnAction.ROSTER_DIBUAT,
                position_after=next_pos, actor=actor, reason="Dari jadwal jaga",
            )
            added += 1
        elif entry.availability == Availability.OFF_DUTY:
            entry.availability = Availability.TERSEDIA
            entry.save(update_fields=["availability"])
    for nurse_id, entry in existing.items():
        if nurse_id not in wanted and entry.availability != Availability.OFF_DUTY:
            entry.availability = Availability.OFF_DUTY
            entry.save(update_fields=["availability"])
            CommissionTurnEvent.objects.create(
                operational_day=day, roster_entry=entry, nurse_id=nurse_id,
                action=TurnAction.AVAILABILITY_BERUBAH, actor=actor, reason="Tidak bertugas di cabang ini menurut jadwal jaga",
            )
            off += 1
    return {"added": added, "off": off, "synced": True}


@transaction.atomic
def move_entry(entry: NurseRosterEntry, *, direction: str, user) -> NurseRosterEntry:
    """Koordinator Shift menggeser urutan papan satu langkah (naik/turun)."""
    from core.permissions import can_manage_roster, is_aom

    if not (can_manage_roster(user) or is_aom(user)):
        raise PermissionDenied("Hanya Koordinator Shift yang mengatur urutan papan.")
    day = entry.operational_day
    day.assert_editable()
    ordered = list(
        NurseRosterEntry.objects.select_for_update().filter(operational_day=day).order_by("position", "id")
    )
    idx = next(i for i, e in enumerate(ordered) if e.pk == entry.pk)
    target = idx - 1 if direction == "naik" else idx + 1
    if target < 0 or target >= len(ordered):
        return entry
    ordered[idx], ordered[target] = ordered[target], ordered[idx]
    before = entry.position
    for pos, e in enumerate(ordered, start=1):
        if e.position != pos:
            e.position = pos
            e.save(update_fields=["position"])
    CommissionTurnEvent.objects.create(
        operational_day=day, roster_entry=entry, nurse_id=entry.nurse_id, action=TurnAction.URUTAN_DIUBAH,
        position_before=before, position_after=target + 1, actor=user,
    )
    entry.refresh_from_db()
    return entry


@transaction.atomic
def hand_over(entry: NurseRosterEntry, *, user) -> NurseRosterEntry:
    """Pasien diserahkan: perawat ditandai sedang menangani sampai tally-nya dicatat."""
    from core.permissions import can_manage_roster, is_aom

    if not (can_manage_roster(user) or is_aom(user)):
        raise PermissionDenied("Hanya Koordinator Shift yang menyerahkan pasien ke perawat.")
    if entry.availability != Availability.TERSEDIA:
        raise ValidationError(f"{entry.nurse} sedang tidak tersedia.")
    entry.operational_day.assert_editable()
    entry.availability = Availability.MENANGANI
    entry.version += 1
    entry.save(update_fields=["availability", "version"])
    CommissionTurnEvent.objects.create(
        operational_day=entry.operational_day, roster_entry=entry, nurse_id=entry.nurse_id,
        action=TurnAction.PASIEN_DISERAHKAN, position_before=entry.position, actor=user,
    )
    return entry


@transaction.atomic
def after_tally(day, nurse_id: int, *, amount: int, user) -> None:
    """Tally dicatat saat tindakan selesai: perawat kembali tersedia, pindah ke belakang papan."""
    entry = NurseRosterEntry.objects.filter(operational_day=day, nurse_id=nurse_id).first()
    if entry is None:
        return
    pos_before, pos_after = _move_to_back(day, entry)
    entry.turns_taken += amount
    if entry.availability == Availability.MENANGANI:
        entry.availability = Availability.TERSEDIA
    entry.save(update_fields=["turns_taken", "availability"])
    CommissionTurnEvent.objects.create(
        operational_day=day, roster_entry=entry, nurse_id=nurse_id, action=TurnAction.TINDAKAN_SELESAI,
        position_before=pos_before, position_after=pos_after, actor=user, reason=f"Tally +{amount}",
    )


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



# --- Koreksi tally ---------------------------------------------------------------


def can_correct_tally(user, clinic) -> bool:
    """Koordinator Shift cabang itu, Direktur Operasional, atau pemegang hak khusus
    "Mengoreksi tally" (`Capability.TALLY_CORRECT`) di cabang yang dapat ia akses
    (keputusan 3 Okt 2026). Hak khusus tidak ikut hilang saat peran direset."""
    from accounts.models import Capability
    from core.permissions import can_access_clinic, caps, is_aom

    if is_aom(user):
        return True
    if not can_access_clinic(user, clinic):
        return False
    return Capability.TALLY_CORRECT in caps(user) or user.user_roles.filter(
        clinic=clinic, role="SUPERVISOR"
    ).exists()


@transaction.atomic
def correct_tally(tally: NurseActionTally, *, user, amount: int, nurse=None, action_name: str = "",
                  reason: str) -> NurseActionTally:
    """Ubah jumlah (0 = batal), perawat, atau nama tindakan satu catatan tally.

    Total bulanan dihitung dari catatan tally, jadi ikut terkoreksi. Hitungan giliran hari itu
    di papan (`turns_taken`) disesuaikan dengan selisihnya. Wajib alasan; diaudit sebagai
    CORRECTION.
    """
    from audit.models import AuditAction
    from audit.services import log_update, snapshot

    day = tally.operational_day
    if not can_correct_tally(user, day.clinic):
        raise PermissionDenied("Koreksi tally hanya oleh Koordinator Shift cabang ini, Direktur Operasional, atau pemegang hak koreksi tally.")
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("Tuliskan alasan koreksi.")
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        raise ValidationError("Jumlah tidak valid.")
    if amount < 0 or amount > 20:
        raise ValidationError("Jumlah harus antara 0 dan 20 (0 berarti tally dibatalkan).")
    nurse = nurse or tally.nurse
    action_name = (action_name or "").strip() or tally.action_name
    if amount == tally.tally and nurse.pk == tally.nurse_id and action_name == tally.action_name:
        raise ValidationError("Tidak ada yang berubah.")

    before = snapshot(tally)
    old_nurse_id, old_amount = tally.nurse_id, tally.tally
    tally.tally = amount
    tally.nurse = nurse
    tally.action_name = action_name
    tally.corrected_by = user
    tally.corrected_at = timezone.now()
    tally.correction_reason = reason[:250]
    tally.save()
    log_update(tally, before, actor=user, reason=reason, action=AuditAction.CORRECTION)

    for nurse_id, delta in ((old_nurse_id, -old_amount), (nurse.pk, amount)):
        entry = NurseRosterEntry.objects.filter(operational_day=day, nurse_id=nurse_id).first()
        if entry is not None and delta:
            entry.turns_taken = max(0, entry.turns_taken + delta)
            entry.save(update_fields=["turns_taken"])
    return tally


def backfill_window(clinic):
    """Rentang tanggal tally susulan: tanggal 1 bulan berjalan sampai hari operasional sekarang."""
    from core.models import operational_date

    today = operational_date(clinic)
    return today.replace(day=1), today


def backfill_nurses(clinic, day=None):
    """Perawat yang boleh diberi tally susulan: pemegang peran Perawat di cabang itu, ditambah
    yang ada di roster hari itu (perawat pinjaman cabang lain)."""
    from django.db.models import Q

    from accounts.models import Role, User

    cond = Q(user_roles__role=Role.PERAWAT, user_roles__clinic=clinic)
    if day is not None:
        cond |= Q(roster_entries__operational_day=day)
    return User.objects.filter(cond, is_active=True).distinct().order_by("display_name", "username")


@transaction.atomic
def record_backfill_tally(clinic, date, *, user, nurse, amount, reason: str) -> NurseActionTally:
    """Tally susulan (8 Okt 2026) untuk perawat yang tidak menulis tally-nya sendiri.

    Hanya pemegang hak koreksi tally cabang itu. Tanpa RM, pasien, dan tindakan; alasan wajib;
    tanggal di bulan berjalan sampai hari ini. Menambah total harian dan bulanan, tetapi tidak
    menggeser papan giliran (urutan dan ketersediaan tetap), sebab pekerjaannya sudah lewat.
    """
    from audit.services import log_create
    from core.models import OperationalDay
    from core.services import get_or_create_day

    if not can_correct_tally(user, clinic):
        raise PermissionDenied("Tally susulan hanya oleh Koordinator Shift cabang ini, Direktur Operasional, atau pemegang hak koreksi tally.")
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("Tuliskan alasan tally susulan.")
    if nurse is None:
        raise ValidationError("Pilih perawat.")
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        raise ValidationError("Jumlah tidak valid.")
    if amount < 1 or amount > 20:
        raise ValidationError("Jumlah harus antara 1 dan 20.")
    start, today = backfill_window(clinic)
    if date is None or not (start <= date <= today):
        raise ValidationError(
            f"Tally susulan hanya untuk tanggal {start:%d/%m/%Y} sampai {today:%d/%m/%Y} (bulan berjalan)."
        )
    if date == today:
        day, _ = get_or_create_day(clinic, date=today, user=user)
    else:
        day = OperationalDay.objects.filter(clinic=clinic, date=date).first()
        if day is None:
            raise ValidationError("Tidak ada sesi hari operasional pada tanggal ini.")
    if not backfill_nurses(clinic, day).filter(pk=nurse.pk).exists():
        raise ValidationError(f"{nurse} bukan perawat cabang ini dan tidak ada di roster tanggal itu.")

    tally = NurseActionTally.objects.create(
        operational_day=day, nurse=nurse, tally=amount, entered_by=user,
        susulan=True, susulan_reason=reason[:250],
    )
    log_create(tally, actor=user, reason=reason,
               label=f"Tally susulan · {amount}x · {nurse} ({clinic.name}, {date:%d/%m/%Y})")
    # Hitungan giliran hari itu ikut bertambah, tanpa memindahkan posisi di papan.
    entry = NurseRosterEntry.objects.filter(operational_day=day, nurse=nurse).first()
    if entry is not None:
        entry.turns_taken += amount
        entry.save(update_fields=["turns_taken"])
    return tally
