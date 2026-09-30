"""Summary of the day: disusun dari data hari itu, dikirim Direktur ke Owner.

Tombol "Simpan dan kirim summary ke Owner" di Checklist Direktur memanggil `send_summary`.
Isinya disusun otomatis kecuali catatan Direktur (lihat `docs/KEBUTUHAN_REDEFINISI_PERAN.md`):

1. hasil Checklist Direktur hari itu per cabang: sudah dicek, temuan, yang belum dicek;
2. catatan Direktur (kotak teks bebas, disimpan di `DailySummary.note`);
3. keputusan yang dicatat/ditetapkan dan task yang dibuat/selesai hari itu;
4. status setiap Permintaan Owner yang masih berjalan.

Isi disimpan sebagai snapshot (`DailySummary.content`) sehingga yang dibaca Owner tidak ikut
berubah bila data berubah sesudahnya. Mengirim ulang di hari yang sama menimpa snapshot dan
menambah `send_count`.
"""
from __future__ import annotations

import datetime as dt

from django.db import transaction
from django.utils import timezone

from audit.models import AuditAction
from audit.services import log_event
from core.models import ActionItem, ActionItemStatus, local_today
from core.permissions import user_clinic_queryset

from .models import AuditCheck, Cadence, CheckResult, DailySummary, Decision, DecisionStatus
from .services import FINDING_SOURCE, assert_director, pending_summary

LIST_LIMIT = 15


def _day_range(day: dt.date):
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(dt.datetime.combine(day, dt.time.min), tz)
    return start, start + dt.timedelta(days=1)


def _item(text: str, meta: str = "", tag: str = "", tone: str = "") -> dict:
    return {"text": text, "meta": meta, "tag": tag, "tone": tone}


def _capped(items: list[dict]) -> list[dict]:
    if len(items) <= LIST_LIMIT:
        return items
    rest = len(items) - LIST_LIMIT
    return items[:LIST_LIMIT] + [_item(f"+{rest} lainnya", "lihat Kanban atau Tim untuk daftar lengkap")]


def _checklist_section(user, day: dt.date) -> dict:
    start, end = _day_range(day)
    items = []
    for clinic in user_clinic_queryset(user).order_by("id"):
        summary = pending_summary(clinic, day)
        daily = summary[Cadence.HARIAN]
        today_checks = list(
            AuditCheck.objects.filter(clinic=clinic, updated_at__gte=start, updated_at__lt=end)
            .select_related("item")
            .order_by("item__cadence", "item__number")
        )
        findings = [c for c in today_checks if c.result == CheckResult.TEMUAN]
        others = [f"{s['label'].lower()} {s['done']}/{s['total']}" for key, s in summary.items()
                  if key != Cadence.HARIAN and s["total"]]
        meta = [f"{len(today_checks)} butir dicek hari ini"] + others
        if daily["pending"]:
            names = ", ".join(i.title for i in daily["pending"][:4])
            more = f" +{len(daily['pending']) - 4}" if len(daily["pending"]) > 4 else ""
            meta.append(f"belum dicek: {names}{more}")
        if findings:
            tag, tone = f"{len(findings)} temuan", "warn"
        elif daily["total"] and not daily["pending"]:
            tag, tone = "Sesuai", "ok"
        else:
            tag, tone = "Belum lengkap", "muted"
        items.append(_item(f"{clinic.name}: harian {daily['done']}/{daily['total']} butir dicek",
                           " · ".join(meta), tag, tone))
        for c in findings:
            items.append(_item(f"Temuan {c.item.title} ({clinic.name})", c.note, "Temuan", "err"))
    return {"title": "Checklist Direktur", "items": items, "empty": "Belum ada cabang aktif."}


