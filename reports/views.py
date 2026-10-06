"""Laporan MVP dan ekspor CSV berotorisasi (PRD 14, 9.2)."""
from __future__ import annotations

import csv
import json
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q
from django.http import Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from audit.models import AuditAction
from audit.services import log_event
from breaks.models import BreakSchedule, BreakStatus
from cash.models import CashSession
from checklists.models import ChecklistResponse, ResponseResult
from core.models import Clinic, OperationalDay, local_today
from core.permissions import (
    can_archive_laporan,
    can_archive_masukan,
    can_change_laporan_status,
    can_create_laporan,
    can_export,
    can_publish_masukan,
    can_view_cash_amounts,
    can_view_laporan,
    can_view_masukan,
    is_aom,
    require,
)
from core.services import active_clinic
from issues.models import Issue, IssueType, OPEN_STATUSES
from nurses.models import CommissionTurnEvent, NurseRosterEntry, TurnAction
from queueing.models import QueueEntry, QueueStatus

from .models import Laporan, Masukan, ReportStatus
from .services import (
    archive_laporan,
    archive_masukan,
    change_laporan_status,
    create_laporan,
    create_masukan,
    log_confidential_access,
    publish_masukan,
    visible_laporan_queryset,
    visible_masukan_queryset,
)


def _range(request):
    end = parse_date(request.GET.get("sampai") or "") or local_today()
    start = parse_date(request.GET.get("dari") or "") or (end - timedelta(days=6))
    return start, end


@login_required
def index(request):
    clinic = active_clinic(request.user)
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

    clinic = active_clinic(request.user)
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


# --- Laporan (plan bagian 9) -------------------------------------------


def _laporan_json(l: Laporan) -> dict:
    return {
        "id": l.pk,
        "clinic": l.clinic.code,
        "visibility": l.visibility,
        "status": l.status,
        "title": l.title,
        "description": l.description,
        "created_by": l.created_by.username if l.created_by_id else None,
        "created_at": l.created_at.isoformat(),
    }


@login_required
def laporan_list(request):
    """Daftar laporan sudah dibatasi scope di service layer — jangan filter di view."""
    clinic = active_clinic(request.user)
    qs = visible_laporan_queryset(request.user, clinic)
    return JsonResponse({"results": [_laporan_json(l) for l in qs]})


@login_required
@require_POST
def laporan_create(request):
    clinic = active_clinic(request.user)
    try:
        laporan = create_laporan(
            clinic=clinic,
            user=request.user,
            title=request.POST.get("title", ""),
            description=request.POST.get("description", ""),
            visibility=request.POST.get("visibility", "CABANG"),
        )
    except (ValidationError, PermissionDenied) as exc:
        status = 403 if isinstance(exc, PermissionDenied) else 400
        return JsonResponse({"error": str(exc)}, status=status)
    return JsonResponse(_laporan_json(laporan), status=201)


@login_required
def laporan_detail(request, pk: int):
    """Akses langsung by-id juga wajib diperiksa server-side (plan 9.1/16)."""
    laporan = get_object_or_404(Laporan, pk=pk)
    if not can_view_laporan(request.user, laporan):
        raise PermissionDenied("Laporan ini rahasia dan tidak dapat Anda akses.")
    log_confidential_access(laporan, user=request.user, request=request)
    return JsonResponse(_laporan_json(laporan))


@login_required
@require_POST
def laporan_status(request, pk: int):
    laporan = get_object_or_404(Laporan, pk=pk)
    try:
        change_laporan_status(
            laporan,
            user=request.user,
            to_status=request.POST.get("status", ""),
            note=request.POST.get("note", ""),
            reason=request.POST.get("reason", ""),
        )
    except (ValidationError, PermissionDenied) as exc:
        status = 403 if isinstance(exc, PermissionDenied) else 400
        return JsonResponse({"error": str(exc)}, status=status)
    return JsonResponse(_laporan_json(laporan))


