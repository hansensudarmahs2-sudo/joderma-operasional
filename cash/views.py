"""View kas: hitung pecahan, dual verification, koreksi (PRD 8.3)."""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.permissions import (
    is_aom,
    can_correct_cash,
    can_edit_cash,
    can_verify_cash,
    can_view_cash_amounts,
    require,
)
from core.services import active_clinic, get_or_create_day

from .models import CashSession, CashSessionType, CashStatus, VerificationResult
from .services import (
    open_variances,
    pending_verification,
    cash_summary,
    correct_after_verification,
    denominations_for,
    dual_control_enabled,
    expected_baseline,
    expected_for,
    get_or_create_session,
    save_count,
    submit_for_verification,
    verify,
)


def _quantities_from_post(post, denominations) -> dict[int, int]:
    result = {}
    for denom in denominations:
        raw = post.get(f"denom_{denom}", "0").strip() or "0"
        result[int(denom)] = int(raw)
    return result


def _session(request, pk: int) -> CashSession:
    """Sesi kas hanya untuk pengguna yang punya akses ke cabangnya."""
    from core.permissions import can_access_clinic

    session = get_object_or_404(CashSession.objects.select_related("operational_day__clinic"), pk=pk)
    if not can_access_clinic(request.user, session.operational_day.clinic):
        raise PermissionDenied("Sesi kas ini milik cabang lain.")
    return session


@login_required
@require(can_view_cash_amounts)
def index(request):
    clinic = active_clinic(request.user)
    day, _ = get_or_create_day(clinic, user=request.user)
    return render(
        request,
        "cash/index.html",
        {
            "day": day,
            "summary": cash_summary(day),
            "can_edit": can_edit_cash(request.user),
            "pending": pending_verification(request.user),
            "open_variances": open_variances(request.user),
            "dual_control": dual_control_enabled(clinic),
        },
    )


@login_required
@require(can_view_cash_amounts, can_edit_cash)
def form(request, session_type: str):
    clinic = active_clinic(request.user)
    day, _ = get_or_create_day(clinic, user=request.user)
    session_type = session_type.upper()
    if session_type not in dict(CashSessionType.choices):
        messages.error(request, "Jenis sesi kas tidak dikenali.")
        return redirect("cash:index")
    session = get_or_create_session(day, session_type, user=request.user)
    counts = {d.denomination: d.quantity for d in session.denominations.all()}
    rows = [
        {"denomination": d, "quantity": counts.get(d, 0), "subtotal": d * counts.get(d, 0)}
        for d in denominations_for(clinic)
    ]
    return render(
        request,
        "cash/form.html",
        {"session": session, "rows": rows, "day": day, "dual_control": dual_control_enabled(clinic),
         "clinic": clinic, "baseline": expected_baseline(session),
         "is_closing": session.session_type == CashSessionType.CLOSING},
    )


