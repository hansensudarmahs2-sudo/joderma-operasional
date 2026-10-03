"""Service kas: hitung pecahan, submit, dual verification, koreksi (PRD 8.3, 20.3)."""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from audit.models import AuditAction
from audit.services import log_event, log_update, snapshot
from core.locking import assert_current_version
from core.models import ClinicConfig

from .models import (
    CashDenominationCount,
    CashSession,
    CashSessionType,
    CashStatus,
    CashVerification,
    VerificationResult,
)


def denominations_for(clinic) -> list[int]:
    return list(ClinicConfig.get(clinic, "cash.denominations"))


def dual_control_enabled(clinic) -> bool:
    return bool(ClinicConfig.get(clinic, "cash.dual_control_enabled"))


@transaction.atomic
def get_or_create_session(day, session_type: str, user=None, shift: str = "") -> CashSession:
    session, created = CashSession.objects.get_or_create(
        operational_day=day,
        session_type=session_type,
        shift=shift,
        defaults={"counted_by": user},
    )
    if created:
        CashDenominationCount.objects.bulk_create(
            [
                CashDenominationCount(cash_session=session, denomination=d, quantity=0)
                for d in denominations_for(day.clinic)
            ]
        )
        log_event(
            action=AuditAction.CREATE,
            entity_type="cashsession",
            entity_id=session.pk,
            entity_label=str(session),
            actor=user,
            after=snapshot(session),
        )
    return session


@transaction.atomic
def save_count(
    session: CashSession,
    *,
    user,
    quantities: dict[int, int],
    expected_total: int,
    change_fund_total: int = 0,
    other_funds_total: int = 0,
    note: str = "",
    expected_version: int | None = None,
) -> CashSession:
    session.operational_day.assert_editable()

    assert_current_version(session, expected_version)

    if session.is_verified:
        raise ValidationError(
            "Sesi kas sudah diverifikasi. Gunakan koreksi supervisor dengan alasan."
        )

    for denom, qty in quantities.items():
        if qty is None:
            qty = 0
        if int(qty) < 0:
            raise ValidationError("Jumlah lembar/koin tidak boleh negatif.")
        CashDenominationCount.objects.update_or_create(
            cash_session=session, denomination=int(denom), defaults={"quantity": int(qty)}
        )

    before = snapshot(session)
    session.expected_total = max(0, int(expected_total or 0))
    session.change_fund_total = max(0, int(change_fund_total or 0))
    session.other_funds_total = max(0, int(other_funds_total or 0))
    session.note = (note or "").strip()
    session.counted_by = session.counted_by or user
    session.counted_at = timezone.now()
    session.recompute()

    if session.variance != 0 and not session.note:
        raise ValidationError("Catatan wajib diisi bila terdapat selisih kas.")

    session.version += 1
    session.save()
    log_update(session, before, actor=user)
    return session


@transaction.atomic
def submit_for_verification(session: CashSession, user) -> CashSession:
    session.operational_day.assert_editable()
    if session.counted_at is None:
        raise ValidationError("Hitung kas terlebih dahulu sebelum mengajukan verifikasi.")
    before = snapshot(session)
    session.status = CashStatus.MENUNGGU_VERIFIKASI
    session.submitted_at = timezone.now()
    session.counted_by = session.counted_by or user
    session.version += 1
    session.save()
    log_update(session, before, actor=user)

    from notifications.services import notify_role

    notify_role(
        session.operational_day.clinic,
        "SUPERVISOR",
        type_code="CASH_PENDING",
        title="Kas menunggu verifikasi",
        body=f"{session.get_session_type_display()} {session.operational_day.date} menunggu verifikasi.",
        entity_ref=f"cashsession#{session.pk}",
        url_name="cash:review",
        url_args=[session.pk],
    )
    return session


