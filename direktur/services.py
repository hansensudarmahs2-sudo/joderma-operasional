"""Layanan peran Direktur Operasional. Seluruh otorisasi diulang di sini (server-side)."""
from __future__ import annotations

import datetime as dt
import random
import re

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.models import PicAssignment, PicFunction, User
from audit.models import AuditAction
from audit.services import log_create, log_event, log_update, snapshot
from core.models import ActionItem, ActionItemStatus, Priority, TaskAudienceType, local_today
from core.permissions import can_access_clinic, is_aom
from core.task_services import create_task

from .models import (
    AuditCheck,
    AuditItem,
    Cadence,
    CheckResult,
    Decider,
    Decision,
    DecisionStatus,
    DirectorNote,
    NoteSource,
    period_start,
)

FINDING_SOURCE = "audit_direktur"
NOTE_SOURCE = "catatan_direktur"
DECISION_SOURCE = "keputusan"


def assert_director(user) -> None:
    if not is_aom(user):
        raise PermissionDenied("Halaman ini khusus Direktur Operasional.")


def _assert_clinic(user, clinic) -> None:
    if clinic is None or not can_access_clinic(user, clinic):
        raise PermissionDenied("Anda tidak memiliki akses ke cabang ini.")


# --- Penerima task -------------------------------------------------------------

def target_choices(clinic) -> list[tuple[str, str]]:
    """Pilihan penerima task untuk satu cabang: fungsi PIC yang terisi, lalu staf aktif."""
    choices: list[tuple[str, str]] = []
    held = set(
        PicAssignment.objects.filter(clinic=clinic, active=True, user__is_active=True).values_list(
            "function", flat=True
        )
    )
    for value, label in PicFunction.choices:
        if value in held:
            choices.append((f"pic:{value}", f"PIC {label}"))
    users = (
        User.objects.filter(is_active=True, user_roles__clinic=clinic)
        .distinct()
        .order_by("display_name", "username")
    )
    for user in users:
        choices.append((f"user:{user.pk}", str(user)))
    return choices


def parse_target(target: str) -> dict | None:
    """'pic:SHIFT_COORDINATOR' / 'user:12' / '' -> argumen audience create_task."""
    target = (target or "").strip()
    if not target:
        return None
    kind, _, value = target.partition(":")
    if kind == "pic" and value in dict(PicFunction.choices):
        return {"audience_type": TaskAudienceType.PIC_FUNCTION, "pic_function": value}
    if kind == "user" and value.isdigit():
        return {"audience_type": TaskAudienceType.USER, "user_ids": [int(value)]}
    raise ValidationError("Penerima task tidak dikenali.")


