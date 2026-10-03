"""Ringkasan menyeluruh (bird view), matriks Eisenhower, dan kanban.

Satu halaman untuk dua penonton: Owner (cukup tahu ada masalah atau tidak,
keputusan apa yang menggantung, kebijakan apa yang ditetapkan) dan Direktur
Operasional (memantau lalu bertindak). Semua data dihitung dari model yang
sudah ada; tidak ada skor atau peringkat antarorang.
"""
from __future__ import annotations

import datetime as dt

from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.utils import timezone

from core.models import (
    ActionItem,
    ActionItemStatus,
    ClinicConfig,
    OperationalDay,
    Priority,
    TaskAssignmentStatus,
    local_today,
)
from core.permissions import is_aom, is_owner, user_clinic_queryset

from .models import Decision, DecisionStatus

OPEN_ITEM = (ActionItemStatus.BARU, ActionItemStatus.DIKERJAKAN)
RECENT_DONE_DAYS = 7
POLICY_RECENT_DAYS = 30

SOURCE_LABELS = {
    "audit_direktur": "Temuan Direktur",
    "catatan_direktur": "Catatan Direktur",
    "manual": "Task manual",
    "permintaan_owner": "Permintaan Owner",
    "keputusan": "Keputusan",
    "issue": "Komplain/masukan/kerusakan",
    "laporan": "Laporan staf",
    "masukan": "Masukan staf",
}


def can_view_overview(user) -> bool:
    return is_aom(user) or is_owner(user)


def assert_overview(user) -> None:
    if not can_view_overview(user):
        raise PermissionDenied("Ringkasan hanya untuk Owner dan Direktur Operasional.")


def source_group(item: ActionItem) -> str:
    if item.source_type in SOURCE_LABELS:
        return item.source_type
    if item.source_type.startswith("checklist"):
        return "checklist"
    return "lain"


SOURCE_CHOICES = [
    ("audit_direktur", "Temuan Direktur"),
    ("catatan_direktur", "Catatan Direktur"),
    ("manual", "Task manual"),
    ("permintaan_owner", "Permintaan Owner"),
    ("keputusan", "Keputusan"),
    ("issue", "Komplain/masukan/kerusakan"),
    ("laporan", "Laporan staf"),
    ("masukan", "Masukan staf"),
    ("checklist", "Checklist staf"),
    ("lain", "Modul lain"),
]


def source_url(item: ActionItem) -> str:
    """Tautan ke asal task (laporan, permintaan Owner, keputusan), bila ada halamannya."""
    from django.urls import reverse

    routes = {
        "issue": "issues:detail",
        "laporan": "reports:laporan_page_detail",
        "masukan": "reports:masukan_page_detail",
        "permintaan_owner": "owner:request_detail",
        "keputusan": "direktur:decision_detail",
    }
    route = routes.get(item.source_type)
    return reverse(route, args=[item.source_id]) if route and item.source_id else ""


def reporters(items) -> dict[int, object]:
    """Pelapor asal tiap task: orang yang pertama kali melihat/menulis masalahnya.

    Task dari checklist -> staf yang mengisi butir; temuan Direktur -> pemeriksa; permintaan
    Owner -> Owner; catatan -> penulis catatan. Selain itu (task manual, keputusan) pembuat task.
    Satu query per jenis sumber, bukan per task.
    """
    from checklists.models import ChecklistResponse
    from issues.models import Issue
    from owner.models import OwnerRequest
    from reports.models import Laporan, Masukan

    from .models import AuditCheck, DirectorNote

    items = list(items)
    lookups = {
        "checklistresponse": (ChecklistResponse, "checked_by"),
        "audit_direktur": (AuditCheck, "checked_by"),
        "permintaan_owner": (OwnerRequest, "created_by"),
        "catatan_direktur": (DirectorNote, "author"),
        "issue": (Issue, "created_by"),
        "laporan": (Laporan, "created_by"),
        "masukan": (Masukan, "created_by"),
    }
    found: dict[tuple[str, int], object] = {}
    for source, (model, field) in lookups.items():
        ids = {i.source_id for i in items if i.source_type == source and i.source_id}
        if ids:
            for obj in model.objects.filter(pk__in=ids).select_related(field):
                found[(source, obj.pk)] = getattr(obj, field)
    return {
        i.pk: found.get((i.source_type, i.source_id)) or i.created_by
        for i in items
    }


