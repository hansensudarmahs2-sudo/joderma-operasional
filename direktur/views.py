"""Halaman Direktur Operasional. Setiap view dibatasi role AOM di server."""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from django.utils import timezone

from core import task_services
from core.photos import SOURCE_PHOTO_ENTITY, photos_for, save_optional_photo
from core.models import ActionItem, ActionItemStatus, Priority, TaskAssignment, TaskAssignmentStatus, local_today
from core.permissions import is_aom, require, user_clinic_queryset

from . import dashboard, services
from . import summary as daily_summary
from .models import (
    AuditItem,
    DailySummary,
    Cadence,
    CheckResult,
    Decider,
    Decision,
    DecisionStatus,
    DirectorNote,
    NoteSource,
    period_start,
)


def _clinic_from(request, value=None):
    clinics = user_clinic_queryset(request.user).order_by("id")
    value = value if value is not None else request.GET.get("cabang")
    if value and str(value).isdigit():
        clinic = clinics.filter(pk=int(value)).first()
        if clinic is not None:
            return clinic, clinics
    return clinics.first(), clinics


def _errors(request, exc: ValidationError) -> None:
    messages.error(request, " ".join(exc.messages))


def _inbox_counts(user):
    from reports.inbox import can_view_inbox, open_counts

    return open_counts(user) if can_view_inbox(user) else None


@login_required
@require(dashboard.can_view_overview)
def team(request):
    return render(
        request,
        "direktur/team.html",
        {
            "clinics": services.team_overview(request.user),
            "today": local_today(),
            "is_director": is_aom(request.user),
        },
    )


def _filters(request):
    clinic_id = request.GET.get("cabang", "")
    clinic_id = int(clinic_id) if clinic_id.isdigit() else None
    source = request.GET.get("sumber", "")
    if source not in dict(dashboard.SOURCE_CHOICES):
        source = ""
    return clinic_id, source


def _filter_context(request, clinic_id, source):
    return {
        "clinics": user_clinic_queryset(request.user).order_by("id"),
        "clinic_id": clinic_id,
        "source": source,
        "sources": dashboard.SOURCE_CHOICES,
    }


@login_required
@require(dashboard.can_view_overview)
def overview(request):
    user = request.user
    return render(
        request,
        "direktur/overview.html",
        {
            "inbox": _inbox_counts(request.user),
            "bird": dashboard.bird_view(user),
            "matrix": dashboard.eisenhower(user, limit=1),
            "counts": dashboard.headline_counts(user),
            "is_director": is_aom(user),
            "today": local_today(),
        },
    )


@login_required
@require(dashboard.can_view_overview)
def kanban_page(request):
    clinic_id, source = _filters(request)
    return render(
        request,
        "direktur/kanban.html",
        {"board": dashboard.kanban(request.user, clinic_id=clinic_id, source=source),
         **_filter_context(request, clinic_id, source)},
    )


@login_required
@require(dashboard.can_view_overview)
def matrix_page(request):
    clinic_id, source = _filters(request)
    matrix = dashboard.eisenhower(request.user, clinic_id=clinic_id, source=source)
    focus = request.GET.get("kuadran", "")
    if focus in {q["key"] for q in matrix}:
        matrix = [q for q in matrix if q["key"] == focus]
    else:
        focus = ""
    return render(
        request,
        "direktur/matrix.html",
        {"matrix": matrix, "focus": focus, **_filter_context(request, clinic_id, source)},
    )


@login_required
@require(dashboard.can_view_overview)
def gantt_page(request):
    clinic_id, source = _filters(request)
    return render(
        request,
        "direktur/gantt.html",
        {"chart": dashboard.gantt(request.user, clinic_id=clinic_id, source=source),
         **_filter_context(request, clinic_id, source)},
    )


