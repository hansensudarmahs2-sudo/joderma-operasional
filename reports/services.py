"""Service layer laporan dan masukan (plan bagian 9, 10, 11)."""
from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from audit.models import AuditAction
from audit.services import log_create, log_event, log_update, snapshot
from core.permissions import (
    can_access_clinic,
    can_archive_laporan,
    can_archive_masukan,
    can_create_laporan,
    can_publish_masukan,
    can_view_laporan,
    can_view_masukan,
)

from .models import (
    Laporan,
    LaporanUpdate,
    Masukan,
    MasukanPublication,
    ReportStatus,
    ReportVisibility,
)

REASON_REQUIRED_STATUSES = {ReportStatus.CLOSED}


# --- Laporan ---------------------------------------------------------------


@transaction.atomic
def create_laporan(
    *,
    clinic,
    user,
    title: str,
    description: str = "",
    visibility: str = ReportVisibility.CABANG,
) -> Laporan:
    if not can_create_laporan(user):
        raise PermissionDenied("Anda tidak memiliki izin membuat laporan.")
    if not can_access_clinic(user, clinic):
        raise PermissionDenied("Anda tidak memiliki akses ke cabang ini.")
    title = (title or "").strip()
    if not title:
        raise ValidationError("Ringkasan laporan wajib diisi.")
    if visibility not in dict(ReportVisibility.choices):
        raise ValidationError("Visibilitas laporan tidak dikenali.")

    laporan = Laporan.objects.create(
        clinic=clinic,
        visibility=visibility,
        title=title,
        description=(description or "").strip(),
        created_by=user,
    )
    LaporanUpdate.objects.create(
        laporan=laporan, author=user, status=ReportStatus.OPEN, note="Laporan dibuat."
    )
    log_create(laporan, actor=user, label=f"Laporan#{laporan.pk}")

    # Notifikasi laporan rahasia hanya boleh dikirim ke AOM, tidak boleh
    # membocorkan isi/identitas ke staf lain di cabang yang sama (plan 9.1).
    if visibility == ReportVisibility.RAHASIA_AOM:
        from accounts.models import Role
        from notifications.services import notify_role

        notify_role(
            clinic,
            Role.AOM,
            type_code="REPORT_CONFIDENTIAL_NEW",
            title="Laporan rahasia baru",
            body="Laporan rahasia baru memerlukan tinjauan AOM.",
            entity_ref=f"laporan#{laporan.pk}",
        )
    return laporan


def visible_laporan_queryset(user, clinic):
    """Queryset yang SUDAH dibatasi scope; jangan filter setelah render di view."""
    if not can_access_clinic(user, clinic):
        return Laporan.objects.none()
    qs = Laporan.objects.filter(clinic=clinic).select_related("created_by")
    from core.permissions import Capability, caps, has_admin_full_access, is_aom, is_owner

    if is_aom(user) or is_owner(user) or Capability.REPORT_VIEW_CONFIDENTIAL in caps(user) or has_admin_full_access(user):
        return qs
    from django.db.models import Q

    return qs.filter(
        Q(visibility=ReportVisibility.CABANG) | Q(created_by=user)
    )


@transaction.atomic
def change_laporan_status(
    laporan: Laporan, *, user, to_status: str, note: str = "", reason: str = ""
) -> Laporan:
    if not can_view_laporan(user, laporan):
        raise PermissionDenied("Anda tidak memiliki akses ke laporan ini.")
    allowed = laporan.allowed_next_statuses()
    if to_status not in allowed:
        raise ValidationError("Perubahan status tidak diizinkan dari status saat ini.")
    if to_status in REASON_REQUIRED_STATUSES and not (reason.strip() or note.strip()):
        raise ValidationError("Alasan wajib diisi untuk menutup laporan.")

    before = snapshot(laporan)
    from_status = laporan.status
    laporan.status = to_status
    laporan.version += 1
    laporan.save()
    LaporanUpdate.objects.create(
        laporan=laporan, author=user, from_status=from_status, status=to_status, note=note.strip()
    )
    action = AuditAction.CLOSE if to_status == ReportStatus.CLOSED else AuditAction.UPDATE
    log_update(laporan, before, actor=user, reason=reason or note, action=action, label=f"Laporan#{laporan.pk}")
    return laporan


@transaction.atomic
def archive_laporan(laporan: Laporan, *, user, reason: str) -> Laporan:
    """Arsip = soft-delete: data tidak dihapus, wajib alasan + capability + audit (plan 9.2)."""
    if not can_archive_laporan(user):
        raise PermissionDenied("Anda tidak memiliki izin mengarsipkan laporan.")
    if not can_view_laporan(user, laporan):
        raise PermissionDenied("Anda tidak memiliki akses ke laporan ini.")
    if not reason.strip():
        raise ValidationError("Alasan arsip wajib diisi.")
    if laporan.status == ReportStatus.ARCHIVED:
        raise ValidationError("Laporan ini sudah diarsipkan.")

    before = snapshot(laporan)
    laporan.status = ReportStatus.ARCHIVED
    laporan.archived_at = timezone.now()
    laporan.archived_by = user
    laporan.archive_reason = reason.strip()
    laporan.version += 1
    laporan.save()
    LaporanUpdate.objects.create(
        laporan=laporan, author=user, status=ReportStatus.ARCHIVED, note=reason.strip()
    )
    log_update(
        laporan, before, actor=user, reason=reason, action=AuditAction.ARCHIVE, label=f"Laporan#{laporan.pk}"
    )
    return laporan


