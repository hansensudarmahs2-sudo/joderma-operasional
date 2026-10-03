"""Laporan Masuk: semua Komplain, Masukan, Kerusakan, Laporan, dan Masukan staf dari kedua cabang.

Untuk Direktur Operasional dan Owner (keputusan 3 Okt 2026, sesudah laporan kerusakan dan
masukan Regitta dari Citraland tidak terlihat: daftar lama hanya menampilkan cabang aktif, dan
notifikasi masukan hanya dikirim ke pemegang peran AOM di cabang pengirim).

Satu daftar, bisa disaring per cabang, jenis, status, dan kata kunci; nama pelapor selalu tampil.
Izin buka tiap baris tetap mengikuti halaman detailnya masing-masing.
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
]
KIND_LABELS = dict(KINDS)


def can_view_inbox(user) -> bool:
    from core.permissions import has_admin_full_access, is_aom, is_owner

    return is_aom(user) or is_owner(user) or has_admin_full_access(user)


def _name(user) -> str:
    return str(user) if user else "—"


def inbox_rows(user, *, clinic=None, kind: str = "", only_open: bool = True, q: str = "",
               limit: int = 300) -> list[dict]:
    from issues.models import OPEN_STATUSES, Issue

    from .models import Laporan, Masukan, ReportStatus

    rows: list[dict] = []
    q = (q or "").strip()
    issue_kinds = {"KOMPLAIN", "MASUKAN", "KERUSAKAN"}
    if not kind or kind in issue_kinds:
        qs = Issue.objects.select_related("clinic", "created_by")
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
        for i in qs.order_by("-created_at")[:limit]:
            rows.append({
                "kind": i.issue_type, "kind_label": KIND_LABELS[i.issue_type], "clinic": i.clinic,
                "ref": i.number, "title": i.title, "reporter": _name(i.created_by),
                "created_at": i.created_at, "status": i.get_status_display(),
                "open": i.status in OPEN_STATUSES, "critical": i.severity == "KRITIS",
                "restricted": i.is_restricted, "url": reverse("issues:detail", args=[i.pk]),
            })
    if not kind or kind == "LAPORAN":
        qs = Laporan.objects.select_related("clinic", "created_by")
        if clinic is not None:
            qs = qs.filter(clinic=clinic)
        if only_open:
            qs = qs.filter(status__in=[ReportStatus.OPEN, ReportStatus.UNDER_REVIEW])
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q)
                           | Q(created_by__display_name__icontains=q) | Q(created_by__username__icontains=q))
        for r in qs.order_by("-created_at")[:limit]:
            rows.append({
                "kind": "LAPORAN", "kind_label": KIND_LABELS["LAPORAN"], "clinic": r.clinic,
                "ref": f"L-{r.pk}", "title": r.title, "reporter": _name(r.created_by),
                "created_at": r.created_at, "status": r.get_status_display(),
                "open": r.status in (ReportStatus.OPEN, ReportStatus.UNDER_REVIEW), "critical": False,
                "restricted": r.visibility == "RAHASIA_AOM",
                "url": reverse("reports:laporan_page_detail", args=[r.pk]),
            })
    if not kind or kind == "SARAN":
        qs = Masukan.objects.select_related("clinic", "created_by")
        if clinic is not None:
            qs = qs.filter(clinic=clinic)
        if only_open:
            qs = qs.filter(archived_at__isnull=True)
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q)
                           | Q(created_by__display_name__icontains=q) | Q(created_by__username__icontains=q))
        for m in qs.order_by("-created_at")[:limit]:
            rows.append({
                "kind": "SARAN", "kind_label": KIND_LABELS["SARAN"], "clinic": m.clinic,
                "ref": f"M-{m.pk}", "title": m.title, "reporter": _name(m.created_by),
                "created_at": m.created_at,
                "status": "Diarsipkan" if m.archived_at else ("Dipublikasikan" if m.is_published else "Baru"),
                "open": m.archived_at is None, "critical": False, "restricted": True,
                "url": reverse("reports:masukan_page_detail", args=[m.pk]),
            })
    rows.sort(key=lambda r: r["created_at"], reverse=True)
    return rows[:limit]


def open_counts(user) -> dict:
    """Jumlah yang masih terbuka per cabang dan jenis, untuk kotak ringkas di dashboard."""
    rows = inbox_rows(user, only_open=True, limit=1000)
    by_clinic: dict = {}
    for r in rows:
        c = by_clinic.setdefault(r["clinic"], {"total": 0, "critical": 0})
        c["total"] += 1
        c["critical"] += 1 if r["critical"] else 0
    return {"total": len(rows), "by_clinic": by_clinic,
            "critical": sum(1 for r in rows if r["critical"])}