@login_required
@require(dashboard.can_view_overview)
def decisions(request):
    user = request.user
    if request.method == "POST":
        if not is_aom(user):
            raise PermissionDenied("Hanya Direktur Operasional yang mencatat keputusan.")
        clinic = None
        if request.POST.get("cabang"):
            clinic, _ = _clinic_from(request, request.POST.get("cabang"))
            if clinic is None or str(clinic.pk) != request.POST.get("cabang"):
                messages.error(request, "Cabang tidak valid.")
                return redirect("direktur:decisions")
        try:
            services.create_decision(
                actor=user,
                title=request.POST.get("perkara", ""),
                decider=request.POST.get("pemutus", ""),
                clinic=clinic,
                reference=request.POST.get("rujukan", ""),
                background=request.POST.get("latar", ""),
                needed_by=services.parse_date(request.POST.get("tenggat", ""), "Tenggat"),
            )
            messages.success(request, "Keputusan dicatat.")
        except ValidationError as exc:
            _errors(request, exc)
        return redirect("direktur:decisions")
    status = request.GET.get("status", DecisionStatus.MENUNGGU)
    qs = dashboard.decisions_for(user)
    if status == "KEBIJAKAN":
        qs = qs.filter(status=DecisionStatus.DITETAPKAN, is_policy=True)
    elif status in dict(DecisionStatus.choices):
        qs = qs.filter(status=status)
    return render(
        request,
        "direktur/decisions.html",
        {
            "decisions": qs.order_by("needed_by", "-decided_on", "-created_at"),
            "status": status,
            "statuses": [*DecisionStatus.choices, ("KEBIJAKAN", "Kebijakan berlaku"), ("SEMUA", "Semua")],
            "deciders": Decider.choices,
            "clinics": user_clinic_queryset(user).order_by("id"),
            "is_director": is_aom(user),
            "today": local_today(),
        },
    )


@login_required
@require(dashboard.can_view_overview)
def decision_detail(request, pk: int):
    decision = get_object_or_404(dashboard.decisions_for(request.user), pk=pk)
    if request.method == "POST":
        if not is_aom(request.user):
            raise PermissionDenied("Hanya Direktur Operasional yang mencatat keputusan.")
        try:
            if request.POST.get("aksi") == "batalkan":
                services.cancel_decision(decision, actor=request.user, reason=request.POST.get("alasan", ""))
                messages.warning(request, "Keputusan dibatalkan.")
            else:
                services.settle_decision(
                    decision,
                    actor=request.user,
                    decision_text=request.POST.get("isi", ""),
                    is_policy=request.POST.get("kebijakan") == "1",
                    decided_on=services.parse_date(request.POST.get("tanggal", ""), "Tanggal"),
                )
                messages.success(request, "Keputusan ditetapkan.")
        except ValidationError as exc:
            _errors(request, exc)
        return redirect("direktur:decision_detail", pk=decision.pk)
    return render(
        request,
        "direktur/decision_detail.html",
        {"decision": decision, "is_director": is_aom(request.user), "today": local_today()},
    )


@login_required
@require(is_aom)
def checklist(request):
    cadence = request.GET.get("siklus", Cadence.HARIAN).upper()
    if cadence not in dict(Cadence.choices):
        cadence = Cadence.HARIAN
    clinic, clinics = _clinic_from(request)
    if clinic is None:
        messages.error(request, "Belum ada cabang aktif.")
        return redirect("core:dashboard")
    today = local_today()
    summary = services.pending_summary(clinic, today)
    rows = services.board(clinic, cadence, today)
    return render(
        request,
        "direktur/checklist.html",
        {
            "clinic": clinic,
            "clinics": clinics,
            "cadence": cadence,
            "cadences": Cadence.choices,
            "summary": summary,
            "period_start": period_start(cadence, today),
            "rows": rows,
            "photos": photos_for("auditcheck", [r["check"].pk for r in rows if r.get("check")]),
            "results": CheckResult.choices,
            "targets": services.target_choices(clinic),
            "priorities": Priority.choices,
            "suggestions": services.direct_check_suggestions(clinic, today) if cadence == Cadence.HARIAN else [],
            "owner_summary": DailySummary.objects.filter(date=today).first(),
            "summary_preview": daily_summary.compose(request.user, today),
        },
    )


