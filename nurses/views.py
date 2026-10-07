"""View giliran perawat: urutan, ledger, override (PRD 8.5)."""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import Role, User
from audit.services import log_create
from core.permissions import can_manage_roster, is_aom, is_supervisor, require
from core.services import active_clinic, get_or_create_day, rm_prefix
from queueing.models import QueueEntry

from .forms import NurseActionTallyForm
from orders.services import normalize_rm_number
from .models import (
    Availability,
    CommissionTurnEvent,
    NurseRosterEntry,
    ProcedureAssignment,
    ProcedureCategory,
    ProcedureStatus,
    NurseActionTally,
)
from .services import (
    backfill_nurses,
    backfill_window,
    can_correct_tally,
    correct_tally,
    record_backfill_tally,
    after_tally,
    hand_over,
    move_entry,
    rotation_board,
    sync_roster_with_duty,
    assign_procedure,
    cancel_procedure,
    complete_procedure,
    next_nurse,
    rotation_policy,
    set_availability,
    set_roster,
    skip_nurse,
    start_procedure,
)


def _back(request, default: str = "nurses:board"):
    """Kembali ke halaman asal (mis. Tindakan saya) bila `next` aman; selain itu ke papan."""
    from django.utils.http import url_has_allowed_host_and_scheme

    nxt = request.POST.get("next", "")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()},
                                               require_https=request.is_secure()):
        return redirect(nxt)
    return redirect(default)


def _is_staff_view(user) -> bool:
    from core import peran

    return peran.persona(user) == peran.STAF


def _tally_nurses(day):
    """Pilihan perawat di form tally: yang ada di roster hari ini dan tidak off."""
    ids = NurseRosterEntry.objects.filter(operational_day=day).exclude(
        availability=Availability.OFF_DUTY
    ).values_list("nurse_id", flat=True)
    qs = User.objects.filter(is_active=True, pk__in=list(ids))
    if not qs.exists():
        qs = User.objects.filter(
            is_active=True, user_roles__clinic=day.clinic, user_roles__role=Role.PERAWAT
        ).distinct()
    return qs.order_by("display_name", "username")


@login_required
def board(request):
    clinic = active_clinic(request.user)
    day, _ = get_or_create_day(clinic, user=request.user)
    if not NurseRosterEntry.objects.filter(operational_day=day).exists():
        sync_roster_with_duty(day, actor=request.user)
    rotation = rotation_board(day)
    return render(
        request,
        "nurses/board.html",
        {
            "day": day,
            "rotation": rotation,
            "next_entry": rotation["next"],
            "policy": rotation_policy(clinic),
            "can_manage": can_manage_roster(request.user) or is_aom(request.user),
            "tallies": NurseActionTally.objects.filter(operational_day=day).select_related("nurse", "entered_by"),
            "tally_form": NurseActionTallyForm(nurse_queryset=_tally_nurses(day)),
            "rm_prefix": rm_prefix(clinic),
            "can_correct": can_correct_tally(request.user, clinic),
        },
    )


@login_required
@require_POST
def create_tally(request):
    clinic = active_clinic(request.user)
    day, _ = get_or_create_day(clinic, user=request.user)
    # Staf (fase 7) hanya mencatat tally untuk dirinya sendiri, dari Tindakan saya.
    nurses = User.objects.filter(pk=request.user.pk) if _is_staff_view(request.user) else _tally_nurses(day)
    form = NurseActionTallyForm(request.POST, nurse_queryset=nurses)
    if form.is_valid():
        tally = form.save(commit=False)
        tally.rm_number = normalize_rm_number(clinic, tally.rm_number)
        tally.operational_day = day
        tally.entered_by = request.user
        with transaction.atomic():
            tally.save()
            # Tally baru tercatat di audit (3 Okt 2026): siapa mencatat, untuk perawat siapa, kapan.
            log_create(tally, actor=request.user, request=request,
                       label=f"{tally.rm_number} · {tally.action_name} · {tally.tally}x · {tally.nurse} ({clinic.name})")
            after_tally(day, tally.nurse_id, amount=tally.tally, user=request.user)
        messages.success(request, "Tally tindakan disimpan.")
    else:
        messages.error(request, "Data tally belum lengkap atau tidak valid.")
    return _back(request)


