"""Service issue: penomoran, SLA, assignment, transisi status, penutupan (PRD 8.7–8.9)."""
from __future__ import annotations

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from audit.models import AuditAction
from audit.services import log_create, log_event, log_update, snapshot
from core.locking import assert_current_version
from core.models import ClinicConfig, Priority

from .models import (
    Issue,
    IssueAssignment,
    IssueStatus,
    IssueType,
    IssueUpdate,
    NUMBER_PREFIX,
    OPEN_STATUSES,
    REASON_REQUIRED_STATUSES,
    WORKFLOWS,
)

RESOLUTION_REQUIRED_TYPES = {IssueType.KOMPLAIN, IssueType.KERUSAKAN}


def generate_number(clinic, issue_type: str, when=None) -> str:
    """Nomor mudah dibaca: DMG-20260911-004 (PRD 12.2).

    Urutan dihitung lintas cabang karena nomor unik di seluruh aplikasi. Sebelumnya dihitung per
    cabang, sehingga catatan kedua cabang pada hari yang sama bisa mendapat nomor yang sama dan
    gagal tersimpan (ditemukan 3 Okt 2026). Cabang tampil terpisah di halaman, tidak di nomor.
    """
    when = when or timezone.localtime(timezone.now())
    prefix = NUMBER_PREFIX[issue_type]
    day_part = when.strftime("%Y%m%d")
    stem = f"{prefix}-{day_part}-"
    last = (
        Issue.objects.filter(number__startswith=stem)
        .aggregate(m=Max("number"))["m"]
    )
    seq = int(last.split("-")[-1]) + 1 if last else 1
    return f"{stem}{seq:03d}"


def sla_targets(clinic, severity: str) -> tuple[timedelta, timedelta]:
    assign_h = float(ClinicConfig.get(clinic, f"sla.{severity}.assign_hours", 24))
    resolve_h = float(ClinicConfig.get(clinic, f"sla.{severity}.resolve_hours", 72))
    return timedelta(hours=assign_h), timedelta(hours=resolve_h)


@transaction.atomic
def create_issue(
    *,
    clinic,
    issue_type: str,
    title: str,
    user,
    description: str = "",
    severity: str = Priority.SEDANG,
    category: str = "",
    is_restricted: bool = False,
    is_anonymous: bool = False,
    **extra,
) -> Issue:
    title = (title or "").strip()
    if not title:
        raise ValidationError("Ringkasan/judul wajib diisi.")
    if issue_type not in dict(IssueType.choices):
        raise ValidationError("Tipe catatan tidak dikenali.")

    now = timezone.now()
    local_now = timezone.localtime(now)
    assign_delta, resolve_delta = sla_targets(clinic, severity)
    allowed = {f.name for f in Issue._meta.fields}
    payload = {k: v for k, v in extra.items() if k in allowed and v not in (None, "")}

    fields = dict(
        clinic=clinic,
        issue_type=issue_type,
        title=title,
        description=(description or "").strip(),
        severity=severity,
        category=(category or "").strip(),
        is_restricted=bool(is_restricted),
        is_anonymous=bool(is_anonymous),
        assign_due_at=now + assign_delta,
        due_at=now + resolve_delta,
        created_by=user,
        **payload,
    )
    for attempt in range(5):
        try:
            # Savepoint: bila dua orang menyimpan bersamaan dan nomornya bentrok, coba nomor berikutnya.
            with transaction.atomic():
                issue = Issue.objects.create(number=generate_number(clinic, issue_type, local_now), **fields)
            break
        except IntegrityError:
            if attempt == 4:
                raise
    IssueUpdate.objects.create(
        issue=issue, author=user, status=IssueStatus.BARU, note="Catatan dibuat."
    )
    log_create(issue, actor=user, label=issue.number)

    from notifications.services import notify_leaders, notify_role

    # Direktur Operasional selalu diberi tahu, dari cabang mana pun; Owner untuk yang kritis.
    notify_leaders(
        owners=severity == Priority.KRITIS,
        type_code="ISSUE_CRITICAL" if severity == Priority.KRITIS else "ISSUE_NEW",
        title=f"{'KRITIS: ' if severity == Priority.KRITIS else ''}{issue.get_issue_type_display()} "
              f"{clinic.name}: {issue.number}",
        body=f"{title} · dicatat {user}" if not is_anonymous else title,
        entity_ref=f"issue#{issue.pk}",
        url_name="issues:detail",
        url_args=[issue.pk],
    )
    if severity == Priority.KRITIS:
        notify_role(
            clinic,
            "SUPERVISOR",
            type_code="ISSUE_CRITICAL",
            title=f"KRITIS: {issue.number}",
            body=title,
            entity_ref=f"issue#{issue.pk}",
            url_name="issues:detail",
            url_args=[issue.pk],
        )
    else:
        notify_role(
            clinic,
            "SUPERVISOR",
            type_code="ISSUE_NEW",
            title=f"{issue.get_issue_type_display()} baru: {issue.number}",
            body=title,
            entity_ref=f"issue#{issue.pk}",
            url_name="issues:detail",
            url_args=[issue.pk],
        )
    return issue