# --- Kanban --------------------------------------------------------------------

class Column:
    BARU = "BARU"
    DIKERJAKAN = "DIKERJAKAN"
    MENUNGGU = "MENUNGGU"
    SELESAI = "SELESAI"


COLUMNS = [
    (Column.BARU, "Baru"),
    (Column.DIKERJAKAN, "Dikerjakan"),
    (Column.MENUNGGU, "Menunggu konfirmasi"),
    (Column.SELESAI, f"Selesai ({RECENT_DONE_DAYS} hari)"),
]


def kanban_column(item: ActionItem, assignments) -> str | None:
    """Kolom kanban dari status task + status penerimanya.

    `ActionItem.status` sendiri hanya berpindah BARU -> SELESAI pada alur task,
    jadi posisi "dikerjakan" dan "menunggu konfirmasi" dibaca dari assignment.
    """
    if item.status == ActionItemStatus.BATAL:
        return None
    if item.status == ActionItemStatus.SELESAI:
        return Column.SELESAI
    active = [a for a in assignments if a.status != TaskAssignmentStatus.CANCELLED]
    states = {a.status for a in active}
    if active and states <= {TaskAssignmentStatus.SUBMITTED, TaskAssignmentStatus.CONFIRMED} and (
        TaskAssignmentStatus.SUBMITTED in states
    ):
        return Column.MENUNGGU
    if item.status == ActionItemStatus.DIKERJAKAN or states & {
        TaskAssignmentStatus.IN_PROGRESS,
        TaskAssignmentStatus.REVISION_REQUIRED,
        TaskAssignmentStatus.SUBMITTED,
        TaskAssignmentStatus.CONFIRMED,
    }:
        return Column.DIKERJAKAN
    return Column.BARU


def _items(user, *, clinic_id=None, source=""):
    clinics = user_clinic_queryset(user)
    since = timezone.now() - dt.timedelta(days=RECENT_DONE_DAYS)
    qs = (
        ActionItem.objects.filter(clinic__in=clinics)
        .filter(Q(status__in=OPEN_ITEM) | Q(status=ActionItemStatus.SELESAI, updated_at__gte=since))
        .select_related("clinic", "owner", "created_by")
        .prefetch_related("task_assignments__assignee", "waiting_decisions")
    )
    if clinic_id:
        qs = qs.filter(clinic_id=clinic_id)
    items = list(qs)
    if source:
        items = [i for i in items if source_group(i) == source]
    return items


def _card(item: ActionItem, now, reporter=None) -> dict:
    assignments = list(item.task_assignments.all())
    names = [str(a.assignee) for a in assignments if a.status != TaskAssignmentStatus.CANCELLED]
    return {
        "item": item,
        "column": kanban_column(item, assignments),
        "recipients": names,
        "reporter": reporter,
        "source": dict(SOURCE_CHOICES).get(source_group(item), "Modul lain"),
        "age_days": (now - item.created_at).days,
        "overdue": item.is_overdue,
        "on_hold": item.on_hold,
    }


