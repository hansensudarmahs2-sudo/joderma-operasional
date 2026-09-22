"""View kas: hitung pecahan, dual verification, koreksi (PRD 8.3)."""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.permissions import (
    can_correct_cash,
    can_edit_cash,
    can_verify_cash,
    can_view_cash_amounts,
    require,
)
from core.services import active_clinic, get_or_create_day

from .models import CashSession, CashSessionType, CashStatus, VerificationResult
from .services import (
    cash_summary,
    correct_after_verification,
    denominations_for,
    dual_control_enabled,
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
        {"session": session, "rows": rows, "day": day, "dual_control": dual_control_enabled(clinic)},
    )


@login_required
@require(can_view_cash_amounts, can_edit_cash)
@require_POST
def save(request, pk: int):
    session = get_object_or_404(CashSession, pk=pk)
    clinic = session.operational_day.clinic
    try:
        save_count(
            session,
            user=request.user,
            quantities=_quantities_from_post(request.POST, denominations_for(clinic)),
            expected_total=int(request.POST.get("diharapkan") or 0),
            change_fund_total=int(request.POST.get("kembalian") or 0),
            other_funds_total=int(request.POST.get("dana_lain") or 0),
            note=request.POST.get("catatan", ""),
            expected_version=int(request.POST.get("versi") or session.version),
        )
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
    session = get_object_or_404(CashSession, pk=pk)
    try:
        submit_for_verification(session, request.user)
        messages.success(request, "Kas diajukan untuk verifikasi.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("cash:index")


@login_required
@require(can_view_cash_amounts)
def review(request, pk: int):
    session = get_object_or_404(CashSession, pk=pk)
    rows = [
        {"denomination": d.denomination, "quantity": d.quantity, "subtotal": d.subtotal}
        for d in session.denominations.all()
    ]
    return render(
        request,
        "cash/review.html",
        {
            "session": session,
            "rows": rows,
            "can_verify": can_verify_cash(request.user),
            "can_correct": can_correct_cash(request.user),
            "results": VerificationResult.choices,
            "verifications": session.verifications.select_related("verifier"),
        },
    )


@login_required
@require(can_verify_cash)
@require_POST
def verify_action(request, pk: int):
    session = get_object_or_404(CashSession, pk=pk)
    try:
        recounted = request.POST.get("hitung_ulang")
        verify(
            session,
            verifier=request.user,
            recounted_total=int(recounted) if recounted else None,
            result=request.POST.get("hasil") or None,
            note=request.POST.get("catatan", ""),
        )
        messages.success(request, "Verifikasi kas tersimpan.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    except ValueError:
        messages.error(request, "Total hitung ulang harus berupa angka.")
    return redirect("cash:review", pk=session.pk)


@login_required
@require(can_correct_cash)
@require_POST
def correct(request, pk: int):
    session = get_object_or_404(CashSession, pk=pk)
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
