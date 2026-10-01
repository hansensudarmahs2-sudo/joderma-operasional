"""Domain service untuk task dan delegasi AOM/PIC."""
from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.models import PicAssignment, Role, User
from notifications.services import notify_user

from .models import (
    ActionItem,
    ActionItemStatus,
    Priority,
    TaskAssignment,
    TaskAssignmentMode,
    TaskAssignmentStatus,
    TaskAudienceSnapshot,
    TaskAudienceType,
    TaskEvent,
    TaskEventType,
)
from .permissions import can_access_clinic, is_aom, is_pic


def _recipient_payload(user: User) -> dict:
    return {"id": user.pk, "username": user.username, "display_name": str(user)}


def resolve_task_recipients(
    *,
    clinic,
    audience_type: str,
    user_ids=None,
    role: str = "",
    pic_function: str = "",
) -> list[User]:
    qs = User.objects.filter(is_active=True)
    if audience_type == TaskAudienceType.USER:
        ids = list(user_ids or [])
        if len(ids) != 1:
            raise ValidationError("Target satu user membutuhkan tepat satu penerima.")
        qs = qs.filter(pk=ids[0], user_roles__clinic=clinic)
    elif audience_type == TaskAudienceType.USERS:
        ids = list(user_ids or [])
        if not ids:
            raise ValidationError("Target beberapa user membutuhkan minimal satu penerima.")
        qs = qs.filter(pk__in=ids, user_roles__clinic=clinic)
    elif audience_type == TaskAudienceType.PIC_FUNCTION:
        if not pic_function:
            raise ValidationError("Fungsi PIC wajib dipilih.")
        ids = PicAssignment.objects.filter(
            clinic=clinic, function=pic_function, active=True
        ).values_list("user_id", flat=True)
        qs = qs.filter(pk__in=ids)
    elif audience_type == TaskAudienceType.ROLE:
        if not role:
            raise ValidationError("Role/tier wajib dipilih.")
        qs = qs.filter(user_roles__clinic=clinic, user_roles__role=role)
    elif audience_type == TaskAudienceType.CLINIC:
        qs = qs.filter(user_roles__clinic=clinic)
    else:
        raise ValidationError("Target penerima tidak dikenali.")

    recipients = list(qs.distinct().order_by("username"))
    if not recipients:
        raise ValidationError("Task tidak dapat dikirim karena tidak ada penerima.")
    return recipients


def _criteria(audience_type: str, user_ids, role: str, pic_function: str) -> dict:
    return {
        "audience_type": audience_type,
        "user_ids": list(user_ids or []),
        "role": role,
        "pic_function": pic_function,
    }


@transaction.atomic
def send_task(
    action_item: ActionItem,
    *,
    actor,
    audience_type: str,
    user_ids=None,
    role: str = "",
    pic_function: str = "",
    mode: str = TaskAssignmentMode.INDIVIDUAL,
) -> list[TaskAssignment]:
    if not can_access_clinic(actor, action_item.clinic):
        raise PermissionDenied("Anda tidak memiliki akses ke cabang task ini.")
    if mode not in dict(TaskAssignmentMode.choices):
        raise ValidationError("Mode assignment tidak dikenali.")

    recipients = resolve_task_recipients(
        clinic=action_item.clinic,
        audience_type=audience_type,
        user_ids=user_ids,
        role=role,
        pic_function=pic_function,
    )
    action_item.assignment_mode = mode
    if action_item.status == ActionItemStatus.BATAL:
        raise ValidationError("Task batal tidak dapat dikirim ulang.")
    action_item.save(update_fields=["assignment_mode", "updated_at"])

    TaskAudienceSnapshot.objects.update_or_create(
        action_item=action_item,
        defaults={
            "audience_type": audience_type,
            "criteria": _criteria(audience_type, user_ids, role, pic_function),
            "recipients": [_recipient_payload(user) for user in recipients],
            "created_by": actor,
        },
    )

    assignments = []
    for recipient in recipients:
        assignment, created = TaskAssignment.objects.get_or_create(
            action_item=action_item,
            assignee=recipient,
            defaults={"status": TaskAssignmentStatus.OPEN},
        )
        assignments.append(assignment)
        if created:
            TaskEvent.objects.create(
                action_item=action_item,
                assignment=assignment,
                event_type=TaskEventType.SENT,
                actor=actor,
                metadata={"assignee": recipient.username, "mode": mode},
            )
            notify_user(
                recipient,
                type_code="TASK_ASSIGNED",
                title=f"Task baru: {action_item.title}",
                entity_ref=f"actionitem#{action_item.pk}",
                url_name="core:action_items",
            )
    return assignments


