"""Aturan Permintaan Owner, jadwal ringkas, dan summary harian untuk tampilan Owner."""
from __future__ import annotations

import datetime as dt

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.models import Role, User
from audit.models import AuditAction
from audit.services import log_create, log_event, log_update, snapshot
from core.models import ActionItemStatus, local_today
from core.permissions import is_aom, is_owner

from .models import OwnerRequest, OwnerRequestNote, RequestKind

TITLE_MAX = 200
URGENT_DAYS = 3
NORMAL_DAYS = 30


# --- Izin --------------------------------------------------------------------


def can_view_requests(user) -> bool:
    return is_owner(user) or is_aom(user)


def can_create_request(user) -> bool:
    """Hanya Owner / Direktur Utama yang membuat permintaan."""
    return is_owner(user)


def can_view_summary(user) -> bool:
    return is_owner(user) or is_aom(user)


# --- Permintaan --------------------------------------------------------------


def _directors():
    return User.objects.filter(is_active=True, user_roles__role=Role.AOM).distinct()


def _owners():
    return User.objects.filter(is_active=True, user_roles__role=Role.OWNER).distinct()


def _notify(users, *, actor, request: OwnerRequest, title: str, body: str = "", entity_ref: str | None = None) -> None:
    from notifications.services import notify_user

    for u in users:
        if u.pk == getattr(actor, "pk", None):
            continue
        notify_user(
            u,
            type_code="permintaan_owner",
            title=title,
            body=body,
            entity_ref=entity_ref or f"permintaan_owner:{request.pk}",
            url_name="owner:request_detail",
            url_args=[request.pk],
        )


def parse_target(raw: str, *, required: bool = True) -> dt.date | None:
    raw = (raw or "").strip()
    if not raw and not required:
        return None
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        raise ValidationError("Tanggal target wajib diisi.")


def _cap_from(day: dt.date, urgent: bool) -> dt.date:
    return day + dt.timedelta(days=URGENT_DAYS if urgent else NORMAL_DAYS)


def recorded_on(req: OwnerRequest) -> dt.date:
    """Tanggal temuan dicatat, menurut zona waktu klinik."""
    return timezone.localtime(req.created_at).date() if req.created_at else local_today()


def deadline_cap(req: OwnerRequest) -> dt.date | None:
    """Batas target temuan: 3 hari bila mendesak, 30 hari bila tidak. Permintaan tidak berbatas."""
    if req.kind != RequestKind.TEMUAN:
        return None
    return _cap_from(recorded_on(req), req.urgent)


def effective_target(req: OwnerRequest) -> dt.date | None:
    """Target dari Direktur bila ada; untuk temuan tanpa target, batasnya."""
    return req.target_date or deadline_cap(req)


@transaction.atomic
def create_request(
    *, actor, title: str, description: str = "", target_date: dt.date | None = None,
    kind: str = RequestKind.PERMINTAAN, clinic=None, urgent: bool = False,
) -> OwnerRequest:
    """Permintaan (target wajib) atau temuan dari Owner ke Inbox Direktur.

    Temuan mendesak otomatis bertarget hari ini + 3 hari; target temuan biasa ditetapkan Direktur
    kemudian, paling lambat 30 hari sejak dicatat.
    """
    if not can_create_request(actor):
        raise PermissionDenied("Permintaan hanya dibuat oleh Owner / Direktur Utama.")
    if kind not in dict(RequestKind.choices):
        raise ValidationError("Jenis tidak dikenal.")
    title = (title or "").strip()
    if not title:
        raise ValidationError("Tulis apa yang diminta." if kind == RequestKind.PERMINTAAN else "Tulis temuannya.")
    if len(title) > TITLE_MAX:
        raise ValidationError(f"Judul terlalu panjang (maks. {TITLE_MAX} karakter); rinciannya tulis di kolom rincian.")
    if kind == RequestKind.TEMUAN:
        cap = _cap_from(local_today(), bool(urgent))
        if urgent and target_date is None:
            target_date = cap
        if target_date is not None and target_date > cap:
            raise ValidationError(f"Target temuan paling lambat {cap:%d/%m/%Y}.")
    if target_date is None and kind == RequestKind.PERMINTAAN:
        raise ValidationError("Tanggal target wajib diisi.")
    if target_date is not None and target_date < local_today():
        raise ValidationError("Tanggal target tidak boleh sebelum hari ini.")
    req = OwnerRequest.objects.create(
        kind=kind, title=title, description=(description or "").strip(), target_date=target_date,
        clinic=clinic, urgent=bool(urgent), created_by=actor,
    )
    log_create(req, actor=actor, label=title)
    label = "Temuan Owner" if kind == RequestKind.TEMUAN else "Permintaan Owner"
    detail = [f"target {target_date:%d/%m/%Y}" if target_date else "tanpa target",
              clinic.name if clinic else "lintas cabang", f"dari {actor}"]
    _notify(_directors(), actor=actor, request=req,
            title=f"{label} baru{' (mendesak)' if urgent else ''}: {title}", body=" · ".join(detail))
    return req


