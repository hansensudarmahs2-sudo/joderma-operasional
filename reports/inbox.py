"""Inbox Direktur Operasional (dulu "Laporan Masuk"): satu pintu untuk semua yang masuk.

Isi: Komplain, Masukan, Kerusakan, Laporan staf, Masukan staf dari kedua cabang (3 Okt 2026),
ditambah Permintaan dan Temuan Owner serta Catatan Direktur milik sendiri (tahap 2 paket B).

Alur GTD: setiap item yang masuk dipilah Direktur Operasional (reports/triage.py) menjadi task,
diteruskan ke pemegang wewenang lain, dibawa ke rapat bersama, atau tidak ditindaklanjuti.
Tab bawaan "Belum dipilah" berisi yang masih terbuka dan belum dipilah. Item yang sudah ditangani
di cabang (status bukan Baru), permintaan yang sudah punya task, dan catatan yang sudah dijadikan
task dianggap sudah dipilah walau tanpa baris pilah.

Owner membaca semuanya kecuali Catatan Direktur. Izin buka tiap baris tetap mengikuti halaman
detailnya masing-masing.
"""
from __future__ import annotations

from django.db.models import Q
from django.urls import reverse

KINDS = [
    ("KOMPLAIN", "Komplain"),
    ("MASUKAN", "Masukan"),
    ("KERUSAKAN", "Kerusakan"),
    ("LAPORAN", "Laporan staf"),
    ("SARAN", "Masukan staf"),
    ("PERMINTAAN", "Permintaan Owner"),
    ("TEMUAN", "Temuan Owner"),
    ("CATATAN", "Catatan Direktur"),
]
KIND_LABELS = dict(KINDS)

STATES = [
    ("belum", "Belum dipilah"),
    ("dipantau", "Diteruskan, dipantau"),
    ("sudah", "Sudah dipilah"),
    ("semua", "Semua"),
]

# Jenis sumber di InboxTriage dan ActionItem.source_type untuk task hasil pilah.
SOURCE_ISSUE = "issue"
SOURCE_LAPORAN = "laporan"
SOURCE_MASUKAN = "masukan"
SOURCE_REQUEST = "permintaan_owner"
SOURCE_NOTE = "catatan_direktur"
SOURCES = (SOURCE_ISSUE, SOURCE_LAPORAN, SOURCE_MASUKAN, SOURCE_REQUEST, SOURCE_NOTE)


def can_view_inbox(user) -> bool:
    from core.permissions import has_admin_full_access, is_aom, is_owner

    return is_aom(user) or is_owner(user) or has_admin_full_access(user)


def can_triage(user) -> bool:
    from core.permissions import is_aom

    return is_aom(user)


def _name(user) -> str:
    return str(user) if user else "—"


def _triages(source_type: str, ids) -> dict:
    from .models import InboxTriage

    ids = list(ids)
    if not ids:
        return {}
    return {
        t.source_id: t
        for t in InboxTriage.objects.filter(source_type=source_type, source_id__in=ids).select_related(
            "task", "decision", "triaged_by"
        )
    }


def _issue_rows(clinic, kind, only_open, q, limit, pk=None):
    from issues.models import OPEN_STATUSES, Issue, IssueStatus

    qs = Issue.objects.select_related("clinic", "created_by")
    if pk is not None:
        qs = qs.filter(pk=pk)
    if clinic is not None:
        qs = qs.filter(clinic=clinic)
    if kind:
        qs = qs.filter(issue_type=kind)
    if only_open:
        qs = qs.filter(status__in=OPEN_STATUSES)
    if q:
        qs = qs.filter(Q(number__icontains=q) | Q(title__icontains=q) | Q(description__icontains=q)
                       | Q(location__icontains=q) | Q(created_by__display_name__icontains=q)
                       | Q(created_by__username__icontains=q))
    items = list(qs.order_by("-created_at")[:limit])
    return [{
        "kind": i.issue_type, "kind_label": KIND_LABELS[i.issue_type], "clinic": i.clinic,
        "ref": i.number, "title": i.title, "description": i.description, "reporter": _name(i.created_by),
        "created_at": i.created_at, "status": i.get_status_display(),
        "open": i.status in OPEN_STATUSES, "critical": i.severity == "KRITIS",
        "restricted": i.is_restricted, "url": reverse("issues:detail", args=[i.pk]),
        "source_type": SOURCE_ISSUE, "source_id": i.pk,
        "handled": "" if i.status == IssueStatus.BARU else f"ditangani di cabang ({i.get_status_display().lower()})",
    } for i in items]


