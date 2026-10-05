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


def is_aom(user) -> bool:
    return has_role(user, Role.AOM)


def is_pic(user) -> bool:
    return has_role(user, Role.PIC)


def can_access_clinic(user, clinic) -> bool:
    if not user or not user.is_authenticated or clinic is None:
        return False
    if is_aom(user) or is_owner(user):
        return True
    return user.user_roles.filter(clinic=clinic).exists()


# Peran yang bekerja lintas cabang: boleh menjadi penerima task/penanggung jawab di cabang mana pun
# walau UserRole-nya tercatat di satu cabang saja (5 Okt 2026: Direktur Operasional hanya punya
# peran di Jemur, padahal task untuknya bisa berlaku di kedua cabang).
CROSS_BRANCH_ROLES = (Role.AOM,)


def clinic_member_q(clinic, prefix: str = ""):
    """Filter User: anggota cabang `clinic`, termasuk Direktur Operasional (lintas cabang)."""
    from django.db.models import Q

    return Q(**{f"{prefix}user_roles__clinic": clinic}) | Q(**{f"{prefix}user_roles__role__in": CROSS_BRANCH_ROLES})


def is_clinic_member(user, clinic) -> bool:
    if user is None or clinic is None:
        return False
    return user.user_roles.filter(clinic=clinic).exists() or user.user_roles.filter(role__in=CROSS_BRANCH_ROLES).exists()


def user_clinic_queryset(user):
    from core.models import Clinic

    if not user or not user.is_authenticated:
        return Clinic.objects.none()
    qs = Clinic.objects.filter(active=True)
    if is_aom(user) or is_owner(user):
        return qs
    return qs.filter(user_roles__user=user).distinct()


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
    """Nominal kas: kasir/front desk, supervisor, Direktur Operasional (verifikator), owner berizin.

    Admin TIDAK otomatis.
    """
    return (
        is_front_desk(user)
        or is_supervisor(user)
        or is_aom(user)
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
        or is_aom(user)
        or Capability.CASH_APPROVE in caps(user)
        or has_admin_full_access(user)
    )


def can_correct_cash(user) -> bool:
    """Koreksi setelah verifikasi: supervisor dan Direktur Operasional (PRD 20.3)."""
    return (is_supervisor(user) or is_aom(user) or Capability.CASH_APPROVE in caps(user)
            or has_admin_full_access(user))


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
        or is_aom(user)
        or is_owner(user)
        or Capability.AUDIT_VIEW in caps(user)
        or has_admin_full_access(user)
    )


def can_export(user) -> bool:
    return (
        is_supervisor(user)
        or is_aom(user)
        or is_owner(user)
        or Capability.REPORT_EXPORT in caps(user)
        or has_admin_full_access(user)
    )


def can_manage_users(user) -> bool:
    return (
        is_admin(user)
        or Capability.USER_MANAGE in caps(user)
        or has_admin_full_access(user)
        or is_bootstrap_superuser(user)
    )


def can_manage_templates(user) -> bool:
    return is_admin(user) or is_supervisor(user) or is_bootstrap_superuser(user)


def can_manage_config(user) -> bool:
    return is_admin(user) or is_bootstrap_superuser(user)


def can_edit_clinic_profile(user) -> bool:
    """Nama, alamat, nomor HP, jam, DPJ, APJ cabang: Admin dan Direktur Operasional."""
    return is_admin(user) or is_aom(user) or is_bootstrap_superuser(user)


def can_view_clinic_profile(user) -> bool:
    return can_edit_clinic_profile(user) or is_owner(user)


def can_review_checklist(user) -> bool:
    return is_supervisor(user)


def can_fill_checklist(user) -> bool:
    return bool(roles(user))  # semua staf aktif


def can_access_checklist_run(user, run) -> bool:
    """Scope cabang dan target role checklist; AOM/owner lintas cabang."""
    if not can_access_clinic(user, run.operational_day.clinic):
        return False
    if is_aom(user) or is_owner(user) or is_supervisor(user):
        return True
    target_roles = set(
        run.template_snapshot.get("target_roles", run.template.target_roles) or []
    )
    if not target_roles:
        return True
    return bool(target_roles & roles(user))


def can_edit_checklist_response(user, response) -> bool:
    if not can_access_checklist_run(user, response.run) or not can_fill_checklist(user):
        return False
    item_roles = set(response.performer_roles or []) | set(response.verifier_roles or [])
    if not item_roles or bool(item_roles & roles(user)) or is_aom(user) or is_owner(user):
        return True
    # Pelaksana yang ditugaskan lewat pembagian tugas harian (mis. delegasi saat
    # Koordinator Shift libur) boleh mengisi porsinya walau tidak memegang perannya.
    portion = getattr(response, "portion", "")
    if portion:
        from jadwal.services import is_assigned

        day = response.run.operational_day
        return is_assigned(user, day.clinic, day.date, portion)
    return False


def can_close_day(user) -> bool:
    """Koordinator Shift (supervisor) dan Direktur Operasional."""
    return is_supervisor(user) or is_aom(user)