@transaction.atomic
def add_note(req: OwnerRequest, *, actor, body: str) -> OwnerRequestNote:
    if not can_view_requests(actor):
        raise PermissionDenied("Catatan hanya dari Owner atau Direktur Operasional.")
    body = (body or "").strip()
    if not body:
        raise ValidationError("Catatan kosong.")
    note = OwnerRequestNote.objects.create(request=req, author=actor, body=body)
    log_event(action=AuditAction.CREATE, entity_type="ownerrequestnote", entity_id=note.pk,
              entity_label=req.title, actor=actor, after={"request": req.pk, "body": body[:300]})
    # Catatan Owner ke Direktur; catatan Direktur ke Owner.
    recipients = _directors() if is_owner(actor) and not is_aom(actor) else _owners()
    _notify(recipients, actor=actor, request=req, title=f"Catatan baru: {req.title}", body=body[:200])
    return note


@transaction.atomic
def set_plan(req: OwnerRequest, *, actor, plan_title: str, target_date: dt.date | None) -> OwnerRequest:
    """Direktur memberi nama task besar dan target, dalam batas 3/30 hari sejak temuan dicatat."""
    if not is_aom(actor):
        raise PermissionDenied("Hanya Direktur Operasional yang menyusun rencana penanganan.")
    if req.kind != RequestKind.TEMUAN:
        raise ValidationError("Rencana penanganan hanya untuk temuan.")
    if req.completed_at:
        raise ValidationError("Temuan ini sudah dinyatakan selesai.")
    plan_title = (plan_title or "").strip()
    if len(plan_title) > TITLE_MAX:
        raise ValidationError(f"Nama task besar terlalu panjang (maks. {TITLE_MAX} karakter).")
    cap = deadline_cap(req)
    if target_date is None and req.urgent:
        target_date = req.target_date or cap  # temuan mendesak selalu bertanggal
    if target_date is not None and target_date != req.target_date:
        if target_date < local_today():
            raise ValidationError("Tanggal target tidak boleh sebelum hari ini.")
        if target_date > cap:
            reason = "mendesak, 3 hari" if req.urgent else "1 bulan"
            raise ValidationError(f"Target paling lambat {cap:%d/%m/%Y} ({reason} sejak temuan dicatat).")
    before = snapshot(req)
    req.plan_title = plan_title
    req.target_date = target_date
    req.save(update_fields=["plan_title", "target_date", "updated_at"])
    log_update(req, before, actor=actor)
    return req


def has_pending_target(req: OwnerRequest) -> bool:
    return req.proposed_target is not None


def _is_finished(req: OwnerRequest) -> bool:
    return bool(req.completed_at) or progress(req)["state"] == "done"


@transaction.atomic
def propose_target(req: OwnerRequest, *, actor, target_date: dt.date | None, reason: str) -> OwnerRequest:
    """Direktur mengusulkan target baru; Owner yang memutuskan. Usulan baru menggantikan yang menunggu."""
    if not is_aom(actor):
        raise PermissionDenied("Hanya Direktur Operasional yang mengusulkan target.")
    req = OwnerRequest.objects.select_for_update().get(pk=req.pk)
    if _is_finished(req):
        raise ValidationError("Permintaan ini sudah selesai.")
    if target_date is None:
        raise ValidationError("Tanggal tidak valid.")
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("Tulis alasan usulan.")
    if target_date < local_today():
        raise ValidationError("Tanggal target tidak boleh sebelum hari ini.")
    if target_date == req.target_date:
        raise ValidationError("Usulan sama dengan target sekarang.")
    cap = deadline_cap(req)
    if cap is not None and target_date <= cap:
        raise ValidationError("Masih dalam batas; ubah langsung di Rencana penanganan.")
    old = req.target_date
    req.proposed_target = target_date
    req.proposed_reason = reason
    req.proposed_by = actor
    req.proposed_at = timezone.now()
    req.save(update_fields=["proposed_target", "proposed_reason", "proposed_by", "proposed_at", "updated_at"])
    OwnerRequestNote.objects.create(
        request=req, author=actor, body=f"Usul target baru {target_date:%d/%m/%Y}: {reason}")
    log_event(action=AuditAction.UPDATE, entity_type="ownerrequest", entity_id=req.pk, entity_label=req.title,
              actor=actor, after={"usul_target": target_date.isoformat(), "alasan": reason[:300]})
    old_text = f"{old:%d/%m/%Y}" if old else "tanpa target"
    _notify(_owners(), actor=actor, request=req, title=f"Usulan target baru: {req.title}",
            body=f"{old_text} → {target_date:%d/%m/%Y} · {reason}", entity_ref=f"permintaan_owner:{req.pk}:target")
    return req


