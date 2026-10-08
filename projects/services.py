"""Aturan Projects (server-side): izin, pembuatan, peran, task, dan penutupan project.

Task project adalah `core.ActionItem` (``source_type="proyek"``). Pembuatan/pembatalan task
memakai `core.task_services`; di sini hanya aturan yang khas project. Tampilan hanya cermin dari
fungsi `can_*` di bawah.
"""
from __future__ import annotations

import datetime as dt

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from accounts.models import Role, User
from audit.models import AuditAction
from audit.services import log_create, log_event, log_update, snapshot
from core.models import (
    ActionItem,
    ActionItemStatus,
    Priority,
    TaskAssignment,
    TaskAssignmentMode,
    TaskAssignmentStatus,
    TaskAudienceType,
    TaskEvent,
    TaskEventType,
)
from core.permissions import clinic_member_q, is_aom, is_owner, is_owner_only, user_clinic_queryset
from notifications.services import notify_user

from .models import SOURCE_TYPE, Project, ProjectStatus

OPEN_ITEM_STATES = (ActionItemStatus.BARU, ActionItemStatus.DIKERJAKAN)


# --- Izin ---------------------------------------------------------------------------------


def _authenticated(user) -> bool:
    return bool(user and getattr(user, "is_authenticated", False))


def _is_leader(user, project: Project) -> bool:
    return project.leader_id == user.pk


def _is_co_leader(user, project: Project) -> bool:
    return project.co_leaders.filter(pk=user.pk).exists()


def _is_admin_level(user, project: Project) -> bool:
    return is_owner(user) or is_aom(user) or project.created_by_id == user.pk


def can_create_project(user) -> bool:
    return _authenticated(user) and (is_owner(user) or is_aom(user))


def _recipient_project_ids(user):
    """Project tempat `user` menerima task (penugasan yang tidak dibatalkan)."""
    return (
        TaskAssignment.objects.filter(assignee=user, action_item__source_type=SOURCE_TYPE)
        .exclude(status=TaskAssignmentStatus.CANCELLED)
        .values("action_item__source_id")
    )


def is_task_recipient(user, project: Project) -> bool:
    return _recipient_project_ids(user).filter(action_item__source_id=project.pk).exists()


def can_view_project(user, project: Project) -> bool:
    """Lihat project: pengatur, atau penerima task di project itu (8 Okt 2026: hanya melihat)."""
    if not _authenticated(user):
        return False
    return can_manage_tasks(user, project) or is_task_recipient(user, project)


def can_manage_tasks(user, project: Project) -> bool:
    """Tambah/ubah/tugaskan task, batalkan selesai dengan revisi. Penerima task tidak termasuk."""
    if not _authenticated(user):
        return False
    return _is_admin_level(user, project) or _is_leader(user, project) or _is_co_leader(user, project)


def can_edit_project(user, project: Project) -> bool:
    """Ubah target & uraian, atur co-leader."""
    if not _authenticated(user):
        return False
    return _is_admin_level(user, project) or _is_leader(user, project)


def can_admin_project(user, project: Project) -> bool:
    """Tunjuk/ganti Project leader, tutup, dan batalkan project."""
    return _authenticated(user) and _is_admin_level(user, project)


def user_has_projects(user) -> bool:
    """Menu Projects: Owner/Direktur, atau leader/co-leader/penerima task di project yang masih berjalan."""
    if not _authenticated(user):
        return False
    if is_owner(user) or is_aom(user):
        return True
    return Project.objects.filter(
        Q(leader=user) | Q(co_leaders=user) | Q(pk__in=_recipient_project_ids(user)), status=ProjectStatus.AKTIF
    ).exists()


def visible_projects(user):
    """Project yang boleh dilihat `user` (tanpa urutan; urutkan di pemanggil)."""
    if not _authenticated(user):
        return Project.objects.none()
    if is_owner(user) or is_aom(user):
        return Project.objects.all()
    return Project.objects.filter(
        Q(created_by=user) | Q(leader=user) | Q(co_leaders=user) | Q(pk__in=_recipient_project_ids(user))
    ).distinct()


