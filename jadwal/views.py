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
from .models import DutyPortion, DutyRoster, DutyStatus

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


def _save_duty(request, clinic) -> None:
    """Simpan perubahan jadwal satu orang dari form (bulanan atau harian), dengan pesan."""
    user = get_object_or_404(User, pk=request.POST.get("orang") or 0)
    try:
        day = dt.date.fromisoformat(request.POST.get("tanggal", ""))
    except ValueError:
        messages.error(request, "Tanggal tidak valid.")
        return
    status = request.POST.get("status", "")
    target = None
    if ":" in status:  # pilihan gabungan di halaman harian, mis. "PERBANTUAN:2"
        status, _, target_pk = status.partition(":")
        target = Clinic.objects.filter(pk=target_pk if target_pk.isdigit() else 0).first()
    else:
        target = Clinic.objects.filter(pk=request.POST.get("tujuan") or 0).first()
    home = services.home_clinic_for(user, day, default=clinic)
    current = DutyRoster.objects.filter(user=user, date=day).first()
    wanted_clinic = home if status == DutyStatus.MASUK else (target if status == DutyStatus.PERBANTUAN else None)
    if current and current.status == status and current.clinic_id == getattr(wanted_clinic, "pk", None) \
            and not request.POST.get("catatan", "").strip():
        messages.info(request, f"Jadwal {user} {day:%d/%m} tidak berubah.")
        return
    try:
        row = services.set_duty(user=user, day=day, status=status, home_clinic=home, clinic=target,
                                actor=request.user, note=request.POST.get("catatan", ""))
    except PermissionDenied as exc:
        messages.error(request, str(exc))
        return
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        return
    text = f"Jadwal {user} {day:%d/%m}: {row.get_status_display()}"
    if row.clinic_id and row.clinic_id != row.home_clinic_id:
        text += f" ke {row.clinic.name}"
    sync = getattr(row, "sync", {}) or {}
    if sync.get("released"):
        text += f". Porsi dilepas: {', '.join(sync['released'])}"
    if sync.get("filled"):
        text += f". Diisi: {'; '.join(sync['filled'])}"
    messages.success(request, text + ".")


def _editable_ids(actor, people, day_or_none=None) -> set[int]:
    """Orang di daftar yang jadwalnya boleh diubah `actor`."""
    if services.can_edit_roster(actor):
        return {p["user"].pk for p in people}
    out = set()
    for p in people:
        home = p.get("home_clinic")
        if home is not None and services.can_edit_duty(actor, home):
            out.add(p["user"].pk)
    return out


@login_required
def roster(request):
    clinic = _clinic(request)
    year, month = _month(request)
    if request.method == "POST":
        if not services.can_edit_duty(request.user, clinic):
            raise PermissionDenied(
                "Jadwal jaga diubah Direktur Operasional, Admin, atau Koordinator Shift cabang ini.")
        _save_duty(request, clinic)
        return redirect(f"{reverse('jadwal:roster')}?cabang={clinic.pk}&bulan={year:04d}-{month:02d}")
    grid = services.roster_grid(clinic, year, month)
    for p in grid["people"]:
        p["home_clinic"] = clinic if p["home"] else services.home_clinic_for(p["user"], dt.date(year, month, 1))
    editable = _editable_ids(request.user, grid["people"])
    for p in grid["people"]:
        p["editable"] = p["user"].pk in editable
    return render(
        request,
        "jadwal/roster.html",
        {
            "clinic": clinic,
            "clinics": user_clinic_queryset(request.user),
            "grid": grid,
            "month": _nav(year, month),
            "can_edit": services.can_edit_duty(request.user, clinic),
            "statuses": DutyStatus.choices,
            "other_clinics": Clinic.objects.filter(active=True).exclude(pk=clinic.pk),
            "today": local_today(),
        },
    )


def _row_cell(row, clinic) -> dict:
    """Status satu baris jadwal dilihat dari cabang `clinic`."""
    if row.status == DutyStatus.MASUK:
        return {"code": "M", "label": "Masuk" if row.clinic_id == clinic.pk else f"Masuk di {row.clinic.name}"}
    if row.status == DutyStatus.PERBANTUAN:
        if row.clinic_id == clinic.pk:
            return {"code": "B", "label": f"Perbantuan dari {row.home_clinic.name}"}
        return {"code": "P", "label": f"Perbantuan ke {row.clinic.name}"}
    if row.status == DutyStatus.CUTI:
        return {"code": "C", "label": "Cuti"}
    return {"code": "O", "label": "Off"}