@transaction.atomic
def create_task(
    *,
    clinic,
    actor,
    title: str,
    audience_type: str,
    user_ids=None,
    role: str = "",
    pic_function: str = "",
    mode: str = TaskAssignmentMode.INDIVIDUAL,
    description: str = "",
    priority: str = Priority.SEDANG,
    due_at=None,
    source_type: str = "manual",
    source_id=None,
    source_label: str = "",
) -> ActionItem:
    if not title.strip():
        raise ValidationError("Judul task wajib diisi.")
    item = ActionItem.objects.create(
        clinic=clinic,
        title=title.strip(),
        description=description.strip(),
        source_type=source_type or "manual",
        source_id=source_id,
        source_label=source_label,
        created_by=actor,
        priority=priority,
        due_at=due_at,
        assignment_mode=mode,
    )
    assignments = send_task(
        item,
        actor=actor,
        audience_type=audience_type,
        user_ids=user_ids,
        role=role,
        pic_function=pic_function,
        mode=mode,
    )
    if len(assignments) == 1:
        item.owner = assignments[0].assignee
        item.save(update_fields=["owner", "updated_at"])
    return item


@transaction.atomic
def claim_shared_task(assignment: TaskAssignment, *, user) -> TaskAssignment:
    item = assignment.action_item
    if item.assignment_mode != TaskAssignmentMode.BERSAMA:
        raise ValidationError("Task individual tidak perlu diambil.")
    if assignment.assignee_id != user.pk:
        raise PermissionDenied("Anda bukan penerima task ini.")
    if TaskAssignment.objects.filter(
        action_item=item, claimed_by__isnull=False
    ).exclude(claimed_by=user).exists():
        raise ValidationError("Task bersama sudah diambil penerima lain.")
    TaskAssignment.objects.filter(action_item=item).update(claimed_by=user)
    assignment.refresh_from_db()
    assignment.status = TaskAssignmentStatus.IN_PROGRESS
    assignment.save(update_fields=["status", "updated_at"])
    TaskEvent.objects.create(
        action_item=item,
        assignment=assignment,
        event_type=TaskEventType.CLAIMED,
        actor=user,
    )
    return assignment


@transaction.atomic
def submit_assignment(assignment: TaskAssignment, *, user, note: str = "") -> TaskAssignment:
    if assignment.assignee_id != user.pk and assignment.claimed_by_id != user.pk:
        raise PermissionDenied("Anda bukan penerima task ini.")
    if assignment.status in {TaskAssignmentStatus.CONFIRMED, TaskAssignmentStatus.CANCELLED}:
        raise ValidationError("Task ini sudah selesai atau dibatalkan.")
    assignment.status = TaskAssignmentStatus.SUBMITTED
    assignment.submitted_at = timezone.now()
    assignment.save(update_fields=["status", "submitted_at", "updated_at"])
    TaskEvent.objects.create(
        action_item=assignment.action_item,
        assignment=assignment,
        event_type=TaskEventType.SUBMITTED,
        actor=user,
        note=note.strip(),
    )
    return assignment


def can_review_assignment(assignment: TaskAssignment, reviewer) -> bool:
    """Predikat publik: siapa yang boleh konfirmasi/minta revisi assignment ini.

    Dipakai juga di view layer (dashboard, action items) untuk menampilkan
    tombol 'Konfirmasi selesai'/'Minta revisi' hanya kepada reviewer yang
    berwenang — server-side tetap memvalidasi ulang lewat
    `confirm_assignment`/`request_revision`, UI hanya cerminan (PRD 6).
    """
    item = assignment.action_item
    if reviewer.pk in {assignment.assignee_id, assignment.claimed_by_id}:
        return False
    if item.created_by_id == reviewer.pk:
        return True
    if is_aom(reviewer):
        return True
    return bool(is_pic(reviewer) and item.created_by and is_pic(item.created_by))


