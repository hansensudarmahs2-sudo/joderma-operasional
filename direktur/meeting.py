"""Bahan rapat mingguan (tahap 2 paket D).

Rapat bersama tiap Kamis (K-015). Bahan dihitung otomatis untuk periode Kamis minggu lalu sampai
Rabu sebelum rapat: agenda keputusan, permintaan dan temuan Owner, task yang selesai dan
terverifikasi, task lewat target, yang menunggu verifikasi, dan ringkasan Inbox per cabang.
Tidak menulis apa pun; bisa dicetak atau disalin sebagai teks untuk WhatsApp.
"""
from __future__ import annotations

import datetime as dt

from django.utils import timezone

from core.models import ActionItem, ActionItemStatus, TaskAssignmentStatus, local_today
from core.permissions import user_clinic_queryset

from . import dashboard
from .models import DecisionStatus


def period_for(meeting: dt.date) -> tuple[dt.date, dt.date]:
    """Kamis minggu lalu s.d. Rabu sebelum rapat (inklusif)."""
    return meeting - dt.timedelta(days=7), meeting - dt.timedelta(days=1)


def _bounds(start: dt.date, end: dt.date):
    tz = timezone.get_current_timezone()
    return (timezone.make_aware(dt.datetime.combine(start, dt.time.min), tz),
            timezone.make_aware(dt.datetime.combine(end + dt.timedelta(days=1), dt.time.min), tz))


def parse_meeting(raw: str | None, today: dt.date | None = None) -> dt.date:
    today = today or local_today()
    try:
        day = dt.date.fromisoformat((raw or "").strip())
    except ValueError:
        return dashboard.next_meeting(today)
    return dashboard.next_meeting(day)  # tanggal apa pun dibulatkan ke Kamis berikutnya


def compose(user, meeting: dt.date) -> dict:
    from owner.models import OwnerRequest
    from owner.services import progress, verification_queue
    from reports.inbox import inbox_rows

    dashboard.assert_overview(user)
    start, end = period_for(meeting)
    t0, t1 = _bounds(start, end)
    clinics = user_clinic_queryset(user)

    agenda = dashboard.meeting_agenda(user)
    decided = list(
        dashboard.decisions_for(user).filter(
            status=DecisionStatus.DITETAPKAN, decided_on__gte=start, decided_on__lte=end
        ).order_by("decided_on")
    )

    requests = []
    for req in OwnerRequest.objects.select_related("clinic", "created_by").order_by("created_at"):
        p = progress(req)
        new = t0 <= req.created_at < t1
        if new or p["state"] != "done":
            requests.append({**p, "new": new})

    done_items = list(
        ActionItem.objects.filter(clinic__in=clinics, status=ActionItemStatus.SELESAI, updated_at__gte=t0,
                                  updated_at__lt=t1)
        .select_related("clinic")
        .prefetch_related("task_assignments__assignee", "task_assignments__reviewer")
        .order_by("updated_at")
    )
    done = []
    for item in done_items:
        ok = [a for a in item.task_assignments.all() if a.status == TaskAssignmentStatus.CONFIRMED]
        done.append({"item": item, "people": ", ".join(sorted({str(a.assignee) for a in ok})),
                     "reviewers": ", ".join(sorted({str(a.reviewer) for a in ok if a.reviewer}))})

    open_items = list(
        ActionItem.objects.filter(clinic__in=clinics, status__in=dashboard.OPEN_ITEM)
        .select_related("clinic")
        .prefetch_related("task_assignments__assignee", "waiting_decisions")
    )
    overdue = sorted((i for i in open_items if i.is_overdue), key=lambda i: i.due_at)
    overdue_rows = [{"item": i, "people": ", ".join(str(a.assignee) for a in i.task_assignments.all()
                                                    if a.status != TaskAssignmentStatus.CANCELLED),
                     "days": (timezone.now() - i.due_at).days} for i in overdue]
    waiting = [
        {"item": i, "people": ", ".join(str(a.assignee) for a in i.task_assignments.all()
                                        if a.status == TaskAssignmentStatus.SUBMITTED),
         "dirut": i.reviewed_by_dirut}
        for i in open_items
        if dashboard.kanban_column(i, list(i.task_assignments.all())) == dashboard.Column.MENUNGGU
    ]
    new_tasks = ActionItem.objects.filter(clinic__in=clinics, created_at__gte=t0, created_at__lt=t1).count()

    # Catatan Direktur bersifat pribadi: tidak masuk bahan rapat yang dibagikan.
    rows = [r for r in inbox_rows(user, state="semua", limit=5000)
            if t0 <= r["created_at"] < t1 and r["kind"] != "CATATAN"]
    by_clinic: dict[str, dict] = {}
    for r in rows:
        name = r["clinic"].name if r["clinic"] else "Lintas cabang"
        c = by_clinic.setdefault(name, {"total": 0, "kinds": {}, "untriaged": 0, "critical": []})
        c["total"] += 1
        c["kinds"][r["kind_label"]] = c["kinds"].get(r["kind_label"], 0) + 1
        if r["state"] == "belum":
            c["untriaged"] += 1
        if r["critical"]:
            c["critical"].append(r)
    open_untriaged = sum(1 for r in inbox_rows(user, state="belum", limit=5000) if r["kind"] != "CATATAN")

    return {
        "meeting": meeting,
        "start": start,
        "end": end,
        "agenda_rapat": agenda["rapat"],
        "agenda_lain": agenda["lain"],
        "decided": decided,
        "requests": requests,
        "done": done,
        "overdue": overdue_rows,
        "waiting": waiting,
        "verify_dirut": [w for w in waiting if w["dirut"]],
        "new_tasks": new_tasks,
        "inbox": dict(sorted(by_clinic.items())),
        "inbox_total": len(rows),
        "open_untriaged": open_untriaged,
        "generated_at": timezone.now(),
    }