def _day_people(clinic, the_day: dt.date) -> list[dict]:
    """Semua orang yang terkait cabang ini pada tanggal itu, dengan status dan cabang asalnya."""
    from accounts.models import Role

    grid = services.roster_grid(clinic, the_day.year, the_day.month)
    index = (the_day - grid["days"][0]).days
    rows = {r.user_id: r for r in DutyRoster.objects.filter(date=the_day).select_related(
        "clinic", "home_clinic")}
    people, seen = [], set()
    for p in grid["people"]:
        seen.add(p["user"].pk)
        row = rows.get(p["user"].pk)
        home = row.home_clinic if row else (clinic if p["home"] else services.home_clinic_for(p["user"], the_day))
        people.append({"user": p["user"], "cell": p["row"][index], "row": row, "home_clinic": home})
    others = (
        User.objects.filter(is_active=True, user_roles__clinic=clinic)
        .exclude(pk__in=seen)
        .exclude(user_roles__role__in=[Role.AOM, Role.OWNER])
        .distinct()
    )
    for u in others:
        if not (u.role_codes() - {Role.ADMIN}):
            continue
        home = services.home_clinic_for(u, the_day, default=clinic)
        if home != clinic:
            # Punya jadwal di cabang lain dan tidak ke sini bulan ini (mis. peran lama yang
            # tertinggal di cabang ini): bukan staf cabang ini, jangan ditampilkan.
            continue
        people.append({"user": u, "cell": {"code": "", "label": "Belum diisi"}, "row": rows.get(u.pk),
                       "home_clinic": home})
    for p in people:
        row = p["row"]
        if row is not None:
            p["cell"] = _row_cell(row, clinic)
        if row is None:
            p["value"] = ""
        elif row.status == DutyStatus.PERBANTUAN:
            p["value"] = f"PERBANTUAN:{row.clinic_id}"
        else:
            p["value"] = row.status
    people.sort(key=lambda p: (p["home_clinic"] != clinic, str(p["user"]).lower()))
    return people


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
    if request.method == "POST" and request.POST.get("aksi") == "jadwal":
        _save_duty(request, clinic)
        return redirect(f"{reverse('jadwal:day', args=[the_day.isoformat()])}?cabang={clinic.pk}#bertugas")
    if request.method == "POST":
        portion = get_object_or_404(DutyPortion, pk=request.POST.get("porsi"), clinic=clinic)
        users = list(User.objects.filter(pk__in=request.POST.getlist("orang")))
        if not users:
            messages.error(request, "Pilih minimal satu orang.")
        else:
            if not services.can_swap_portion(request.user, portion, the_day):
                raise PermissionDenied("Porsi ini di luar fungsi Anda.")
            try:
                services.set_portion_people(portion, the_day, users, actor=request.user,
                                            note=request.POST.get("catatan", ""))
                messages.success(request, f"{portion.name}: {', '.join(str(u) for u in users)}.")
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
        return redirect(f"{reverse('jadwal:day', args=[the_day.isoformat()])}?cabang={clinic.pk}")
    staff = services.staff_on_duty(clinic, the_day)
    all_clinics = list(Clinic.objects.filter(active=True).order_by("id"))
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
                "can_swap": services.can_swap_portion(request.user, portion, the_day),
                "candidates": [u for u in staff if not wanted or u.role_codes() & wanted]
                or staff,
            }
        )
    order = ["OPENING", "KAS", "KEBERSIHAN", "LIMBAH", "APOTEK", "CLOSING"]
    rows.sort(key=lambda r: (order.index(r["portion"].group) if r["portion"].group in order else 99,
                             r["portion"].sort_order))
    people = _day_people(clinic, the_day)
    editable = _editable_ids(request.user, people)
    for p in people:
        p["editable"] = p["user"].pk in editable
        p["choices"] = [
            ("MASUK", f"Masuk di {p['home_clinic'].name}" if p["home_clinic"] else "Masuk"),
            *[(f"PERBANTUAN:{c.pk}", f"Perbantuan ke {c.name}") for c in all_clinics
              if not p["home_clinic"] or c.pk != p["home_clinic"].pk],
            ("OFF", "Off"),
            ("CUTI", "Cuti"),
        ]
    return render(
        request,
        "jadwal/day.html",
        {
            "clinic": clinic,
            "day": the_day,
            "people": people,
            "can_edit_any": any(p["editable"] for p in people),
            "is_past": the_day < local_today(),
            "today": local_today(),
            "rows": rows,
            "staff": staff,
            "can_swap": any(r["can_swap"] for r in rows),
            "swap_all": services.can_swap_duties(request.user, clinic),
            "prev": the_day - dt.timedelta(days=1),
            "next": the_day + dt.timedelta(days=1),
            "month": f"{the_day:%Y-%m}",
        },
    )


@login_required
def mine(request):
    """Jadwal saya (fase 7): jadwal jaga dan porsi tugas diri sendiri sebulan, bukan grid tim."""
    from .models import DutyAssignment

    year, month = _month(request)
    days = services.month_days(year, month)
    rows = {r.date: r for r in DutyRoster.objects.filter(user=request.user, date__in=days).select_related("clinic")}
    portions: dict = {}
    for a in (DutyAssignment.objects.filter(user=request.user, date__in=days, portion__active=True)
              .select_related("portion", "clinic").order_by("portion__sort_order")):
        portions.setdefault(a.date, []).append(a)
    today = local_today()
    lines = [{"date": d, "duty": rows.get(d), "portions": portions.get(d, []), "is_today": d == today,
              "is_past": d < today} for d in days]
    working = sum(1 for r in rows.values() if r.is_working)
    return render(request, "jadwal/mine.html", {
        "nav": _nav(year, month), "lines": lines, "working": working,
        "off": sum(1 for r in rows.values() if not r.is_working),
    })
