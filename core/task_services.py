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
from .permissions import can_access_clinic, is_aom, is_owner, is_pic


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
    _notify_reviewers(assignment, actor=user, note=note)
    return assignment


def reviewers_for(item: ActionItem) -> list[User]:
    """Orang yang diberi tahu saat task diajukan selesai."""
    if item.reviewed_by_dirut:
        return list(User.objects.filter(is_active=True, user_roles__role=Role.OWNER).distinct())
    people = list(User.objects.filter(is_active=True, user_roles__role=Role.AOM).distinct())
    if item.created_by and item.created_by.is_active and item.created_by not in people:
        people.append(item.created_by)
    return people


def _notify_reviewers(assignment: TaskAssignment, *, actor, note: str) -> None:
    item = assignment.action_item
    url = "direktur:task_detail"
    for person in reviewers_for(item):
        if person.pk in {actor.pk, assignment.assignee_id}:
            continue
        notify_user(
            person,
            type_code="TASK_SUBMITTED",
            title=f"Menunggu verifikasi: {item.title}",
            body=f"{actor} mengajukan selesai. {note.strip()[:200]}".strip(),
            entity_ref=f"actionitem#{item.pk}",
            url_name=url,
            url_args=[item.pk],
        )


@transaction.atomic
def report_progress(assignment: TaskAssignment, *, user, note: str) -> TaskEvent:
    """PIC melaporkan kemajuan (teks; foto ditambahkan view). Status penerima menjadi Dikerjakan."""
    if assignment.assignee_id != user.pk and assignment.claimed_by_id != user.pk:
        raise PermissionDenied("Anda bukan penerima task ini.")
    if assignment.status not in (
        TaskAssignmentStatus.OPEN, TaskAssignmentStatus.IN_PROGRESS, TaskAssignmentStatus.REVISION_REQUIRED
    ):
        raise ValidationError("Task ini sudah diajukan selesai, dikonfirmasi, atau dibatalkan.")
    note = (note or "").strip()
    if not note:
        raise ValidationError("Tulis kemajuannya.")
    if assignment.status == TaskAssignmentStatus.OPEN:
        assignment.status = TaskAssignmentStatus.IN_PROGRESS
        assignment.save(update_fields=["status", "updated_at"])
    return TaskEvent.objects.create(
        action_item=assignment.action_item, assignment=assignment, event_type=TaskEventType.PROGRESS,
        actor=user, note=note,
    )


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
    if item.reviewed_by_dirut:
        # Pekerjaan Direktur Operasional sendiri (atau task yang pemeriksanya ditetapkan Dirut):
        # hanya Direktur Utama / Owner yang memverifikasi.
        return is_owner(reviewer)
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
    notify_user(
        assignment.assignee, type_code="TASK_CONFIRMED", title=f"Dikonfirmasi selesai: {assignment.action_item.title}",
        body=f"oleh {reviewer}" + (f" — {note.strip()[:200]}" if note.strip() else ""),
        entity_ref=f"actionitem#{assignment.action_item_id}", url_name="core:action_items",
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
    notify_user(
        assignment.assignee, type_code="TASK_REVISION", title=f"Perlu revisi: {assignment.action_item.title}",
        body=f"{reviewer}: {note.strip()[:250]}", entity_ref=f"actionitem#{assignment.action_item_id}",
        url_name="core:action_items",
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
def update_task(
    item: ActionItem, *, actor, status: str, priority: str, due_at, progress_note: str, review_by: str | None = None,
) -> ActionItem:
    """Ubah status berjalan (Baru/Dikerjakan), prioritas, target, catatan progres, dan pemeriksa."""
    from .models import ReviewBy

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
    if review_by is not None:
        if review_by not in dict(ReviewBy.choices):
            raise ValidationError("Pemeriksa tidak dikenali.")
        item.review_by = review_by
    item.save(update_fields=["status", "priority", "due_at", "progress_note", "review_by", "updated_at"])
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
    if item.reviewed_by_dirut:
        raise ValidationError(
            "Task ini diverifikasi Direktur Utama / Owner: penerima mengajukan selesai, lalu Dirut mengonfirmasi."
        )
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
    is_dirut_reviewer = is_owner(actor) and item.reviewed_by_dirut
    if not (can_manage_task(item, actor) or is_recipient or is_dirut_reviewer):
        raise PermissionDenied("Anda tidak terlibat di task ini.")
    return TaskEvent.objects.create(action_item=item, event_type=TaskEventType.COMMENT, actor=actor, note=note)


# --- Tugas saya (halaman Hari Ini) -------------------------------------------------

MY_OPEN_ASSIGNMENT = (
    TaskAssignmentStatus.OPEN,
    TaskAssignmentStatus.IN_PROGRESS,
    TaskAssignmentStatus.REVISION_REQUIRED,
    TaskAssignmentStatus.SUBMITTED,
)


def _my_task_row(item: ActionItem, assignment: TaskAssignment | None, user, now) -> dict:
    shared = item.assignment_mode == TaskAssignmentMode.BERSAMA
    status = assignment.status if assignment else None
    workable = status in (
        TaskAssignmentStatus.OPEN,
        TaskAssignmentStatus.IN_PROGRESS,
        TaskAssignmentStatus.REVISION_REQUIRED,
    )
    local_due = timezone.localtime(item.due_at).date() if item.due_at else None
    return {
        "item": item,
        "assignment": assignment,
        "waiting": status == TaskAssignmentStatus.SUBMITTED,
        "revision": status == TaskAssignmentStatus.REVISION_REQUIRED,
        "overdue": item.is_overdue,
        "due_today": bool(local_due and local_due == timezone.localtime(now).date() and not item.is_overdue),
        "can_claim": bool(assignment and shared and assignment.claimed_by_id is None
                          and status == TaskAssignmentStatus.OPEN),
        "can_submit": bool(assignment and workable and (not shared or assignment.claimed_by_id == user.pk)),
        "last_progress": item.task_events.filter(event_type=TaskEventType.PROGRESS).order_by("-created_at").first(),
        "dirut": item.reviewed_by_dirut,
    }


def my_tasks(user) -> list[dict]:
    """Task yang masih harus dikerjakan pengguna, untuk ditampilkan di Hari Ini.

    - Dibaca dari penerima task (`TaskAssignment`), bukan hanya `ActionItem.owner`: task yang
      dikirim ke beberapa orang atau ke satu peran tidak punya owner tunggal.
    - Semua cabang yang dapat ia akses, dan **tidak** bergantung pada sesi hari operasional:
      tugas tetap tampil walau opening hari itu belum dibuat.
    - Task bersama yang sudah diambil orang lain tidak ditampilkan.
    - Yang sudah diajukan selesai tetap tampil di bawah dengan tanda menunggu konfirmasi.
    """
    from .permissions import user_clinic_queryset

    now = timezone.now()
    open_items = ActionItem.objects.filter(
        clinic__in=user_clinic_queryset(user),
        status__in=[ActionItemStatus.BARU, ActionItemStatus.DIKERJAKAN],
    )
    rows, seen = [], set()
    assignments = (
        TaskAssignment.objects.filter(assignee=user, status__in=MY_OPEN_ASSIGNMENT, action_item__in=open_items)
        .select_related("action_item", "action_item__clinic", "action_item__created_by")
    )
    for a in assignments:
        item = a.action_item
        if item.assignment_mode == TaskAssignmentMode.BERSAMA and a.claimed_by_id not in (None, user.pk):
            continue
        rows.append(_my_task_row(item, a, user, now))
        seen.add(item.pk)
    for item in open_items.filter(owner=user).exclude(pk__in=seen).select_related("clinic", "created_by"):
        if TaskAssignment.objects.filter(action_item=item).exists():
            continue  # sudah dikirim ke orang lain atau sudah dikonfirmasi; bukan tugas terbuka saya
        rows.append(_my_task_row(item, None, user, now))
    import datetime as dt

    far = dt.datetime.max.replace(tzinfo=dt.timezone.utc)
    rows.sort(key=lambda r: (r["waiting"], not r["overdue"], not r["revision"], r["item"].due_at or far,
                             r["item"].created_at))
    return rows
