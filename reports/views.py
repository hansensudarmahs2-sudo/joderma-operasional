"""Laporan MVP dan ekspor CSV berotorisasi (PRD 14, 9.2)."""
from __future__ import annotations

import csv
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date

from audit.models import AuditAction
from audit.services import log_event
from breaks.models import BreakSchedule, BreakStatus
from cash.models import CashSession
from checklists.models import ChecklistResponse, ResponseResult
from core.models import OperationalDay, local_today
from core.permissions import can_export, can_view_cash_amounts, require
from core.services import active_clinic
from issues.models import Issue, IssueType, OPEN_STATUSES
from nurses.models import CommissionTurnEvent, NurseRosterEntry, TurnAction
from queueing.models import QueueEntry, QueueStatus


def _range(request):
    end = parse_date(request.GET.get("sampai") or "") or local_today()
    start = parse_date(request.GET.get("dari") or "") or (end - timedelta(days=6))
    return start, end


@login_required
def index(request):
    clinic = active_clinic()
    start, end = _range(request)
    days = OperationalDay.objects.filter(clinic=clinic, date__range=(start, end))

    checklist_rows = (
        ChecklistResponse.objects.filter(run__operational_day__in=days)
        .values("run__area")
        .annotate(
            total=Count("id"),
            ok=Count("id", filter=Q(result=ResponseResult.OK)),
            masalah=Count(
                "id",
                filter=Q(result__in=[ResponseResult.TIDAK_LENGKAP, ResponseResult.RUSAK]),
            ),
        )
        .order_by("run__area")
    )

    queue_rows = (
        QueueEntry.objects.filter(operational_day__in=days)
        .values("operational_day__date")
        .annotate(
            total=Count("id"),
            selesai=Count("id", filter=Q(queue_status=QueueStatus.SELESAI)),
            batal=Count(
                "id", filter=Q(queue_status__in=[QueueStatus.BATAL, QueueStatus.NO_SHOW])
            ),
        )
        .order_by("operational_day__date")
    )

    nurse_rows = (
        NurseRosterEntry.objects.filter(operational_day__in=days)
        .values("nurse__username", "nurse__display_name")
        .annotate(giliran=Count("turn_events", filter=Q(turn_events__action=TurnAction.TINDAKAN_SELESAI)))
        .order_by("-giliran")
    )
    override_count = CommissionTurnEvent.objects.filter(
        operational_day__in=days, action=TurnAction.OVERRIDE
    ).count()

    issue_rows = (
        Issue.objects.filter(clinic=clinic, created_at__date__range=(start, end))
        .values("issue_type", "status")
        .annotate(jumlah=Count("id"))
        .order_by("issue_type")
    )
    overdue = Issue.objects.filter(
        clinic=clinic, status__in=OPEN_STATUSES, due_at__lt=timezone.now()
    ).select_related("created_by")[:50]

    context = {
        "start": start,
        "end": end,
        "days": days,
        "checklist_rows": checklist_rows,
        "queue_rows": queue_rows,
        "nurse_rows": nurse_rows,
        "override_count": override_count,
        "issue_rows": issue_rows,
        "overdue": overdue,
        "breaks": BreakSchedule.objects.filter(clinic=clinic, date__range=(start, end)).count(),
        "breaks_cancelled": BreakSchedule.objects.filter(
            clinic=clinic, date__range=(start, end), status=BreakStatus.BATAL
        ).count(),
        "can_export": can_export(request.user),
        "can_view_cash": can_view_cash_amounts(request.user),
        "cash_rows": (
            CashSession.objects.filter(operational_day__in=days).select_related("operational_day")
            if can_view_cash_amounts(request.user)
            else []
        ),
    }
    return render(request, "reports/index.html", context)


DATASETS = {"antrean", "kas", "checklist", "issue", "giliran"}


@login_required
@require(can_export)
def export_csv(request, dataset: str):
    """Ekspor tidak boleh melewati izin tampilan pengguna (PRD 9.2)."""
    if dataset not in DATASETS:
        return HttpResponse("Dataset tidak dikenali.", status=404)
    if dataset == "kas" and not can_view_cash_amounts(request.user):
        return HttpResponse("Anda tidak memiliki izin data kas.", status=403)

    clinic = active_clinic()
    start, end = _range(request)
    days = OperationalDay.objects.filter(clinic=clinic, date__range=(start, end))

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{dataset}_{start}_{end}.csv"'
    writer = csv.writer(response)

    if dataset == "antrean":
        writer.writerow(["tanggal", "nomor", "nama", "jenis", "pembayaran", "status", "dibuat"])
        for e in QueueEntry.objects.filter(operational_day__in=days).select_related("operational_day"):
            writer.writerow(
                [
                    e.operational_day.date,
                    e.queue_no,
                    e.display_name,
                    e.get_visit_type_display(),
                    e.get_payment_status_display(),
                    e.get_queue_status_display(),
                    timezone.localtime(e.created_at).strftime("%Y-%m-%d %H:%M"),
                ]
            )
    elif dataset == "kas":
        writer.writerow(["tanggal", "jenis", "diharapkan", "aktual", "selisih", "status"])
        for s in CashSession.objects.filter(operational_day__in=days).select_related("operational_day"):
            writer.writerow(
                [
                    s.operational_day.date,
                    s.get_session_type_display(),
                    s.expected_total,
                    s.actual_total,
                    s.variance,
                    s.get_status_display(),
                ]
            )
    elif dataset == "checklist":
        writer.writerow(["tanggal", "area", "item", "hasil", "jumlah", "catatan", "petugas"])
        for r in ChecklistResponse.objects.filter(run__operational_day__in=days).select_related(
            "run", "run__operational_day", "checked_by"
        ):
            writer.writerow(
                [
                    r.run.operational_day.date,
                    r.run.get_area_display(),
                    r.label,
                    r.get_result_display(),
                    r.quantity if r.quantity is not None else "",
                    r.note,
                    r.checked_by or "",
                ]
            )
    elif dataset == "issue":
        writer.writerow(["nomor", "tipe", "judul", "tingkat", "status", "dibuat", "target", "penanggung_jawab"])
        qs = Issue.objects.filter(clinic=clinic, created_at__date__range=(start, end))
        from core.permissions import is_owner, is_supervisor

        if not (is_supervisor(request.user) or is_owner(request.user)):
            qs = qs.filter(is_restricted=False)
        for i in qs:
            writer.writerow(
                [
                    i.number,
                    i.get_issue_type_display(),
                    i.title,
                    i.get_severity_display(),
                    i.get_status_display(),
                    timezone.localtime(i.created_at).strftime("%Y-%m-%d %H:%M"),
                    timezone.localtime(i.due_at).strftime("%Y-%m-%d %H:%M") if i.due_at else "",
                    i.current_assignee or "",
                ]
            )
    else:  # giliran
        writer.writerow(["waktu", "tanggal", "perawat", "aksi", "kategori", "alasan", "aktor"])
        for e in CommissionTurnEvent.objects.filter(operational_day__in=days).select_related(
            "nurse", "actor", "procedure_category", "operational_day"
        ):
            writer.writerow(
                [
                    timezone.localtime(e.occurred_at).strftime("%H:%M"),
                    e.operational_day.date,
                    e.nurse or "",
                    e.get_action_display(),
                    e.procedure_category or "",
                    e.reason,
                    e.actor or "",
                ]
            )

    log_event(
        action=AuditAction.EXPORT,
        entity_type="report",
        entity_id=dataset,
        entity_label=f"{dataset} {start}..{end}",
        actor=request.user,
        request=request,
    )
    return response