def is_project_item(item: ActionItem) -> bool:
    return item.source_type == SOURCE_TYPE


def project_for_item(item: ActionItem) -> Project | None:
    if not is_project_item(item) or not item.source_id:
        return None
    return Project.objects.filter(pk=item.source_id).first()


# --- Pembantu -----------------------------------------------------------------------------


def _assert(allowed: bool, message: str) -> None:
    if not allowed:
        raise PermissionDenied(message)


def _assert_active(project: Project) -> None:
    if project.status != ProjectStatus.AKTIF:
        raise ValidationError("Project ini sudah ditutup atau dibatalkan.")


def _active_user(user, label: str) -> User:
    if user is None or not getattr(user, "is_active", False):
        raise ValidationError(f"{label} harus pengguna yang aktif.")
    return user


def _notify_role(user, project: Project, *, actor, title: str) -> None:
    if user.pk == getattr(actor, "pk", None):
        return
    notify_user(
        user,
        type_code="PROJECT_ROLE",
        title=title,
        body=f"Ditunjuk oleh {actor}",
        entity_ref=f"project#{project.pk}:role",
        url_name="projects:detail",
        url_args=[project.pk],
    )


def _audit(project: Project, before: dict | None, *, actor, reason: str = "", action: str = AuditAction.UPDATE):
    log_update(project, before, actor=actor, reason=reason, action=action, label=f"Project: {project.name}")


# --- Project ------------------------------------------------------------------------------


@transaction.atomic
def create_project(
    *, actor, name: str, description: str = "", target_date: dt.date | None = None, clinic=None,
    leader, co_leaders=(),
) -> Project:
    _assert(can_create_project(actor), "Hanya Owner atau Direktur yang dapat membuat project.")
    name = (name or "").strip()
    if not name:
        raise ValidationError("Nama project wajib diisi.")
    if len(name) > 200:
        raise ValidationError("Nama project terlalu panjang (maks. 200 karakter).")
    _active_user(leader, "Project leader")
    co_leaders = [u for u in dict.fromkeys(co_leaders or ()) if u.pk != leader.pk]
    for u in co_leaders:
        _active_user(u, "Co-project leader")
    project = Project.objects.create(
        name=name, description=(description or "").strip(), target_date=target_date, clinic=clinic,
        leader=leader, created_by=actor,
    )
    project.co_leaders.set(co_leaders)
    log_create(project, actor=actor, label=f"Project: {project.name}")
    _notify_role(leader, project, actor=actor, title=f"Anda Project leader: {project.name}")
    for u in co_leaders:
        _notify_role(u, project, actor=actor, title=f"Anda Co-project leader: {project.name}")
    return project


@transaction.atomic
def update_project(project: Project, *, actor, description: str, target_date: dt.date | None) -> Project:
    _assert(can_edit_project(actor, project),
            "Hanya Project leader, pembuat, Owner, atau Direktur yang dapat mengubah project.")
    _assert_active(project)
    before = snapshot(project)
    project.description = (description or "").strip()
    project.target_date = target_date
    project.save(update_fields=["description", "target_date", "updated_at"])
    _audit(project, before, actor=actor)
    return project


@transaction.atomic
def set_leader(project: Project, *, actor, leader) -> Project:
    _assert(can_admin_project(actor, project),
            "Hanya pembuat project, Owner, atau Direktur yang dapat mengganti Project leader.")
    _assert_active(project)
    _active_user(leader, "Project leader")
    if leader.pk == project.leader_id:
        raise ValidationError("Orang ini sudah menjadi Project leader.")
    before = snapshot(project)
    project.leader = leader
    project.save(update_fields=["leader", "updated_at"])
    project.co_leaders.remove(leader)  # tidak boleh rangkap
    _audit(project, before, actor=actor)
    _notify_role(leader, project, actor=actor, title=f"Anda Project leader: {project.name}")
    return project


