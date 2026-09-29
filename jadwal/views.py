"""Halaman jadwal jaga dan pembagian tugas harian."""
from __future__ import annotations

import datetime as dt

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.models import User
from core.models import Clinic, local_today
from core.permissions import can_access_clinic, user_clinic_queryset
from core.services import active_clinic

from . import services
from .models import DutyPortion, DutyStatus

MONTHS = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September",
          "Oktober", "November", "Desember"]


def _clinic(request) -> Clinic:
    pk = request.GET.get("cabang") or request.POST.get("cabang")
    clinic = get_object_or_404(Clinic, pk=pk) if pk else active_clinic(request.user)
    if not can_access_clinic(request.user, clinic):
        raise PermissionDenied("Anda tidak memiliki akses ke cabang ini.")
    return clinic


def _month(request) -> tuple[int, int]:
    raw = request.GET.get("bulan") or request.POST.get("bulan") or ""
    try:
        year, month = (int(x) for x in raw.split("-"))
        dt.date(year, month, 1)
        return year, month
    except ValueError:
        today = local_today()
        return today.year, today.month


def _nav(year: int, month: int) -> dict:
    prev = (year - 1, 12) if month == 1 else (year, month - 1)
    nxt = (year + 1, 1) if month == 12 else (year, month + 1)
    return {
        "label": f"{MONTHS[month - 1]} {year}",
        "value": f"{year:04d}-{month:02d}",
        "prev": f"{prev[0]:04d}-{prev[1]:02d}",
        "next": f"{nxt[0]:04d}-{nxt[1]:02d}",
    }


@login_required
def roster(request):
    clinic = _clinic(request)
    year, month = _month(request)
    if request.method == "POST":
        if not services.can_edit_roster(request.user):
            raise PermissionDenied("Jadwal jaga hanya diubah Direktur Operasional atau Admin.")
        user = get_object_or_404(User, pk=request.POST.get("orang"))
        try:
            day = dt.date.fromisoformat(request.POST.get("tanggal", ""))
            status = request.POST.get("status", "")
            target = Clinic.objects.filter(pk=request.POST.get("tujuan") or 0).first()
            services.set_duty(
                user=user, day=day, status=status, home_clinic=clinic, clinic=target,
                actor=request.user, note=request.POST.get("catatan", ""),
            )
            messages.success(request, f"Jadwal {user} {day:%d/%m} disimpan.")
        except ValueError:
            messages.error(request, "Tanggal tidak valid.")
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        return redirect(f"{reverse('jadwal:roster')}?cabang={clinic.pk}&bulan={year:04d}-{month:02d}")
    grid = services.roster_grid(clinic, year, month)
    return render(
        request,
        "jadwal/roster.html",
        {
            "clinic": clinic,
            "clinics": user_clinic_queryset(request.user),
            "grid": grid,
            "month": _nav(year, month),
            "can_edit": services.can_edit_roster(request.user),
            "statuses": DutyStatus.choices,
            "other_clinics": Clinic.objects.filter(active=True).exclude(pk=clinic.pk),
            "today": local_today(),
        },
    )


@login_required
def plan(request):
    clinic = _clinic(request)
    year, month = _month(request)
    if request.method == "POST":
        if not services.can_plan_duties(request.user):
            raise PermissionDenied("Penyusunan hanya oleh Direktur Operasional atau Admin.")
        n = services.plan_month(clinic, year, month, actor=request.user)
        messages.success(request, f"{n} porsi disusun ulang. Porsi yang diubah manual tidak disentuh.")
        return redirect(f"{reverse('jadwal:plan')}?cabang={clinic.pk}&bulan={year:04d}-{month:02d}")
    return render(
        request,
        "jadwal/plan.html",
        {
            "clinic": clinic,
            "clinics": user_clinic_queryset(request.user),
            "plan": services.month_plan(clinic, year, month),
            "month": _nav(year, month),
            "can_plan": services.can_plan_duties(request.user),
            "has_portions": DutyPortion.objects.filter(clinic=clinic, active=True).exists(),
            "today": local_today(),
        },
    )


@login_required
def day(request, date: str):
    clinic = _clinic(request)
    try:
        the_day = dt.date.fromisoformat(date)
    except ValueError:
        raise PermissionDenied("Tanggal tidak valid.")
    can_swap = services.can_swap_duties(request.user, clinic)
    if request.method == "POST":
        portion = get_object_or_404(DutyPortion, pk=request.POST.get("porsi"), clinic=clinic)
        users = list(User.objects.filter(pk__in=request.POST.getlist("orang")))
        if not users:
            messages.error(request, "Pilih minimal satu orang.")
        else:
            try:
                services.set_portion_people(portion, the_day, users, actor=request.user,
                                            note=request.POST.get("catatan", ""))
                messages.success(request, f"{portion.name}: {', '.join(str(u) for u in users)}.")
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
        return redirect(f"{reverse('jadwal:day', args=[the_day.isoformat()])}?cabang={clinic.pk}")
    staff = services.staff_on_duty(clinic, the_day)
    assigned = services.assignments_by_portion(clinic, the_day)
    rows = []
    for portion in DutyPortion.objects.filter(clinic=clinic, active=True).order_by("sort_order"):
        if not portion.runs_on(the_day):
            continue
        wanted = set(portion.eligible_roles or [])
        people = assigned.get(portion.code, [])
        rows.append(
            {
                "portion": portion,
                "people": people,
                "chosen": {a.user_id for a in people},
                "candidates": [u for u in staff if not wanted or u.role_codes() & wanted]
                or staff,
            }
        )
    order = ["OPENING", "KAS", "KEBERSIHAN", "LIMBAH", "APOTEK", "CLOSING"]
    rows.sort(key=lambda r: (order.index(r["portion"].group) if r["portion"].group in order else 99,
                             r["portion"].sort_order))
    return render(
        request,
        "jadwal/day.html",
        {
            "clinic": clinic,
            "day": the_day,
            "rows": rows,
            "staff": staff,
            "can_swap": can_swap,
            "prev": the_day - dt.timedelta(days=1),
            "next": the_day + dt.timedelta(days=1),
            "month": f"{the_day:%Y-%m}",
        },
    )