@login_required
@require_POST
def laporan_archive(request, pk: int):
    laporan = get_object_or_404(Laporan, pk=pk)
    try:
        archive_laporan(laporan, user=request.user, reason=request.POST.get("reason", ""))
    except (ValidationError, PermissionDenied) as exc:
        status = 403 if isinstance(exc, PermissionDenied) else 400
        return JsonResponse({"error": str(exc)}, status=status)
    return JsonResponse(_laporan_json(laporan))


# --- Masukan (plan bagian 10) --------------------------------------------


def _masukan_json(m: Masukan) -> dict:
    return {
        "id": m.pk,
        "clinic": m.clinic.code,
        "title": m.title,
        "description": m.description,
        "created_by": m.created_by.username if m.created_by_id else None,
        "created_at": m.created_at.isoformat(),
        "is_published": m.is_published,
        "archived_at": m.archived_at.isoformat() if m.archived_at else None,
    }


@login_required
def masukan_list(request):
    clinic = active_clinic(request.user)
    qs = visible_masukan_queryset(request.user, clinic)
    return JsonResponse({"results": [_masukan_json(m) for m in qs]})


@login_required
@require_POST
def masukan_create(request):
    clinic = active_clinic(request.user)
    try:
        masukan = create_masukan(
            clinic=clinic,
            user=request.user,
            title=request.POST.get("title", ""),
            description=request.POST.get("description", ""),
        )
    except (ValidationError, PermissionDenied) as exc:
        status = 403 if isinstance(exc, PermissionDenied) else 400
        return JsonResponse({"error": str(exc)}, status=status)
    return JsonResponse(_masukan_json(masukan), status=201)


@login_required
def masukan_detail(request, pk: int):
    masukan = get_object_or_404(Masukan, pk=pk)
    if not can_view_masukan(request.user, masukan):
        raise PermissionDenied("Masukan ini rahasia dan tidak dapat Anda akses.")
    return JsonResponse(_masukan_json(masukan))


@login_required
@require_POST
def masukan_publish(request, pk: int):
    masukan = get_object_or_404(Masukan, pk=pk)
    clinic_ids = request.POST.getlist("clinics")
    if not clinic_ids:
        raw = request.POST.get("clinics", "")
        clinic_ids = [c for c in raw.split(",") if c]
    clinics = list(Clinic.objects.filter(pk__in=clinic_ids))
    try:
        publication = publish_masukan(
            masukan, user=request.user, clinics=clinics, note=request.POST.get("note", "")
        )
    except (ValidationError, PermissionDenied) as exc:
        status = 403 if isinstance(exc, PermissionDenied) else 400
        return JsonResponse({"error": str(exc)}, status=status)
    return JsonResponse(
        {
            "id": publication.pk,
            "masukan_id": masukan.pk,
            "clinics": [c.code for c in publication.clinics.all()],
            "published_at": publication.published_at.isoformat(),
            "source_version": publication.source_version,
        }
    )


@login_required
@require_POST
def masukan_archive(request, pk: int):
    masukan = get_object_or_404(Masukan, pk=pk)
    try:
        archive_masukan(masukan, user=request.user, reason=request.POST.get("reason", ""))
    except (ValidationError, PermissionDenied) as exc:
        status = 403 if isinstance(exc, PermissionDenied) else 400
        return JsonResponse({"error": str(exc)}, status=status)
    return JsonResponse(_masukan_json(masukan))


# --- Halaman HTML laporan/masukan (Fase 5: UI di atas service layer JSON) ---