# Alias historis (nama privat sebelumnya) untuk kompatibilitas pemanggil lama.
_can_review_task = can_review_assignment


@transaction.atomic
def confirm_assignment(assignment: TaskAssignment, *, reviewer, note: str = "") -> TaskAssignment:
    if assignment.status != TaskAssignmentStatus.SUBMITTED:
        raise ValidationError("Task harus diajukan selesai sebelum dikonfirmasi.")
    if not _can_review_task(assignment, reviewer):
        raise PermissionDenied("Penerima task tidak dapat mengonfirmasi task sendiri.")
    assignment.status = TaskAssignmentStatus.CONFIRMED
    assignment.confirmed_at = timezone.now()
    assignment.reviewer = reviewer
    assignment.save(update_fields=["status", "confirmed_at", "reviewer", "updated_at"])
    TaskEvent.objects.create(
        action_item=assignment.action_item,
        assignment=assignment,
        event_type=TaskEventType.CONFIRMED,
        actor=reviewer,
        note=note.strip(),
    )
    if not assignment.action_item.task_assignments.exclude(
        status=TaskAssignmentStatus.CONFIRMED
    ).exists():
        item = assignment.action_item
        item.status = ActionItemStatus.SELESAI
        item.save(update_fields=["status", "updated_at"])
    return assignment


@transaction.atomic
def request_revision(assignment: TaskAssignment, *, reviewer, note: str) -> TaskAssignment:
    if not note.strip():
        raise ValidationError("Catatan revisi wajib diisi.")
    if not _can_review_task(assignment, reviewer):
        raise PermissionDenied("Penerima task tidak dapat meminta revisi task sendiri.")
    assignment.status = TaskAssignmentStatus.REVISION_REQUIRED
    assignment.revision_note = note.strip()
    assignment.reviewer = reviewer
    assignment.save(update_fields=["status", "revision_note", "reviewer", "updated_at"])
    TaskEvent.objects.create(
        action_item=assignment.action_item,
        assignment=assignment,
        event_type=TaskEventType.REVISION_REQUESTED,
        actor=reviewer,
        note=note.strip(),
    )
    return assignment


@transaction.atomic
def cancel_assignment(assignment: TaskAssignment, *, actor, reason: str) -> TaskAssignment:
    if not reason.strip():
        raise ValidationError("Alasan pembatalan wajib diisi.")
    if assignment.action_item.created_by_id != actor.pk and not is_aom(actor):
        raise PermissionDenied("Hanya pemberi tugas atau Direktur Operasional yang dapat membatalkan task.")
    assignment.status = TaskAssignmentStatus.CANCELLED
    assignment.save(update_fields=["status", "updated_at"])
    TaskEvent.objects.create(
        action_item=assignment.action_item,
        assignment=assignment,
        event_type=TaskEventType.CANCELLED,
        actor=actor,
        note=reason.strip(),
    )
    return assignment


# --- Pengelolaan task oleh pemberi tugas / Direktur (halaman detail task) ------

OPEN_ASSIGNMENT_STATES = {
    TaskAssignmentStatus.OPEN,
    TaskAssignmentStatus.IN_PROGRESS,
    TaskAssignmentStatus.REVISION_REQUIRED,
    TaskAssignmentStatus.SUBMITTED,
}


def can_manage_task(item: ActionItem, user) -> bool:
    """Pemberi tugas atau Direktur Operasional boleh mengubah, menutup, dan membatalkan task."""
    if not user or not user.is_authenticated or not can_access_clinic(user, item.clinic):
        return False
    return item.created_by_id == user.pk or is_aom(user)