def _decisions_and_tasks_section(user, day: dt.date) -> dict:
    from .dashboard import decisions_for

    start, end = _day_range(day)
    items = []
    decisions = decisions_for(user)
    for d in decisions.filter(status=DecisionStatus.DITETAPKAN, decided_on=day).order_by("updated_at"):
        items.append(_item(f"Ditetapkan: {d.title}", d.decision_text[:160],
                           "Kebijakan" if d.is_policy else "Keputusan", "info"))
    for d in decisions.filter(created_at__gte=start, created_at__lt=end).exclude(decided_on=day).order_by("created_at"):
        meta = f"diputuskan oleh {d.get_decider_display()}"
        if d.needed_by:
            meta += f" · sebelum {d.needed_by:%d/%m}"
        items.append(_item(f"Dicatat: {d.title}", meta, "Menunggu keputusan", "warn"))

    clinics = user_clinic_queryset(user)
    tasks = ActionItem.objects.filter(clinic__in=clinics).select_related("clinic", "owner")
    new = []
    # Task tindak lanjut temuan Direktur sudah tampil di bagian Checklist Direktur.
    fresh = tasks.filter(created_at__gte=start, created_at__lt=end).exclude(status=ActionItemStatus.BATAL)
    for t in fresh.exclude(source_type=FINDING_SOURCE).order_by("created_at"):
        meta = [t.clinic.name]
        if t.owner:
            meta.append(str(t.owner))
        if t.due_at:
            meta.append(f"target {timezone.localtime(t.due_at):%d/%m}")
        new.append(_item(f"Task baru: {t.title}", " · ".join(meta), "Task baru", "muted"))
    done = [
        _item(f"Selesai: {t.title}", t.clinic.name, "Selesai", "ok")
        for t in tasks.filter(status=ActionItemStatus.SELESAI, updated_at__gte=start, updated_at__lt=end)
        .order_by("updated_at")
    ]
    items += _capped(new) + _capped(done)
    return {"title": "Keputusan dan task hari ini", "items": items,
            "empty": "Tidak ada keputusan atau task yang berubah hari ini."}


def _requests_section(user, day: dt.date) -> dict:
    from owner.services import request_rows

    items = []
    for r in request_rows(user, include_done_days=0):
        req = r["request"]
        meta = [f"target {req.target_date:%d/%m}"]
        if r["total"]:
            meta.insert(0, f"{r['done']}/{r['total']} task selesai")
        if r["late"]:
            meta.append(f"lewat {r['days_late']} hari")
        tone = {"done": "ok", "running": "info"}.get(r["state"], "muted")
        tag = "Lewat target" if r["late"] else r["label"]
        items.append(_item(req.title, " · ".join(meta), tag, "err" if r["late"] else tone))
    return {"title": "Permintaan Owner", "items": items, "empty": "Tidak ada permintaan yang berjalan."}


def compose(user, day: dt.date | None = None) -> dict:
    """Isi summary (tanpa catatan) untuk satu tanggal. Tidak menulis apa pun."""
    assert_director(user)
    day = day or local_today()
    return {
        "sections": [
            _checklist_section(user, day),
            _decisions_and_tasks_section(user, day),
            _requests_section(user, day),
        ]
    }


def _notify_owners(summary: DailySummary, *, updated: bool) -> None:
    from django.urls import reverse

    from accounts.models import Role, User
    from notifications.models import Notification

    url = f"{reverse('owner:summary')}?tanggal={summary.date.isoformat()}"
    title = f"Summary harian {summary.date:%d/%m}{' diperbarui' if updated else ''}"
    body = f"Dari {summary.sent_by}, pukul {timezone.localtime(summary.sent_at):%H.%M}"
    ref = f"summary_harian:{summary.date.isoformat()}"
    for owner in User.objects.filter(is_active=True, user_roles__role=Role.OWNER).distinct():
        # Satu notifikasi belum dibaca per tanggal: kiriman ulang memperbarui, bukan menambah.
        unread = Notification.objects.filter(user=owner, type_code="summary_harian", entity_ref=ref,
                                             read_at__isnull=True).first()
        if unread:
            unread.title, unread.body, unread.url = title, body, url
            unread.save(update_fields=["title", "body", "url"])
        else:
            Notification.objects.create(user=owner, type_code="summary_harian", entity_ref=ref,
                                        title=title, body=body, url=url)


@transaction.atomic
def send_summary(*, actor, note: str = "", day: dt.date | None = None) -> DailySummary:
    """Simpan dan kirim summary hari ini ke Owner. Dapat diulang di hari yang sama."""
    assert_director(actor)
    day = day or local_today()
    content = compose(actor, day)
    now = timezone.now()
    note = (note or "").strip()
    summary = DailySummary.objects.select_for_update().filter(date=day).first()
    updated = summary is not None
    if summary is None:
        summary = DailySummary.objects.create(date=day, note=note, content=content, sent_by=actor, sent_at=now)
    else:
        summary.note, summary.content, summary.sent_by, summary.sent_at = note, content, actor, now
        summary.send_count += 1
        summary.save()
    log_event(
        action=AuditAction.UPDATE if updated else AuditAction.CREATE,
        entity_type="dailysummary",
        entity_id=summary.pk,
        entity_label=str(summary),
        actor=actor,
        after={"date": day.isoformat(), "send_count": summary.send_count, "note": note[:300]},
        reason="Kirim summary ke Owner",
    )
    _notify_owners(summary, updated=updated)
    return summary