@transaction.atomic
def add_co_leader(project: Project, *, actor, user) -> Project:
    _assert(can_edit_project(actor, project),
            "Hanya Project leader, pembuat, Owner, atau Direktur yang dapat mengatur co-leader.")
    _assert_active(project)
    _active_user(user, "Co-project leader")
    if user.pk == project.leader_id:
        raise ValidationError("Project leader tidak perlu menjadi co-leader.")
    if _is_co_leader(user, project):
        raise ValidationError("Orang ini sudah menjadi Co-project leader.")
    project.co_leaders.add(user)
    log_event(action=AuditAction.UPDATE, entity_type="project", entity_id=project.pk,
              entity_label=f"Project: {project.name}", actor=actor, after={"co_leader_ditambah": user.pk})
    _notify_role(user, project, actor=actor, title=f"Anda Co-project leader: {project.name}")
    return project


@transaction.atomic
def remove_co_leader(project: Project, *, actor, user) -> Project:
    _assert(can_edit_project(actor, project),
            "Hanya Project leader, pembuat, Owner, atau Direktur yang dapat mengatur co-leader.")
    _assert_active(project)
    if not _is_co_leader(user, project):
        raise ValidationError("Orang ini bukan Co-project leader.")
    project.co_leaders.remove(user)
    log_event(action=AuditAction.UPDATE, entity_type="project", entity_id=project.pk,
              entity_label=f"Project: {project.name}", actor=actor, after={"co_leader_dihapus": user.pk})
    return project


@transaction.atomic
def close_project(project: Project, *, actor, note: str = "") -> Project:
    _assert(can_admin_project(actor, project),
            "Hanya pembuat project, Owner, atau Direktur yang dapat menutup project.")
    _assert_active(project)
    if project.tasks().filter(status__in=OPEN_ITEM_STATES).exists():
        raise ValidationError("Masih ada task yang belum selesai.")
    before = snapshot(project)
    project.status = ProjectStatus.SELESAI
    project.closed_at = timezone.now()
    project.closed_by = actor
    project.close_note = (note or "").strip()
    project.save(update_fields=["status", "closed_at", "closed_by", "close_note", "updated_at"])
    _audit(project, before, actor=actor, reason=project.close_note, action=AuditAction.CLOSE)
    return project


@transaction.atomic
def cancel_project(project: Project, *, actor, note: str) -> Project:
    from core import task_services as ts

    _assert(can_admin_project(actor, project),
            "Hanya pembuat project, Owner, atau Direktur yang dapat membatalkan project.")
    _assert_active(project)
    note = (note or "").strip()
    if not note:
        raise ValidationError("Alasan pembatalan wajib diisi.")
    for item in project.tasks().filter(status__in=OPEN_ITEM_STATES):
        ts.cancel_task(item, actor=actor, reason=f"Project dibatalkan: {note}")
    before = snapshot(project)
    project.status = ProjectStatus.DIBATALKAN
    project.closed_at = timezone.now()
    project.closed_by = actor
    project.close_note = note
    project.save(update_fields=["status", "closed_at", "closed_by", "close_note", "updated_at"])
    _audit(project, before, actor=actor, reason=note, action=AuditAction.CANCEL)
    return project


# --- Task ---------------------------------------------------------------------------------


def _pick_clinic(actor, project: Project, clinic, user_ids):
    """Cabang eksplisit > cabang project > cabang pertama actor yang beranggotakan semua penerima."""
    if clinic is not None:
        return clinic
    if project.clinic_id:
        return project.clinic
    clinics = list(user_clinic_queryset(actor).order_by("pk"))
    if not clinics:
        raise ValidationError("Anda tidak terdaftar di cabang mana pun.")
    for candidate in clinics:
        members = User.objects.filter(is_active=True).filter(
            clinic_member_q(candidate, include_owners=True), pk__in=user_ids)
        if members.distinct().count() == len(user_ids):
            return candidate
    return clinics[0]