@transaction.atomic
def assign_issue(issue: Issue, *, supervisor, assignee, due_at=None, note: str = "") -> Issue:
    from core.permissions import is_clinic_member

    if not is_clinic_member(assignee, issue.clinic):
        raise ValidationError("Penanggung jawab harus berasal dari cabang catatan.")
    before = snapshot(issue)
    IssueAssignment.objects.filter(issue=issue, active=True).update(active=False)
    assignment = IssueAssignment.objects.create(
        issue=issue, assignee=assignee, assigned_by=supervisor, due_at=due_at, active=True
    )
    if due_at:
        issue.due_at = due_at

    target_status = (
        IssueStatus.DITUGASKAN
        if IssueStatus.DITUGASKAN in issue.allowed_next_statuses()
        or issue.status in {IssueStatus.DITINJAU, IssueStatus.DITRIASE}
        else issue.status
    )
    if target_status != issue.status:
        IssueUpdate.objects.create(
            issue=issue,
            author=supervisor,
            from_status=issue.status,
            status=target_status,
            note=note or f"Ditugaskan kepada {assignee}.",
        )
        issue.status = target_status
    else:
        IssueUpdate.objects.create(
            issue=issue, author=supervisor, status=issue.status, note=f"Ditugaskan kepada {assignee}."
        )
    issue.version += 1
    issue.save()
    log_update(issue, before, actor=supervisor, label=issue.number)

    from notifications.services import notify_user

    notify_user(
        assignee,
        type_code="ISSUE_ASSIGNED",
        title=f"Ditugaskan: {issue.number}",
        body=issue.title,
        entity_ref=f"issue#{issue.pk}",
        url_name="issues:detail",
        url_args=[issue.pk],
    )
    return issue


@transaction.atomic
def change_status(
    issue: Issue,
    *,
    user,
    to_status: str,
    note: str = "",
    resolution_summary: str = "",
    reason: str = "",
    expected_version: int | None = None,
) -> Issue:
    assert_current_version(issue, expected_version)

    allowed = WORKFLOWS.get(issue.issue_type, {}).get(issue.status, set())
    if to_status not in allowed:
        raise ValidationError(
            f"Perubahan status dari {issue.get_status_display()} ke status tersebut tidak diizinkan."
        )

    if to_status in REASON_REQUIRED_STATUSES and not (reason.strip() or note.strip()):
        raise ValidationError("Alasan wajib diisi untuk menolak atau menutup catatan.")

    if to_status == IssueStatus.SELESAI and issue.issue_type in RESOLUTION_REQUIRED_TYPES:
        summary = resolution_summary.strip() or issue.resolution_summary
        if not summary:
            raise ValidationError("Ringkasan penyelesaian wajib diisi sebelum menandai selesai.")
        issue.resolution_summary = summary

    if to_status == IssueStatus.DITUTUP and issue.issue_type in RESOLUTION_REQUIRED_TYPES:
        if not issue.resolution_summary.strip():
            raise ValidationError("Ringkasan penyelesaian wajib diisi sebelum penutupan.")

    before = snapshot(issue)
    from_status = issue.status
    issue.status = to_status
    if to_status in REASON_REQUIRED_STATUSES:
        issue.closed_reason = (reason or note).strip()
    if to_status == IssueStatus.DITUTUP:
        issue.closed_at = timezone.now()
    if to_status == IssueStatus.DIVERIFIKASI:
        issue.verified_by = user
        issue.verified_at = timezone.now()
    issue.version += 1
    issue.save()

    IssueUpdate.objects.create(
        issue=issue, author=user, from_status=from_status, status=to_status, note=note.strip()
    )
    action = {
        IssueStatus.DITUTUP: AuditAction.CLOSE,
        IssueStatus.DIVERIFIKASI: AuditAction.VERIFY,
    }.get(to_status, AuditAction.UPDATE)
    log_update(issue, before, actor=user, reason=reason or note, action=action, label=issue.number)
    return issue


