"""State machine hari operasional dan helper klinik (PRD 7)."""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from audit.models import AuditAction
from audit.services import log_event, log_update, snapshot

from .models import Clinic, DayStatus, OperationalDay, local_today

# Tutup hari boleh dari status mana pun yang belum tutup (keputusan 3 Okt 2026): staf sering
# tidak menjalankan Siap/Buka/Mulai penutupan, dan hari tidak boleh tertahan karenanya.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    DayStatus.DRAFT: {DayStatus.OPENING_IN_PROGRESS},
    DayStatus.OPENING_IN_PROGRESS: {DayStatus.READY, DayStatus.READY_WITH_ISSUES, DayStatus.CLOSED},
    DayStatus.READY: {DayStatus.OPEN, DayStatus.OPENING_IN_PROGRESS, DayStatus.CLOSED},
    DayStatus.READY_WITH_ISSUES: {DayStatus.OPEN, DayStatus.OPENING_IN_PROGRESS, DayStatus.CLOSED},
    DayStatus.OPEN: {DayStatus.CLOSING, DayStatus.CLOSED},
    DayStatus.CLOSING: {DayStatus.CLOSED, DayStatus.OPEN},
    DayStatus.CLOSED: {DayStatus.OPEN},  # hanya lewat reopen_day()
}


CLINIC_SESSION_KEY = "active_clinic"


def clinic_key(clinic) -> str:
    """Kunci tetap cabang, tidak bergantung pada kode di database.

    Di mini PC kode Citraland adalah ``JC``, di data uji ``citraland``. Kode program yang
    membedakan cabang (prefix RM, butir khusus cabang) memakai kunci ini, bukan kode mentah.
    """
    code = (getattr(clinic, "code", "") or "").strip()
    text = f"{code} {getattr(clinic, 'name', '') or ''}".lower()
    if "citraland" in text or code.upper() == "JC":
        return "citraland"
    if "jemur" in text or code.upper() == "JJ":
        return "jemur-andayani"
    return code.lower()


def rm_prefix(clinic) -> str:
    """Prefix nomor RM cabang: JJ- Jemur, JC- Citraland."""
    return {"jemur-andayani": "JJ-", "citraland": "JC-"}.get(clinic_key(clinic), "J_-")


def home_clinic_id(user) -> int | None:
    """Cabang asal pengguna bila hari ini ia tidak bertugas (off, cuti) atau belum dijadwalkan.

    Urutan: cabang asal di jadwal jaga hari ini → cabang asal jadwal terdekat → cabang fungsi
    PIC aktif (bila hanya satu cabang).
    """
    from accounts.models import PicAssignment
    from jadwal.models import DutyRoster

    today = local_today()
    rows = DutyRoster.objects.filter(user=user)
    row = rows.filter(date=today).first()
    if row is None:
        row = rows.filter(date__lte=today).order_by("-date").first() or rows.order_by("date").first()
    if row is not None:
        return row.home_clinic_id
    pic_clinics = set(PicAssignment.objects.filter(user=user, active=True).values_list("clinic_id", flat=True))
    if len(pic_clinics) == 1:
        return pic_clinics.pop()
    return None


def active_clinic(user=None) -> Clinic:
    """Cabang tempat pengguna bekerja sekarang.

    Urutan: pilihan cabang di sesi hari ini (pengalih cabang di kanan atas) → cabang tugas di
    jadwal jaga hari ini → cabang asal (lihat `home_clinic_id`) → cabang pertama yang dapat
    diakses.
    """
    if user is not None:
        from .permissions import user_clinic_queryset

        clinics = user_clinic_queryset(user)
        clinic = None
        override = getattr(user, "_clinic_override", None)
        if override:
            clinic = clinics.filter(pk=override).first()
        if clinic is None and getattr(user, "is_authenticated", False):
            # Staf perbantuan (mis. Yani di Citraland hari Minggu) bekerja di cabang
            # menurut jadwal jaga hari itu, bukan cabang pertama pada daftar perannya.
            from jadwal.models import WORKING_STATUSES, DutyRoster

            duty = (
                DutyRoster.objects.filter(user=user, date=local_today(), status__in=WORKING_STATUSES)
                .values_list("clinic_id", flat=True)
                .first()
            )
            if duty:
                clinic = clinics.filter(pk=duty).first()
            if clinic is None:
                home = home_clinic_id(user)
                if home:
                    clinic = clinics.filter(pk=home).first()
        if clinic is None:
            clinic = clinics.order_by("id").first()
        if clinic is None and getattr(user, "is_superuser", False):
            clinic = Clinic.objects.filter(active=True).order_by("id").first()
    else:
        clinic = Clinic.objects.filter(active=True).order_by("id").first()
    if clinic is None:
        raise ValidationError(
            "Belum ada klinik aktif untuk pengguna ini. Jalankan `manage.py seed_demo` "
            "atau atur peran cabang lewat Admin."
        )
    return clinic


def _transition(day: OperationalDay, new_status: str):
    if new_status not in ALLOWED_TRANSITIONS.get(day.status, set()):
        raise ValidationError(
            f"Perubahan status dari {day.get_status_display()} ke {new_status} tidak diizinkan."
        )
    day.status = new_status


@transaction.atomic
def get_or_create_day(clinic: Clinic, date=None, user=None) -> tuple[OperationalDay, bool]:
    """Satu sesi aktif per cabang dan tanggal (PRD 7)."""
    date = date or local_today()
    day, created = OperationalDay.objects.get_or_create(
        clinic=clinic, date=date, defaults={"created_by": user}
    )
    if created:
        from checklists.services import instantiate_runs_for_day

        instantiate_runs_for_day(day, user=user)
        day.status = DayStatus.OPENING_IN_PROGRESS
        day.save(update_fields=["status"])
        log_event(
            action=AuditAction.CREATE,
            entity_type="operationalday",
            entity_id=day.pk,
            entity_label=str(day),
            actor=user,
            after=snapshot(day),
        )
    return day, created