@transaction.atomic
def add_task(
    project: Project, *, actor, title: str, description: str = "", user_ids,
    mode: str = TaskAssignmentMode.INDIVIDUAL, due_at=None, priority: str = Priority.SEDANG, clinic=None,
) -> ActionItem:
    from core import task_services as ts

    _assert(can_manage_tasks(actor, project), "Anda tidak dapat mengatur task project ini.")
    _assert_active(project)
    try:
        ids = list(dict.fromkeys(int(i) for i in (user_ids or [])))
    except (TypeError, ValueError):
        raise ValidationError("Penerima tidak dikenali.")
    if not ids:
        raise ValidationError("Pilih minimal satu penerima.")
    if mode not in dict(TaskAssignmentMode.choices):
        raise ValidationError("Mode penyelesaian tidak dikenali.")
    if priority not in dict(Priority.choices):
        raise ValidationError("Prioritas tidak dikenali.")
    if not (title or "").strip():
        raise ValidationError("Judul task wajib diisi.")
    clinic = _pick_clinic(actor, project, clinic, ids)
    valid = User.objects.filter(is_active=True).filter(
        clinic_member_q(clinic, include_owners=True), pk__in=ids).distinct().count()
    if valid != len(ids):
        raise ValidationError("Semua penerima harus pengguna aktif di cabang task.")
    return ts.create_task(
        clinic=clinic,
        actor=actor,
        title=title,
        audience_type=TaskAudienceType.USER if len(ids) == 1 else TaskAudienceType.USERS,
        user_ids=ids,
        mode=mode,
        description=description or "",
        priority=priority,
        due_at=due_at,
        source_type=SOURCE_TYPE,
        source_id=project.pk,
        source_label=f"Project: {project.name}"[:120],
        include_owners=True,  # Owner dapat menerima task project di cabang mana pun
    )


@transaction.atomic
def reopen_assignment(assignment: TaskAssignment, *, actor, note: str) -> TaskAssignment:
    """Pengatur membatalkan status selesai satu penerima, dengan catatan revisi."""
    from core.task_services import _notify_task

    item = assignment.action_item
    project = project_for_item(item)
    if project is None:
        raise ValidationError("Ini bukan task project.")
    _assert(can_manage_tasks(actor, project), "Anda tidak dapat mengatur task project ini.")
    _assert_active(project)
    if item.status == ActionItemStatus.BATAL:
        raise ValidationError("Task ini sudah dibatalkan.")
    if assignment.status != TaskAssignmentStatus.CONFIRMED:
        raise ValidationError("Hanya task yang sudah selesai yang dapat dikembalikan untuk revisi.")
    note = (note or "").strip()
    if not note:
        raise ValidationError("Tulis catatan revisi.")
    assignment.status = TaskAssignmentStatus.REVISION_REQUIRED
    assignment.revision_note = note
    assignment.reviewer = actor
    assignment.confirmed_at = None
    assignment.save(update_fields=["status", "revision_note", "reviewer", "confirmed_at", "updated_at"])
    TaskEvent.objects.create(
        action_item=item, assignment=assignment, event_type=TaskEventType.REVISION_REQUESTED, actor=actor, note=note,
    )
    if item.status == ActionItemStatus.SELESAI:
        item.status = ActionItemStatus.DIKERJAKAN
        item.save(update_fields=["status", "updated_at"])
    log_event(action=AuditAction.UPDATE, entity_type="actionitem", entity_id=item.pk,
              entity_label=f"Batal selesai: {item.title}"[:200], actor=actor, reason=note,
              after={"assignment": assignment.pk, "status": assignment.status})
    _notify_task([assignment.assignee], actor=actor, item=item, type_code="TASK_REVISION",
                 title=f"Perlu revisi: {item.title}", body=f"{actor}: {note[:250]}", to_staff=True)
    return assignment


@transaction.atomic
def cancel_project_task(item: ActionItem, *, actor, reason: str) -> ActionItem:
    from core import task_services as ts

    if project_for_item(item) is None:
        raise ValidationError("Ini bukan task project.")
    return ts.cancel_task(item, actor=actor, reason=reason)


