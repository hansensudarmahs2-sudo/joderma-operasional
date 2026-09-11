"""Otorisasi server-side terpusat (PRD 6.2, 6.3, 20.1).

Semua pemeriksaan izin dilakukan di server. Menyembunyikan tombol di UI TIDAK
dianggap sebagai kontrol akses.
"""
from __future__ import annotations

from functools import wraps

from django.core.exceptions import PermissionDenied

from accounts.models import Capability, Role


def roles(user) -> set[str]:
    if not user or not user.is_authenticated:
        return set()
    return user.role_codes()


def caps(user) -> set[str]:
    if not user or not user.is_authenticated:
        return set()
    return user.capability_codes()


def has_role(user, *wanted: str) -> bool:
    return bool(roles(user) & set(wanted))


def is_supervisor(user) -> bool:
    return has_role(user, Role.SUPERVISOR)


def is_owner(user) -> bool:
    return has_role(user, Role.OWNER)


def is_admin(user) -> bool:
    return has_role(user, Role.ADMIN)


def has_admin_full_access(user) -> bool:
    """Admin dengan akses penuh ke data bisnis.

    PRD 6.3 menetapkan admin teknis TIDAK otomatis berwenang atas data bisnis
    sensitif — itu default-nya. Namun bila klinik memutuskan peran admin dipegang
    manajemen (bukan vendor IT), kapabilitas ini memberi akses penuh.

    Sengaja dibuat opt-in per pengguna, bukan melekat pada peran ADMIN, agar:
      - pemberiannya tercatat di audit log sebagai keputusan sadar;
      - admin teknis pihak ketiga tetap dapat dibatasi;
      - dapat dicabut tanpa mengubah kode.

    Lihat OWNER_DECISION_REVIEW.md D8.
    """
    return Capability.ADMIN_FULL_ACCESS in caps(user)


def is_bootstrap_superuser(user) -> bool:
    """Superuser Django hasil `createsuperuser`.

    Diperlukan agar instalasi baru dapat di-bootstrap: tanpa ini, superuser
    pertama tidak dapat membuat akun siapa pun lewat UI dan instalasi menjadi
    buntu. Hak ini sengaja dibatasi pada tugas ADMINISTRATIF saja
    (kelola pengguna, konfigurasi, template).

    Superuser TIDAK otomatis memperoleh hak BISNIS sensitif — nominal kas,
    detail pasien, komplain terbatas, dan audit log tetap memerlukan peran atau
    kapabilitas eksplisit (PRD 6.3 least privilege).
    """
    return bool(user and user.is_authenticated and user.is_superuser)


def is_front_desk(user) -> bool:
    return has_role(user, Role.FRONT_DESK)


def is_nurse(user) -> bool:
    return has_role(user, Role.PERAWAT)


# --- Kapabilitas turunan -------------------------------------------------

def can_view_cash_amounts(user) -> bool:
    """Nominal kas: kasir/front desk, supervisor, owner berizin. Admin TIDAK otomatis."""
    return (
        is_front_desk(user)
        or is_supervisor(user)
        or Capability.CASH_VIEW_AMOUNTS in caps(user)
        or has_admin_full_access(user)
    )


def can_edit_cash(user) -> bool:
    return is_front_desk(user) or is_supervisor(user) or has_admin_full_access(user)


def can_verify_cash(user) -> bool:
    """PRD 8.3: penghitung kedua ATAU supervisor melakukan verifikasi.

    Front desk lain harus bisa menjadi penghitung kedua — bila hanya supervisor
    yang berwenang dan supervisor itu sendiri yang menghitung, dual-control
    membuat kas tidak pernah dapat diverifikasi (buntu).
    """
    return (
        is_supervisor(user)
        or is_front_desk(user)
        or Capability.CASH_APPROVE in caps(user)
        or has_admin_full_access(user)
    )


def can_correct_cash(user) -> bool:
    """Koreksi setelah verifikasi tetap hanya supervisor (PRD 20.3)."""
    return is_supervisor(user) or Capability.CASH_APPROVE in caps(user) or has_admin_full_access(user)


def can_view_patient_detail(user) -> bool:
    return (
        is_front_desk(user)
        or is_nurse(user)
        or is_supervisor(user)
        or Capability.PATIENT_VIEW_DETAIL in caps(user)
        or has_admin_full_access(user)
    )


def can_manage_queue(user) -> bool:
    return is_front_desk(user) or is_supervisor(user) or has_admin_full_access(user)


def can_manage_roster(user) -> bool:
    return is_supervisor(user)


def can_manage_breaks(user) -> bool:
    return is_supervisor(user)


def can_view_audit(user) -> bool:
    return (
        is_supervisor(user)
        or is_owner(user)
        or Capability.AUDIT_VIEW in caps(user)
        or has_admin_full_access(user)
    )


def can_export(user) -> bool:
    return (
        is_supervisor(user)
        or is_owner(user)
        or Capability.REPORT_EXPORT in caps(user)
        or has_admin_full_access(user)
    )


def can_manage_users(user) -> bool:
    return is_admin(user) or is_bootstrap_superuser(user)


def can_manage_templates(user) -> bool:
    return is_admin(user) or is_supervisor(user) or is_bootstrap_superuser(user)


def can_manage_config(user) -> bool:
    return is_admin(user) or is_bootstrap_superuser(user)


def can_review_checklist(user) -> bool:
    return is_supervisor(user)


def can_fill_checklist(user) -> bool:
    return bool(roles(user))  # semua staf aktif


def can_close_day(user) -> bool:
    return is_supervisor(user)


def can_assign_issue(user) -> bool:
    return is_supervisor(user)


def can_view_restricted_issue(user, issue) -> bool:
    """Komplain terbatas: pembuat, assignee, supervisor, owner (PRD 6.3)."""
    if not getattr(issue, "is_restricted", False):
        return True
    if (
        is_supervisor(user)
        or is_owner(user)
        or Capability.ISSUE_VIEW_RESTRICTED in caps(user)
        or has_admin_full_access(user)
    ):
        return True
    if issue.created_by_id == user.pk:
        return True
    return issue.assignments.filter(assignee_id=user.pk, active=True).exists()


def read_only_for(user) -> bool:
    """Owner bersifat read-only kecuali diberi kapabilitas approval."""
    return is_owner(user) and not (roles(user) - {Role.OWNER})


# --- Decorator -----------------------------------------------------------

def require(*predicates):
    """Decorator view: semua predikat harus True, jika tidak -> 403."""

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                raise PermissionDenied("Login diperlukan.")
            for pred in predicates:
                if not pred(request.user):
                    raise PermissionDenied(
                        "Anda tidak memiliki izin untuk mengakses bagian ini."
                    )
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def require_roles(*wanted: str):
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                raise PermissionDenied("Login diperlukan.")
            if not has_role(request.user, *wanted):
                raise PermissionDenied("Peran Anda tidak diizinkan mengakses bagian ini.")
            return view(request, *args, **kwargs)

        return wrapper

    return decorator