def log_confidential_access(laporan: Laporan, *, user, request=None) -> None:
    """Catat akses laporan rahasia agar konsisten dengan pola issues (plan 11)."""
    if laporan.visibility != ReportVisibility.RAHASIA_AOM:
        return
    log_event(
        action=AuditAction.VIEW_RESTRICTED,
        entity_type="laporan",
        entity_id=laporan.pk,
        entity_label=f"Laporan#{laporan.pk}",
        actor=user,
        request=request,
    )


# --- Masukan -----------------------------------------------------------


@transaction.atomic
def create_masukan(*, clinic, user, title: str, description: str = "") -> Masukan:
    if not can_access_clinic(user, clinic):
        raise PermissionDenied("Anda tidak memiliki akses ke cabang ini.")
    title = (title or "").strip()
    if not title:
        raise ValidationError("Ringkasan masukan wajib diisi.")

    masukan = Masukan.objects.create(
        clinic=clinic, title=title, description=(description or "").strip(), created_by=user
    )
    log_create(masukan, actor=user, label=f"Masukan#{masukan.pk}")

    from accounts.models import Role
    from notifications.services import notify_role

    notify_role(
        clinic,
        Role.AOM,
        type_code="MASUKAN_NEW",
        title="Masukan baru",
        body="Masukan baru menunggu tinjauan AOM.",
        entity_ref=f"masukan#{masukan.pk}",
    )
    return masukan


def visible_masukan_queryset(user, clinic):
    """Masukan privat milik user + milik user lain hanya jika AOM/berizin."""
    if not can_access_clinic(user, clinic):
        return Masukan.objects.none()
    qs = Masukan.objects.filter(clinic=clinic).select_related("created_by")
    from core.permissions import Capability, caps, has_admin_full_access, is_aom, is_owner

    if is_aom(user) or is_owner(user) or Capability.REPORT_VIEW_CONFIDENTIAL in caps(user) or has_admin_full_access(user):
        return qs
    return qs.filter(created_by=user)


@transaction.atomic
def publish_masukan(masukan: Masukan, *, user, clinics, note: str = "") -> MasukanPublication:
    """AOM memublikasikan masukan ke cabang; snapshot isi tidak berubah lagi (plan 10)."""
    if not can_publish_masukan(user):
        raise PermissionDenied("Anda tidak memiliki izin memublikasikan masukan.")
    if not can_view_masukan(user, masukan):
        raise PermissionDenied("Anda tidak memiliki akses ke masukan ini.")
    clinic_list = list(clinics or [])
    if not clinic_list:
        raise ValidationError("Publikasi masukan membutuhkan minimal satu cabang tujuan.")

    # Publisher dengan capability khusus tetap dibatasi pada cabang aktif yang
    # menjadi scope-nya. AOM/owner memiliki scope lintas cabang sesuai matriks akses.
    from core.permissions import is_aom, is_owner, user_clinic_queryset

    allowed_ids = set(user_clinic_queryset(user).values_list("pk", flat=True))
    invalid = [clinic for clinic in clinic_list if not clinic.active or clinic.pk not in allowed_ids]
    if invalid and not (is_aom(user) or is_owner(user)):
        raise PermissionDenied("Anda tidak memiliki akses ke salah satu cabang tujuan.")
    if any(not clinic.active for clinic in clinic_list):
        raise ValidationError("Publikasi hanya dapat dikirim ke cabang aktif.")

    publication = MasukanPublication.objects.create(
        masukan=masukan,
        published_by=user,
        title_snapshot=masukan.title,
        description_snapshot=masukan.description,
        source_version=masukan.version,
    )
    publication.clinics.set(clinic_list)

    log_event(
        action=AuditAction.PUBLISH,
        entity_type="masukanpublication",
        entity_id=publication.pk,
        entity_label=f"Masukan#{masukan.pk} → {', '.join(c.code for c in clinic_list)}",
        actor=user,
        after={
            "masukan_id": masukan.pk,
            "clinics": [c.code for c in clinic_list],
            "source_version": masukan.version,
        },
        reason=note,
    )

    from accounts.models import User
    from notifications.services import notify_user

    recipients = User.objects.filter(
        is_active=True, user_roles__clinic__in=clinic_list
    ).distinct()
    for recipient in recipients:
        notify_user(
            recipient,
            type_code="MASUKAN_PUBLISHED",
            title="Masukan baru dipublikasikan",
            body=masukan.title,
            entity_ref=f"masukanpublication#{publication.pk}",
        )
    return publication


@transaction.atomic
def archive_masukan(masukan: Masukan, *, user, reason: str) -> Masukan:
    if not can_archive_masukan(user):
        raise PermissionDenied("Anda tidak memiliki izin mengarsipkan masukan.")
    if not can_view_masukan(user, masukan):
        raise PermissionDenied("Anda tidak memiliki akses ke masukan ini.")
    if not reason.strip():
        raise ValidationError("Alasan arsip wajib diisi.")
    if masukan.archived_at is not None:
        raise ValidationError("Masukan ini sudah diarsipkan.")

    before = snapshot(masukan)
    masukan.archived_at = timezone.now()
    masukan.archived_by = user
    masukan.archive_reason = reason.strip()
    masukan.version += 1
    masukan.save()
    log_update(
        masukan, before, actor=user, reason=reason, action=AuditAction.ARCHIVE, label=f"Masukan#{masukan.pk}"
    )
    return masukan