@transaction.atomic
def decide_target(req: OwnerRequest, *, actor, approve: bool, note: str = "", expected: str | None = None) -> OwnerRequest:
    """Owner menyetujui (target diganti) atau menolak (alasan wajib) usulan target. Jawaban pertama menang."""
    if not is_owner(actor):
        raise PermissionDenied("Hanya Owner / Direktur Utama yang memutuskan target.")
    req = OwnerRequest.objects.select_for_update().get(pk=req.pk)
    if not has_pending_target(req):
        raise ValidationError("Tidak ada usulan target yang menunggu.")
    if expected:
        from django.utils.dateparse import parse_datetime

        if parse_datetime(expected.strip()) != req.proposed_at:
            raise ValidationError("Usulan target sudah berubah; periksa lagi.")
    if _is_finished(req):
        raise ValidationError("Permintaan ini sudah selesai.")
    note = (note or "").strip()
    if not approve and not note:
        raise ValidationError("Tulis alasan penolakan.")
    proposed = req.proposed_target
    before = snapshot(req)
    if approve:
        req.target_date = proposed
    req.proposed_target = None
    req.proposed_reason = ""
    req.proposed_by = None
    req.proposed_at = None
    req.save(update_fields=["target_date", "proposed_target", "proposed_reason", "proposed_by", "proposed_at",
                            "updated_at"])
    if approve:
        body = (f"Target baru {proposed:%d/%m/%Y} disetujui." + (f" {note}" if note else "")
                + " Target task turunan tidak ikut berubah; ubah di task bila perlu.")
        log_update(req, before, actor=actor, action=AuditAction.APPROVE)
    else:
        body = f"Usulan target {proposed:%d/%m/%Y} ditolak: {note}"
        log_event(action=AuditAction.UPDATE, entity_type="ownerrequest", entity_id=req.pk, entity_label=req.title,
                  actor=actor, after={"usulan_target_ditolak": proposed.isoformat(), "catatan": note[:300]})
    OwnerRequestNote.objects.create(request=req, author=actor, body=body)
    _notify(_directors(), actor=actor, request=req,
            title=f"Target {'disetujui' if approve else 'ditolak'}: {req.title}", body=body[:200],
            entity_ref=f"permintaan_owner:{req.pk}:target")
    return req


@transaction.atomic
def complete_finding(req: OwnerRequest, *, actor) -> OwnerRequest:
    """Direktur menyatakan temuan selesai & terverifikasi. Tidak pernah otomatis."""
    if not is_aom(actor):
        raise PermissionDenied("Hanya Direktur Operasional yang menyatakan temuan selesai.")
    if req.kind != RequestKind.TEMUAN:
        raise ValidationError("Hanya temuan yang dinyatakan selesai oleh Direktur.")
    if req.completed_at:
        raise ValidationError("Temuan ini sudah dinyatakan selesai.")
    tasks = list(req.tasks())
    if not tasks:
        raise ValidationError("Temuan belum punya sub task.")
    if any(t.status != ActionItemStatus.SELESAI for t in tasks):
        raise ValidationError("Masih ada sub task yang belum selesai.")
    req.completed_at = timezone.now()
    req.completed_by = actor
    req.save(update_fields=["completed_at", "completed_by", "updated_at"])
    log_event(action=AuditAction.UPDATE, entity_type="ownerrequest", entity_id=req.pk, entity_label=req.title,
              actor=actor, after={"completed_at": req.completed_at.isoformat(), "completed_by": actor.pk})
    _notify(_owners(), actor=actor, request=req, title=f"Temuan selesai & terverifikasi: {req.title}",
            body=f"oleh {actor}")
    return req


