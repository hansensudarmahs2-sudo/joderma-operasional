"""Service jadwal istirahat: konflik overlap + minimum staffing warning (PRD 8.6, 20.6)."""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from accounts.models import Role, User
from audit.models import AuditAction
from audit.services import log_create, log_update, snapshot
from core.models import ClinicConfig

from .models import BreakSchedule, BreakStatus


def min_staffing(clinic) -> dict[str, int]:
    return {
        Role.FRONT_DESK: int(ClinicConfig.get(clinic, "break.min_active_front_desk")),
        Role.PERAWAT: int(ClinicConfig.get(clinic, "break.min_active_nurse")),
    }


def has_overlap(user, start_at, end_at, exclude_pk=None) -> bool:
    qs = BreakSchedule.objects.filter(user=user, status__in=[BreakStatus.DIJADWALKAN, BreakStatus.BERJALAN])
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return qs.filter(start_at__lt=end_at, end_at__gt=start_at).exists()


def staffing_warnings(clinic, start_at, end_at, exclude_pk=None, extra_away_user=None) -> list[str]:
    """Peringatan bila staf aktif turun di bawah minimum konfigurasi.

    `extra_away_user` adalah orang yang jadwalnya sedang dibuat/diubah dan belum
    tersimpan; tanpa ini, pengecekan minimum staf tidak menghitung dirinya.
    """
    minimums = min_staffing(clinic)
    warnings: list[str] = []
    overlapping = BreakSchedule.objects.filter(
        clinic=clinic,
        status__in=[BreakStatus.DIJADWALKAN, BreakStatus.BERJALAN],
        start_at__lt=end_at,
        end_at__gt=start_at,
    )
    if exclude_pk:
        overlapping = overlapping.exclude(pk=exclude_pk)
    away_ids = set(overlapping.values_list("user_id", flat=True))
    if extra_away_user is not None:
        away_ids.add(extra_away_user.pk)

    for role, minimum in minimums.items():
        if minimum <= 0:
            continue
        role_users = set(
            User.objects.filter(is_active=True, user_roles__role=role).values_list("id", flat=True)
        )
        if not role_users:
            continue
        remaining = len(role_users - away_ids)
        label = dict(Role.choices)[role]
        if remaining < minimum:
            warnings.append(
                f"Hanya {remaining} {label} aktif pada rentang waktu ini (minimum {minimum})."
            )
    return warnings


@transaction.atomic
def create_break(
    clinic,
    *,
    supervisor,
    user,
    date,
    break_type: str,
    start_at,
    end_at,
    location_note: str = "",
    staffing_override_reason: str = "",
) -> tuple[BreakSchedule, list[str]]:
    if end_at <= start_at:
        raise ValidationError("Waktu selesai harus setelah waktu mulai.")
    if has_overlap(user, start_at, end_at):
        raise ValidationError(f"{user} sudah memiliki jadwal yang bertabrakan pada rentang waktu ini.")

    warnings = staffing_warnings(clinic, start_at, end_at, extra_away_user=user)
    if warnings and not staffing_override_reason.strip():
        raise ValidationError(
            " ".join(warnings) + " Isi alasan override bila jadwal ini tetap diperlukan."
        )

    schedule = BreakSchedule.objects.create(
        clinic=clinic,
        user=user,
        date=date,
        break_type=break_type,
        start_at=start_at,
        end_at=end_at,
        location_note=(location_note or "").strip(),
        staffing_override_reason=staffing_override_reason.strip(),
        created_by=supervisor,
    )
    log_create(schedule, actor=supervisor, reason=staffing_override_reason)
    if warnings:
        log_update(
            schedule,
            None,
            actor=supervisor,
            reason=staffing_override_reason,
            action=AuditAction.OVERRIDE,
        )

    from notifications.services import notify_user

    notify_user(
        user,
        type_code="BREAK_SCHEDULED",
        title="Jadwal istirahat baru",
        body=f"{schedule.get_break_type_display()} {start_at:%d/%m %H:%M}-{end_at:%H:%M}",
        entity_ref=f"breakschedule#{schedule.pk}",
        url_name="breaks:list",
    )
    return schedule, warnings


@transaction.atomic
def update_break(
    schedule: BreakSchedule,
    *,
    supervisor,
    start_at=None,
    end_at=None,
    break_type=None,
    location_note=None,
    status=None,
    staffing_override_reason: str = "",
    reason: str = "",
) -> tuple[BreakSchedule, list[str]]:
    before = snapshot(schedule)
    new_start = start_at or schedule.start_at
    new_end = end_at or schedule.end_at
    if new_end <= new_start:
        raise ValidationError("Waktu selesai harus setelah waktu mulai.")
    if has_overlap(schedule.user, new_start, new_end, exclude_pk=schedule.pk):
        raise ValidationError("Jadwal bertabrakan dengan jadwal lain milik orang yang sama.")

    warnings = staffing_warnings(
        schedule.clinic, new_start, new_end, exclude_pk=schedule.pk, extra_away_user=schedule.user
    )
    if warnings and not (staffing_override_reason.strip() or schedule.staffing_override_reason):
        raise ValidationError(" ".join(warnings) + " Isi alasan override untuk melanjutkan.")

    schedule.start_at = new_start
    schedule.end_at = new_end
    if break_type:
        schedule.break_type = break_type
    if location_note is not None:
        schedule.location_note = location_note.strip()
    if status:
        schedule.status = status
    if staffing_override_reason.strip():
        schedule.staffing_override_reason = staffing_override_reason.strip()
    schedule.version += 1
    schedule.save()
    log_update(
        schedule,
        before,
        actor=supervisor,
        reason=reason or staffing_override_reason,
        action=AuditAction.OVERRIDE if warnings else AuditAction.UPDATE,
    )
    return schedule, warnings


@transaction.atomic
def cancel_break(schedule: BreakSchedule, *, supervisor, reason: str) -> BreakSchedule:
    if not reason.strip():
        raise ValidationError("Alasan wajib diisi untuk membatalkan jadwal.")
    before = snapshot(schedule)
    schedule.status = BreakStatus.BATAL
    schedule.version += 1
    schedule.save()
    log_update(schedule, before, actor=supervisor, reason=reason, action=AuditAction.CANCEL)
    return schedule


def upcoming_breaks(clinic, now, minutes: int = 60):
    from datetime import timedelta

    horizon = now + timedelta(minutes=minutes)
    return (
        BreakSchedule.objects.filter(clinic=clinic, status__in=[BreakStatus.DIJADWALKAN, BreakStatus.BERJALAN])
        .filter(Q(start_at__lte=horizon, end_at__gte=now))
        .select_related("user")
        .order_by("start_at")
    )