@transaction.atomic
def add_update(issue: Issue, *, user, note: str) -> IssueUpdate:
    note = (note or "").strip()
    if not note:
        raise ValidationError("Catatan tidak boleh kosong.")
    update = IssueUpdate.objects.create(issue=issue, author=user, status=issue.status, note=note)
    log_event(
        action=AuditAction.UPDATE,
        entity_type="issueupdate",
        entity_id=update.pk,
        entity_label=issue.number,
        actor=user,
        after={"note": note},
    )
    return update


@transaction.atomic
def record_repair(
    issue: Issue,
    *,
    user,
    repair_action: str,
    vendor: str = "",
    cost: int | None = None,
    repaired_at=None,
) -> Issue:
    if issue.issue_type != IssueType.KERUSAKAN:
        raise ValidationError("Perbaikan hanya berlaku untuk laporan kerusakan.")
    if not repair_action.strip():
        raise ValidationError("Tindakan perbaikan wajib diisi.")
    before = snapshot(issue)
    issue.repair_action = repair_action.strip()
    issue.repair_vendor = vendor.strip()
    issue.repair_cost = cost
    issue.repaired_at = repaired_at or timezone.now()
    issue.resolution_summary = issue.resolution_summary or repair_action.strip()
    issue.version += 1
    issue.save()
    log_update(issue, before, actor=user, label=issue.number)
    return issue


@transaction.atomic
def mark_asset_do_not_use(asset, *, supervisor, reason: str):
    if not reason.strip():
        raise ValidationError("Alasan wajib diisi untuk menandai aset 'Jangan digunakan'.")
    before = snapshot(asset)
    asset.do_not_use = True
    asset.do_not_use_reason = reason.strip()
    asset.save()
    log_update(asset, before, actor=supervisor, reason=reason, action=AuditAction.OVERRIDE)
    return asset


@transaction.atomic
def mark_duplicate(issue: Issue, *, user, original: Issue, reason: str = "") -> Issue:
    if original.pk == issue.pk:
        raise ValidationError("Catatan tidak dapat menjadi duplikat dirinya sendiri.")
    before = snapshot(issue)
    issue.duplicate_of = original
    issue.version += 1
    issue.save()
    IssueUpdate.objects.create(
        issue=issue, author=user, status=issue.status, note=f"Ditandai duplikat dari {original.number}. {reason}".strip()
    )
    log_update(issue, before, actor=user, reason=reason, label=issue.number)
    return issue


def issue_counters(clinic) -> dict:
    qs = Issue.objects.filter(clinic=clinic)
    now = timezone.now()
    open_qs = qs.filter(status__in=OPEN_STATUSES)
    return {
        "komplain_open": open_qs.filter(issue_type=IssueType.KOMPLAIN).count(),
        "masukan_open": open_qs.filter(issue_type=IssueType.MASUKAN).count(),
        "kerusakan_open": open_qs.filter(issue_type=IssueType.KERUSAKAN).count(),
        "kritis_open": open_qs.filter(severity=Priority.KRITIS).count(),
        "overdue": open_qs.filter(due_at__lt=now).count(),
        "unassigned": open_qs.filter(assignments__isnull=True).count(),
    }
