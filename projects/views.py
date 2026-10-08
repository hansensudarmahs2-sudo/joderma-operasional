"""Halaman Projects: daftar, buat, detail (task, bukti, pengaturan), dan detail task.

Semua izin diperiksa di sini dan di `projects.services`; menyembunyikan menu bukan kontrol akses.
"""
from __future__ import annotations

import datetime as dt

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.models import Role, User, UserRole
from core.models import (
    ActionItem,
    ActionItemStatus,
    Priority,
    TaskAssignment,
    TaskAssignmentMode,
    TaskAssignmentStatus,
    TaskEvent,
    TaskEventType,
    local_today,
)
from core.permissions import CROSS_BRANCH_ROLES, can_access_clinic, is_owner_only, user_clinic_queryset
from core.photos import documents_for, photos_for

from . import services as ps
from .models import SOURCE_TYPE, Project, ProjectStatus


# --- Pembantu -----------------------------------------------------------------------------


def _parse_date(value: str, label: str = "Tanggal"):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise ValidationError(f"{label} tidak valid.")


def _active_user(raw, label: str) -> User:
    try:
        pk = int(raw)
    except (TypeError, ValueError):
        raise ValidationError(f"{label} wajib dipilih.")
    user = User.objects.filter(pk=pk, is_active=True).first()
    if user is None:
        raise ValidationError(f"{label} tidak ditemukan atau tidak aktif.")
    return user


def _any_user(raw) -> User:
    """Pengguna mana pun (termasuk nonaktif), untuk melepas co-leader yang sudah dinonaktifkan."""
    try:
        user = User.objects.filter(pk=int(raw)).first()
    except (TypeError, ValueError):
        user = None
    if user is None:
        raise ValidationError("Co-project leader tidak ditemukan.")
    return user


def _clinic_or_none(raw, user):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        pk = int(raw)
    except ValueError:
        raise ValidationError("Cabang tidak dikenali.")
    clinic = user_clinic_queryset(user).filter(pk=pk).first()
    if clinic is None:
        raise ValidationError("Cabang tidak dikenali atau Anda tidak punya akses ke cabang itu.")
    return clinic


def _people() -> list[dict]:
    """Pengguna aktif ber-peran untuk pilihan leader/penerima; `clinics` memungkinkan penyaringan per cabang."""
    users = (
        User.objects.filter(is_active=True).filter(user_roles__in=UserRole.objects.exclude(role=Role.ADMIN))
        .distinct()
        .prefetch_related("user_roles")
        .order_by("display_name", "username")
    )
    out = []
    for u in users:
        roles = list(u.user_roles.all())
        # Direktur Operasional dan Owner menerima task di cabang mana pun (Owner lewat kartu di dashboard-nya).
        if any(r.role in (*CROSS_BRANCH_ROLES, Role.OWNER) for r in roles):
            clinics = "*"
        else:
            clinics = ",".join(sorted({str(r.clinic_id) for r in roles}))
        out.append({"user": u, "clinics": clinics})
    return out


def _require_view(user, project: Project) -> None:
    if not ps.can_view_project(user, project):
        raise PermissionDenied("Anda tidak memiliki akses ke project ini.")


# --- Daftar -------------------------------------------------------------------------------


@login_required
def project_list(request):
    user = request.user
    if not ps.user_has_projects(user):
        raise PermissionDenied("Anda bukan leader, co-leader, atau penerima task project yang sedang berjalan.")
    selesai = request.GET.get("semua") == "1"
    qs = ps.visible_projects(user).select_related("leader", "clinic")
    if selesai:
        qs = qs.exclude(status=ProjectStatus.AKTIF)
    else:
        qs = qs.filter(status=ProjectStatus.AKTIF)
    qs = qs.order_by(F("target_date").asc(nulls_last=True), "-created_at")
    today = local_today()
    rows = [{"project": p, "progress": p.progress(), "overdue": p.is_overdue(today)} for p in qs]
    return render(request, "projects/list.html", {
        "rows": rows, "selesai": selesai, "can_create": ps.can_create_project(user),
    })


# --- Buat ---------------------------------------------------------------------------------


