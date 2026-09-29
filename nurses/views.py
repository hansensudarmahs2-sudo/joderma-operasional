"""View giliran perawat: urutan, ledger, override (PRD 8.5)."""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import Role, User
from core.permissions import can_manage_roster, is_aom, is_supervisor, require
from core.services import active_clinic, get_or_create_day
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
            "rm_prefix": "JJ-" if clinic.code == "jemur-andayani" else "JC-" if clinic.code == "citraland" else "RM-",
        },
    )


@login_required
@require_POST
def create_tally(request):
    clinic = active_clinic(request.user)
    day, _ = get_or_create_day(clinic, user=request.user)
    form = NurseActionTallyForm(request.POST, nurse_queryset=_tally_nurses(day))
    if form.is_valid():
        tally = form.save(commit=False)
        tally.rm_number = normalize_rm_number(clinic, tally.rm_number)
        tally.operational_day = day
        tally.entered_by = request.user
        tally.save()
        after_tally(day, tally.nurse_id, amount=tally.tally, user=request.user)
        messages.success(request, "Tally tindakan disimpan.")
    else:
        messages.error(request, "Data tally belum lengkap atau tidak valid.")
    return redirect("nurses:board")


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
        return redirect("nurses:board")
    try:
        start_procedure(assignment, user=request.user)
        messages.success(request, "Tindakan dimulai.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("nurses:board")


@login_required
@require_POST
def complete(request, pk: int):
    assignment = get_object_or_404(ProcedureAssignment, pk=pk)
    if assignment.nurse_id != request.user.pk and not is_supervisor(request.user):
        messages.error(request, "Hanya perawat terkait atau supervisor yang dapat menyelesaikan.")
        return redirect("nurses:board")
    try:
        complete_procedure(assignment, user=request.user)
        messages.success(request, "Tindakan selesai; giliran berpindah.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("nurses:board")


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
        return redirect("nurses:board")
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
    return redirect("nurses:board")


@login_required
def ledger(request):
    clinic = active_clinic(request.user)
    day, _ = get_or_create_day(clinic, user=request.user)
    events = CommissionTurnEvent.objects.filter(operational_day=day).select_related(
        "nurse", "actor", "procedure_category"
    )
    return render(request, "nurses/ledger.html", {"day": day, "events": events})