def progress(req: OwnerRequest, today: dt.date | None = None) -> dict:
    """Status permintaan/temuan dari task turunannya.

    Permintaan selesai otomatis bila semua task selesai. Temuan baru selesai bila Direktur
    menyatakannya (`complete_finding`); sebelum itu, semua sub task selesai = "Siap ditutup".
    """
    today = today or local_today()
    tasks = list(req.tasks())
    total = len(tasks)
    done = sum(1 for t in tasks if t.status == ActionItemStatus.SELESAI)
    temuan = req.kind == RequestKind.TEMUAN
    if temuan and req.completed_at:
        state, label = "done", "Selesai & terverifikasi"
    elif total == 0:
        state, label = "waiting", "Menunggu Direktur"
    elif done == total:
        state, label = ("ready", "Siap ditutup") if temuan else ("done", "Selesai")
    else:
        state, label = "running", "Berjalan"
    target = effective_target(req)
    late = state != "done" and target is not None and target < today
    finished_on = timezone.localtime(req.completed_at).date() if req.completed_at else None
    return {
        "request": req,
        "tasks": tasks,
        "total": total,
        "done": done,
        "percent": round(done * 100 / total) if total else 0,
        "state": state,
        "label": label,
        "late": late,
        "target": target,
        "target_set": req.target_date is not None,
        "days_left": (target - today).days if target else None,
        "days_late": max(0, (today - target).days) if target else 0,
        "finished_late_by": max(0, (finished_on - target).days) if finished_on and target else 0,
    }


def subtask_rows(req: OwnerRequest) -> list[dict]:
    """Sub task temuan untuk Owner: siapa yang mengerjakan dan status verifikasinya."""
    from core.models import TaskAssignmentStatus

    rows = []
    for task in req.tasks().prefetch_related("task_assignments__assignee"):
        active = [a for a in task.task_assignments.all() if a.status != TaskAssignmentStatus.CANCELLED]
        confirmed = [a for a in active if a.status == TaskAssignmentStatus.CONFIRMED]
        if task.status == ActionItemStatus.SELESAI:
            self_done = not confirmed or any(a.reviewer_id in (None, a.assignee_id) for a in confirmed)
            state, label = "done", ("Selesai oleh Direktur" if self_done else "Terverifikasi Direktur")
        elif any(a.status == TaskAssignmentStatus.SUBMITTED for a in active):
            state, label = "waiting", "Menunggu verifikasi"
        else:
            state, label = "running", "Berjalan"
        rows.append({
            "task": task,
            "state": state,
            "label": label,
            "people": ", ".join(sorted({str(a.assignee) for a in (confirmed or active)})),
            "finished_at": max((a.confirmed_at for a in confirmed if a.confirmed_at), default=None),
        })
    return rows


def request_rows(user, *, include_done_days: int = 14) -> list[dict]:
    """Permintaan yang masih berjalan, ditambah yang selesai belakangan ini."""
    if not can_view_requests(user):
        raise PermissionDenied("Permintaan Owner hanya untuk Owner dan Direktur Operasional.")
    today = local_today()
    rows = [progress(r, today) for r in OwnerRequest.objects.select_related("created_by", "clinic")]
    since = today - dt.timedelta(days=include_done_days)
    rows = [r for r in rows if r["state"] != "done" or r["request"].updated_at.date() >= since
            or any(t.updated_at.date() >= since for t in r["tasks"])]
    order = {"waiting": 1, "running": 1, "ready": 1, "done": 2}
    far = dt.date.max
    rows.sort(key=lambda r: (
        not (r["request"].kind == RequestKind.TEMUAN and r["request"].urgent and r["state"] != "done"), not r["late"], order[r["state"]], r["target"] or far,
    ))
    return rows


# --- Keputusan Owner (7 Okt 2026) ------------------------------------------------------

DECIDE_ACTIONS = ("setuju", "tolak", "rapat")


def _notify_decision_outcome(decision, *, actor, text: str) -> None:
    """Hasil keputusan Owner ke semua Direktur Operasional aktif dan pengaju perkara."""
    from notifications.services import notify_user

    people = {u.pk: u for u in _directors()}
    if decision.created_by_id and decision.created_by.is_active:
        people.setdefault(decision.created_by_id, decision.created_by)
    for person in people.values():
        if person.pk == actor.pk:
            continue
        notify_user(
            person, type_code="DECISION_DECIDED", title=f"Keputusan Owner: {decision.title}", body=text,
            entity_ref=f"decision#{decision.pk}", url_name="direktur:decision_detail", url_args=[decision.pk],
        )