@login_required
def laporan_page(request):
    """Daftar laporan dengan filter status eksplisit (data selesai/arsip tidak disembunyikan)."""
    from core.services import list_branch_scope

    clinic = active_clinic(request.user)
    branch = list_branch_scope(request)
    qs = Laporan.objects.none()
    for c in branch["scope"]:
        qs = qs | visible_laporan_queryset(request.user, c)
    qs = qs.select_related("clinic", "created_by")
    status = request.GET.get("status", "")
    if status:
        qs = qs.filter(status=status)
    if request.method == "POST":
        try:
            create_laporan(
                clinic=clinic,
                user=request.user,
                title=request.POST.get("title", ""),
                description=request.POST.get("description", ""),
                visibility=request.POST.get("visibility", "CABANG"),
            )
            messages.success(request, "Laporan dikirim.")
        except (ValidationError, PermissionDenied) as exc:
            messages.error(request, str(exc) if isinstance(exc, PermissionDenied) else " ".join(exc.messages))
        return redirect("reports:laporan_page")
    return render(
        request,
        "reports/laporan_list.html",
        {
            "laporan_list": qs.order_by("-created_at")[:200],
            "status": status,
            "see_reporter": is_aom(request.user),
            **branch,
            "statuses": ReportStatus.choices,
            "can_create": can_create_laporan(request.user),
        },
    )


def _owner_view(user) -> bool:
    """Owner membuka detail laporan dan masukan baca saja (POST ditolak di core/peran.py)."""
    from core.peran import OWNER, persona

    return persona(user) == OWNER


@login_required
def laporan_page_detail(request, pk: int):
    """Direct URL access selalu diperiksa server-side, bukan hanya disembunyikan di UI."""
    laporan = get_object_or_404(Laporan, pk=pk)
    if not can_view_laporan(request.user, laporan):
        raise PermissionDenied("Laporan ini rahasia dan tidak dapat Anda akses.")
    log_confidential_access(laporan, user=request.user, request=request)
    if request.method == "POST":
        action = request.POST.get("aksi")
        try:
            if action == "arsip":
                archive_laporan(laporan, user=request.user, reason=request.POST.get("alasan", ""))
                messages.success(request, "Laporan diarsipkan.")
            else:
                change_laporan_status(
                    laporan,
                    user=request.user,
                    to_status=request.POST.get("status", ""),
                    note=request.POST.get("catatan", ""),
                    reason=request.POST.get("alasan", ""),
                )
                messages.success(request, "Status laporan diperbarui.")
        except (ValidationError, PermissionDenied) as exc:
            messages.error(request, str(exc) if isinstance(exc, PermissionDenied) else " ".join(exc.messages))
        return redirect("reports:laporan_page_detail", pk=pk)
    return render(
        request,
        "reports/laporan_detail.html",
        {
            "laporan": laporan,
            "can_archive": can_archive_laporan(request.user) and not _owner_view(request.user),
            "allowed_next": laporan.allowed_next_statuses()
            if can_change_laporan_status(request.user, laporan) and not _owner_view(request.user) else [],
        },
    )


@login_required
def masukan_page(request):
    """Daftar masukan (privat pengirim+AOM) dengan filter status eksplisit."""
    from core.services import list_branch_scope

    clinic = active_clinic(request.user)
    branch = list_branch_scope(request)
    qs = Masukan.objects.none()
    for c in branch["scope"]:
        qs = qs | visible_masukan_queryset(request.user, c)
    qs = qs.select_related("clinic", "created_by")
    status = request.GET.get("status", "")
    if status == "archived":
        qs = qs.exclude(archived_at=None)
    elif status == "active":
        qs = qs.filter(archived_at=None)
    if request.method == "POST":
        try:
            create_masukan(
                clinic=clinic,
                user=request.user,
                title=request.POST.get("title", ""),
                description=request.POST.get("description", ""),
            )
            messages.success(request, "Masukan dikirim.")
        except (ValidationError, PermissionDenied) as exc:
            messages.error(request, str(exc) if isinstance(exc, PermissionDenied) else " ".join(exc.messages))
        return redirect("reports:masukan_page")
    return render(
        request,
        "reports/masukan_list.html",
        {
            "masukan_list": qs.order_by("-created_at")[:200],
            "status": status,
            "see_reporter": is_aom(request.user),
            **branch,
            "can_publish": can_publish_masukan(request.user),
        },
    )