@login_required
@require(can_view_cash_amounts, can_edit_cash)
@require_POST
def save(request, pk: int):
    session = _session(request, pk)
    clinic = session.operational_day.clinic
    try:
        cash_in = int(request.POST.get("tunai_masuk") or 0)
        cash_out = int(request.POST.get("tunai_keluar") or 0)
        # 6 Okt 2026: angka diharapkan disusun sistem dari kas akhir sebelumnya / kas awal hari itu;
        # kolom "diharapkan" hanya dipakai bila belum ada pembanding sama sekali.
        expected, basis = expected_for(session, cash_in=cash_in, cash_out=cash_out,
                                       manual=int(request.POST.get("diharapkan") or 0))
        save_count(
            session,
            user=request.user,
            quantities=_quantities_from_post(request.POST, denominations_for(clinic)),
            expected_total=expected,
            change_fund_total=int(request.POST.get("kembalian") or session.change_fund_total or 0),
            other_funds_total=int(request.POST.get("dana_lain") or session.other_funds_total or 0),
            note=request.POST.get("catatan", ""),
            expected_version=int(request.POST.get("versi") or session.version),
            cash_in_total=cash_in,
            cash_out_total=cash_out,
            expected_basis=basis,
        )
        from jejak.services import stamp

        stamp(request, "KAS", clinic=clinic, entity=session)
        if request.POST.get("ajukan") == "1":
            submit_for_verification(session, request.user)
            stamp(request, "KAS_AJUKAN", clinic=clinic, entity=session)
            messages.success(request, "Hitungan kas disimpan dan diajukan untuk verifikasi.")
            return redirect("cash:index")
        messages.success(request, "Hitungan kas disimpan.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    except ValueError:
        messages.error(request, "Nilai jumlah harus berupa angka bulat tanpa titik/koma.")
    return redirect("cash:form", session_type=session.session_type)


@login_required
@require(can_view_cash_amounts, can_edit_cash)
@require_POST
def submit(request, pk: int):
    session = _session(request, pk)
    try:
        submit_for_verification(session, request.user)
        from jejak.services import stamp

        stamp(request, "KAS_AJUKAN", clinic=session.operational_day.clinic, entity=session)
        messages.success(request, "Kas diajukan untuk verifikasi.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("cash:index")


@login_required
@require(can_view_cash_amounts)
def review(request, pk: int):
    session = _session(request, pk)
    rows = [
        {"denomination": d.denomination, "quantity": d.quantity, "subtotal": d.subtotal}
        for d in session.denominations.all()
    ]
    baseline = expected_baseline(session)
    hint = None
    if baseline["base"] is not None and session.counted_at:
        base = baseline["base"]
        if session.session_type == CashSessionType.CLOSING:
            base += session.cash_in_total - session.cash_out_total
        if base != session.expected_total:
            diff = session.actual_total - base
            hint = {"label": baseline["label"], "expected": base, "variance": diff, "abs": abs(diff)}
    return render(
        request,
        "cash/review.html",
        {
            "session": session,
            "hint": hint,
            "rows": rows,
            "can_verify": can_verify_cash(request.user),
            "can_close_admin": is_aom(request.user),
            "can_correct": can_correct_cash(request.user),
            "results": VerificationResult.choices,
            "verifications": session.verifications.select_related("verifier"),
        },
    )


ADMIN_ERROR_NOTE = "Kekeliruan administratif"


@login_required
@require(can_verify_cash)
@require_POST
def verify_action(request, pk: int):
    session = _session(request, pk)
    try:
        recounted = request.POST.get("hitung_ulang")
        result = request.POST.get("hasil") or None
        note = request.POST.get("catatan", "").strip()
        if request.POST.get("aksi") == "administratif":
            if not is_aom(request.user):
                raise PermissionDenied("Menutup selisih sebagai kekeliruan administratif hanya untuk Direktur Operasional.")
            # Uang benar, pencatatan keliru (mis. Diharapkan tidak diisi): perkara ditutup.
            result = VerificationResult.DISETUJUI_DENGAN_CATATAN
            note = ADMIN_ERROR_NOTE + (f": {note}" if note else "")
        verify(
            session,
            verifier=request.user,
            recounted_total=int(recounted) if recounted else None,
            result=result,
            note=note,
        )
        messages.success(request, "Verifikasi kas tersimpan." if result != VerificationResult.DISETUJUI_DENGAN_CATATAN
                         else "Kas terverifikasi dengan catatan; perkara selisih ditutup.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    except ValueError:
        messages.error(request, "Total hitung ulang harus berupa angka.")
    return redirect("cash:review", pk=session.pk)


@login_required
@require(can_correct_cash)
@require_POST
def correct(request, pk: int):
    session = _session(request, pk)
    clinic = session.operational_day.clinic
    try:
        correct_after_verification(
            session,
            supervisor=request.user,
            quantities=_quantities_from_post(request.POST, denominations_for(clinic)),
            expected_total=int(request.POST.get("diharapkan") or session.expected_total),
            reason=request.POST.get("alasan", ""),
        )
        messages.warning(request, "Koreksi kas tercatat; sesi kembali menunggu verifikasi.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("cash:review", pk=session.pk)
