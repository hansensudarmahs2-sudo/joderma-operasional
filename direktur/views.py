"""Halaman Direktur Operasional. Setiap view dibatasi role AOM di server."""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.models import ActionItem, Priority, local_today
from core.permissions import is_aom, require, user_clinic_queryset

from . import dashboard, services
from .models import (
    AuditItem,
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
            "rows": services.board(clinic, cadence, today),
            "results": CheckResult.choices,
            "targets": services.target_choices(clinic),
            "priorities": Priority.choices,
            "suggestions": services.direct_check_suggestions(clinic, today) if cadence == Cadence.HARIAN else [],
        },
    )


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
    except ValidationError as exc:
        _errors(request, exc)
    else:
        if check.finding_id:
            messages.warning(request, f"{item.title}: temuan dicatat dan task tindak lanjut dibuat.")
        else:
            messages.success(request, f"{item.title}: {check.get_result_display().lower()}.")
    return redirect(f"{back}#butir-{item.pk}")


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
