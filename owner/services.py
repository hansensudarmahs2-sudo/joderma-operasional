"""Aturan Permintaan Owner, jadwal ringkas, dan summary harian untuk tampilan Owner."""
from __future__ import annotations

import datetime as dt

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from accounts.models import Role, User
from audit.models import AuditAction
from audit.services import log_create, log_event
from core.models import ActionItemStatus, local_today
from core.permissions import is_aom, is_owner

from .models import OwnerRequest, OwnerRequestNote

TITLE_MAX = 200


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


def _notify(users, *, actor, request: OwnerRequest, title: str, body: str = "") -> None:
    from notifications.services import notify_user

    for u in users:
        if u.pk == getattr(actor, "pk", None):
            continue
        notify_user(
            u,
            type_code="permintaan_owner",
            title=title,
            body=body,
            entity_ref=f"permintaan_owner:{request.pk}",
            url_name="owner:request_detail",
            url_args=[request.pk],
        )


def parse_target(raw: str) -> dt.date:
    try:
        return dt.date.fromisoformat((raw or "").strip())
    except ValueError:
        raise ValidationError("Tanggal target wajib diisi.")


@transaction.atomic
def create_request(*, actor, title: str, description: str = "", target_date: dt.date) -> OwnerRequest:
    if not can_create_request(actor):
        raise PermissionDenied("Permintaan hanya dibuat oleh Owner / Direktur Utama.")
    title = (title or "").strip()
    if not title:
        raise ValidationError("Tulis apa yang diminta.")
    if len(title) > TITLE_MAX:
        raise ValidationError(f"Permintaan terlalu panjang (maks. {TITLE_MAX} karakter); rinciannya tulis di kolom rincian.")
    if target_date < local_today():
        raise ValidationError("Tanggal target tidak boleh sebelum hari ini.")
    req = OwnerRequest.objects.create(
        title=title, description=(description or "").strip(), target_date=target_date, created_by=actor
    )
    log_create(req, actor=actor, label=title)
    _notify(_directors(), actor=actor, request=req, title=f"Permintaan Owner baru: {title}",
            body=f"Target {target_date:%d/%m/%Y} · dari {actor}")
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


def progress(req: OwnerRequest, today: dt.date | None = None) -> dict:
    """Status permintaan dari task turunannya (dipecah Direktur)."""
    today = today or local_today()
    tasks = list(req.tasks())
    total = len(tasks)
    done = sum(1 for t in tasks if t.status == ActionItemStatus.SELESAI)
    if total == 0:
        state, label = "waiting", "Menunggu Direktur"
    elif done == total:
        state, label = "done", "Selesai"
    else:
        state, label = "running", "Berjalan"
    late = state != "done" and req.target_date < today
    return {
        "request": req,
        "tasks": tasks,
        "total": total,
        "done": done,
        "percent": round(done * 100 / total) if total else 0,
        "state": state,
        "label": label,
        "late": late,
        "days_left": (req.target_date - today).days,
        "days_late": max(0, (today - req.target_date).days),
    }


def request_rows(user, *, include_done_days: int = 14) -> list[dict]:
    """Permintaan yang masih berjalan, ditambah yang selesai belakangan ini."""
    if not can_view_requests(user):
        raise PermissionDenied("Permintaan Owner hanya untuk Owner dan Direktur Operasional.")
    today = local_today()
    rows = [progress(r, today) for r in OwnerRequest.objects.select_related("created_by")]
    since = today - dt.timedelta(days=include_done_days)
    rows = [r for r in rows if r["state"] != "done" or r["request"].updated_at.date() >= since
            or any(t.updated_at.date() >= since for t in r["tasks"])]
    order = {"waiting": 1, "running": 1, "done": 2}
    rows.sort(key=lambda r: (not r["late"], order[r["state"]], r["request"].target_date))
    return rows


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