def _project_managers(project: Project) -> list[User]:
    """Project leader, co-leader, dan pembuat (tanpa duplikat)."""
    people = {project.leader_id: project.leader}
    for u in project.co_leaders.all():
        people.setdefault(u.pk, u)
    people.setdefault(project.created_by_id, project.created_by)
    return list(people.values())


OPEN_ASSIGNMENT_STATES = (
    TaskAssignmentStatus.OPEN,
    TaskAssignmentStatus.IN_PROGRESS,
    TaskAssignmentStatus.REVISION_REQUIRED,
)


@transaction.atomic
def decline_assignment(assignment: TaskAssignment, *, actor, reason: str) -> TaskAssignment:
    """Owner menolak task project yang ditugaskan kepadanya; pengatur project diberi tahu."""
    from core.task_services import _finish_item_if_all_confirmed

    _assert(assignment.assignee_id == getattr(actor, "pk", None) and is_owner_only(actor),
            "Hanya Owner penerima task yang dapat menolak task ini.")
    item = assignment.action_item
    project = project_for_item(item)
    if project is None:
        raise ValidationError("Ini bukan task project.")
    if item.status not in OPEN_ITEM_STATES or assignment.status not in OPEN_ASSIGNMENT_STATES:
        raise ValidationError("Task ini sudah selesai atau dibatalkan, tidak dapat ditolak.")
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("Tulis alasan menolak.")
    was_claimer = item.assignment_mode == TaskAssignmentMode.BERSAMA and assignment.claimed_by_id == assignment.assignee_id
    assignment.status = TaskAssignmentStatus.CANCELLED
    assignment.save(update_fields=["status", "updated_at"])
    if was_claimer:
        TaskAssignment.objects.filter(action_item=item).update(claimed_by=None)
        assignment.claimed_by = None
    TaskEvent.objects.create(
        action_item=item, assignment=assignment, event_type=TaskEventType.CANCELLED, actor=actor,
        note=f"Ditolak: {reason}", metadata={"ditolak": True},
    )
    log_event(action=AuditAction.UPDATE, entity_type="actionitem", entity_id=item.pk,
              entity_label=f"Task ditolak: {item.title}"[:200], actor=actor, reason=reason,
              after={"assignment": assignment.pk, "status": assignment.status, "ditolak": True})
    _finish_item_if_all_confirmed(item, actor)  # penerima lain bisa saja sudah selesai semua
    people = {u.pk: u for u in _project_managers(project)}
    for u in User.objects.filter(is_active=True, user_roles__role=Role.AOM).distinct():
        people.setdefault(u.pk, u)
    for person in people.values():
        if person.pk == actor.pk:
            continue
        notify_user(
            person,
            type_code="PROJECT_TASK_DECLINED",
            title=f"Task ditolak: {item.title}",
            body=f"{actor}: {reason}",
            entity_ref=f"actionitem#{item.pk}:ditolak#{assignment.pk}",
            url_name="projects:task_detail",
            url_args=[project.pk, item.pk],
        )
    return assignment


def my_project_assignments(user) -> list[dict]:
    """Task project yang masih harus dikerjakan `user` (baris `core.task_services.my_task_row`), untuk kartu Owner."""
    from core.task_services import my_tasks

    return [
        r for r in my_tasks(user)
        if r["assignment"] is not None and r["item"].source_type == SOURCE_TYPE
        and r["assignment"].status in OPEN_ASSIGNMENT_STATES
    ]


def notify_task_done(item: ActionItem, *, actor) -> None:
    """Kabari leader, co-leader, dan pembuat project (bukan pelaku) bahwa satu penerima menyelesaikan task."""
    project = project_for_item(item)
    if project is None:
        return
    for person in _project_managers(project):
        if person.pk == actor.pk:
            continue
        notify_user(
            person,
            type_code="PROJECT_TASK_DONE",
            title=f"Task project selesai: {item.title}",
            body=f"{actor} · Project {project.name}",
            entity_ref=f"actionitem#{item.pk}",
            url_name="projects:task_detail",
            url_args=[project.pk, item.pk],
        )