@login_required
@require(is_aom)
@require_POST
def summary_send(request):
    """Tombol "Simpan dan kirim summary ke Owner" di Checklist Direktur."""
    item = daily_summary.send_summary(actor=request.user, note=request.POST.get("catatan", ""))
    if item.send_count > 1:
        messages.success(request, f"Summary diperbarui dan dikirim ulang ke Owner (kiriman ke-{item.send_count}).")
    else:
        messages.success(request, "Summary tersimpan dan dikirim ke Owner.")
    back = request.POST.get("next", "")
    if not back.startswith("/direktur/") or "//" in back:
        back = reverse("direktur:checklist")
    return redirect(f"{back}#summary-owner")


@login_required
@require(is_aom)
@require_POST
def record(request, item_id: int):
    item = get_object_or_404(AuditItem, pk=item_id)
    clinic, _ = _clinic_from(request, request.POST.get("cabang"))
    back = f"{reverse('direktur:checklist')}?siklus={item.cadence}&cabang={clinic.pk if clinic else ''}"
    if clinic is None or str(clinic.pk) != request.POST.get("cabang"):
        messages.error(request, "Cabang tidak valid.")
        return redirect(back)
    try:
        with transaction.atomic():
            check = _record_check_with_photo(request, item, clinic)
    except ValidationError as exc:
        _errors(request, exc)
    else:
        if check.finding_id:
            messages.warning(request, f"{item.title}: temuan dicatat dan task tindak lanjut dibuat.")
        else:
            messages.success(request, f"{item.title}: {check.get_result_display().lower()}.")
    return redirect(f"{back}#butir-{item.pk}")


def _record_check_with_photo(request, item, clinic):
    check = services.record_check(
        item=item,
        clinic=clinic,
        actor=request.user,
        result=request.POST.get("hasil", ""),
        note=request.POST.get("catatan", ""),
        direct=request.POST.get("langsung") == "1",
        reason=request.POST.get("alasan", ""),
        target=request.POST.get("penerima", ""),
        due_at=services.parse_due(request.POST.get("batas", "")),
        priority=request.POST.get("prioritas") or Priority.SEDANG,
    )
    save_optional_photo(request, entity_type="auditcheck", entity_id=check.pk)
    return check


@login_required
@require(is_aom)
@require_POST
def finding_close(request, pk: int):
    item = get_object_or_404(ActionItem, pk=pk)
    try:
        services.close_finding(item, actor=request.user, note=request.POST.get("catatan", ""))
        messages.success(request, "Ditandai selesai.")
    except ValidationError as exc:
        _errors(request, exc)
    target = request.POST.get("next", "")
    if not target.startswith("/direktur/") or "//" in target:
        target = reverse("direktur:team")
    return redirect(target)


@login_required
@require(is_aom)
def notes(request):
    archived = request.GET.get("arsip") == "1"
    if request.method == "POST":
        clinic = None
        if request.POST.get("cabang"):
            clinic, _ = _clinic_from(request, request.POST.get("cabang"))
            if clinic is None or str(clinic.pk) != request.POST.get("cabang"):
                messages.error(request, "Cabang tidak valid.")
                return redirect("direktur:notes")
        try:
            services.create_note(
                author=request.user,
                body=request.POST.get("isi", ""),
                source=request.POST.get("sumber", NoteSource.MANUAL),
                clinic=clinic,
            )
            messages.success(request, "Catatan disimpan.")
        except ValidationError as exc:
            _errors(request, exc)
        return redirect("direktur:notes")
    return render(
        request,
        "direktur/notes.html",
        {
            "notes": services.notes_for(request.user, archived=archived),
            "archived": archived,
            "clinics": user_clinic_queryset(request.user).order_by("id"),
            "sources": NoteSource.choices,
        },
    )