def parse_due(value: str):
    """Tanggal batas (YYYY-MM-DD) -> akhir hari itu, waktu lokal."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        day = dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError("Format batas waktu tidak valid.") from exc
    return timezone.make_aware(dt.datetime.combine(day, dt.time(21, 0)))


def _create_task_or_record(
    *, clinic, actor, title, description, target, priority, due_at, source_type, source_id, source_label
) -> ActionItem:
    audience = parse_target(target)
    if audience is None:
        # Temuan/catatan tanpa penerima tetap tercatat dan terlihat di Team Viewer.
        item = ActionItem.objects.create(
            clinic=clinic,
            title=title.strip(),
            description=description.strip(),
            source_type=source_type,
            source_id=source_id,
            source_label=source_label,
            priority=priority,
            due_at=due_at,
            created_by=actor,
        )
        log_create(item, actor=actor)
        return item
    return create_task(
        clinic=clinic,
        actor=actor,
        title=title,
        description=description,
        priority=priority,
        due_at=due_at,
        source_type=source_type,
        source_id=source_id,
        source_label=source_label,
        **audience,
    )


def create_manual_task(
    *, actor, clinic, title, description="", target="", priority=Priority.SEDANG, due_at=None, decision=None
) -> ActionItem:
    """Task dari Direktur. Dengan `decision`, task tercatat sebagai tindak lanjut keputusan itu."""
    assert_director(actor)
    _assert_clinic(actor, clinic)
    if not (title or "").strip():
        raise ValidationError("Judul task wajib diisi.")
    if not (target or "").strip():
        raise ValidationError("Pilih penerima task.")
    if decision is not None:
        if decision.status != DecisionStatus.DITETAPKAN:
            raise ValidationError("Tindak lanjut hanya untuk keputusan yang sudah ditetapkan.")
        if decision.clinic_id not in (None, clinic.pk):
            raise ValidationError("Keputusan ini untuk cabang lain.")
    return _create_task_or_record(
        clinic=clinic,
        actor=actor,
        title=title,
        description=description or "",
        target=target,
        priority=priority,
        due_at=due_at,
        source_type=DECISION_SOURCE if decision else "manual",
        source_id=decision.pk if decision else None,
        source_label=(decision.reference or "Keputusan") if decision else "Task Direktur",
    )


def create_task_from_source(
    *, actor, clinic, title, target, description="", priority=Priority.SEDANG, due_at=None,
    source_type: str, source_id: int, source_label: str = "",
) -> ActionItem:
    """Task hasil pilah Inbox: bersumber dari laporan, masukan, permintaan/temuan Owner."""
    assert_director(actor)
    _assert_clinic(actor, clinic)
    if not (title or "").strip():
        raise ValidationError("Judul task wajib diisi.")
    if not (target or "").strip():
        raise ValidationError("Pilih penerima task.")
    if priority not in dict(Priority.choices):
        priority = Priority.SEDANG
    return _create_task_or_record(
        clinic=clinic, actor=actor, title=title, description=description or "", target=target,
        priority=priority, due_at=due_at, source_type=source_type, source_id=source_id,
        source_label=source_label,
    )


# --- Checklist Direktur --------------------------------------------------------

def items_for(clinic, cadence: str):
    return [
        item
        for item in AuditItem.objects.filter(cadence=cadence, active=True).prefetch_related("points")
        if item.applies_to(clinic)
    ]


def board(clinic, cadence: str, today: dt.date | None = None) -> list[dict]:
    """Butir + hasil cek periode berjalan untuk satu cabang (None = belum dicek)."""
    today = today or local_today()
    start = period_start(cadence, today)
    checks = {
        c.item_id: c
        for c in AuditCheck.objects.filter(
            clinic=clinic, period_start=start, item__cadence=cadence
        ).select_related("finding", "checked_by")
    }
    return [{"item": item, "check": checks.get(item.pk)} for item in items_for(clinic, cadence)]


def pending_summary(clinic, today: dt.date | None = None) -> dict[str, dict]:
    today = today or local_today()
    out = {}
    for cadence, label in Cadence.choices:
        rows = board(clinic, cadence, today)
        out[cadence] = {
            "label": label,
            "period_start": period_start(cadence, today),
            "total": len(rows),
            "done": sum(1 for r in rows if r["check"] is not None),
            "pending": [r["item"] for r in rows if r["check"] is None],
        }
    return out


def direct_check_suggestions(clinic, today: dt.date | None = None, count: int = 3) -> list[dict]:
    """Saran 2-3 rincian harian untuk dicek langsung; tetap sama sepanjang hari per cabang."""
    today = today or local_today()
    pool = [
        {"item": item, "point": point}
        for item in items_for(clinic, Cadence.HARIAN)
        for point in item.points.all()
    ]
    rng = random.Random(today.toordinal() * 1000 + clinic.pk)
    return rng.sample(pool, min(count, len(pool)))


@transaction.atomic
def record_check(
    *,
    item: AuditItem,
    clinic,
    actor,
    result: str,
    note: str = "",
    direct: bool = False,
    reason: str = "",
    target: str = "",
    due_at=None,
    priority: str = Priority.SEDANG,
    today: dt.date | None = None,
) -> AuditCheck:
    """Catat cek satu butir untuk periode berjalan.

    - Temuan wajib dijelaskan dan membuat tepat satu task tindak lanjut
      (idempoten: mencatat ulang tidak menggandakan task).
    - Mengubah hasil yang sudah tercatat wajib beralasan dan diaudit sebagai
      CORRECTION, mengikuti aturan checklist pelaksana.
    """
    assert_director(actor)
    _assert_clinic(actor, clinic)
    if not item.active or not item.applies_to(clinic):
        raise ValidationError("Butir ini tidak berlaku untuk cabang tersebut.")
    if result not in dict(CheckResult.choices):
        raise ValidationError("Hasil cek tidak dikenali.")
    note = (note or "").strip()
    if result == CheckResult.TEMUAN and not note:
        raise ValidationError("Tuliskan temuannya.")

    today = today or local_today()
    start = period_start(item.cadence, today)
    check = (
        AuditCheck.objects.select_for_update()
        .filter(item=item, clinic=clinic, period_start=start)
        .first()
    )
    if check is None:
        check = AuditCheck.objects.create(
            item=item,
            clinic=clinic,
            period_start=start,
            result=result,
            direct=direct,
            note=note,
            item_snapshot=item.to_snapshot(),
            checked_by=actor,
        )
        log_create(check, actor=actor)
    else:
        if check.result != result and not (reason or "").strip():
            raise ValidationError("Hasil cek sudah tercatat. Tuliskan alasan koreksi.")
        before = snapshot(check)
        changed_result = check.result != result
        check.result = result
        check.direct = direct
        check.note = note
        check.checked_by = actor
        check.save()
        log_update(
            check,
            before,
            actor=actor,
            reason=(reason or "").strip(),
            action=AuditAction.CORRECTION if changed_result else AuditAction.UPDATE,
        )

    if result == CheckResult.TEMUAN and check.finding_id is None:
        if not target and item.pic_function and PicAssignment.objects.filter(
            clinic=clinic, function=item.pic_function, active=True, user__is_active=True
        ).exists():
            target = f"pic:{item.pic_function}"
        check.finding = _create_task_or_record(
            clinic=clinic,
            actor=actor,
            title=f"Temuan {item.title} ({clinic.name})",
            description=note,
            target=target,
            priority=priority,
            due_at=due_at,
            source_type=FINDING_SOURCE,
            source_id=check.pk,
            source_label=f"Cek {item.get_cadence_display().lower()} Direktur: {item.title}",
        )
        check.save(update_fields=["finding", "updated_at"])
    return check


def open_findings(clinic):
    return (
        ActionItem.objects.filter(
            clinic=clinic,
            source_type=FINDING_SOURCE,
            status__in=[ActionItemStatus.BARU, ActionItemStatus.DIKERJAKAN],
        )
        .select_related("owner")
        .prefetch_related("task_assignments__assignee")
        .order_by("created_at")
    )


@transaction.atomic
def close_finding(item: ActionItem, *, actor, note: str) -> ActionItem:
    """Direktur menutup temuan (terutama yang belum/tanpa penerima)."""
    assert_director(actor)
    _assert_clinic(actor, item.clinic)
    if item.source_type not in {FINDING_SOURCE, NOTE_SOURCE, "manual"}:
        raise ValidationError("Hanya task Direktur yang dapat ditutup dari halaman ini.")
    if not (note or "").strip():
        raise ValidationError("Tuliskan catatan penutupan.")
    before = snapshot(item)
    item.status = ActionItemStatus.SELESAI
    item.progress_note = note.strip()
    item.save(update_fields=["status", "progress_note", "updated_at"])
    log_update(item, before, actor=actor, action=AuditAction.CLOSE, reason=note.strip())
    return item


# --- Catatan -------------------------------------------------------------------

_WA_PREFIX = re.compile(
    r"^\s*\[?\d{1,2}[./-]\d{1,2}[./-]\d{2,4}[, ]+\d{1,2}[.:]\d{2}(?:[.:]\d{2})?\s*(?:[AaPp][Mm])?\]?"
    r"\s*(?:-\s*)?[^:]{1,40}:\s*"
)


def strip_wa_prefix(line: str) -> str:
    """'[27/09/26 10.15] Heni: Freezer penuh' -> 'Freezer penuh'."""
    return _WA_PREFIX.sub("", line, count=1).strip()


def suggest_title(body: str, limit: int = 120) -> str:
    for line in (body or "").splitlines():
        text = strip_wa_prefix(line)
        if text:
            return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
    return ""


def notes_for(user, *, archived: bool = False):
    assert_director(user)
    return DirectorNote.objects.filter(author=user, archived_at__isnull=not archived).select_related(
        "clinic", "converted_task"
    )


def create_note(*, author, body: str, source: str = NoteSource.MANUAL, clinic=None) -> DirectorNote:
    assert_director(author)
    if clinic is not None:
        _assert_clinic(author, clinic)
    if not (body or "").strip():
        raise ValidationError("Catatan kosong.")
    if source not in dict(NoteSource.choices):
        source = NoteSource.MANUAL
    note = DirectorNote.objects.create(author=author, body=body.strip(), source=source, clinic=clinic)
    log_create(note, actor=author)
    return note


def _own_note(note: DirectorNote, user) -> None:
    assert_director(user)
    if note.author_id != user.pk:
        raise PermissionDenied("Catatan ini milik orang lain.")


@transaction.atomic
def set_note_archived(note: DirectorNote, *, user, archived: bool) -> DirectorNote:
    _own_note(note, user)
    before = snapshot(note)
    note.archived_at = timezone.now() if archived else None
    note.save(update_fields=["archived_at", "updated_at"])
    log_update(note, before, actor=user, action=AuditAction.ARCHIVE if archived else AuditAction.REOPEN)
    return note


@transaction.atomic
def convert_note(
    note: DirectorNote,
    *,
    user,
    clinic,
    title: str,
    target: str,
    priority: str = Priority.SEDANG,
    due_at=None,
) -> ActionItem:
    """Jadikan catatan sebagai task. Catatan tetap ada sebagai asal task."""
    _own_note(note, user)
    note = DirectorNote.objects.select_for_update().get(pk=note.pk)
    if note.converted_task_id:
        raise ValidationError("Catatan ini sudah dijadikan task.")
    _assert_clinic(user, clinic)
    title = (title or "").strip() or suggest_title(note.body)
    if not title:
        raise ValidationError("Judul task wajib diisi.")
    if not (target or "").strip():
        raise ValidationError("Pilih penerima task.")
    item = _create_task_or_record(
        clinic=clinic,
        actor=user,
        title=title,
        description=note.body,
        target=target,
        priority=priority,
        due_at=due_at,
        source_type=NOTE_SOURCE,
        source_id=note.pk,
        source_label="Catatan Direktur",
    )
    note.converted_task = item
    note.converted_at = timezone.now()
    if note.clinic_id is None:
        note.clinic = clinic
    note.save(update_fields=["converted_task", "converted_at", "clinic", "updated_at"])
    log_event(
        action=AuditAction.UPDATE,
        entity_type="directornote",
        entity_id=note.pk,
        entity_label=str(note),
        actor=user,
        after={"converted_task": item.pk},
        reason="Dijadikan task",
    )
    return item


# --- Team Viewer ---------------------------------------------------------------

OPEN_ASSIGNMENT = ("OPEN", "IN_PROGRESS", "REVISION_REQUIRED")


def team_overview(user, today: dt.date | None = None) -> list[dict]:
    """Ringkasan baca-saja per cabang: apa yang sudah dan belum dikerjakan tim.

    Tidak ada skor atau peringkat antar-orang; yang ditampilkan hanya apa yang
    belum selesai dan siapa pemiliknya.
    """
    from checklists.models import ChecklistResponse, ResponseResult
    from core.models import OperationalDay, TaskAssignment, TaskAssignmentStatus
    from core.permissions import user_clinic_queryset

    from .dashboard import assert_overview

    assert_overview(user)  # Direktur dan Owner (Owner hanya membaca)
    today = today or local_today()
    week_ago = timezone.now() - dt.timedelta(days=7)
    clinics = []
    for clinic in user_clinic_queryset(user).order_by("id"):
        day = OperationalDay.objects.filter(clinic=clinic, date=today).first()
        runs = []
        if day:
            for run in day.checklist_runs.select_related("template").order_by("session", "area"):
                responses = list(run.responses.all())
                required = [r for r in responses if r.required]
                unfilled = [r for r in required if r.result == ResponseResult.BELUM]
                runs.append(
                    {
                        "run": run,
                        "name": run.template_snapshot.get("name") or run.template.name,
                        "roles": run.template_snapshot.get("target_roles") or [],
                        "total": len(required),
                        "unfilled": len(unfilled),
                        "problems": sum(1 for r in responses if r.is_problem),
                    }
                )

        assignments = (
            TaskAssignment.objects.filter(action_item__clinic=clinic)
            .exclude(status=TaskAssignmentStatus.CANCELLED)
            .select_related("assignee", "action_item")
        )
        people: dict[int, dict] = {}
        for a in assignments:
            is_open = a.status in OPEN_ASSIGNMENT
            is_waiting = a.status == TaskAssignmentStatus.SUBMITTED
            is_recent_done = (
                a.status == TaskAssignmentStatus.CONFIRMED and a.confirmed_at and a.confirmed_at >= week_ago
            )
            if not (is_open or is_waiting or is_recent_done):
                continue
            row = people.setdefault(
                a.assignee_id, {"user": a.assignee, "open": [], "waiting": [], "done": [], "pic": []}
            )
            key = "open" if is_open else "waiting" if is_waiting else "done"
            row[key].append(a)
        for pa in PicAssignment.objects.filter(clinic=clinic, active=True).select_related("user"):
            row = people.setdefault(
                pa.user_id, {"user": pa.user, "open": [], "waiting": [], "done": [], "pic": []}
            )
            row["pic"].append(pa.get_function_display())
        for row in people.values():
            row["open"].sort(key=lambda a: (a.action_item.due_at is None, a.action_item.due_at, a.created_at))
        pic_holders = {value: [] for value, _ in PicFunction.choices}
        for pa in PicAssignment.objects.filter(clinic=clinic, active=True, user__is_active=True).select_related("user"):
            pic_holders[pa.function].append(pa.user)

        clinics.append(
            {
                "clinic": clinic,
                "day": day,
                "runs": runs,
                "runs_unfilled": sum(r["unfilled"] for r in runs),
                "people": sorted(
                    people.values(),
                    key=lambda r: (-len(r["open"]), -len(r["waiting"]), str(r["user"]).lower()),
                ),
                "pic_holders": [
                    {"label": label, "users": pic_holders[value]} for value, label in PicFunction.choices
                ],
                "findings": list(open_findings(clinic)),
                "audit": pending_summary(clinic, today),
            }
        )
    return clinics


# --- Keputusan dan kebijakan -------------------------------------------------------

def parse_date(value: str, label: str = "Tanggal"):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError(f"{label} tidak valid.") from exc


def create_decision(
    *, actor, title: str, decider: str, clinic=None, reference: str = "", background: str = "",
    needed_by=None,
) -> Decision:
    assert_director(actor)
    if clinic is not None:
        _assert_clinic(actor, clinic)
    if not (title or "").strip():
        raise ValidationError("Perkara wajib diisi.")
    if decider not in dict(Decider.choices):
        raise ValidationError("Pilih siapa yang memutuskan.")
    decision = Decision.objects.create(
        clinic=clinic,
        reference=(reference or "").strip(),
        title=title.strip(),
        background=(background or "").strip(),
        decider=decider,
        needed_by=needed_by,
        created_by=actor,
    )
    log_create(decision, actor=actor)
    return decision


@transaction.atomic
def settle_decision(
    decision: Decision, *, actor, decision_text: str, is_policy: bool = False, decided_on=None
) -> Decision:
    """Catat keputusan yang sudah diambil (oleh siapa pun pemutusnya)."""
    assert_director(actor)
    if decision.clinic_id:
        _assert_clinic(actor, decision.clinic)
    if decision.status == DecisionStatus.DIBATALKAN:
        raise ValidationError("Keputusan yang dibatalkan tidak dapat ditetapkan.")
    if not (decision_text or "").strip():
        raise ValidationError("Tuliskan isi keputusannya.")
    before = snapshot(decision)
    decision.status = DecisionStatus.DITETAPKAN
    decision.decision_text = decision_text.strip()
    decision.is_policy = bool(is_policy)
    decision.decided_on = decided_on or local_today()
    decision.save()
    log_update(decision, before, actor=actor, action=AuditAction.APPROVE)
    _release_waiting(decision, actor=actor, verb="ditetapkan")
    return decision


@transaction.atomic
def cancel_decision(decision: Decision, *, actor, reason: str) -> Decision:
    assert_director(actor)
    if decision.clinic_id:
        _assert_clinic(actor, decision.clinic)
    if not (reason or "").strip():
        raise ValidationError("Alasan pembatalan wajib diisi.")
    before = snapshot(decision)
    decision.status = DecisionStatus.DIBATALKAN
    decision.decision_text = reason.strip()
    decision.save()
    log_update(decision, before, actor=actor, action=AuditAction.CANCEL, reason=reason.strip())
    _release_waiting(decision, actor=actor, verb="dibatalkan")
    return decision


# --- Task yang menunggu keputusan (K-015) ----------------------------------------

def _task_event(item: ActionItem, *, actor, note: str, **metadata) -> None:
    from core.models import TaskEvent, TaskEventType

    TaskEvent.objects.create(
        action_item=item, event_type=TaskEventType.COMMENT, actor=actor, note=note, metadata=metadata
    )


def _check_hold(actor, item: ActionItem, decision: Decision) -> None:
    assert_director(actor)
    _assert_clinic(actor, item.clinic)
    if decision.clinic_id not in (None, item.clinic_id):
        raise ValidationError("Keputusan ini untuk cabang lain.")


@transaction.atomic
def hold_task(item: ActionItem, decision: Decision, *, actor) -> None:
    """Tandai task menunggu keputusan: tenggatnya tidak dihitung terlambat sampai keputusan diambil."""
    _check_hold(actor, item, decision)
    if decision.status != DecisionStatus.MENUNGGU:
        raise ValidationError("Keputusan ini sudah tidak menunggu.")
    if item.status not in (ActionItemStatus.BARU, ActionItemStatus.DIKERJAKAN):
        raise ValidationError("Task ini sudah selesai atau dibatalkan.")
    if decision.waiting_tasks.filter(pk=item.pk).exists():
        return
    decision.waiting_tasks.add(item)
    _task_event(item, actor=actor, note=f"Ditahan menunggu keputusan: {decision}", decision=decision.pk,
                hold=True)
    log_event(action=AuditAction.UPDATE, entity_type="decision", entity_id=decision.pk,
              entity_label=f"{decision} · tahan task #{item.pk}", actor=actor,
              after={"waiting_task": item.pk})


@transaction.atomic
def release_task(item: ActionItem, decision: Decision, *, actor) -> None:
    _check_hold(actor, item, decision)
    if not decision.waiting_tasks.filter(pk=item.pk).exists():
        return
    decision.waiting_tasks.remove(item)
    _task_event(item, actor=actor, note=f"Tidak lagi menunggu keputusan: {decision}", decision=decision.pk,
                hold=False)
    log_event(action=AuditAction.UPDATE, entity_type="decision", entity_id=decision.pk,
              entity_label=f"{decision} · lepas task #{item.pk}", actor=actor,
              before={"waiting_task": item.pk})


@transaction.atomic
def bring_to_meeting(item: ActionItem, *, actor, title: str = "", background: str = "", needed_by=None) -> Decision:
    """Dari detail task: catat perkara untuk rapat bersama lalu tahan task-nya."""
    decision = create_decision(
        actor=actor,
        title=title or item.title,
        decider=Decider.RAPAT_BERSAMA,
        clinic=item.clinic,
        background=background,
        needed_by=needed_by,
    )
    hold_task(item, decision, actor=actor)
    return decision


def _release_waiting(decision: Decision, *, actor, verb: str) -> None:
    """Keputusan diambil/dibatalkan: task yang menunggu aktif kembali dan PIC-nya diberi tahu."""
    from core.models import TaskAssignmentStatus
    from notifications.services import notify_user

    open_states = (ActionItemStatus.BARU, ActionItemStatus.DIKERJAKAN)
    for item in decision.waiting_tasks.filter(status__in=open_states).select_related("created_by"):
        note = f"Keputusan {verb}: {decision}"
        if decision.decision_text:
            note += f" — {decision.decision_text[:200]}"
        if _task_event_exists(item, decision, verb):
            continue
        _task_event(item, actor=actor, note=note, decision=decision.pk, released=verb)
        people = {
            a.assignee
            for a in item.task_assignments.exclude(status=TaskAssignmentStatus.CANCELLED).select_related("assignee")
        }
        for person in people:
            notify_user(person, type_code="TASK_DECISION", title=f"Keputusan {verb}: {item.title}",
                        body=decision.decision_text[:300], entity_ref=f"actionitem#{item.pk}",
                        url_name="core:action_items")


def _task_event_exists(item: ActionItem, decision: Decision, verb: str) -> bool:
    """Isi keputusan boleh diperbarui; pemberitahuan cukup sekali per keputusan per task."""
    return item.task_events.filter(metadata__decision=decision.pk, metadata__released=verb).exists()