@transaction.atomic
def decide(decision, *, actor, verdict: str, note: str = ""):
    """Owner menjawab permintaan keputusan Direktur: Setujui, Tolak (alasan wajib), atau Bahas di rapat."""
    from direktur.models import Decider, Decision, DecisionStatus, Verdict
    from direktur.services import _release_waiting, is_owner_decision

    if not is_owner(actor):
        raise PermissionDenied("Hanya Owner / Direktur Utama yang memutuskan perkara ini.")
    if verdict not in DECIDE_ACTIONS:
        raise ValidationError("Pilihan keputusan tidak dikenal.")
    decision = Decision.objects.select_for_update().get(pk=decision.pk)
    if decision.status != DecisionStatus.MENUNGGU or not is_owner_decision(decision):
        raise ValidationError("Perkara ini sudah diputuskan, dibatalkan, atau dipindah ke rapat.")
    note = (note or "").strip()
    if verdict == "tolak" and not note:
        raise ValidationError("Tulis alasan penolakan.")
    before = snapshot(decision)
    name = str(actor)
    if verdict == "rapat":
        decision.decider = Decider.RAPAT_BERSAMA
        if note:
            line = f"Catatan Owner ({name}, {local_today():%d/%m/%Y}): {note}"
            decision.background = f"{decision.background}\n\n{line}".strip()
        decision.save()
        log_update(decision, before, actor=actor)
        text = "Dibawa ke rapat Kamis" + (f": {note}" if note else "")
    else:
        decision.status = DecisionStatus.DITETAPKAN
        decision.verdict = Verdict.SETUJU if verdict == "setuju" else Verdict.TOLAK
        decision.decided_by = actor
        decision.decided_on = local_today()
        label = "Disetujui" if verdict == "setuju" else "Ditolak"
        decision.decision_text = f"{label} {name}" + (f": {note}" if note else "")
        decision.save()
        log_update(decision, before, actor=actor, action=AuditAction.APPROVE)
        _release_waiting(decision, actor=actor, verb="ditetapkan")
        text = decision.decision_text
    _notify_decision_outcome(decision, actor=actor, text=text)
    return decision


def decisions_awaiting(user) -> list[dict]:
    """Kartu "Menunggu keputusan Anda": perkara Owner/Dirut yang masih menunggu, terlambat dulu."""
    from direktur.dashboard import decisions_for
    from direktur.models import DecisionStatus
    from direktur.services import OWNER_DECIDERS

    if not is_owner(user):
        return []
    today = local_today()
    qs = decisions_for(user).filter(status=DecisionStatus.MENUNGGU, decider__in=OWNER_DECIDERS)
    rows = [
        {"decision": d, "late": d.is_overdue(today), "age_days": (today - timezone.localtime(d.created_at).date()).days}
        for d in qs.select_related("created_by", "clinic")
    ]
    rows.sort(key=lambda r: (not r["late"], r["decision"].needed_by or dt.date.max, r["decision"].created_at))
    return rows


# --- Summary Harian dua arah (7 Okt 2026) -------------------------------------------------


def record_summary_read(summary, user) -> None:
    """Owner membuka summary satu tanggal: catat waktunya. Direktur sendiri tidak dicatat."""
    from direktur.models import DailySummaryRead

    if summary is None or not is_owner(user) or is_aom(user):
        return
    DailySummaryRead.objects.update_or_create(summary=summary, user=user, defaults={"read_at": timezone.now()})


def summary_reads(summary) -> list[dict]:
    """Status baca tiap Owner aktif: baca, lama (sebelum dikirim ulang), atau belum."""
    reads = {r.user_id: r.read_at for r in summary.reads.all()}
    rows = []
    for owner in _owners().order_by("display_name", "username"):
        at = reads.get(owner.pk)
        state = "belum" if at is None else ("lama" if at < summary.sent_at else "baca")
        rows.append({"user": owner, "read_at": at, "state": state})
    return rows


def summary_is_read(summary) -> bool:
    return summary.reads.filter(read_at__gte=summary.sent_at).exists()