@login_required
def project_new(request):
    user = request.user
    if not ps.can_create_project(user):
        raise PermissionDenied("Hanya Owner atau Direktur yang dapat membuat project.")
    values = {"name": "", "description": "", "target": "", "clinic": "", "leader": "", "co_leaders": []}
    if request.method == "POST":
        values = {
            "name": request.POST.get("nama", ""),
            "description": request.POST.get("uraian", ""),
            "target": request.POST.get("target", ""),
            "clinic": request.POST.get("cabang", ""),
            "leader": request.POST.get("leader", ""),
            "co_leaders": request.POST.getlist("co_leaders"),
        }
        try:
            leader = _active_user(values["leader"], "Project leader")
            co_leaders = [_active_user(raw, "Co-project leader") for raw in values["co_leaders"]]
            project = ps.create_project(
                actor=user, name=values["name"], description=values["description"],
                target_date=_parse_date(values["target"], "Target"),
                clinic=_clinic_or_none(values["clinic"], user), leader=leader, co_leaders=co_leaders,
            )
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, "Project dibuat; leader dan co-leader diberi tahu.")
            return redirect("projects:detail", pk=project.pk)
    return render(request, "projects/new.html", {
        "values": values, "people": _people(), "clinics": user_clinic_queryset(user).order_by("name"),
        "today": local_today(),
    })


# --- Detail project -----------------------------------------------------------------------


def _evidence(items: list[ActionItem]) -> dict[int, dict]:
    """Bukti per task: foto dan dokumen dari penerima (taskassignment) dan percakapan (taskevent)."""
    ids = [i.pk for i in items]
    asg = dict(TaskAssignment.objects.filter(action_item_id__in=ids).values_list("pk", "action_item_id"))
    evt = dict(TaskEvent.objects.filter(action_item_id__in=ids).values_list("pk", "action_item_id"))
    out = {i.pk: {"photos": [], "docs": []} for i in items}
    for entity, mapping in (("taskassignment", asg), ("taskevent", evt)):
        for entity_id, photos in photos_for(entity, mapping.keys()).items():
            out[mapping[entity_id]]["photos"].extend(photos)
        for entity_id, docs in documents_for(entity, mapping.keys()).items():
            out[mapping[entity_id]]["docs"].extend(docs)
    for ev in out.values():
        ev["count"] = len(ev["photos"]) + len(ev["docs"])
        stamps = [a.uploaded_at for a in ev["photos"] + ev["docs"]]
        ev["latest"] = max(stamps) if stamps else None
    return out


def _work_link(user) -> dict:
    """Tempat penerima mengerjakan task-nya: kartu dashboard Owner, atau Tugas hari ini."""
    if is_owner_only(user):
        return {"work_url": reverse("owner:dashboard") + "#tugas-project", "work_label": "Dashboard Owner"}
    return {"work_url": reverse("core:today"), "work_label": "Tugas hari ini"}


def _task_rows(project: Project, user=None) -> list[dict]:
    items = list(
        project.tasks().select_related("clinic").prefetch_related("task_assignments__assignee",
                                                                  "task_assignments__claimed_by")
        .order_by("due_at", "created_at")
    )
    evidence = _evidence(items)
    declined = set(TaskEvent.objects.filter(
        action_item_id__in=[i.pk for i in items], event_type=TaskEventType.CANCELLED, metadata__ditolak=True,
    ).values_list("assignment_id", flat=True))
    rows = []
    for item in items:
        everyone = list(item.task_assignments.all())
        active = [a for a in everyone if a.status != TaskAssignmentStatus.CANCELLED]
        all_declined = bool(
            item.status in ps.OPEN_ITEM_STATES and everyone and not active
            and any(a.pk in declined for a in everyone)
        )
        names = ", ".join(str(a.assignee) for a in active)
        shared = item.assignment_mode == TaskAssignmentMode.BERSAMA
        claimer = next((a.claimed_by for a in active if a.claimed_by_id), None)
        if shared:
            who = f"diambil: {claimer}" if claimer else f"salah satu: {names}"
        else:
            who = names
        confirmed = sum(a.status == TaskAssignmentStatus.CONFIRMED for a in active)
        counter = f"{confirmed}/{len(active)} selesai" if not shared and len(active) > 1 else ""
        rows.append({"item": item, "who": who or "—", "counter": counter, "evidence": evidence[item.pk],
                     "all_declined": all_declined,
                     "mine": bool(user) and any(a.assignee_id == user.pk for a in active)})
    return rows


@login_required
def project_detail(request, pk: int):
    project = get_object_or_404(Project.objects.select_related("leader", "clinic", "created_by"), pk=pk)
    user = request.user
    _require_view(user, project)
    if request.method == "POST":
        return _handle_detail_post(request, project)
    rows = _task_rows(project, user)
    gallery = sorted((r for r in rows if r["evidence"]["count"]),
                     key=lambda r: r["evidence"]["latest"], reverse=True)
    active = project.is_active
    clinics = user_clinic_queryset(user).order_by("name")
    can_manage = active and ps.can_manage_tasks(user, project)
    return render(request, "projects/detail.html", {
        "project": project,
        "co_leaders": project.co_leaders.order_by("display_name", "username"),
        "progress": project.progress(),
        "overdue": project.is_overdue(),
        "rows": rows,
        "gallery": gallery,
        "can_manage": can_manage,
        "can_edit": active and ps.can_edit_project(user, project),
        "can_admin": active and ps.can_admin_project(user, project),
        # Penerima task hanya melihat; pekerjaannya sendiri dikerjakan dari Tugas hari ini.
        "viewer_only": not ps.can_manage_tasks(user, project),
        **_work_link(user),
        "people": _people() if can_manage else [],
        "clinics": clinics,
        "priorities": Priority.choices,
        "today": local_today(),
    })