def _laporan_rows(clinic, only_open, q, limit, pk=None):
    from .models import Laporan, ReportStatus

    qs = Laporan.objects.select_related("clinic", "created_by")
    if pk is not None:
        qs = qs.filter(pk=pk)
    if clinic is not None:
        qs = qs.filter(clinic=clinic)
    if only_open:
        qs = qs.filter(status__in=[ReportStatus.OPEN, ReportStatus.UNDER_REVIEW])
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q)
                       | Q(created_by__display_name__icontains=q) | Q(created_by__username__icontains=q))
    secret = "RAHASIA_AOM"
    return [{
        "kind": "LAPORAN", "kind_label": KIND_LABELS["LAPORAN"], "clinic": r.clinic,
        "ref": f"L-{r.pk}", "title": r.title, "description": r.description, "reporter": _name(r.created_by),
        "created_at": r.created_at, "status": r.get_status_display(),
        "open": r.status in (ReportStatus.OPEN, ReportStatus.UNDER_REVIEW), "critical": False,
        "restricted": r.visibility == secret, "url": reverse("reports:laporan_page_detail", args=[r.pk]),
        "source_type": SOURCE_LAPORAN, "source_id": r.pk,
        "handled": "" if r.status == ReportStatus.OPEN else f"ditangani ({r.get_status_display().lower()})",
    } for r in qs.order_by("-created_at")[:limit]]


def _masukan_rows(clinic, only_open, q, limit, pk=None):
    from .models import Masukan

    qs = Masukan.objects.select_related("clinic", "created_by")
    if pk is not None:
        qs = qs.filter(pk=pk)
    if clinic is not None:
        qs = qs.filter(clinic=clinic)
    if only_open:
        qs = qs.filter(archived_at__isnull=True)
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q)
                       | Q(created_by__display_name__icontains=q) | Q(created_by__username__icontains=q))
    return [{
        "kind": "SARAN", "kind_label": KIND_LABELS["SARAN"], "clinic": m.clinic,
        "ref": f"M-{m.pk}", "title": m.title, "description": m.description, "reporter": _name(m.created_by),
        "created_at": m.created_at,
        "status": "Diarsipkan" if m.archived_at else ("Dipublikasikan" if m.is_published else "Baru"),
        "open": m.archived_at is None, "critical": False, "restricted": True,
        "url": reverse("reports:masukan_page_detail", args=[m.pk]),
        "source_type": SOURCE_MASUKAN, "source_id": m.pk,
        "handled": "dipublikasikan" if m.is_published else "",
    } for m in qs.order_by("-created_at")[:limit]]


def _request_rows(clinic, kind, only_open, q, limit, pk=None):
    from owner.models import OwnerRequest, RequestKind
    from owner.services import progress

    qs = OwnerRequest.objects.select_related("clinic", "created_by", "category")
    if pk is not None:
        qs = qs.filter(pk=pk)
    if clinic is not None:
        qs = qs.filter(clinic=clinic)
    if kind in ("PERMINTAAN", "TEMUAN"):
        qs = qs.filter(kind=kind)
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q)
                       | Q(created_by__display_name__icontains=q) | Q(created_by__username__icontains=q))
    rows = []
    for req in qs.order_by("-created_at")[:limit]:
        p = progress(req)
        is_open = p["state"] != "done"
        if only_open and not is_open:
            continue
        key = "TEMUAN" if req.kind == RequestKind.TEMUAN else "PERMINTAAN"
        rows.append({
            "kind": key, "kind_label": KIND_LABELS[key], "clinic": req.clinic,
            "ref": f"P-{req.pk}", "title": req.title, "description": req.description,
            "reporter": _name(req.created_by), "created_at": req.created_at,
            "status": p["label"] + (" · lewat target" if p["late"] else ""),
            "open": is_open, "critical": req.urgent, "restricted": False,
            "url": reverse("owner:request_detail", args=[req.pk]),
            "source_type": SOURCE_REQUEST, "source_id": req.pk,
            "handled": f"sudah dipecah menjadi {p['total']} task" if p["total"] else "",
            "target_date": req.target_date,
            "category": req.category.name if req.category else "Tanpa kategori",
        })
    return rows