def kanban(user, *, clinic_id=None, source="", limit: int | None = None) -> list[dict]:
    assert_overview(user)
    now = timezone.now()
    board = {key: [] for key, _ in COLUMNS}
    items = _items(user, clinic_id=clinic_id, source=source)
    who = reporters(items)
    for item in items:
        card = _card(item, now, who.get(item.pk))
        if card["column"]:
            board[card["column"]].append(card)
    far = dt.datetime.max.replace(tzinfo=dt.timezone.utc)
    out = []
    for key, label in COLUMNS:
        cards = board[key]
        if key == Column.SELESAI:
            cards.sort(key=lambda c: c["item"].updated_at, reverse=True)
        else:
            cards.sort(key=lambda c: (c["item"].due_at or far, c["item"].created_at))
        out.append({"key": key, "label": label, "count": len(cards), "cards": cards[:limit] if limit else cards})
    return out


# --- Eisenhower ------------------------------------------------------------------

QUADRANTS = [
    ("I", "Kerjakan sekarang", "Penting · mendesak"),
    ("II", "Jadwalkan", "Penting · tidak mendesak"),
    ("III", "Delegasikan", "Tidak penting · mendesak"),
    ("IV", "Tinjau ulang", "Tidak penting · tidak mendesak"),
]


def urgent_hours(clinic) -> int:
    try:
        return int(ClinicConfig.get(clinic, "dashboard.urgent_hours", 48))
    except (TypeError, ValueError):
        return 48


def quadrant(item: ActionItem, now, hours: int) -> str:
    important = item.priority in (Priority.TINGGI, Priority.KRITIS)
    urgent = item.priority == Priority.KRITIS or bool(
        item.due_at and item.due_at <= now + dt.timedelta(hours=hours)
    )
    if important:
        return "I" if urgent else "II"
    return "III" if urgent else "IV"


def eisenhower(user, *, clinic_id=None, source="", limit: int | None = None) -> list[dict]:
    assert_overview(user)
    now = timezone.now()
    hours_by_clinic: dict[int, int] = {}
    buckets = {key: [] for key, _, _ in QUADRANTS}
    items = [i for i in _items(user, clinic_id=clinic_id, source=source) if i.status in OPEN_ITEM]
    who = reporters(items)
    for item in items:
        hours = hours_by_clinic.setdefault(item.clinic_id, urgent_hours(item.clinic))
        buckets[quadrant(item, now, hours)].append(_card(item, now, who.get(item.pk)))
    far = dt.datetime.max.replace(tzinfo=dt.timezone.utc)
    out = []
    for key, title, subtitle in QUADRANTS:
        cards = sorted(buckets[key], key=lambda c: (c["item"].due_at or far, c["item"].created_at))
        out.append(
            {"key": key, "title": title, "subtitle": subtitle, "count": len(cards),
             "cards": cards[:limit] if limit else cards}
        )
    return out


# --- Keputusan -------------------------------------------------------------------

def decisions_for(user):
    assert_overview(user)
    clinics = user_clinic_queryset(user)
    return Decision.objects.filter(Q(clinic__isnull=True) | Q(clinic__in=clinics)).select_related("clinic")


def pending_decisions(user):
    return decisions_for(user).filter(status=DecisionStatus.MENUNGGU).order_by("needed_by", "created_at")


MEETING_WEEKDAY = 3  # Kamis


def next_meeting(today: dt.date) -> dt.date:
    """Rapat mingguan hari Kamis; pada hari Kamis, rapatnya hari itu juga."""
    return today + dt.timedelta(days=(MEETING_WEEKDAY - today.weekday()) % 7)


def meeting_agenda(user, today: dt.date | None = None) -> dict:
    """Perkara yang menunggu keputusan untuk halaman utama (K-015).

    `rapat`: dibahas di rapat bersama Kamis; `lain`: menunggu pemutus lain (Owner, Dirut, dst.).
    Tiap baris membawa task yang tertahan menunggu perkara itu.
    """
    from django.db.models import Prefetch

    today = today or local_today()
    open_tasks = ActionItem.objects.filter(status__in=OPEN_ITEM).select_related("clinic")
    rows = []
    for d in pending_decisions(user).prefetch_related(Prefetch("waiting_tasks", queryset=open_tasks)):
        rows.append({"decision": d, "tasks": list(d.waiting_tasks.all()), "late": d.is_overdue(today),
                     "age_days": (today - timezone.localtime(d.created_at).date()).days})
    from .models import Decider

    return {
        "date": next_meeting(today),
        "rapat": [r for r in rows if r["decision"].decider == Decider.RAPAT_BERSAMA],
        "lain": [r for r in rows if r["decision"].decider != Decider.RAPAT_BERSAMA],
        "held": sum(len(r["tasks"]) for r in rows),
    }


