"""Daftar semua task: saring, cari, urutkan (permintaan Owner, Oktober 2026).

Status tampilan dihitung dari task + penerimanya (sama dengan kanban), jadi penyaringan dan
pengurutan dilakukan di Python sesudah satu query berprefetch. Jumlah task klinik masih ratusan;
bila sudah puluhan ribu, pindahkan ke query.
"""
from __future__ import annotations

import datetime as dt

from django.utils import timezone

from core.models import ActionItem, ActionItemStatus, Priority, TaskAssignmentStatus
from core.permissions import user_clinic_queryset

from . import dashboard

PAGE_SIZE = 50

STATUS_FILTERS = [
    ("terbuka", "Semua yang terbuka"),
    ("baru", "Baru"),
    ("dikerjakan", "Dikerjakan"),
    ("menunggu", "Menunggu konfirmasi"),
    ("lewat", "Lewat target"),
    ("tertahan", "Menunggu keputusan"),
    ("tanpa_pic", "Belum ada penerima"),
    ("selesai", "Selesai"),
    ("batal", "Dibatalkan"),
    ("semua", "Semua"),
]

SORTS = {
    "judul": "Task",
    "cabang": "Cabang",
    "pelapor": "Pelapor",
    "pic": "PIC",
    "prioritas": "Prioritas",
    "status": "Status",
    # "Mulai" = tanggal task dibuat/diberikan (keputusan PO 8 Okt 2026), tampil di sebelah Target.
    "dibuat": "Mulai",
    "target": "Target",
    "diperbarui": "Diperbarui",
}
DEFAULT_SORT = "target"

_PRIORITY_RANK = {Priority.KRITIS: 0, Priority.TINGGI: 1, Priority.SEDANG: 2, Priority.RENDAH: 3}
_STATUS_RANK = {"Baru": 0, "Dikerjakan": 1, "Menunggu konfirmasi": 2, "Selesai": 3, "Dibatalkan": 4}


def _status_label(item, column) -> str:
    if item.status == ActionItemStatus.BATAL:
        return "Dibatalkan"
    if item.status == ActionItemStatus.SELESAI:
        return "Selesai"
    return {
        dashboard.Column.BARU: "Baru",
        dashboard.Column.DIKERJAKAN: "Dikerjakan",
        dashboard.Column.MENUNGGU: "Menunggu konfirmasi",
    }.get(column, "Baru")


def parse_filters(params) -> dict:
    def digits(key):
        value = (params.get(key) or "").strip()
        return int(value) if value.isdigit() else None

    def date(key):
        try:
            return dt.date.fromisoformat((params.get(key) or "").strip())
        except ValueError:
            return None

    status = params.get("status") or "terbuka"
    if status not in dict(STATUS_FILTERS):
        status = "terbuka"
    priority = params.get("prioritas") or ""
    if priority not in dict(Priority.choices):
        priority = ""
    source = params.get("sumber") or ""
    if source not in dict(dashboard.SOURCE_CHOICES):
        source = ""
    sort = params.get("urut") or DEFAULT_SORT
    if sort.lstrip("-") not in SORTS:
        sort = DEFAULT_SORT
    return {
        "q": (params.get("q") or "").strip()[:100],
        "cabang": digits("cabang"),
        "pic": digits("pic"),
        "status": status,
        "prioritas": priority,
        "sumber": source,
        "dari": date("dari"),
        "sampai": date("sampai"),
        "urut": sort,
    }