def _handle_detail_post(request, project: Project):
    user = request.user
    aksi = request.POST.get("aksi", "")
    post = request.POST
    try:
        if aksi == "tambah_task":
            _add_task(request, project)
        elif aksi == "ubah":
            ps.update_project(project, actor=user, description=post.get("uraian", ""),
                              target_date=_parse_date(post.get("target", ""), "Target"))
            messages.success(request, "Project diperbarui.")
        elif aksi == "tambah_coleader":
            ps.add_co_leader(project, actor=user, user=_active_user(post.get("user"), "Co-project leader"))
            messages.success(request, "Co-project leader ditambahkan.")
        elif aksi == "hapus_coleader":
            ps.remove_co_leader(project, actor=user, user=_any_user(post.get("user")))
            messages.success(request, "Co-project leader dihapus.")
        elif aksi == "ganti_leader":
            ps.set_leader(project, actor=user, leader=_active_user(post.get("leader"), "Project leader"))
            messages.success(request, "Project leader diganti.")
        elif aksi == "tutup":
            ps.close_project(project, actor=user, note=post.get("catatan", ""))
            messages.success(request, "Project ditutup.")
        elif aksi == "batalkan":
            ps.cancel_project(project, actor=user, note=post.get("alasan", ""))
            messages.warning(request, "Project dibatalkan.")
        else:
            messages.error(request, "Aksi tidak dikenali.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    except PermissionDenied as exc:
        # Hanya form "+ Task" yang menampilkan penolakan sebagai pesan (mis. akses cabang); lainnya 403.
        if aksi != "tambah_task":
            raise
        messages.error(request, str(exc) or "Anda tidak dapat menambah task di cabang itu.")
    return redirect("projects:detail", pk=project.pk)


def _add_task(request, project: Project) -> None:
    from direktur.services import parse_due

    post = request.POST
    clinic = _clinic_or_none(post.get("cabang", ""), request.user)
    ps.add_task(
        project, actor=request.user, title=post.get("judul", ""), description=post.get("uraian", ""),
        user_ids=post.getlist("penerima"), mode=post.get("mode") or TaskAssignmentMode.INDIVIDUAL,
        due_at=parse_due(post.get("target", "")), priority=post.get("prioritas") or Priority.SEDANG,
        clinic=clinic,
    )
    messages.success(request, "Task ditambahkan dan penerima diberi tahu.")


# --- Detail task --------------------------------------------------------------------------


@login_required
def task_detail(request, pk: int, task_pk: int):
    project = get_object_or_404(Project.objects.select_related("leader", "clinic"), pk=pk)
    user = request.user
    _require_view(user, project)
    item = get_object_or_404(
        ActionItem.objects.select_related("clinic", "created_by"),
        pk=task_pk, source_type=SOURCE_TYPE, source_id=project.pk,
    )
    if request.method == "POST":
        return _handle_task_post(request, project, item)
    assignments = list(item.task_assignments.select_related("assignee", "claimed_by", "reviewer"))
    events = list(item.task_events.select_related("actor", "assignment__assignee"))
    a_photos = photos_for("taskassignment", [a.pk for a in assignments])
    a_docs = documents_for("taskassignment", [a.pk for a in assignments])
    e_photos = photos_for("taskevent", [e.pk for e in events])
    e_docs = documents_for("taskevent", [e.pk for e in events])
    last_submit = {}
    decline_reason = {}
    for e in events:
        if e.event_type == TaskEventType.SUBMITTED and e.assignment_id and e.note:
            last_submit[e.assignment_id] = e.note
        if e.event_type == TaskEventType.CANCELLED and e.assignment_id and e.metadata.get("ditolak"):
            decline_reason[e.assignment_id] = e.note.removeprefix("Ditolak: ")
    can_manage = project.is_active and ps.can_manage_tasks(user, project) and item.status != ActionItemStatus.BATAL
    rows = [{
        "a": a,
        "photos": a_photos.get(a.pk, []),
        "docs": a_docs.get(a.pk, []),
        "note": last_submit.get(a.pk, ""),
        "declined": a.status == TaskAssignmentStatus.CANCELLED and a.pk in decline_reason,
        "decline_reason": decline_reason.get(a.pk, ""),
        "can_reopen": can_manage and a.status == TaskAssignmentStatus.CONFIRMED,
    } for a in assignments]
    for e in events:
        e.photos = e_photos.get(e.pk, [])
        e.docs = e_docs.get(e.pk, [])
    mine = [a for a in assignments if a.assignee_id == user.pk and a.status != TaskAssignmentStatus.CANCELLED]
    my_open = next((a for a in mine if a.status in ps.OPEN_ASSIGNMENT_STATES), None)
    return render(request, "projects/task_detail.html", {
        "project": project, "item": item, "rows": rows, "events": events,
        "can_manage": can_manage,
        # Penerima boleh membalas di task miliknya sendiri (add_task_comment memeriksa keterlibatan).
        "can_comment": ps.can_manage_tasks(user, project) or bool(mine),
        "my_open": my_open if item.status in ps.OPEN_ITEM_STATES else None,
        **_work_link(user),
        "shared": item.assignment_mode == TaskAssignmentMode.BERSAMA,
    })


def _handle_task_post(request, project: Project, item: ActionItem):
    aksi = request.POST.get("aksi", "")
    try:
        if aksi == "revisi":
            try:
                assignment = item.task_assignments.get(pk=int(request.POST.get("assignment", "")))
            except (TypeError, ValueError, TaskAssignment.DoesNotExist):
                raise ValidationError("Penerima tidak ditemukan.")
            ps.reopen_assignment(assignment, actor=request.user, note=request.POST.get("catatan", ""))
            messages.warning(request, f"Status selesai dibatalkan; {assignment.assignee} diminta merevisi.")
        elif aksi == "batal_task":
            ps.cancel_project_task(item, actor=request.user, reason=request.POST.get("alasan", ""))
            messages.warning(request, "Task dibatalkan.")
        elif aksi == "komentar":
            from core.task_services import add_task_comment

            # Penerima yang hanya melihat project membalas di task miliknya yang masih berlaku saja.
            if not ps.can_manage_tasks(request.user, project) and not item.task_assignments.filter(
                assignee=request.user
            ).exclude(status=TaskAssignmentStatus.CANCELLED).exists():
                raise PermissionDenied("Anda hanya dapat membalas di task milik Anda.")
            add_task_comment(item, actor=request.user, note=request.POST.get("catatan", ""))
            messages.success(request, "Balasan terkirim.")
        else:
            messages.error(request, "Aksi tidak dikenali.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("projects:task_detail", pk=project.pk, task_pk=item.pk)


# --- Aksi penerima Owner (kartu "Tugas saya (project)" di dashboard Owner) -----------------


def _my_assignment_or_404(request, pk: int) -> TaskAssignment:
    """Assignment task project milik pengguna sendiri; yang lain 404."""
    assignment = get_object_or_404(
        TaskAssignment.objects.select_related("action_item", "action_item__clinic"),
        pk=pk, assignee=request.user, action_item__source_type=SOURCE_TYPE,
    )
    if not can_access_clinic(request.user, assignment.action_item.clinic):
        raise PermissionDenied("Anda tidak memiliki akses ke task cabang ini.")
    return assignment


def _back_to_card(request):
    from core.views import _back

    return _back(request, "owner:dashboard" if is_owner_only(request.user) else "core:today")


@login_required
@require_POST
def my_submit(request, pk: int):
    """Penerima menandai task project selesai dengan bukti (aturan sama dengan Hari Ini staf)."""
    from core.views import submit_with_evidence

    submit_with_evidence(request, _my_assignment_or_404(request, pk))
    return _back_to_card(request)


@login_required
@require_POST
def my_comment(request, pk: int):
    """Balasan penerima di percakapan task project."""
    from core.task_services import add_task_comment

    item = get_object_or_404(
        ActionItem.objects.filter(task_assignments__assignee=request.user).distinct(),
        pk=pk, source_type=SOURCE_TYPE,
    )
    try:
        add_task_comment(item, actor=request.user, note=request.POST.get("catatan", ""))
        messages.success(request, "Balasan terkirim.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return _back_to_card(request)


@login_required
@require_POST
def my_decline(request, pk: int):
    """Owner menolak task project yang ditugaskan kepadanya (alasan wajib); hanya Owner (diperiksa di service)."""
    assignment = _my_assignment_or_404(request, pk)
    try:
        ps.decline_assignment(assignment, actor=request.user, reason=request.POST.get("alasan", ""))
        messages.success(request, "Task ditolak; pengatur project diberi tahu.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return _back_to_card(request)
