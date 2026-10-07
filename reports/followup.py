"""Status catatan staf maju otomatis saat semua task hasil pilah Inbox selesai (disetujui PO 7 Okt 2026).

Task yang lahir dari ``reports.triage.assign`` membawa ``source_type`` + ``source_id`` catatan asalnya
(komplain/masukan/kerusakan di ``issues`` atau laporan staf). Begitu semua task aktif untuk sumber itu
selesai, statusnya dimajukan lewat alurnya sendiri sampai target:

- Komplain   -> Selesai
- Kerusakan  -> Selesai (verifikasi dan penutupan tetap manual)
- Masukan    -> Diterapkan
- Laporan    -> Selesai (RESOLVED)

Ini tindakan sistem: izin ubah status tidak diperiksa (Owner yang mengonfirmasi task Direktur belum
tentu boleh mengubah status catatan), tetapi alur status, riwayat, audit, dan pemberitahuan pelapor
tetap berlaku. Penutupan akhir tetap keputusan manusia.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError

NOTE = "Otomatis: task hasil pilah selesai."
SUMMARY_CAP = 1000

# Urutan jalur per tipe; langkah berikutnya = status terjauh di jalur yang diizinkan alurnya.
ISSUE_PATHS = {
    "KOMPLAIN": ["DITINJAU", "DITUGASKAN", "DALAM_PROSES", "SELESAI"],
    "KERUSAKAN": ["DITRIASE", "DITUGASKAN", "DALAM_PERBAIKAN", "SELESAI"],
    "MASUKAN": ["DIPERTIMBANGKAN", "DIRENCANAKAN", "DITERAPKAN"],
}
LAPORAN_PATH = ["UNDER_REVIEW", "RESOLVED"]
CLOSED_ISSUE = {"DITUTUP", "DIVERIFIKASI", "DITOLAK"}
CLOSED_LAPORAN = {"CLOSED", "ARCHIVED"}


def _next_step(current: str, path: list[str], allowed: set[str], closed: set[str]) -> str | None:
    """Status berikutnya di jalur, atau None bila sudah di/ melewati target, ditutup, atau tak ada jalan."""
    if current in closed:
        return None
    start = path.index(current) + 1 if current in path else 0
    for status in reversed(path[start:]):
        if status in allowed:
            return status
    return None


def _all_tasks_done(item):
    from core.models import ActionItem, ActionItemStatus

    items = list(
        ActionItem.objects.filter(source_type=item.source_type, source_id=item.source_id)
        .exclude(status=ActionItemStatus.BATAL)
    )
    if not items or any(i.status != ActionItemStatus.SELESAI for i in items):
        return None
    return items


def _summary(items) -> str:
    from core.models import TaskAssignmentStatus, TaskEvent, TaskEventType

    parts = []
    for it in items:
        names = ", ".join(
            str(a.assignee)
            for a in it.task_assignments.exclude(status=TaskAssignmentStatus.CANCELLED).select_related("assignee")
        )
        note = (
            TaskEvent.objects.filter(action_item=it, event_type__in=[TaskEventType.SUBMITTED, TaskEventType.CONFIRMED])
            .exclude(note="")
            .order_by("-created_at", "-id")
            .values_list("note", flat=True)
            .first()
        ) or ""
        text = f'Diselesaikan lewat task "{it.title}"' + (f" ({names})" if names else "")
        parts.append(text + (f": {note.strip()}" if note.strip() else ""))
    return "; ".join(parts)[:SUMMARY_CAP]


def advance_source_from_tasks(item, *, actor) -> None:
    """Majukan status catatan asal ``item`` bila semua task aktifnya selesai. Tidak pernah gagal karena sumber hilang."""
    from reports.inbox import SOURCE_ISSUE, SOURCE_LAPORAN

    if item.source_type not in {SOURCE_ISSUE, SOURCE_LAPORAN} or not item.source_id:
        return
    items = _all_tasks_done(item)
    if items is None:
        return
    if item.source_type == SOURCE_ISSUE:
        _advance_issue(item.source_id, items, actor)
    else:
        _advance_laporan(item.source_id, actor)


def _advance_issue(pk: int, items, actor) -> None:
    from issues.models import WORKFLOWS, Issue
    from issues.services import RESOLUTION_REQUIRED_TYPES, _apply_status

    issue = Issue.objects.filter(pk=pk).first()
    path = ISSUE_PATHS.get(issue.issue_type) if issue else None
    if not path:
        return
    summary = ""
    if issue.issue_type in RESOLUTION_REQUIRED_TYPES and not issue.resolution_summary.strip():
        summary = _summary(items)
    for _ in range(len(path)):
        step = _next_step(issue.status, path, WORKFLOWS.get(issue.issue_type, {}).get(issue.status, set()), CLOSED_ISSUE)
        if step is None:
            return
        try:
            _apply_status(issue, user=actor, to_status=step, note=NOTE, resolution_summary=summary)
        except ValidationError:
            return


def _advance_laporan(pk: int, actor) -> None:
    from reports.models import Laporan
    from reports.services import _apply_laporan_status

    laporan = Laporan.objects.filter(pk=pk).first()
    if laporan is None:
        return
    for _ in range(len(LAPORAN_PATH)):
        step = _next_step(laporan.status, LAPORAN_PATH, laporan.allowed_next_statuses(), CLOSED_LAPORAN)
        if step is None:
            return
        try:
            _apply_laporan_status(laporan, user=actor, to_status=step, note=NOTE)
        except ValidationError:
            return
