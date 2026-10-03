"""Tampilan Owner / Direktur Utama: Dashboard, Permintaan, Summary Harian, Jadwal.

Menu Owner dibangun di `core/peran.py`; halaman di luar tampilan ini ditolak oleh
`core.middleware.PersonaAccessMiddleware`. Angka ringkasan memakai fungsi yang sama dengan
Ringkasan Direktur (`direktur.dashboard`), supaya keduanya tidak pernah berbeda.
"""
from __future__ import annotations

import datetime as dt

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from core.models import Clinic, local_today
from core.photos import photos_for, save_optional_photo
from core.permissions import is_aom, require, user_clinic_queryset
from direktur import dashboard
from direktur.models import DailySummary

from . import services
from .models import OwnerRequest

DAYS = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]


def _date(raw: str | None, default: dt.date) -> dt.date:
    try:
        return dt.date.fromisoformat(raw or "")
    except ValueError:
        return default


def _day_label(day: dt.date) -> str:
    return f"{DAYS[day.weekday()]}, {day:%d/%m/%Y}"


def _inbox_counts(user):
    from reports.inbox import can_view_inbox, open_counts

    return open_counts(user) if can_view_inbox(user) else None


@login_required
@require(dashboard.can_view_overview)
def dashboard_page(request):
    user = request.user
    return render(
        request,
        "owner/dashboard.html",
        {
            "inbox": _inbox_counts(request.user),
            "bird": dashboard.bird_view(user),
            "matrix": dashboard.eisenhower(user, limit=1),
            "counts": dashboard.headline_counts(user),
            "requests": services.request_rows(user),
            "can_create": services.can_create_request(user),
            "today": local_today(),
        },
    )


@login_required
@require(services.can_create_request)
def request_new(request):
    form = {"judul": "", "rincian": "", "target": ""}
    if request.method == "POST":
        form = {k: request.POST.get(k, "") for k in form}
        try:
            with transaction.atomic():
                req = services.create_request(
                    actor=request.user,
                    title=form["judul"],
                    description=form["rincian"],
                    target_date=services.parse_target(form["target"]),
                )
                save_optional_photo(request, entity_type="ownerrequest", entity_id=req.pk)
            messages.success(request, "Permintaan dikirim ke Direktur Operasional.")
            return redirect("owner:request_detail", pk=req.pk)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
    return render(request, "owner/request_form.html", {"form": form, "today": local_today()})


@login_required
@require(services.can_view_requests)
def request_detail(request, pk: int):
    req = get_object_or_404(OwnerRequest.objects.select_related("created_by"), pk=pk)
    if request.method == "POST":
        try:
            with transaction.atomic():
                note = services.add_note(req, actor=request.user, body=request.POST.get("catatan", ""))
                save_optional_photo(request, entity_type="ownerrequestnote", entity_id=note.pk)
            messages.success(request, "Catatan disimpan.")
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        return redirect("owner:request_detail", pk=req.pk)
    notes = list(req.notes.select_related("author"))
    return render(
        request,
        "owner/request_detail.html",
        {
            "row": services.progress(req),
            "notes": notes,
            "photos": photos_for("ownerrequest", [req.pk]).get(req.pk, []),
            "note_photos": photos_for("ownerrequestnote", [n.pk for n in notes]),
            "is_director": is_aom(request.user),
        },
    )


@login_required
@require(services.can_view_summary)
def summary(request):
    today = local_today()
    day = _date(request.GET.get("tanggal"), today)
    recent = list(DailySummary.objects.select_related("sent_by").order_by("-date")[:14])
    return render(
        request,
        "owner/summary.html",
        {
            "day": day,
            "day_label": _day_label(day),
            "summary": DailySummary.objects.filter(date=day).select_related("sent_by").first(),
            "prev": day - dt.timedelta(days=1),
            "next": day + dt.timedelta(days=1) if day < today else None,
            "today": today,
            "recent": recent,
        },
    )


@login_required
@require(dashboard.can_view_overview)
def jadwal(request):
    clinics = list(user_clinic_queryset(request.user).order_by("id"))
    if not clinics:
        raise PermissionDenied("Tidak ada cabang yang dapat Anda lihat.")
    clinic = next((c for c in clinics if str(c.pk) == request.GET.get("cabang")), clinics[0])
    today = local_today()
    day = _date(request.GET.get("tanggal"), today)
    return render(
        request,
        "owner/jadwal.html",
        {
            "clinics": clinics,
            "clinic": clinic,
            "day": day,
            "day_label": _day_label(day),
            "today": today,
            "prev": day - dt.timedelta(days=1),
            "next": day + dt.timedelta(days=1),
            "duty": services.duty_today(clinic, day),
        },
    )