@login_required
@require(is_aom)
@require_POST
def note_archive(request, pk: int):
    note = get_object_or_404(DirectorNote, pk=pk, author=request.user)
    archive = request.POST.get("aksi") != "pulihkan"
    services.set_note_archived(note, user=request.user, archived=archive)
    messages.success(request, "Catatan diarsipkan." if archive else "Catatan dipulihkan.")
    return redirect(f"{reverse('direktur:notes')}{'' if archive else '?arsip=1'}")


@login_required
@require(is_aom)
def note_convert(request, pk: int):
    note = get_object_or_404(DirectorNote, pk=pk, author=request.user)
    if note.converted_task_id:
        messages.info(request, "Catatan ini sudah dijadikan task.")
        return redirect("direktur:notes")
    clinic, clinics = _clinic_from(
        request, request.POST.get("cabang") or request.GET.get("cabang") or note.clinic_id
    )
    if request.method == "POST":
        try:
            services.convert_note(
                note,
                user=request.user,
                clinic=clinic,
                title=request.POST.get("judul", ""),
                target=request.POST.get("penerima", ""),
                priority=request.POST.get("prioritas") or Priority.SEDANG,
                due_at=services.parse_due(request.POST.get("batas", "")),
            )
            messages.success(request, "Catatan dijadikan task.")
            return redirect("direktur:notes")
        except ValidationError as exc:
            _errors(request, exc)
    return render(
        request,
        "direktur/task_form.html",
        {
            "note": note,
            "clinic": clinic,
            "clinics": clinics,
            "targets": services.target_choices(clinic) if clinic else [],
            "priorities": Priority.choices,
            "title": request.POST.get("judul") or services.suggest_title(note.body),
            "description": note.body,
        },
    )


@login_required
@require(is_aom)
def task_new(request):
    clinic, clinics = _clinic_from(request, request.POST.get("cabang") or request.GET.get("cabang"))
    if request.method == "POST":
        try:
            services.create_manual_task(
                actor=request.user,
                clinic=clinic,
                title=request.POST.get("judul", ""),
                description=request.POST.get("uraian", ""),
                target=request.POST.get("penerima", ""),
                priority=request.POST.get("prioritas") or Priority.SEDANG,
                due_at=services.parse_due(request.POST.get("batas", "")),
            )
            messages.success(request, "Task dikirim.")
            return redirect("direktur:team")
        except ValidationError as exc:
            _errors(request, exc)
    return render(
        request,
        "direktur/task_form.html",
        {
            "note": None,
            "clinic": clinic,
            "clinics": clinics,
            "targets": services.target_choices(clinic) if clinic else [],
            "priorities": Priority.choices,
            "title": request.POST.get("judul", ""),
            "description": request.POST.get("uraian", ""),
        },
    )


# --- Detail task -------------------------------------------------------------------

_BACK = {
    "gantt": ("direktur:gantt", "Jadwal Task"),
    "kanban": ("direktur:kanban", "Kanban"),
    "prioritas": ("direktur:matrix", "Prioritas"),
    "tim": ("direktur:team", "Tim"),
}


def _due_from_form(item: ActionItem, value: str):
    """Tanggal dari formulir. Bila tanggalnya tidak berubah, jam target lama dipertahankan."""
    value = (value or "").strip()
    if item.due_at and value == timezone.localtime(item.due_at).date().isoformat():
        return item.due_at
    return services.parse_due(value)


def _assignment_action(request, item: ActionItem, aksi: str) -> str:
    assignment = get_object_or_404(TaskAssignment, pk=request.POST.get("assignment"), action_item=item)
    note = request.POST.get("catatan", "")
    if aksi == "konfirmasi":
        task_services.confirm_assignment(assignment, reviewer=request.user, note=note)
        return f"Pekerjaan {assignment.assignee} dikonfirmasi."
    if aksi == "revisi":
        task_services.request_revision(assignment, reviewer=request.user, note=note)
        return f"Revisi diminta ke {assignment.assignee}."
    if not task_services.can_manage_task(item, request.user):
        raise PermissionDenied("Hanya pemberi tugas atau Direktur Operasional yang dapat membatalkan penerima.")
    task_services.cancel_assignment(assignment, actor=request.user, reason=note)
    return f"{assignment.assignee} dikeluarkan dari task."


