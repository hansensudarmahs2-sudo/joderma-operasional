"""View jadwal istirahat (PRD 8.6)."""
from __future__ import annotations

import datetime as dt

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from accounts.models import User
from core.permissions import can_manage_breaks, require
from core.models import local_today
from core.services import active_clinic

from .models import BreakSchedule, BreakStatus, BreakType
from .services import cancel_break, create_break, min_staffing, staffing_warnings, update_break


def _parse_dt(date_value, time_str: str):
    naive = dt.datetime.combine(date_value, dt.time.fromisoformat(time_str))
    return timezone.make_aware(naive, timezone.get_current_timezone())


@login_required
def list_view(request):
    clinic = active_clinic(request.user)
    date_value = parse_date(request.GET.get("tanggal") or "") or local_today()
    schedules = (
        BreakSchedule.objects.filter(clinic=clinic, date=date_value)
        .select_related("user", "created_by")
        .order_by("start_at")
    )
    mine = [s for s in schedules if s.user_id == request.user.pk]
    return render(
        request,
        "breaks/list.html",
        {
            "date": date_value,
            "schedules": schedules,
            "mine": mine,
            "can_manage": can_manage_breaks(request.user),
            "minimums": min_staffing(clinic),
            "types": BreakType.choices,
        },
    )


@login_required
@require(can_manage_breaks)
def create(request):
    clinic = active_clinic(request.user)
    users = User.objects.filter(is_active=True).order_by("username")
    if request.method == "POST":
        try:
            date_value = parse_date(request.POST.get("tanggal", "")) or local_today()
            start_at = _parse_dt(date_value, request.POST.get("mulai", "12:00"))
            end_at = _parse_dt(date_value, request.POST.get("selesai", "13:00"))
            target = get_object_or_404(User, pk=request.POST.get("pengguna"))
            _, warnings = create_break(
                clinic,
                supervisor=request.user,
                user=target,
                date=date_value,
                break_type=request.POST.get("jenis", BreakType.ISTIRAHAT),
                start_at=start_at,
                end_at=end_at,
                location_note=request.POST.get("lokasi", ""),
                staffing_override_reason=request.POST.get("alasan_override", ""),
            )
            if warnings:
                messages.warning(request, "Override minimum staf: " + " ".join(warnings))
            messages.success(request, "Jadwal istirahat dibuat.")
            return redirect("breaks:list")
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        except ValueError:
            messages.error(request, "Format jam tidak valid. Gunakan format HH:MM.")
    return render(
        request,
        "breaks/form.html",
        {"users": users, "types": BreakType.choices, "today": local_today()},
    )


@login_required
@require(can_manage_breaks)
@require_POST
def update(request, pk: int):
    schedule = get_object_or_404(BreakSchedule, pk=pk)
    try:
        start_at = end_at = None
        if request.POST.get("mulai"):
            start_at = _parse_dt(schedule.date, request.POST["mulai"])
        if request.POST.get("selesai"):
            end_at = _parse_dt(schedule.date, request.POST["selesai"])
        _, warnings = update_break(
            schedule,
            supervisor=request.user,
            start_at=start_at,
            end_at=end_at,
            status=request.POST.get("status") or None,
            staffing_override_reason=request.POST.get("alasan_override", ""),
            reason=request.POST.get("alasan", ""),
        )
        if warnings:
            messages.warning(request, " ".join(warnings))
        messages.success(request, "Jadwal diperbarui.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    except ValueError:
        messages.error(request, "Format jam tidak valid.")
    return redirect("breaks:list")


@login_required
@require(can_manage_breaks)
@require_POST
def cancel(request, pk: int):
    schedule = get_object_or_404(BreakSchedule, pk=pk)
    try:
        cancel_break(schedule, supervisor=request.user, reason=request.POST.get("alasan", ""))
        messages.success(request, "Jadwal dibatalkan.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("breaks:list")