@transaction.atomic
def verify(
    session: CashSession,
    *,
    verifier,
    recounted_total: int | None = None,
    result: str | None = None,
    note: str = "",
) -> CashSession:
    """Dual-control: verifikator tidak boleh sama dengan penghitung (PRD 20.3).

    Boleh dilakukan setelah hari ditutup: verifikasi tidak mengubah hitungan, hanya menetapkan
    hasil dan memindahkan tanggung jawab selisih ke verifikator.
    """

    if session.status != CashStatus.MENUNGGU_VERIFIKASI:
        raise ValidationError("Sesi kas tidak dalam status menunggu verifikasi.")

    if dual_control_enabled(session.operational_day.clinic):
        if session.counted_by_id and session.counted_by_id == verifier.pk:
            raise ValidationError(
                "Dual-control aktif: penghitung pertama tidak dapat memverifikasi hitungannya sendiri."
            )

    if recounted_total is not None and int(recounted_total) != int(session.actual_total):
        raise ValidationError(
            f"Total hitung ulang (Rp {int(recounted_total):,}) berbeda dari catatan "
            f"(Rp {int(session.actual_total):,}). Perbaiki hitungan sebelum verifikasi."
            .replace(",", ".")
        )

    note = (note or "").strip()
    if result is None:
        result = VerificationResult.SESUAI if session.variance == 0 else VerificationResult.SELISIH
    if result in {VerificationResult.SELISIH, VerificationResult.DISETUJUI_DENGAN_CATATAN, VerificationResult.DITOLAK} and not note:
        raise ValidationError("Catatan wajib diisi untuk hasil verifikasi ini.")

    before = snapshot(session)
    CashVerification.objects.create(
        cash_session=session,
        verifier=verifier,
        recounted_total=recounted_total,
        result=result,
        note=note,
    )

    if result == VerificationResult.DITOLAK:
        session.status = CashStatus.DRAFT
    elif result == VerificationResult.DISETUJUI_DENGAN_CATATAN:
        session.status = CashStatus.DISETUJUI_DENGAN_CATATAN
    elif session.variance == 0:
        session.status = CashStatus.SESUAI
    else:
        session.status = CashStatus.SELISIH
    session.version += 1
    session.save()
    log_update(session, before, actor=verifier, reason=note, action=AuditAction.VERIFY)
    return session


@transaction.atomic
def correct_after_verification(
    session: CashSession,
    *,
    supervisor,
    quantities: dict[int, int],
    expected_total: int,
    reason: str,
) -> CashSession:
    """Koreksi setelah verifikasi: wajib supervisor + alasan; nilai lama tetap di audit."""
    if not reason.strip():
        raise ValidationError("Alasan wajib diisi untuk koreksi kas setelah verifikasi.")
    session.operational_day.assert_editable()

    before = snapshot(session)
    for denom, qty in quantities.items():
        if int(qty) < 0:
            raise ValidationError("Jumlah lembar/koin tidak boleh negatif.")
        CashDenominationCount.objects.update_or_create(
            cash_session=session, denomination=int(denom), defaults={"quantity": int(qty)}
        )
    session.expected_total = max(0, int(expected_total or 0))
    session.recompute()
    session.correction_reason = reason.strip()
    session.corrected_by = supervisor
    session.status = CashStatus.MENUNGGU_VERIFIKASI
    session.version += 1
    session.save()
    log_update(session, before, actor=supervisor, reason=reason, action=AuditAction.OVERRIDE)
    return session


def cash_summary(day) -> dict:
    sessions = {s.session_type: s for s in CashSession.objects.filter(operational_day=day)}
    opening = sessions.get(CashSessionType.OPENING)
    closing = sessions.get(CashSessionType.CLOSING)
    return {
        "opening": opening,
        "closing": closing,
        "opening_status": opening.get_status_display() if opening else "Belum dicatat",
        "closing_status": closing.get_status_display() if closing else "Belum dicatat",
        "has_variance": any(s.variance != 0 for s in sessions.values()),
        "pending_verification": any(
            s.status == CashStatus.MENUNGGU_VERIFIKASI for s in sessions.values()
        ),
    }



def pending_verification(user, *, limit: int = 30):
    """Sesi kas yang menunggu verifikasi di semua cabang yang dapat diakses pengguna."""
    from core.permissions import can_verify_cash, user_clinic_queryset

    if not can_verify_cash(user):
        return CashSession.objects.none()
    return (
        CashSession.objects.filter(
            status=CashStatus.MENUNGGU_VERIFIKASI,
            operational_day__clinic__in=user_clinic_queryset(user),
        )
        .select_related("operational_day__clinic", "counted_by")
        .order_by("operational_day__date", "id")[:limit]
    )