def can_assign_issue(user) -> bool:
    return is_supervisor(user) or is_pic(user) or is_aom(user)


def can_view_restricted_issue(user, issue) -> bool:
    """Komplain terbatas: pembuat, assignee, supervisor, owner (PRD 6.3)."""
    if not can_access_clinic(user, issue.clinic):
        return False
    if not getattr(issue, "is_restricted", False):
        return True
    if (
        is_supervisor(user)
        or is_aom(user)
        or is_owner(user)
        or Capability.ISSUE_VIEW_RESTRICTED in caps(user)
        or Capability.REPORT_VIEW_CONFIDENTIAL in caps(user)
        or has_admin_full_access(user)
    ):
        return True
    if issue.created_by_id == user.pk:
        return True
    return issue.assignments.filter(assignee_id=user.pk, active=True).exists()


def can_view_laporan(user, laporan) -> bool:
    """Laporan CABANG: staf aktif cabang sama. RAHASIA_AOM: pelapor + AOM (plan 9.1).

    Tidak ada publikasi otomatis lintas cabang; laporan RAHASIA_AOM tidak
    pernah terlihat oleh user lain di cabang yang sama kecuali diberi
    kapabilitas eksplisit.
    """
    from reports.models import ReportVisibility

    if not can_access_clinic(user, laporan.clinic):
        return False
    if laporan.visibility != ReportVisibility.RAHASIA_AOM:
        return True
    if laporan.created_by_id == user.pk:
        return True
    return (
        is_aom(user)
        or is_owner(user)
        or Capability.REPORT_VIEW_CONFIDENTIAL in caps(user)
        or has_admin_full_access(user)
    )


def can_create_laporan(user) -> bool:
    return bool(roles(user))  # semua staf aktif


def can_archive_laporan(user) -> bool:
    return (
        is_aom(user)
        or is_owner(user)
        or Capability.REPORT_VIEW_CONFIDENTIAL in caps(user)
        or has_admin_full_access(user)
    )


def can_view_masukan(user, masukan) -> bool:
    """Masukan: pengirim dan AOM sebelum publikasi (plan 10)."""
    if not can_access_clinic(user, masukan.clinic):
        return False
    if masukan.created_by_id == user.pk:
        return True
    return (
        is_aom(user)
        or is_owner(user)
        or Capability.REPORT_VIEW_CONFIDENTIAL in caps(user)
        or has_admin_full_access(user)
    )


def can_publish_masukan(user) -> bool:
    return (
        is_aom(user)
        or Capability.SUGGESTION_PUBLISH in caps(user)
        or has_admin_full_access(user)
    )


def can_view_published_masukan(user, publication) -> bool:
    """Masukan yang sudah dipublikasikan terlihat oleh staf aktif cabang tujuan."""
    return any(can_access_clinic(user, c) for c in publication.clinics.all())


def can_archive_masukan(user) -> bool:
    return (
        is_aom(user)
        or is_owner(user)
        or Capability.REPORT_VIEW_CONFIDENTIAL in caps(user)
        or has_admin_full_access(user)
    )


def can_edit_stok(user) -> bool:
    """Stok Apotek: unggah, ubah parameter, tindak lanjut. Keputusan product owner 1 Okt 2026:
    halaman ini milik operasional apotek, jadi apoteker dan asisten apoteker penuh haknya."""
    return has_role(user, Role.APOTEKER, Role.ASISTEN_APOTEKER, Role.AOM)


def can_view_stok(user) -> bool:
    """Owner hanya membaca (PRD A6, belum diputuskan lain)."""
    return can_edit_stok(user) or is_owner(user)


def can_edit_absensi(user) -> bool:
    """Absensi jam kerja: impor berkas mesin dan koreksi cap.

    Isinya jam kerja seluruh staf dan dasar penilaian lembur, jadi haknya sempit:
    Direktur Operasional, dan Admin yang diberi akses penuh data bisnis (D8).
    """
    return is_aom(user) or has_admin_full_access(user) or is_bootstrap_superuser(user)


def can_view_absensi(user) -> bool:
    """Owner ikut membaca papan skor dan daftar pengecualian, tanpa boleh mengimpor."""
    return can_edit_absensi(user) or is_owner(user)


def can_correct_absensi(user) -> bool:
    """Mengoreksi cap absen, dan karenanya skor serta lembur seseorang.

    Lebih sempit daripada `can_edit_absensi`: mengimpor berkas hanya memasukkan apa
    yang dicatat mesin, sedangkan mengoreksi cap mengubah angka yang dipakai menilai
    orang. Keputusan product owner (D4, Okt 2026): hanya Direktur Operasional,
    Direktur Utama, dan Owner. Admin sistem tidak termasuk, meski boleh mengubah
    jadwal jaga.

    `Role.OWNER` mencakup Owner dan Direktur Utama.
    """
    return is_aom(user) or is_owner(user) or is_bootstrap_superuser(user)


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