@transaction.atomic
def add_summary_note(summary, *, actor, body: str):
    """Tanggapan pada summary: Owner → semua Direktur aktif, Direktur → semua Owner aktif."""
    from django.urls import reverse

    from direktur.models import DailySummaryNote
    from notifications.services import notify_user

    if not (is_owner(actor) or is_aom(actor)):
        raise PermissionDenied("Tanggapan summary hanya dari Owner atau Direktur Operasional.")
    body = (body or "").strip()
    if not body:
        raise ValidationError("Tanggapan kosong.")
    note = DailySummaryNote.objects.create(summary=summary, author=actor, body=body)
    log_event(action=AuditAction.CREATE, entity_type="dailysummarynote", entity_id=note.pk,
              entity_label=f"Tanggapan Summary {summary.date:%d/%m/%Y}", actor=actor,
              after={"summary": summary.pk, "body": body[:300]})
    recipients = _directors() if is_owner(actor) and not is_aom(actor) else _owners()
    url = reverse("owner:summary") + f"?tanggal={summary.date:%Y-%m-%d}"
    for person in recipients.exclude(pk=actor.pk):
        notif = notify_user(person, type_code="SUMMARY_NOTE",
                            title=f"Tanggapan Summary {summary.date:%d/%m}: {body[:60]}", body=body[:200],
                            entity_ref=f"dailysummary:{summary.pk}")
        if notif is not None:
            notif.url = url
            notif.save(update_fields=["url"])
    return note


# --- Jadwal ringkas ----------------------------------------------------------


def duty_today(clinic, day: dt.date) -> dict:
    """Siapa bertugas di cabang ini pada satu tanggal, dan siapa yang libur."""
    from jadwal.models import DutyRoster, DutyStatus
    from jadwal.services import has_roster, working_rows

    working = []
    for row in working_rows(clinic, day):
        if not row.user.is_active:
            continue
        working.append({
            "user": row.user,
            "title": row.user.job_title,
            "note": f"perbantuan dari {row.home_clinic.name}" if row.status == DutyStatus.PERBANTUAN else "",
        })
    away = []
    rows = (
        DutyRoster.objects.filter(home_clinic=clinic, date=day)
        .exclude(status=DutyStatus.MASUK)
        .select_related("user", "clinic")
        .order_by("user__display_name", "user__username")
    )
    for row in rows:
        if not row.user.is_active:
            continue
        if row.status == DutyStatus.PERBANTUAN:
            label = f"di {row.clinic.name}"
        else:
            label = row.get_status_display()
        away.append({"user": row.user, "label": label})
    return {"working": working, "away": away, "filled": has_roster(clinic, day)}


# --- Verifikasi oleh Direktur Utama / Owner (tahap 2 paket C) ------------------------

def verification_queue(user) -> list:
    """Penerima yang sudah mengajukan selesai pada task yang diperiksa Dirut/Owner."""
    from core.models import TaskAssignment, TaskAssignmentStatus
    from core.permissions import user_clinic_queryset
    from core.task_services import can_review_assignment

    if not is_owner(user):
        return []
    qs = (
        TaskAssignment.objects.filter(
            status=TaskAssignmentStatus.SUBMITTED, action_item__clinic__in=user_clinic_queryset(user),
            action_item__status__in=[ActionItemStatus.BARU, ActionItemStatus.DIKERJAKAN],
        )
        .select_related("action_item", "action_item__clinic", "assignee")
        .order_by("submitted_at")
    )
    rows = []
    for a in qs:
        if not a.action_item.reviewed_by_dirut or not can_review_assignment(a, user):
            continue
        last = a.events.filter(event_type="SUBMITTED").order_by("-created_at").first()
        rows.append({"assignment": a, "item": a.action_item, "note": last.note if last else ""})
    return rows


def recent_achievements(user, days: int = 7) -> list:
    """Task yang selesai dan terverifikasi dalam `days` hari terakhir: laporan capaian ke Dirut."""
    from django.utils import timezone

    from core.models import ActionItem, TaskAssignmentStatus
    from core.permissions import user_clinic_queryset

    since = timezone.now() - dt.timedelta(days=days)
    items = (
        ActionItem.objects.filter(
            clinic__in=user_clinic_queryset(user), status=ActionItemStatus.SELESAI, updated_at__gte=since,
        )
        .select_related("clinic")
        .prefetch_related("task_assignments__assignee", "task_assignments__reviewer")
        .order_by("-updated_at")
    )
    rows = []
    for item in items:
        done = [a for a in item.task_assignments.all() if a.status == TaskAssignmentStatus.CONFIRMED]
        rows.append({
            "item": item,
            "people": ", ".join(sorted({str(a.assignee) for a in done})),
            "reviewers": ", ".join(sorted({str(a.reviewer) for a in done if a.reviewer})),
        })
    return rows