def opening_progress(day: OperationalDay) -> dict:
    from checklists.models import ChecklistResponse, ResponseResult

    responses = ChecklistResponse.objects.filter(run__operational_day=day)
    total = responses.count()
    done = responses.exclude(result=ResponseResult.BELUM).count()
    failed = responses.filter(
        result__in=[ResponseResult.TIDAK_LENGKAP, ResponseResult.RUSAK]
    ).count()
    required_pending = responses.filter(required=True).exclude(
        result__in=[ResponseResult.OK, ResponseResult.TIDAK_BERLAKU]
    ).count()
    return {
        "total": total,
        "done": done,
        "failed": failed,
        "required_pending": required_pending,
        "percent": round(done * 100 / total) if total else 0,
    }


def cash_opening_recorded(day: OperationalDay) -> bool:
    from cash.models import CashSession, CashSessionType, CashStatus

    return CashSession.objects.filter(
        operational_day=day, session_type=CashSessionType.OPENING
    ).exclude(status=CashStatus.DRAFT).exists()


@transaction.atomic
def mark_ready(day: OperationalDay, user, *, with_issues: bool = False, reason: str = ""):
    """READY hanya jika semua item wajib lulus DAN kas awal sudah dicatat (PRD 7)."""
    before = snapshot(day)
    progress = opening_progress(day)

    if with_issues:
        if not reason.strip():
            raise ValidationError("Alasan wajib diisi untuk status Siap dengan catatan.")
        _transition(day, DayStatus.READY_WITH_ISSUES)
        day.ready_exception_reason = reason.strip()
    else:
        if progress["required_pending"]:
            raise ValidationError(
                f"{progress['required_pending']} item wajib belum berstatus OK. "
                "Gunakan 'Siap dengan catatan' bila kondisi diterima dengan pengecualian."
            )
        if not cash_opening_recorded(day):
            raise ValidationError("Kas awal belum dicatat. Catat kas awal sebelum menandai Siap.")
        _transition(day, DayStatus.READY)

    day.save()
    log_update(
        day,
        before,
        actor=user,
        reason=reason,
        action=AuditAction.OVERRIDE if with_issues else AuditAction.UPDATE,
    )
    return day


@transaction.atomic
def open_day(day: OperationalDay, user):
    before = snapshot(day)
    _transition(day, DayStatus.OPEN)
    day.opened_at = timezone.now()
    day.opened_by = user
    day.save()
    log_update(day, before, actor=user, action=AuditAction.UPDATE)
    return day


@transaction.atomic
def start_closing(day: OperationalDay, user):
    before = snapshot(day)
    _transition(day, DayStatus.CLOSING)
    day.save()
    log_update(day, before, actor=user)
    return day


def closing_blockers(day: OperationalDay) -> list[str]:
    """Tidak boleh tutup bila kas akhir belum diajukan atau ada item kritis (PRD 18).

    Kas akhir cukup **diajukan** (menunggu verifikasi). Verifikasi dilakukan Direktur Operasional
    sesudahnya, juga setelah hari ditutup; tanggung jawab selisih berpindah ke verifikator saat
    ia memverifikasi (keputusan 3 Okt 2026).
    """
    from cash.models import CashSession, CashSessionType, CashStatus
    from issues.models import Issue, IssueStatus, IssueType
    from core.models import Priority

    blockers: list[str] = []
    closing_cash = CashSession.objects.filter(
        operational_day=day, session_type=CashSessionType.CLOSING
    ).exclude(status__in=[CashStatus.DRAFT]).exists()
    if not closing_cash:
        blockers.append("Kas akhir belum dihitung dan diajukan (verifikasi Direktur boleh menyusul).")

    open_critical = Issue.objects.filter(
        clinic=day.clinic,
        severity=Priority.KRITIS,
        status__in=[IssueStatus.BARU, IssueStatus.DITINJAU],
    ).count()
    if open_critical:
        blockers.append(f"{open_critical} catatan kritis belum ditriase/ditugaskan.")
    return blockers


@transaction.atomic
def close_day(day: OperationalDay, user, *, override_reason: str = ""):
    before = snapshot(day)
    blockers = closing_blockers(day)
    if blockers and not override_reason.strip():
        raise ValidationError(
            "Hari belum dapat ditutup: " + " ".join(blockers) + " Koordinator Shift dapat menutup dengan alasan."
        )
    _transition(day, DayStatus.CLOSED)
    day.closed_at = timezone.now()
    day.closed_by = user
    day.close_override_reason = override_reason.strip()
    day.save()
    log_update(
        day,
        before,
        actor=user,
        reason=override_reason,
        action=AuditAction.OVERRIDE if override_reason else AuditAction.CLOSE,
    )
    return day


@transaction.atomic
def reopen_day(day: OperationalDay, user, *, reason: str):
    if not reason.strip():
        raise ValidationError("Alasan wajib diisi untuk membuka kembali hari operasional.")
    before = snapshot(day)
    if day.status != DayStatus.CLOSED:
        raise ValidationError("Hanya hari yang sudah ditutup dapat dibuka kembali.")
    day.status = DayStatus.OPEN
    day.reopen_reason = reason.strip()
    day.closed_at = None
    day.closed_by = None
    day.save()
    log_update(day, before, actor=user, reason=reason, action=AuditAction.REOPEN)
    return day