def recent_policies(user, today: dt.date | None = None):
    today = today or local_today()
    since = today - dt.timedelta(days=POLICY_RECENT_DAYS)
    return decisions_for(user).filter(
        status=DecisionStatus.DITETAPKAN, decided_on__gte=since
    ).order_by("-decided_on", "-updated_at")


# --- Bird view -------------------------------------------------------------------

def bird_view(user, today: dt.date | None = None) -> dict:
    """Keadaan per cabang dalam tiga warna, dengan alasannya dalam kalimat.

    Merah  : ada task lewat target, temuan tanpa penerima, atau keputusan lewat tenggat.
    Kuning : ada temuan terbuka, task menunggu konfirmasi, keputusan menggantung,
             atau checklist staf hari ini belum lengkap setelah jam buka.
    Hijau  : tidak ada di atas.
    """
    from . import services

    assert_overview(user)
    today = today or local_today()
    now = timezone.now()
    pending = list(pending_decisions(user))
    cards = []
    for clinic in user_clinic_queryset(user).order_by("id"):
        day = OperationalDay.objects.filter(clinic=clinic, date=today).first()
        open_items = ActionItem.objects.filter(clinic=clinic, status__in=OPEN_ITEM)
        overdue = [i for i in open_items if i.is_overdue]
        findings = list(services.open_findings(clinic))
        no_recipient = [f for f in findings if not f.task_assignments.all()]
        waiting = open_items.filter(task_assignments__status=TaskAssignmentStatus.SUBMITTED).distinct().count()
        clinic_pending = [d for d in pending if d.clinic_id in (None, clinic.pk)]
        late_decisions = [d for d in clinic_pending if d.is_overdue(today)]
        staff_total = staff_unfilled = 0
        if day:
            from checklists.models import ResponseResult

            for run in day.checklist_runs.all():
                required = [r for r in run.responses.all() if r.required]
                staff_total += len(required)
                staff_unfilled += sum(1 for r in required if r.result == ResponseResult.BELUM)
        audit = services.pending_summary(clinic, today)

        red, yellow = [], []
        if overdue:
            red.append(f"{len(overdue)} task lewat target")
        if no_recipient:
            red.append(f"{len(no_recipient)} temuan tanpa penerima")
        if late_decisions:
            red.append(f"{len(late_decisions)} keputusan lewat tenggat")
        if len(findings) - len(no_recipient) > 0:
            yellow.append(f"{len(findings) - len(no_recipient)} temuan Direktur terbuka")
        if waiting:
            yellow.append(f"{waiting} task menunggu konfirmasi")
        if len(clinic_pending) - len(late_decisions) > 0:
            yellow.append(f"{len(clinic_pending) - len(late_decisions)} keputusan menggantung")
        opened = bool(day and day.opened_at)
        if opened and staff_unfilled:
            yellow.append(f"{staff_unfilled} butir checklist staf belum diisi")
        level = "merah" if red else "kuning" if yellow else "hijau"
        cards.append(
            {
                "clinic": clinic,
                "day": day,
                "level": level,
                "reasons": red + yellow,
                "staff_total": staff_total,
                "staff_done": staff_total - staff_unfilled,
                "audit": audit,
                "findings": len(findings),
                "overdue": len(overdue),
                "waiting": waiting,
            }
        )
    problems = [c for c in cards if c["level"] != "hijau"]
    return {
        "cards": cards,
        "any_problem": bool(problems),
        "pending_decisions": pending,
        "late_decisions": [d for d in pending if d.is_overdue(today)],
        "recent_policies": list(recent_policies(user, today)[:8]),
        "generated_at": now,
    }