@login_required
@require_POST
def hand_over_view(request, pk: int):
    entry = get_object_or_404(NurseRosterEntry, pk=pk, operational_day__clinic=active_clinic(request.user))
    try:
        hand_over(entry, user=request.user)
        messages.success(request, f"Pasien diserahkan ke {entry.nurse}.")
    except (ValidationError, PermissionDenied) as exc:
        messages.error(request, " ".join(getattr(exc, "messages", [str(exc)])))
    return redirect("nurses:board")


@login_required
@require_POST
def move_view(request, pk: int):
    entry = get_object_or_404(NurseRosterEntry, pk=pk, operational_day__clinic=active_clinic(request.user))
    try:
        move_entry(entry, direction=request.POST.get("arah", ""), user=request.user)
    except (ValidationError, PermissionDenied) as exc:
        messages.error(request, " ".join(getattr(exc, "messages", [str(exc)])))
    return redirect("nurses:board")


@login_required
@require_POST
def sync_view(request):
    if not (can_manage_roster(request.user) or is_aom(request.user)):
        raise PermissionDenied("Hanya Koordinator Shift yang menyinkronkan roster.")
    clinic = active_clinic(request.user)
    day, _ = get_or_create_day(clinic, user=request.user)
    result = sync_roster_with_duty(day, actor=request.user)
    if result["synced"]:
        messages.success(request, f"Roster mengikuti jadwal jaga: {result['added']} ditambah, {result['off']} ditandai off.")
    else:
        messages.error(request, "Jadwal jaga hari ini belum diisi.")
    return redirect("nurses:board")


@login_required
@require(can_manage_roster)
def roster_form(request):
    clinic = active_clinic(request.user)
    day, _ = get_or_create_day(clinic, user=request.user)
    nurses = User.objects.filter(is_active=True, user_roles__role=Role.PERAWAT).distinct()
    if request.method == "POST":
        try:
            set_roster(
                day,
                supervisor=request.user,
                nurse_ids=[int(v) for v in request.POST.getlist("perawat")],
                reason=request.POST.get("alasan", ""),
            )
            messages.success(request, "Roster perawat disimpan.")
            return redirect("nurses:board")
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
    current = list(
        NurseRosterEntry.objects.filter(operational_day=day)
        .order_by("position")
        .values_list("nurse_id", flat=True)
    )
    return render(
        request, "nurses/roster.html", {"day": day, "nurses": nurses, "current": current}
    )


