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

from core import kategori, task_services
from core.photos import SOURCE_PHOTO_ENTITY, documents_for, photos_for, save_optional_photo
from core.models import (
    ActionItem,
    ActionItemStatus,
    ClinicConfig,
    Priority,
    ReviewBy,
    TaskAssignment,
    TaskAssignmentStatus,
    TaskCategory,
    local_today,
)
from core.permissions import is_aom, is_owner, is_owner_only, require, user_clinic_queryset

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
    from core.photos import task_photos

    user = request.user
    # 5 Okt 2026: Ringkasan adalah halaman pertama Direktur; task untuknya sendiri juga tampil di sini.
    mine = task_services.my_tasks(user)
    return render(
        request,
        "direktur/overview.html",
        {
            "my_tasks": mine,
            "task_photos": task_photos([t["item"] for t in mine]),
            "my_issues": user.issue_assignments.filter(active=True).select_related("issue")[:10],
            "inbox": _inbox_counts(request.user),
            "bird": dashboard.bird_view(user),
            "matrix": dashboard.eisenhower(user, limit=1),
            "counts": dashboard.headline_counts(user),
            "agenda": dashboard.meeting_agenda(user),
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
        {
            "decision": decision,
            "is_director": is_aom(request.user),
            "can_owner_decide": is_owner(request.user) and decision.status == DecisionStatus.MENUNGGU
            and services.is_owner_decision(decision),
            "today": local_today(),
            "waiting": decision.waiting_tasks.select_related("clinic").order_by("status", "due_at"),
            "followups": ActionItem.objects.filter(
                source_type=services.DECISION_SOURCE, source_id=decision.pk
            ).select_related("clinic").order_by("created_at"),
        },
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
    clinics = user_clinic_queryset(request.user).order_by("id")
    ref = request.POST.get("keputusan") or request.GET.get("keputusan") or ""
    decision = (
        get_object_or_404(dashboard.decisions_for(request.user), pk=int(ref)) if ref.isdigit() else None
    )
    branch = branch_context(request, clinics, default=decision.clinic_id if decision else None)
    if request.method == "POST":
        try:
            pairs = branch_targets(request.POST, clinics)
            with transaction.atomic():
                for clinic, target in pairs:
                    services.create_manual_task(
                        actor=request.user,
                        clinic=clinic,
                        title=request.POST.get("judul", ""),
                        description=request.POST.get("uraian", ""),
                        target=target,
                        priority=request.POST.get("prioritas") or Priority.SEDANG,
                        due_at=services.parse_due(request.POST.get("batas", "")),
                        decision=decision,
                    )
            messages.success(request, "Task dikirim." if len(pairs) == 1 else f"Task dikirim ke {len(pairs)} cabang.")
            if decision:
                return redirect("direktur:decision_detail", pk=decision.pk)
            return redirect("direktur:team")
        except ValidationError as exc:
            _errors(request, exc)
    title = request.POST.get("judul", "")
    description = request.POST.get("uraian", "")
    if decision and request.method != "POST":
        title = f"Tindak lanjut: {decision.title}"[:200]
        description = decision.decision_text
    return render(
        request,
        "direktur/task_form.html",
        {
            **branch,
            "note": None,
            "decision": decision,
            "priorities": Priority.choices,
            "title": title,
            "description": description,
        },
    )


# --- Detail task -------------------------------------------------------------------

_BACK = {
    "daftar": ("direktur:tasks", "Daftar Task"),
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
    rating = task_services.parse_rating(request.POST.get("bintang"))
    rating_note = request.POST.get("catatan_bintang", "")
    if aksi == "konfirmasi":
        task_services.confirm_assignment(assignment, reviewer=request.user, note=note, rating=rating,
                                         rating_note=rating_note)
        return f"Pekerjaan {assignment.assignee} dikonfirmasi."
    if aksi == "nilai":
        task_services.rate_assignment(assignment, actor=request.user, rating=rating, note=rating_note)
        return f"Bintang untuk {assignment.assignee} disimpan."
    if aksi == "revisi":
        task_services.request_revision(assignment, reviewer=request.user, note=note)
        return f"Revisi diminta ke {assignment.assignee}."
    if not task_services.can_manage_task(item, request.user):
        raise PermissionDenied("Hanya pemberi tugas atau Direktur Operasional yang dapat membatalkan penerima.")
    task_services.cancel_assignment(assignment, actor=request.user, reason=note)
    return f"{assignment.assignee} dikeluarkan dari task."


def _close_rating_context(item, assignments, user) -> dict:
    """Formulir "Tandai selesai": siapa yang mendapat bintang (task bersama: hanya pengambilnya)."""
    open_rows = [a for a in assignments if a.status in task_services.OPEN_ASSIGNMENT_STATES]
    targets = task_services.close_rating_targets(item, open_rows, user)
    names = ", ".join(str(a.assignee) for a in open_rows if a.pk in targets)
    shared_unclaimed = (item.assignment_mode == "BERSAMA" and not any(a.claimed_by_id for a in assignments)
                        and any(task_services.needs_rating(a.assignee) for a in open_rows))
    return {"close_needs_rating": bool(targets), "close_rating_names": names,
            "close_shared_unclaimed": shared_unclaimed}


@login_required
@require(dashboard.can_view_overview)
def task_detail(request, pk: int):
    item = get_object_or_404(
        ActionItem.objects.filter(clinic__in=user_clinic_queryset(request.user)).select_related(
            "clinic", "owner", "created_by", "category"
        ),
        pk=pk,
    )
    can_manage = task_services.can_manage_task(item, request.user)
    if request.method == "POST":
        aksi = request.POST.get("aksi", "")
        try:
            if aksi in {"konfirmasi", "revisi", "keluarkan", "nilai"}:
                messages.success(request, _assignment_action(request, item, aksi))
            elif aksi == "catatan":
                task_services.add_task_comment(item, actor=request.user, note=request.POST.get("catatan", ""))
                messages.success(request, "Catatan ditambahkan.")
            elif aksi in {"tahan", "lepas"}:
                ref = request.POST.get("keputusan", "")
                decision = get_object_or_404(dashboard.decisions_for(request.user), pk=int(ref) if ref.isdigit() else 0)
                if aksi == "tahan":
                    services.hold_task(item, decision, actor=request.user)
                    messages.success(request, f"Task ditahan menunggu keputusan: {decision}.")
                else:
                    services.release_task(item, decision, actor=request.user)
                    messages.success(request, "Task tidak lagi menunggu keputusan.")
            elif aksi == "rapat":
                decision = services.bring_to_meeting(
                    item,
                    actor=request.user,
                    title=request.POST.get("perkara", ""),
                    background=request.POST.get("latar", ""),
                    needed_by=services.parse_date(request.POST.get("tenggat", ""), "Tenggat"),
                )
                messages.success(request, f"Perkara dicatat untuk rapat Kamis: {decision}.")
            elif not can_manage:
                raise PermissionDenied("Hanya pemberi tugas atau Direktur Operasional yang dapat mengubah task ini.")
            elif aksi == "setujui_target":
                task_services.approve_proposed_due(
                    item, actor=request.user, expected_due=request.POST.get("usulan") or None
                )
                messages.success(request, "Target baru disetujui; penerima diberi tahu.")
            elif aksi == "ubah":
                task_services.update_task(
                    item,
                    actor=request.user,
                    status=request.POST.get("status", item.status),
                    priority=request.POST.get("prioritas", item.priority),
                    due_at=_due_from_form(item, request.POST.get("batas", "")),
                    progress_note=request.POST.get("progres", ""),
                    review_by=request.POST.get("pemeriksa") or None,
                )
                messages.success(request, "Task diperbarui.")
            elif aksi == "selesai":
                task_services.close_task(item, actor=request.user, note=request.POST.get("catatan", ""),
                                         rating=task_services.parse_rating(request.POST.get("bintang")),
                                         rating_note=request.POST.get("catatan_bintang", ""))
                messages.success(request, "Task ditandai selesai.")
            elif aksi == "kategori":
                kategori.set_task_category(item, actor=request.user, raw=request.POST.get("kategori", ""))
                messages.success(request, "Kategori task disimpan.")
            elif aksi == "batal":
                task_services.cancel_task(item, actor=request.user, reason=request.POST.get("catatan", ""))
                messages.warning(request, "Task dibatalkan.")
            else:
                messages.error(request, "Aksi tidak dikenali.")
        except ValidationError as exc:
            _errors(request, exc)
        return redirect("direktur:task_detail", pk=item.pk)

    assignments = list(item.task_assignments.select_related("assignee", "claimed_by", "reviewer", "rated_by"))
    now = timezone.now()
    owner_view = is_owner_only(request.user)
    rows = [
        {
            "a": a,
            # 5 Okt 2026: penerima (termasuk Direktur yang menugaskan dirinya sendiri) bisa lapor progres dan
            # ajukan selesai dari halaman ini, tidak hanya dari Tugas saya.
            "can_submit": a.assignee_id == request.user.pk and item.status not in (
                ActionItemStatus.SELESAI, ActionItemStatus.BATAL)
            # Owner tidak boleh membuka rute core Hari Ini: hanya task project, lewat rute projects.
            and (not owner_view or item.source_type == "proyek")
            and task_services.my_task_row(item, a, request.user, now)["can_submit"],
            "owner_card": owner_view,
            "can_review": a.status == TaskAssignmentStatus.SUBMITTED
            and task_services.can_review_assignment(a, request.user),
            "can_remove": can_manage and a.status in task_services.OPEN_ASSIGNMENT_STATES,
            # Bintang (8 Okt 2026): halaman ini hanya untuk Direktur/Owner, jadi semua bintang tampil.
            "rated": task_services.needs_rating(a.assignee),
            "can_rate": a.status == TaskAssignmentStatus.CONFIRMED and task_services.needs_rating(a.assignee)
            and task_services.can_rate_assignment(a, request.user),
        }
        for a in assignments
    ]
    is_open = item.status not in (ActionItemStatus.SELESAI, ActionItemStatus.BATAL)
    entity = SOURCE_PHOTO_ENTITY.get(item.source_type)
    events = list(item.task_events.select_related("actor", "assignment__assignee"))
    waiting_on = list(item.waiting_decisions.all())
    held_ids = {d.pk for d in waiting_on}
    hold_choices = []
    if is_aom(request.user) and is_open:
        hold_choices = [
            d for d in dashboard.pending_decisions(request.user) if d.clinic_id in (None, item.clinic_id)
            and d.pk not in held_ids
        ]
    return render(
        request,
        "direktur/task_detail.html",
        {
            "item": item,
            "rows": rows,
            "source_photos": photos_for(entity, [item.source_id]).get(item.source_id, [])
            if entity and item.source_id else [],
            "evidence_photos": photos_for("taskassignment", [a.pk for a in assignments]),
            "evidence_docs": documents_for("taskassignment", [a.pk for a in assignments]),
            "events": events,
            "event_photos": photos_for("taskevent", [e.pk for e in events]),
            "event_docs": documents_for("taskevent", [e.pk for e in events]),
            "dirut_review": item.reviewed_by_dirut,
            "review_choices": ReviewBy.choices,
            "source": dict(dashboard.SOURCE_CHOICES).get(dashboard.source_group(item), "Modul lain"),
            "column": dict(dashboard.COLUMNS).get(dashboard.kanban_column(item, assignments)),
            "can_manage": can_manage,
            "reporter": dashboard.reporters([item]).get(item.pk),
            "source_url": dashboard.source_url(item),
            "waiting_on": waiting_on,
            "hold_choices": hold_choices,
            "is_director": is_aom(request.user),
            "can_comment": can_manage or any(a.assignee_id == request.user.pk for a in assignments)
            or (is_owner(request.user) and item.reviewed_by_dirut),
            "is_open": is_open,
            "i_receive": any(r["can_submit"] for r in rows),
            # Tandai selesai: bintang wajib bila ada penerima staf yang ikut dikonfirmasi.
            **_close_rating_context(item, assignments, request.user),
            "categories": kategori.category_choices(item.category),
            "priorities": Priority.choices,
            "statuses": [(ActionItemStatus.BARU, "Baru"), (ActionItemStatus.DIKERJAKAN, "Dikerjakan")],
            "due_value": timezone.localtime(item.due_at).date().isoformat() if item.due_at else "",
            "back": _BACK.get(request.GET.get("dari", ""))
            or (("owner:dashboard", "Dashboard") if is_owner(request.user) and not is_aom(request.user)
                else _BACK["kanban"]),
        },
    )


# --- Daftar task -------------------------------------------------------------------

@login_required
@require(dashboard.can_view_overview)
def task_list(request):
    """Semua task dalam satu tabel: saring, cari, urutkan, unduh CSV. Owner hanya membaca."""
    from django.core.paginator import Paginator

    from . import task_list as tl

    f = tl.parse_filters(request.GET)
    rows = tl.rows(request.user, f)
    if request.GET.get("unduh") == "csv":
        return _task_csv(request, rows, f)
    page = Paginator(rows, tl.PAGE_SIZE).get_page(request.GET.get("hal"))
    params = request.GET.copy()
    params.pop("hal", None)
    params.pop("unduh", None)

    def link(**changes):
        q = params.copy()
        for k, v in changes.items():
            q[k] = v
        return q.urlencode()

    current = f["urut"]
    headers = []
    for key, label in tl.SORTS.items():
        active = current.lstrip("-") == key
        next_sort = f"-{key}" if current == key else key
        headers.append({"key": key, "label": label, "query": link(urut=next_sort), "active": active,
                        "desc": active and current.startswith("-")})
    return render(
        request,
        "direktur/task_list.html",
        {
            "page": page,
            "total": len(rows),
            "f": f,
            "columns": [h for h in headers if h["key"] != "cabang"],
            "active_filters": _active_filters(request.user, f),
            "base_query": params.urlencode(),
            "csv_query": link(unduh="csv"),
            "clinics": user_clinic_queryset(request.user).order_by("id"),
            "statuses": tl.STATUS_FILTERS,
            "priorities": Priority.choices,
            "sources": dashboard.SOURCE_CHOICES,
            "pics": tl.pic_choices(request.user),
            "categories": TaskCategory.objects.order_by("sort_order", "name"),
            "no_category": tl.NO_CATEGORY,
            "is_director": is_aom(request.user),
            "filtered": any(f[k] for k in ("q", "cabang", "pic", "prioritas", "sumber", "kategori", "dari", "sampai"))
            or f["status"] != "terbuka",
        },
    )


def _active_filters(user, f) -> list[str]:
    """Ringkasan saringan aktif di bawah judul, karena saringannya kini ada di pop up."""
    from accounts.models import User

    from . import task_list as tl

    out = []
    if f["q"]:
        out.append(f"Cari: “{f['q']}”")
    if f["status"] != "terbuka":
        out.append(dict(tl.STATUS_FILTERS).get(f["status"], f["status"]))
    if f["cabang"]:
        clinic = user_clinic_queryset(user).filter(pk=f["cabang"]).first()
        if clinic:
            out.append(clinic.name)
    if f["pic"]:
        pic = User.objects.filter(pk=f["pic"]).first()
        if pic:
            out.append(f"PIC: {pic}")
    if f["prioritas"]:
        out.append(f"Prioritas {dict(Priority.choices).get(f['prioritas'], f['prioritas'])}")
    if f["sumber"]:
        out.append(dict(dashboard.SOURCE_CHOICES).get(f["sumber"], f["sumber"]))
    if f["kategori"] == tl.NO_CATEGORY:
        out.append(f"Kategori: {kategori.NONE_LABEL}")
    elif f["kategori"]:
        cat = TaskCategory.objects.filter(pk=f["kategori"]).first()
        if cat:
            out.append(f"Kategori: {cat.name}")
    if f["dari"] or f["sampai"]:
        dari = f["dari"].strftime("%d/%m/%Y") if f["dari"] else "awal"
        sampai = f["sampai"].strftime("%d/%m/%Y") if f["sampai"] else "sekarang"
        out.append(f"Mulai {dari}–{sampai}")
    return out


def _task_csv(request, rows, f):
    import csv

    from django.http import StreamingHttpResponse

    from audit.models import AuditAction
    from audit.services import log_event
    from audit.views import _cell, _Echo

    log_event(action=AuditAction.EXPORT, entity_type="actionitem", entity_label=f"Ekspor daftar task {len(rows)} baris",
              actor=request.user, after={"filter": {k: str(v) for k, v in f.items() if v}, "rows": len(rows)},
              request=request)
    writer = csv.writer(_Echo())

    def fmt(moment):
        return timezone.localtime(moment).strftime("%Y-%m-%d %H:%M") if moment else ""

    def lines():
        yield "﻿"
        yield writer.writerow(["ID", "Task", "Cabang", "Sumber", "Kategori", "Pelapor", "Dibuat oleh", "PIC",
                               "Prioritas", "Status", "Menunggu keputusan", "Lewat target", "Target", "Dibuat",
                               "Diperbarui"])
        for r in rows:
            i = r["item"]
            yield writer.writerow([
                i.pk, _cell(i.title), _cell(i.clinic.name), _cell(r["source"]),
                _cell(i.category.name if i.category else ""), _cell(r["reporter"] or ""),
                _cell(i.created_by or ""), _cell(r["pic_names"]), i.get_priority_display(), r["status"],
                "ya" if r["on_hold"] else "", "ya" if r["overdue"] else "", fmt(i.due_at), fmt(i.created_at),
                fmt(i.updated_at),
            ])

    stamp = timezone.localtime().strftime("%Y%m%d-%H%M")
    response = StreamingHttpResponse(lines(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="daftar_task_{stamp}.csv"'
    return response


# --- Bahan rapat mingguan ------------------------------------------------------------

@login_required
@require(dashboard.can_view_overview)
def meeting_page(request):
    """Bahan rapat Kamis: periode Kamis lalu s.d. Rabu, bisa dicetak atau disalin ke WhatsApp."""
    import datetime as dt

    from . import meeting

    day = meeting.parse_meeting(request.GET.get("tanggal"))
    data = meeting.compose(request.user, day)
    return render(
        request,
        "direktur/meeting.html",
        {
            **data,
            "text": meeting.as_text(data),
            "prev": day - dt.timedelta(days=7),
            "next": day + dt.timedelta(days=7),
            "is_director": is_aom(request.user),
        },
    )


# --- KPI per staf (tahap 3 paket F) --------------------------------------------------

def _kpi_scope(request):
    from . import kpi

    clinics = list(user_clinic_queryset(request.user).order_by("id"))
    raw = request.GET.get("cabang", "")
    clinic = next((c for c in clinics if raw.isdigit() and c.pk == int(raw)), None)
    first = kpi.parse_month(request.GET.get("bulan"))
    return clinics, clinic, first


@login_required
@require(dashboard.can_view_overview)
def kpi_page(request):
    """KPI per staf per bulan: angka per metrik, tanpa skor gabungan (uji coba)."""
    from . import kpi

    clinics, clinic, first = _kpi_scope(request)
    rows = kpi.compose([clinic] if clinic else clinics, first)
    if request.GET.get("unduh") == "csv":
        return _kpi_csv(request, first, clinic, rows)
    settings_rows = [
        {"clinic": c, "tolerance": ClinicConfig.get(c, kpi.OPEN_TOLERANCE_KEY, 15),
         "bulk_items": ClinicConfig.get(c, kpi.BULK_ITEMS_KEY, 5),
         "bulk_seconds": ClinicConfig.get(c, kpi.BULK_SECONDS_KEY, 60)}
        for c in ([clinic] if clinic else clinics)
    ]
    return render(request, "direktur/kpi.html", {
        "rows": rows, "clinics": clinics, "clinic": clinic, "first": first, "last": kpi.month_end(first),
        "prev": kpi.shift_month(first, -1), "next": kpi.shift_month(first, 1),
        "is_current": first == local_today().replace(day=1), "settings_rows": settings_rows,
    })


@login_required
@require(dashboard.can_view_overview)
def kpi_staff(request, user_id):
    """Rincian KPI satu staf per hari, untuk memeriksa angka di halaman KPI."""
    from accounts.models import User

    from . import kpi

    person = get_object_or_404(User, pk=user_id)
    clinics, clinic, first = _kpi_scope(request)
    rows = kpi.compose([clinic] if clinic else clinics, first, only_user=person)
    return render(request, "direktur/kpi_staff.html", {
        "person": person, "kpi": rows[0] if rows else None, "clinics": clinics, "clinic": clinic,
        "first": first, "prev": kpi.shift_month(first, -1), "next": kpi.shift_month(first, 1),
        "is_current": first == local_today().replace(day=1),
    })


def _kpi_csv(request, first, clinic, rows):
    import csv

    from django.http import HttpResponse

    from audit.models import AuditAction
    from audit.services import log_event
    from audit.views import _cell

    from . import kpi

    log_event(action=AuditAction.EXPORT, entity_type="kpi", entity_label=f"Ekspor KPI {first:%Y-%m}",
              actor=request.user, after={"bulan": f"{first:%Y-%m}", "cabang": clinic.name if clinic else "Semua",
                                         "rows": len(rows)}, request=request)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    suffix = clinic.code if clinic else "semua"
    response["Content-Disposition"] = f'attachment; filename="kpi_{first:%Y-%m}_{suffix}.csv"'
    response.write("﻿")
    writer = csv.writer(response)
    writer.writerow(kpi.CSV_HEADER)
    for p in rows:
        writer.writerow([_cell(v) if isinstance(v, str) else v for v in kpi.csv_row(first, p)])
    return response


# --- Kategori permintaan/temuan dan task (8 Okt 2026) ------------------------------------

@login_required
@require(kategori.can_manage_categories)
def categories(request):
    """Atur kategori: tambah, ganti nama, urutan, aktif/nonaktif. Hanya Owner dan Direktur Operasional.

    Tidak ada hapus: kategori yang tidak dipakai lagi dinonaktifkan, data lama tetap berkategori sama."""
    from core.models import TaskCategory

    if request.method == "POST":
        try:
            if request.POST.get("aksi") == "tambah":
                cat = kategori.create_category(actor=request.user, name=request.POST.get("nama", ""),
                                               sort_order=request.POST.get("urutan"))
                messages.success(request, f"Kategori {cat.name} ditambahkan.")
            elif request.POST.get("aksi") == "ubah":
                ref = request.POST.get("kategori", "")
                cat = get_object_or_404(TaskCategory, pk=int(ref) if ref.isascii() and ref.isdigit() else 0)
                cat = kategori.update_category(cat, actor=request.user, name=request.POST.get("nama", ""),
                                               sort_order=request.POST.get("urutan"),
                                               active=request.POST.get("aktif") == "1")
                messages.success(request, f"Kategori {cat.name} disimpan{'' if cat.active else ' (nonaktif)'}.")
            else:
                messages.error(request, "Aksi tidak dikenali.")
        except ValidationError as exc:
            _errors(request, exc)
        return redirect("direktur:kategori")
    return render(request, "direktur/categories.html", {"rows": kategori.categories_with_usage()})


# --- Pilihan cabang untuk task baru: satu cabang atau semua cabang -------------------

ALL_BRANCHES = "semua"


def branch_context(request, clinics, default=None) -> dict:
    """Konteks formulir "Cabang + PIC" (templates/direktur/_branch_pic.html).

    Pilihan "Semua cabang" menampilkan satu pilihan PIC per cabang; hasilnya satu task per cabang
    (untuk hal yang berlaku di kedua cabang, keputusan product owner 3 Okt 2026).
    """
    raw = request.POST.get("cabang") or request.GET.get("cabang") or (str(default) if default else "")
    clinics = list(clinics)
    if raw == ALL_BRANCHES and len(clinics) > 1:
        return {"all_branches": True, "clinic": None, "clinics": clinics,
                "per_clinic": [(c, services.target_choices(c)) for c in clinics], "targets": []}
    clinic = next((c for c in clinics if raw.isdigit() and c.pk == int(raw)), clinics[0] if clinics else None)
    return {"all_branches": False, "clinic": clinic, "clinics": clinics, "per_clinic": [],
            "targets": services.target_choices(clinic) if clinic else []}


def branch_targets(post, clinics) -> list[tuple]:
    """[(cabang, penerima), ...] dari formulir _branch_pic. Validasi isi dilakukan service."""
    clinics = list(clinics)
    raw = post.get("cabang", "")
    if raw == ALL_BRANCHES:
        return [(c, post.get(f"penerima_{c.pk}", "")) for c in clinics]
    clinic = next((c for c in clinics if raw.isdigit() and c.pk == int(raw)), None)
    if clinic is None:
        raise ValidationError("Cabang tidak valid.")
    return [(clinic, post.get("penerima", ""))]