def _note_rows(user, clinic, only_open, q, limit, pk=None):
    from direktur.models import DirectorNote

    qs = DirectorNote.objects.filter(author=user).select_related("clinic", "converted_task")
    if pk is not None:
        qs = qs.filter(pk=pk)
    if clinic is not None:
        qs = qs.filter(clinic=clinic)
    if only_open:
        qs = qs.filter(archived_at__isnull=True, converted_task__isnull=True)
    if q:
        qs = qs.filter(body__icontains=q)
    return [{
        "kind": "CATATAN", "kind_label": KIND_LABELS["CATATAN"], "clinic": n.clinic,
        "ref": f"C-{n.pk}", "title": str(n) or "(catatan kosong)", "description": n.body,
        "reporter": _name(user), "created_at": n.created_at,
        "status": "Diarsipkan" if n.archived_at else ("Dijadikan task" if n.converted_task_id else "Baru"),
        "open": not n.archived_at and not n.converted_task_id, "critical": False, "restricted": True,
        "url": reverse("direktur:notes"),
        "source_type": SOURCE_NOTE, "source_id": n.pk,
        "handled": "dijadikan task" if n.converted_task_id else "",
    } for n in qs.order_by("-created_at")[:limit]]


def _state(row) -> str:
    t = row["triage"]
    if t is not None:
        from .models import TriageAction

        return "dipantau" if t.action == TriageAction.TERUSKAN and row["open"] else "sudah"
    if row["handled"] or not row["open"]:
        return "sudah"
    return "belum"


def inbox_rows(user, *, clinic=None, kind: str = "", only_open: bool = True, q: str = "",
               state: str = "", limit: int = 300) -> list[dict]:
    """Baris Inbox. `state`: belum / dipantau / sudah; kosong = semua (dengan saringan only_open)."""
    from core.permissions import is_aom

    q = (q or "").strip()
    if state in ("sudah", "semua"):
        only_open = False
    rows: list[dict] = []
    if not kind or kind in ("KOMPLAIN", "MASUKAN", "KERUSAKAN"):
        rows += _issue_rows(clinic, kind, only_open, q, limit)
    if not kind or kind == "LAPORAN":
        rows += _laporan_rows(clinic, only_open, q, limit)
    if not kind or kind == "SARAN":
        rows += _masukan_rows(clinic, only_open, q, limit)
    if not kind or kind in ("PERMINTAAN", "TEMUAN"):
        rows += _request_rows(clinic, kind, only_open, q, limit)
    if (not kind or kind == "CATATAN") and is_aom(user):
        rows += _note_rows(user, clinic, only_open, q, limit)

    by_source: dict[str, list[int]] = {}
    for r in rows:
        by_source.setdefault(r["source_type"], []).append(r["source_id"])
    found = {s: _triages(s, ids) for s, ids in by_source.items()}
    for r in rows:
        r["triage"] = found.get(r["source_type"], {}).get(r["source_id"])
        r["state"] = _state(r)
    if state in ("belum", "dipantau", "sudah"):
        rows = [r for r in rows if r["state"] == state]
    rows.sort(key=lambda r: r["created_at"], reverse=True)
    return rows[:limit]


def open_counts(user) -> dict:
    """Angka untuk kartu Inbox di Ringkasan/Dashboard: terbuka per cabang dan yang belum dipilah."""
    rows = inbox_rows(user, only_open=True, limit=1000)
    by_clinic: dict = {}
    shared = 0
    for r in rows:
        if r["clinic"] is None:
            shared += 1
            continue
        c = by_clinic.setdefault(r["clinic"], {"total": 0, "critical": 0})
        c["total"] += 1
        c["critical"] += 1 if r["critical"] else 0
    return {"total": len(rows), "by_clinic": by_clinic, "shared": shared,
            "critical": sum(1 for r in rows if r["critical"]),
            "untriaged": sum(1 for r in rows if r["state"] == "belum"),
            "watching": sum(1 for r in rows if r["state"] == "dipantau")}


def find_row(user, source_type: str, source_id: int) -> dict | None:
    """Satu item Inbox (untuk halaman pilah), lewat jalur yang sama dengan daftar."""
    getters = {
        SOURCE_ISSUE: lambda: _issue_rows(None, "", False, "", 1, pk=source_id),
        SOURCE_LAPORAN: lambda: _laporan_rows(None, False, "", 1, pk=source_id),
        SOURCE_MASUKAN: lambda: _masukan_rows(None, False, "", 1, pk=source_id),
        SOURCE_REQUEST: lambda: _request_rows(None, "", False, "", 1, pk=source_id),
        SOURCE_NOTE: lambda: _note_rows(user, None, False, "", 1, pk=source_id),
    }
    if source_type not in getters:
        return None
    found = getters[source_type]()
    row = found[0] if found else None
    if row is None:
        return None
    row["triage"] = _triages(source_type, [source_id]).get(source_id)
    row["state"] = _state(row)
    return row