def _assert_manage(item: ActionItem, user) -> None:
    if not can_manage_task(item, user):
        raise PermissionDenied("Hanya pemberi tugas atau Direktur Operasional yang dapat mengubah task ini.")


def _assert_open(item: ActionItem) -> None:
    if item.status in (ActionItemStatus.SELESAI, ActionItemStatus.BATAL):
        raise ValidationError("Task ini sudah selesai atau batal.")


@transaction.atomic
def update_task(item: ActionItem, *, actor, status: str, priority: str, due_at, progress_note: str) -> ActionItem:
    """Ubah status berjalan (Baru/Dikerjakan), prioritas, target, dan catatan progres."""
    from audit.services import log_update, snapshot

    _assert_manage(item, actor)
    _assert_open(item)
    if status not in (ActionItemStatus.BARU, ActionItemStatus.DIKERJAKAN):
        raise ValidationError("Gunakan tombol Tandai selesai atau Batalkan task untuk menutup task.")
    if priority not in dict(Priority.choices):
        raise ValidationError("Prioritas tidak dikenali.")
    before = snapshot(item)
    item.status = status
    item.priority = priority
    item.due_at = due_at
    item.progress_note = (progress_note or "").strip()
    item.save(update_fields=["status", "priority", "due_at", "progress_note", "updated_at"])
    log_update(item, before, actor=actor)
    return item


@transaction.atomic
def close_task(item: ActionItem, *, actor, note: str) -> ActionItem:
    """Pemberi tugas menyatakan task selesai tanpa menunggu penerima mengajukan.

    Penerima yang masih terbuka dikonfirmasi oleh penutup task, supaya task hilang
    dari daftar kerja mereka dan jejaknya tercatat di riwayat.
    """
    from audit.models import AuditAction
    from audit.services import log_update, snapshot

    _assert_manage(item, actor)
    _assert_open(item)
    note = (note or "").strip()
    if not note:
        raise ValidationError("Tuliskan catatan penutupan.")
    now = timezone.now()
    for assignment in item.task_assignments.filter(status__in=OPEN_ASSIGNMENT_STATES):
        assignment.status = TaskAssignmentStatus.CONFIRMED
        assignment.confirmed_at = now
        assignment.reviewer = actor
        assignment.save(update_fields=["status", "confirmed_at", "reviewer", "updated_at"])
        TaskEvent.objects.create(
            action_item=item, assignment=assignment, event_type=TaskEventType.CONFIRMED,
            actor=actor, note=f"Ditutup oleh pemberi tugas: {note}",
        )
    before = snapshot(item)
    item.status = ActionItemStatus.SELESAI
    item.progress_note = note
    item.save(update_fields=["status", "progress_note", "updated_at"])
    log_update(item, before, actor=actor, action=AuditAction.CLOSE, reason=note)
    return item


@transaction.atomic
def cancel_task(item: ActionItem, *, actor, reason: str) -> ActionItem:
    from audit.models import AuditAction
    from audit.services import log_update, snapshot

    _assert_manage(item, actor)
    _assert_open(item)
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("Alasan pembatalan wajib diisi.")
    for assignment in item.task_assignments.filter(status__in=OPEN_ASSIGNMENT_STATES):
        cancel_assignment(assignment, actor=actor, reason=reason)
    before = snapshot(item)
    item.status = ActionItemStatus.BATAL
    item.progress_note = reason
    item.save(update_fields=["status", "progress_note", "updated_at"])
    log_update(item, before, actor=actor, action=AuditAction.CANCEL, reason=reason)
    return item


def add_task_comment(item: ActionItem, *, actor, note: str) -> TaskEvent:
    """Catatan di riwayat task. Boleh ditulis pemberi tugas, Direktur, atau penerima."""
    note = (note or "").strip()
    if not note:
        raise ValidationError("Catatan kosong.")
    is_recipient = item.task_assignments.filter(assignee=actor).exists()
    if not (can_manage_task(item, actor) or is_recipient):
        raise PermissionDenied("Anda tidak terlibat di task ini.")
    return TaskEvent.objects.create(action_item=item, event_type=TaskEventType.COMMENT, actor=actor, note=note)