def _base(user, f):
    qs = ActionItem.objects.filter(clinic__in=user_clinic_queryset(user))
    if f["cabang"]:
        qs = qs.filter(clinic_id=f["cabang"])
    if f["prioritas"]:
        qs = qs.filter(priority=f["prioritas"])
    if f["status"] in ("terbuka", "baru", "dikerjakan", "menunggu", "lewat", "tertahan", "tanpa_pic"):
        qs = qs.filter(status__in=dashboard.OPEN_ITEM)
    elif f["status"] == "selesai":
        qs = qs.filter(status=ActionItemStatus.SELESAI)
    elif f["status"] == "batal":
        qs = qs.filter(status=ActionItemStatus.BATAL)
    tz = timezone.get_current_timezone()
    if f["dari"]:
        qs = qs.filter(created_at__gte=timezone.make_aware(dt.datetime.combine(f["dari"], dt.time.min), tz))
    if f["sampai"]:
        end = f["sampai"] + dt.timedelta(days=1)
        qs = qs.filter(created_at__lt=timezone.make_aware(dt.datetime.combine(end, dt.time.min), tz))
    return (
        qs.select_related("clinic", "owner", "created_by")
        .prefetch_related("task_assignments__assignee", "waiting_decisions")
        .distinct()
    )


def rows(user, f) -> list[dict]:
    dashboard.assert_overview(user)
    items = list(_base(user, f))
    if f["sumber"]:
        items = [i for i in items if dashboard.source_group(i) == f["sumber"]]
    who = dashboard.reporters(items)
    source_labels = dict(dashboard.SOURCE_CHOICES)
    out = []
    for item in items:
        assignments = [a for a in item.task_assignments.all() if a.status != TaskAssignmentStatus.CANCELLED]
        column = dashboard.kanban_column(item, assignments)
        pics = [a.assignee for a in assignments] or ([item.owner] if item.owner else [])
        out.append({
            "item": item,
            "status": _status_label(item, column),
            "column": column,
            "pics": pics,
            "pic_names": ", ".join(str(p) for p in pics),
            "reporter": who.get(item.pk),
            "source": source_labels.get(dashboard.source_group(item), "Modul lain"),
            "overdue": item.is_overdue,
            "on_hold": item.on_hold,
        })
    if f["pic"]:
        out = [r for r in out if any(p.pk == f["pic"] for p in r["pics"])]
    out = _status_filter(out, f["status"])
    if f["q"]:
        needle = f["q"].lower()
        out = [r for r in out if needle in _haystack(r)]
    return _sort(out, f["urut"])


def _status_filter(rows_, status):
    checks = {
        "baru": lambda r: r["status"] == "Baru",
        "dikerjakan": lambda r: r["status"] == "Dikerjakan",
        "menunggu": lambda r: r["status"] == "Menunggu konfirmasi",
        "lewat": lambda r: r["overdue"],
        "tertahan": lambda r: r["on_hold"],
        "tanpa_pic": lambda r: not r["pics"],
    }
    check = checks.get(status)
    return [r for r in rows_ if check(r)] if check else rows_


def _haystack(r) -> str:
    i = r["item"]
    parts = [i.title, i.description, i.source_label, i.clinic.name, r["pic_names"], str(r["reporter"] or ""),
             i.progress_note]
    return " ".join(p or "" for p in parts).lower()


def _sort(rows_, sort):
    desc = sort.startswith("-")
    key = sort.lstrip("-")
    far = dt.datetime.max.replace(tzinfo=dt.timezone.utc)
    keys = {
        "judul": lambda r: r["item"].title.lower(),
        "cabang": lambda r: r["item"].clinic.name,
        "pelapor": lambda r: str(r["reporter"] or "~").lower(),
        "pic": lambda r: r["pic_names"].lower() or "~",
        "prioritas": lambda r: _PRIORITY_RANK.get(r["item"].priority, 9),
        "status": lambda r: _STATUS_RANK.get(r["status"], 9),
        "target": lambda r: r["item"].due_at or far,
        "dibuat": lambda r: r["item"].created_at,
        "diperbarui": lambda r: r["item"].updated_at,
    }
    # Kunci kedua tetap: yang lebih baru dibuat di atas bila nilai utamanya sama.
    rows_ = sorted(rows_, key=lambda r: r["item"].created_at, reverse=True)
    return sorted(rows_, key=keys[key], reverse=desc)


def pic_choices(user):
    """Orang yang pernah menerima task di cabang yang dapat dilihat."""
    from accounts.models import User

    return (
        User.objects.filter(task_assignments__action_item__clinic__in=user_clinic_queryset(user))
        .distinct()
        .order_by("display_name", "username")
    )