@login_required
@require_POST
def assign(request):
    clinic = active_clinic(request.user)
    day, _ = get_or_create_day(clinic, user=request.user)
    category = get_object_or_404(ProcedureCategory, pk=request.POST.get("kategori"))
    queue_entry = None
    if request.POST.get("antrean"):
        queue_entry = QueueEntry.objects.filter(pk=request.POST["antrean"]).first()
    try:
        assignment = assign_procedure(
            day,
            user=request.user,
            category=category,
            nurse_id=request.POST.get("perawat") or None,
            queue_entry=queue_entry,
            note=request.POST.get("catatan", ""),
            override_reason=request.POST.get("alasan_override", ""),
        )
        messages.success(request, f"Tindakan ditugaskan kepada {assignment.nurse}.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("nurses:board")


@login_required
@require_POST
def start(request, pk: int):
    assignment = get_object_or_404(ProcedureAssignment, pk=pk)
    if assignment.nurse_id != request.user.pk and not is_supervisor(request.user):
        messages.error(request, "Hanya perawat terkait atau supervisor yang dapat memulai tindakan.")
        return _back(request)
    try:
        start_procedure(assignment, user=request.user)
        messages.success(request, "Tindakan dimulai.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return _back(request)


@login_required
@require_POST
def complete(request, pk: int):
    assignment = get_object_or_404(ProcedureAssignment, pk=pk)
    if assignment.nurse_id != request.user.pk and not is_supervisor(request.user):
        messages.error(request, "Hanya perawat terkait atau supervisor yang dapat menyelesaikan.")
        return _back(request)
    try:
        complete_procedure(assignment, user=request.user)
        messages.success(request, "Tindakan selesai; giliran berpindah.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return _back(request)


@login_required
@require_POST
def cancel(request, pk: int):
    assignment = get_object_or_404(ProcedureAssignment, pk=pk)
    try:
        cancel_procedure(assignment, user=request.user, reason=request.POST.get("alasan", ""))
        messages.warning(request, "Tindakan dibatalkan dan tercatat di ledger.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("nurses:board")


@login_required
@require(can_manage_roster)
@require_POST
def skip(request, pk: int):
    entry = get_object_or_404(NurseRosterEntry, pk=pk)
    try:
        skip_nurse(entry, user=request.user, reason=request.POST.get("alasan", ""))
        messages.info(request, "Perawat dilewati; tercatat di ledger.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("nurses:board")


@login_required
@require_POST
def availability(request, pk: int):
    entry = get_object_or_404(NurseRosterEntry, pk=pk)
    if entry.nurse_id != request.user.pk and not is_supervisor(request.user):
        messages.error(request, "Anda tidak dapat mengubah ketersediaan perawat lain.")
        return _back(request)
    try:
        set_availability(
            entry,
            user=request.user,
            availability=request.POST.get("ketersediaan", Availability.TERSEDIA),
            reason=request.POST.get("alasan", ""),
        )
        messages.success(request, "Ketersediaan diperbarui.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return _back(request)


@login_required
def ledger(request):
    clinic = active_clinic(request.user)
    day, _ = get_or_create_day(clinic, user=request.user)
    events = CommissionTurnEvent.objects.filter(operational_day=day).select_related(
        "nurse", "actor", "procedure_category"
    )
    return render(request, "nurses/ledger.html", {"day": day, "events": events})



def _parse_date(raw, default):
    import datetime as dt

    try:
        return dt.date.fromisoformat(raw or "")
    except ValueError:
        return default


@login_required
def tally_day(request):
    """Daftar tally satu tanggal untuk dikoreksi (Koordinator Shift / Direktur)."""
    from core.models import Clinic, OperationalDay
    from core.permissions import can_access_clinic, user_clinic_queryset

    clinic = active_clinic(request.user)
    raw_clinic = request.GET.get("cabang", "")
    if raw_clinic:
        clinic = get_object_or_404(Clinic, pk=raw_clinic if raw_clinic.isdigit() else 0)
    if not can_access_clinic(request.user, clinic) or not can_correct_tally(request.user, clinic):
        raise PermissionDenied("Koreksi tally hanya oleh Koordinator Shift cabang ini, Direktur Operasional, atau pemegang hak koreksi tally.")
    start, today = backfill_window(clinic)
    # Bawaan: hari operasional yang berjalan (kemarin bila penutupan molor lewat tengah malam).
    the_date = _parse_date(request.GET.get("tanggal"), today)
    tallies = NurseActionTally.objects.filter(
        operational_day__clinic=clinic, operational_day__date=the_date
    ).select_related("nurse", "entered_by", "corrected_by")
    day = OperationalDay.objects.filter(clinic=clinic, date=the_date).first()
    has_day = day is not None
    return render(request, "nurses/tally_day.html", {
        "clinic": clinic,
        "clinics": [c for c in user_clinic_queryset(request.user).order_by("id") if can_correct_tally(request.user, c)],
        "date": the_date,
        "tallies": tallies,
        "has_day": has_day,
        # Tally susulan: bulan berjalan sampai hari ini, pada tanggal yang punya sesi (hari ini selalu boleh).
        "can_backfill": start <= the_date <= today and (has_day or the_date == today),
        "backfill_start": start,
        "nurses": backfill_nurses(clinic, day),
    })


def _all_nurses():
    return User.objects.filter(
        is_active=True, user_roles__role=Role.PERAWAT
    ).distinct().order_by("display_name", "username")


@login_required
@require_POST
def tally_backfill(request):
    """Tally susulan dari halaman per tanggal (Koordinator Shift / Direktur)."""
    from django.urls import reverse

    from core.models import Clinic

    clinic = get_object_or_404(Clinic, pk=request.POST.get("cabang") if (request.POST.get("cabang") or "").isdigit() else 0)
    if not can_correct_tally(request.user, clinic):
        raise PermissionDenied("Tally susulan hanya oleh Koordinator Shift cabang ini, Direktur Operasional, atau pemegang hak koreksi tally.")
    the_date = _parse_date(request.POST.get("tanggal"), None)
    raw_nurse = request.POST.get("perawat") or ""
    nurse = _all_nurses().filter(pk=raw_nurse).first() if raw_nurse.isdigit() else None
    try:
        record_backfill_tally(clinic, the_date, user=request.user, nurse=nurse,
                              amount=request.POST.get("jumlah", ""), reason=request.POST.get("alasan", ""))
        messages.success(request, "Tally susulan dicatat. Total harian dan bulanan ikut bertambah; urutan papan tidak bergeser.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    query = f"?cabang={clinic.pk}" + (f"&tanggal={the_date.isoformat()}" if the_date else "")
    return redirect(reverse("nurses:tally_day") + query)


@login_required
def tally_correct(request, pk: int):
    tally = get_object_or_404(NurseActionTally.objects.select_related("operational_day__clinic", "nurse"), pk=pk)
    day = tally.operational_day
    if not can_correct_tally(request.user, day.clinic):
        raise PermissionDenied("Koreksi tally hanya oleh Koordinator Shift cabang ini, Direktur Operasional, atau pemegang hak koreksi tally.")
    nurses = _all_nurses()
    if request.method == "POST":
        nurse = nurses.filter(pk=request.POST.get("perawat") or tally.nurse_id).first()
        try:
            correct_tally(tally, user=request.user, amount=request.POST.get("jumlah", ""), nurse=nurse,
                          action_name=request.POST.get("tindakan", ""), reason=request.POST.get("alasan", ""))
            messages.success(request, "Tally dikoreksi. Total bulanan ikut diperbarui.")
            from django.urls import reverse

            return redirect(f"{reverse('nurses:tally_day')}?cabang={day.clinic_id}&tanggal={day.date.isoformat()}")
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
    return render(request, "nurses/tally_correct.html", {"tally": tally, "day": day, "nurses": nurses})


@login_required
def mine(request):
    """Tindakan saya (fase 7): giliran, tindakan, dan tally diri sendiri, bukan papan seluruh tim."""
    from .services import daily_tally, monthly_tally

    clinic = active_clinic(request.user)
    day, _ = get_or_create_day(clinic, user=request.user)
    if not NurseRosterEntry.objects.filter(operational_day=day).exists():
        sync_roster_with_duty(day, actor=request.user)
    rotation = rotation_board(day)
    me = next((r for r in rotation["rows"] if r["entry"].nurse_id == request.user.pk), None)
    available = [r for r in rotation["rows"] if r["entry"].availability == Availability.TERSEDIA]
    queue_place = next((i for i, r in enumerate(available, 1) if me and r["entry"].pk == me["entry"].pk), None)
    procedures = (ProcedureAssignment.objects.filter(operational_day=day, nurse=request.user)
                  .exclude(status=ProcedureStatus.BATAL).select_related("category").order_by("-assigned_at"))
    tallies = NurseActionTally.objects.filter(operational_day=day, nurse=request.user).select_related("entered_by")
    form = NurseActionTallyForm(nurse_queryset=User.objects.filter(pk=request.user.pk),
                                initial={"nurse": request.user.pk})
    return render(request, "nurses/mine.html", {
        "day": day, "me": me, "next_entry": rotation["next"], "reason": rotation["reason"],
        "queue_place": queue_place, "procedures": procedures, "tallies": tallies,
        "today_total": daily_tally(day).get(request.user.pk, 0),
        "month_total": monthly_tally([request.user.pk], day.date)[request.user.pk],
        "tally_form": form, "rm_prefix": rm_prefix(clinic),
    })