def as_text(data: dict) -> str:
    """Ringkasan teks polos untuk ditempel di WhatsApp grup rapat."""
    d = data
    out = [f"*Bahan rapat Kamis {d['meeting']:%d/%m/%Y}*",
           f"Periode {d['start']:%d/%m} – {d['end']:%d/%m}", ""]

    out.append("*Agenda keputusan bersama*")
    if d["agenda_rapat"]:
        for n, r in enumerate(d["agenda_rapat"], 1):
            dec = r["decision"]
            extra = f" (tertahan {len(r['tasks'])} task)" if r["tasks"] else ""
            out.append(f"{n}. {dec.title} — {dec.clinic.name if dec.clinic else 'lintas cabang'}{extra}")
    else:
        out.append("- tidak ada")
    if d["agenda_lain"]:
        out.append(f"Menunggu pemutus lain: {len(d['agenda_lain'])} perkara")
    out.append("")

    if d["decided"]:
        out.append("*Keputusan yang ditetapkan minggu ini*")
        out += [f"- {x.title}: {x.decision_text[:120]}" for x in d["decided"]]
        out.append("")

    out.append("*Permintaan dan temuan Owner*")
    if d["requests"]:
        for r in d["requests"]:
            req = r["request"]
            tag = "temuan" if req.kind == "TEMUAN" else "permintaan"
            prog = f"{r['done']}/{r['total']} task" if r["total"] else r["label"]
            late = " · LEWAT TARGET" if r["late"] else ""
            new = " (baru)" if r["new"] else ""
            out.append(f"- [{tag}] {req.title}{new}: {prog}{late}")
    else:
        out.append("- tidak ada")
    out.append("")

    out.append(f"*Selesai dan terverifikasi: {len(d['done'])} task*")
    out += [f"- {x['item'].title} ({x['item'].clinic.name})" + (f" — {x['people']}" if x["people"] else "")
            for x in d["done"][:15]]
    if len(d["done"]) > 15:
        out.append(f"- …dan {len(d['done']) - 15} lainnya")
    out.append("")

    out.append(f"*Lewat target: {len(d['overdue'])} task*")
    out += [f"- {x['item'].title} ({x['item'].clinic.name}) — {x['people'] or 'tanpa PIC'}, lewat {x['days']} hari"
            for x in d["overdue"][:15]]
    out.append("")

    if d["waiting"]:
        out.append(f"*Menunggu verifikasi: {len(d['waiting'])} task*"
                   + (f" ({len(d['verify_dirut'])} oleh Dirut)" if d["verify_dirut"] else ""))
        out.append("")

    out.append(f"*Inbox minggu ini: {d['inbox_total']} masuk* (belum dipilah sekarang: {d['open_untriaged']})")
    for name, c in d["inbox"].items():
        kinds = ", ".join(f"{k} {v}" for k, v in sorted(c["kinds"].items()))
        out.append(f"- {name}: {c['total']} ({kinds})")
    return "\n".join(out).strip() + "\n"