# --- Ringkasan ringkas (halaman utama) --------------------------------------------

def headline_counts(user, today: dt.date | None = None) -> dict:
    """Angka untuk kartu ringkas di halaman utama, gabungan semua cabang."""
    assert_overview(user)
    today = today or local_today()
    now = timezone.now()
    open_items = [i for i in _items(user) if i.status in OPEN_ITEM]
    waiting = 0
    for item in open_items:
        if kanban_column(item, list(item.task_assignments.all())) == Column.MENUNGGU:
            waiting += 1
    pending = list(pending_decisions(user))
    week = now + dt.timedelta(days=7)
    return {
        "open": len(open_items),
        "overdue": sum(1 for i in open_items if i.is_overdue),
        "waiting": waiting,
        "due_week": sum(1 for i in open_items if i.due_at and now <= i.due_at <= week),
        "decisions": len(pending),
        "late_decisions": sum(1 for d in pending if d.is_overdue(today)),
        "policies": recent_policies(user, today).count(),
    }


# --- Gantt -----------------------------------------------------------------------

def gantt(user, *, clinic_id=None, source="", days_back: int = 7, days_ahead: int = 21) -> dict:
    """Bar per task dari dibuat sampai target, dalam jendela waktu tetap.

    Posisi bar dihitung sebagai persen jendela agar dapat digambar dengan CSS saja.
    Task tanpa target dan task yang lewat target digambar sampai hari ini.
    """
    assert_overview(user)
    now = timezone.now()
    today = timezone.localtime(now).date()
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(dt.datetime.combine(today - dt.timedelta(days=days_back), dt.time.min), tz)
    end = timezone.make_aware(dt.datetime.combine(today + dt.timedelta(days=days_ahead + 1), dt.time.min), tz)
    span = (end - start).total_seconds()

    def pct(moment):
        moment = min(max(moment, start), end)
        return round((moment - start).total_seconds() / span * 100, 2)

    rows = []
    for item in _items(user, clinic_id=clinic_id, source=source):
        card = _card(item, now)
        done = item.status == ActionItemStatus.SELESAI
        # Task lewat target digambar sampai hari ini: bar merah yang memanjang
        # menunjukkan berapa lama ia sudah menggantung.
        finish = item.updated_at if done else (now if item.is_overdue or not item.due_at else item.due_at)
        if finish < start or item.created_at > end:
            continue
        left = pct(item.created_at)
        width = max(pct(finish) - left, 1.2)
        if done:
            state, label = "done", "Selesai"
        elif item.is_overdue:
            state, label = "late", "Lewat target"
        elif not item.due_at:
            state, label = "nodue", "Tanpa target"
        else:
            state, label = "open", "Berjalan"
        rows.append({**card, "left": left, "width": min(width, 100 - left), "state": state, "state_label": label})
    order = {"late": 0, "open": 1, "nodue": 2, "done": 3}
    far = dt.datetime.max.replace(tzinfo=dt.timezone.utc)
    rows.sort(key=lambda r: (r["item"].clinic_id, order[r["state"]], r["item"].due_at or far))
    ticks = []
    day = today - dt.timedelta(days=days_back)
    while day <= today + dt.timedelta(days=days_ahead):
        moment = timezone.make_aware(dt.datetime.combine(day, dt.time.min), tz)
        ticks.append({"left": pct(moment), "label": day.strftime("%d/%m"), "monday": day.weekday() == 0})
        day += dt.timedelta(days=1)
    return {
        "rows": rows,
        "ticks": [t for t in ticks if t["monday"]],
        "today_left": pct(now),
        "start": start,
        "end": end - dt.timedelta(days=1),
    }