@login_required
def masukan_page_detail(request, pk: int):
    masukan = get_object_or_404(Masukan, pk=pk)
    if not can_view_masukan(request.user, masukan):
        raise PermissionDenied("Masukan ini rahasia dan tidak dapat Anda akses.")
    if request.method == "POST":
        action = request.POST.get("aksi")
        try:
            if action == "publikasi":
                clinic_ids = request.POST.getlist("clinics")
                clinics = list(Clinic.objects.filter(pk__in=clinic_ids))
                publish_masukan(
                    masukan, user=request.user, clinics=clinics, note=request.POST.get("catatan", "")
                )
                messages.success(request, "Masukan dipublikasikan ke cabang terpilih.")
            elif action == "arsip":
                archive_masukan(masukan, user=request.user, reason=request.POST.get("alasan", ""))
                messages.success(request, "Masukan diarsipkan.")
        except (ValidationError, PermissionDenied) as exc:
            messages.error(request, str(exc) if isinstance(exc, PermissionDenied) else " ".join(exc.messages))
        return redirect("reports:masukan_page_detail", pk=pk)
    return render(
        request,
        "reports/masukan_detail.html",
        {
            "masukan": masukan,
            "can_publish": can_publish_masukan(request.user) and not _owner_view(request.user),
            "can_archive": can_archive_masukan(request.user) and not _owner_view(request.user),
            "clinics": Clinic.objects.filter(active=True),
        },
    )


@login_required
def inbox(request):
    """Inbox Direktur Operasional: semua yang masuk, dipilah per item (reports/inbox.py, triage.py)."""
    from core.permissions import user_clinic_queryset

    from .inbox import KINDS, STATES, can_triage, can_view_inbox, inbox_rows, open_counts

    if not can_view_inbox(request.user):
        raise PermissionDenied("Inbox untuk Direktur Operasional dan Owner.")
    clinics = list(user_clinic_queryset(request.user).order_by("id"))
    raw = request.GET.get("cabang", "")
    clinic = next((c for c in clinics if raw.isdigit() and c.pk == int(raw)), None)
    kind = request.GET.get("jenis", "")
    if kind not in dict(KINDS):
        kind = ""
    state = request.GET.get("pilah", "belum")
    if state not in dict(STATES):
        state = "belum"
    if request.GET.get("semua") == "1":  # tautan lama "tampilkan yang sudah selesai"
        state = "semua"
    q = request.GET.get("q", "")[:100]
    kinds = KINDS if can_triage(request.user) else [k for k in KINDS if k[0] != "CATATAN"]
    return render(request, "reports/inbox.html", {
        "rows": inbox_rows(request.user, clinic=clinic, kind=kind, state=state, q=q),
        "counts": open_counts(request.user),
        "clinics": clinics, "clinic": clinic, "kind": kind, "kinds": kinds,
        "state": state, "states": STATES, "q": q, "can_triage": can_triage(request.user),
    })


