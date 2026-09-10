"""View antrean: papan kerja front desk + layar bersama (PRD 8.4)."""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.permissions import can_manage_queue, can_view_patient_detail, is_supervisor, require
from core.services import active_clinic, get_or_create_day

from .models import PaymentStatus, QueueEntry, QueueStatus, VisitType
from .services import (
    change_payment_status,
    change_queue_status,
    create_entry,
    keep_number_statuses,
    queue_summary,
    reorder,
    set_priority,
)


@login_required
def board(request):
    clinic = active_clinic()
    day, _ = get_or_create_day(clinic, user=request.user)
    entries = QueueEntry.objects.filter(operational_day=day)

    status_filter = request.GET.get("status")
    if status_filter:
        entries = entries.filter(queue_status=status_filter)

    show_detail = can_view_patient_detail(request.user)
    return render(
        request,
        "queueing/board.html",
        {
            "day": day,
            "entries": entries,
            "summary": queue_summary(day),
            "can_manage": can_manage_queue(request.user),
            "show_detail": show_detail,
            "is_supervisor": is_supervisor(request.user),
            "queue_statuses": QueueStatus.choices,
            "payment_statuses": PaymentStatus.choices,
            "visit_types": VisitType.choices,
            "keep_statuses": keep_number_statuses(clinic),
            "status_filter": status_filter or "",
        },
    )


@login_required
def public_board(request):
    """Layar bersama: inisial/alias, tanpa detail pembayaran (PRD 8.4, 15.2)."""
    clinic = active_clinic()
    day, _ = get_or_create_day(clinic, user=request.user)
    entries = QueueEntry.objects.filter(operational_day=day).exclude(
        queue_status__in=[QueueStatus.BATAL, QueueStatus.SELESAI]
    )
    return render(request, "queueing/public_board.html", {"day": day, "entries": entries})


@login_required
@require(can_manage_queue)
def create(request):
    clinic = active_clinic()
    day, _ = get_or_create_day(clinic, user=request.user)
    if request.method == "POST":
        try:
            entry = create_entry(
                day,
                user=request.user,
                display_name=request.POST.get("nama", ""),
                alias=request.POST.get("alias", ""),
                patient_ref=request.POST.get("patient_ref", ""),
                visit_type=request.POST.get("jenis", VisitType.KONSULTASI),
                payment_status=request.POST.get("pembayaran", PaymentStatus.BELUM_BAYAR),
                note=request.POST.get("catatan", ""),
            )
            messages.success(request, f"Antrean #{entry.queue_no} dibuat.")
            return redirect("queueing:board")
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
    return render(
        request,
        "queueing/form.html",
        {
            "day": day,
            "visit_types": VisitType.choices,
            "payment_statuses": PaymentStatus.choices,
            "default_payment": PaymentStatus.BELUM_BAYAR,
        },
    )


@login_required
def detail(request, pk: int):
    entry = get_object_or_404(QueueEntry, pk=pk)
    if not can_view_patient_detail(request.user):
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied("Anda tidak memiliki izin melihat detail pasien.")
    return render(
        request,
        "queueing/detail.html",
        {
            "entry": entry,
            "payment_events": entry.payment_events.select_related("actor"),
            "status_events": entry.status_events.select_related("actor"),
            "can_manage": can_manage_queue(request.user),
            "payment_statuses": PaymentStatus.choices,
            "queue_statuses": QueueStatus.choices,
        },
    )


@login_required
@require(can_manage_queue)
@require_POST
def set_status(request, pk: int):
    entry = get_object_or_404(QueueEntry, pk=pk)
    try:
        change_queue_status(
            entry,
            user=request.user,
            to_status=request.POST.get("status", ""),
            reason=request.POST.get("alasan", ""),
        )
        messages.success(request, f"Status antrean #{entry.queue_no} diperbarui.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect(request.POST.get("next") or "queueing:board")


@login_required
@require(can_manage_queue)
@require_POST
def set_payment(request, pk: int):
    entry = get_object_or_404(QueueEntry, pk=pk)
    try:
        change_payment_status(
            entry,
            user=request.user,
            to_status=request.POST.get("pembayaran", ""),
            reason=request.POST.get("alasan", ""),
            payment_ref=request.POST.get("referensi", ""),
        )
        messages.success(request, "Status pembayaran diperbarui.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect(request.POST.get("next") or "queueing:board")


@login_required
@require(is_supervisor)
@require_POST
def move(request, pk: int):
    entry = get_object_or_404(QueueEntry, pk=pk)
    try:
        reorder(
            entry,
            user=request.user,
            new_position=int(request.POST.get("posisi") or entry.position),
            reason=request.POST.get("alasan", ""),
        )
        messages.success(request, "Urutan antrean diubah dan tercatat di audit.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    except ValueError:
        messages.error(request, "Posisi harus berupa angka.")
    return redirect("queueing:board")


@login_required
@require(is_supervisor)
@require_POST
def priority(request, pk: int):
    entry = get_object_or_404(QueueEntry, pk=pk)
    try:
        set_priority(entry, user=request.user, reason=request.POST.get("alasan", ""))
        messages.success(request, "Pasien ditandai prioritas.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("queueing:board")