@login_required
@require(dashboard.can_view_overview)
def task_detail(request, pk: int):
    item = get_object_or_404(
        ActionItem.objects.filter(clinic__in=user_clinic_queryset(request.user)).select_related(
            "clinic", "owner", "created_by"
        ),
        pk=pk,
    )
    can_manage = task_services.can_manage_task(item, request.user)
    if request.method == "POST":
        aksi = request.POST.get("aksi", "")
        try:
            if aksi in {"konfirmasi", "revisi", "keluarkan"}:
                messages.success(request, _assignment_action(request, item, aksi))
            elif aksi == "catatan":
                task_services.add_task_comment(item, actor=request.user, note=request.POST.get("catatan", ""))
                messages.success(request, "Catatan ditambahkan.")
            elif not can_manage:
                raise PermissionDenied("Hanya pemberi tugas atau Direktur Operasional yang dapat mengubah task ini.")
            elif aksi == "ubah":
                task_services.update_task(
                    item,
                    actor=request.user,
                    status=request.POST.get("status", item.status),
                    priority=request.POST.get("prioritas", item.priority),
                    due_at=_due_from_form(item, request.POST.get("batas", "")),
                    progress_note=request.POST.get("progres", ""),
                )
                messages.success(request, "Task diperbarui.")
            elif aksi == "selesai":
                task_services.close_task(item, actor=request.user, note=request.POST.get("catatan", ""))
                messages.success(request, "Task ditandai selesai.")
            elif aksi == "batal":
                task_services.cancel_task(item, actor=request.user, reason=request.POST.get("catatan", ""))
                messages.warning(request, "Task dibatalkan.")
            else:
                messages.error(request, "Aksi tidak dikenali.")
        except ValidationError as exc:
            _errors(request, exc)
        return redirect("direktur:task_detail", pk=item.pk)

    assignments = list(item.task_assignments.select_related("assignee", "claimed_by", "reviewer"))
    rows = [
        {
            "a": a,
            "can_review": a.status == TaskAssignmentStatus.SUBMITTED
            and task_services.can_review_assignment(a, request.user),
            "can_remove": can_manage and a.status in task_services.OPEN_ASSIGNMENT_STATES,
        }
        for a in assignments
    ]
    is_open = item.status not in (ActionItemStatus.SELESAI, ActionItemStatus.BATAL)
    entity = SOURCE_PHOTO_ENTITY.get(item.source_type)
    return render(
        request,
        "direktur/task_detail.html",
        {
            "item": item,
            "rows": rows,
            "source_photos": photos_for(entity, [item.source_id]).get(item.source_id, [])
            if entity and item.source_id else [],
            "evidence_photos": photos_for("taskassignment", [a.pk for a in assignments]),
            "events": item.task_events.select_related("actor", "assignment__assignee"),
            "source": dict(dashboard.SOURCE_CHOICES).get(dashboard.source_group(item), "Modul lain"),
            "column": dict(dashboard.COLUMNS).get(dashboard.kanban_column(item, assignments)),
            "can_manage": can_manage,
            "can_comment": can_manage or any(a.assignee_id == request.user.pk for a in assignments),
            "is_open": is_open,
            "priorities": Priority.choices,
            "statuses": [(ActionItemStatus.BARU, "Baru"), (ActionItemStatus.DIKERJAKAN, "Dikerjakan")],
            "due_value": timezone.localtime(item.due_at).date().isoformat() if item.due_at else "",
            "back": _BACK.get(request.GET.get("dari", ""), _BACK["kanban"]),
        },
    )