@login_required
def inbox_triage(request, sumber: str, pk: int):
    """Halaman pilah satu item: tugaskan, teruskan, bawa ke rapat, atau tidak ditindaklanjuti."""
    from core.models import Priority
    from core.permissions import user_clinic_queryset
    from direktur import services as direktur
    from direktur.views import branch_context, branch_targets

    from . import triage
    from .inbox import can_triage, find_row
    from .models import ForwardTo

    if not can_triage(request.user):
        raise PermissionDenied("Pilah Inbox hanya untuk Direktur Operasional.")
    row = find_row(request.user, sumber, pk)
    if row is None:
        raise Http404("Item Inbox tidak ditemukan.")
    clinics = list(user_clinic_queryset(request.user).order_by("id"))
    default_clinic = row["clinic"].pk if row["clinic"] else None
    branch = branch_context(request, clinics, default=default_clinic)
    if request.method == "POST":
        aksi = request.POST.get("aksi", "")
        try:
            if aksi == "tugaskan":
                t = triage.assign(row, actor=request.user, title=request.POST.get("judul", ""),
                                  targets=branch_targets(request.POST, clinics),
                                  description=request.POST.get("uraian", ""),
                                  priority=request.POST.get("prioritas") or Priority.SEDANG,
                                  due_at=direktur.parse_due(request.POST.get("batas", "")))
                extra = f" ({t.note})" if t.note else ""
                messages.success(request, f"Dijadikan task: {t.task.title}{extra}.")
            elif aksi == "teruskan":
                triage.forward(row, actor=request.user, to=request.POST.get("ke", ""),
                               note=request.POST.get("catatan", ""))
                if request.POST.get("ke", "") == ForwardTo.DIRUT:
                    messages.success(request, "Diteruskan ke Owner sebagai permintaan keputusan; Owner sudah diberi tahu.")
                else:
                    messages.success(request, "Dicatat sebagai diteruskan; tetap dipantau di tab Dipantau.")
            elif aksi == "rapat":
                raw = request.POST.get("cabang_rapat", "asal")
                meeting_clinic = "asal" if raw == "asal" else next(
                    (c for c in clinics if raw.isdigit() and c.pk == int(raw)), None)
                t = triage.to_meeting(row, actor=request.user, title=request.POST.get("perkara", ""),
                                      background=request.POST.get("latar", ""),
                                      needed_by=direktur.parse_date(request.POST.get("tenggat", ""), "Tenggat"),
                                      clinic=meeting_clinic)
                messages.success(request, f"Dibawa ke rapat Kamis: {t.decision}.")
            elif aksi == "kebijakan":
                raw = request.POST.get("cabang_kebijakan", "semua")
                policy_clinic = raw if raw in ("asal", "semua") else next(
                    (c for c in clinics if raw.isdigit() and c.pk == int(raw)), None)
                if policy_clinic is None:
                    raise ValidationError("Cabang tidak valid.")
                t = triage.to_policy(row, actor=request.user, title=request.POST.get("judul_kebijakan", ""),
                                     text=request.POST.get("isi_kebijakan", ""), clinic=policy_clinic,
                                     effective_on=direktur.parse_date(request.POST.get("berlaku", ""), "Berlaku mulai"))
                messages.success(request, f"Dijadikan kebijakan dan diumumkan: {t.decision.title}.")
            elif aksi == "tidak":
                triage.dismiss(row, actor=request.user, reason=request.POST.get("alasan", ""))
                messages.success(request, "Dicatat: tidak ditindaklanjuti.")
            else:
                raise ValidationError("Aksi tidak dikenali.")
            return redirect(f"{reverse('reports:inbox')}?pilah=belum")
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
    return render(request, "reports/inbox_triage.html", {
        "row": row,
        **branch,
        "priorities": Priority.choices,
        "forward_choices": ForwardTo.choices,
        "default_priority": "TINGGI" if row["critical"] else "SEDANG",
        "default_due": row.get("target_date"),
    })


@login_required
def policies(request):
    """Kebijakan berlaku: dibaca semua peran (5 Okt 2026). Tanpa nama pelapor atau sumbernya."""
    from core.permissions import user_clinic_queryset
    from direktur.models import Decision, DecisionStatus

    clinics = list(user_clinic_queryset(request.user))
    items = (
        Decision.objects.filter(status=DecisionStatus.DITETAPKAN, is_policy=True)
        .filter(Q(clinic__isnull=True) | Q(clinic__in=clinics))
        .select_related("clinic")
        .order_by("-decided_on", "-id")
    )
    fresh = local_today() - timedelta(days=7)
    return render(request, "reports/policies.html", {
        "items": items, "fresh": fresh, "is_director": is_aom(request.user),
    })
