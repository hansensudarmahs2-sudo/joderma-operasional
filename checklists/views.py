"""View checklist pembukaan dan review (PRD 8.2)."""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.permissions import (
    can_access_checklist_run,
    can_manage_templates,
    can_review_checklist,
    require,
)
from core.services import active_clinic, get_or_create_day

from .models import ChecklistResponse, ChecklistRun, ChecklistTemplate, PROBLEM_RESULTS, ResponseResult
from .services import (
    create_action_item_from_response,
    create_damage_from_response,
    record_response,
    review_run,
    run_progress,
)


def _current_day(request):
    clinic = active_clinic(request.user)
    day, _ = get_or_create_day(clinic, user=request.user)
    return day


def _accessible_run(request, run_id: int) -> ChecklistRun:
    run = get_object_or_404(ChecklistRun, pk=run_id)
    if not can_access_checklist_run(request.user, run):
        raise PermissionDenied("Anda tidak memiliki akses ke checklist cabang ini.")
    return run


def _accessible_response(request, pk: int) -> ChecklistResponse:
    response = get_object_or_404(ChecklistResponse, pk=pk)
    if not can_access_checklist_run(request.user, response.run):
        raise PermissionDenied("Anda tidak memiliki akses ke checklist cabang ini.")
    return response


@login_required
def opening_index(request):
    day = _current_day(request)
    runs = [
        run for run in ChecklistRun.objects.filter(operational_day=day).prefetch_related("responses")
        if can_access_checklist_run(request.user, run)
    ]
    cards = [{"run": run, "progress": run_progress(run)} for run in runs]
    total = sum(card["progress"]["total"] for card in cards)
    done = sum(card["progress"]["done"] for card in cards)
    progress = {
        "total": total,
        "done": done,
        "pending": total - done,
        "percent": round(done * 100 / total) if total else 0,
    }
    session_groups = []
    session_order = ("OPENING", "ANYTIME", "CLOSING")
    for session in session_order:
        session_cards = [card for card in cards if card["run"].session == session]
        if not session_cards:
            continue
        session_total = sum(card["progress"]["total"] for card in session_cards)
        session_done = sum(card["progress"]["done"] for card in session_cards)
        session_groups.append(
            {
                "key": session,
                "label": dict(ChecklistRun._meta.get_field("session").choices).get(session, session),
                "cards": session_cards,
                "done": session_done,
                "total": session_total,
                "percent": round(session_done * 100 / session_total) if session_total else 0,
            }
        )
    return render(
        request,
        "checklists/index.html",
        {
            "day": day,
            "cards": cards,
            "progress": progress,
            "session_groups": session_groups,
            "my_duties": _my_duties(request.user, day, runs),
        },
    )


def _my_duties(user, day, runs) -> list[dict]:
    """Porsi tugas pengguna hari ini beserta butir checklist yang menjadi bagiannya."""
    from jadwal.services import my_assignments

    duties = []
    for a in my_assignments(user, day.date).filter(clinic=day.clinic):
        items = [r for run in runs for r in run.responses.all() if r.portion == a.portion.code]
        done = sum(1 for r in items if r.result != ResponseResult.BELUM)
        run_ids = sorted({r.run_id for r in items})
        duties.append({"assignment": a, "total": len(items), "done": done, "run_id": run_ids[0] if run_ids else None})
    return duties


@login_required
def run_detail(request, run_id: int):
    run = _accessible_run(request, run_id)
    responses = run.responses.select_related("checked_by").all()
    only_problems = request.GET.get("masalah") == "1"
    if only_problems:
        responses = [r for r in responses if r.is_problem or r.result == ResponseResult.BELUM]

    from jadwal.services import assignments_by_portion

    day = run.operational_day
    by_portion = assignments_by_portion(day.clinic, day.date)
    only_mine = request.GET.get("saya") == "1"
    for r in responses:
        people = by_portion.get(r.portion, [])
        r.assignees = [a.user for a in people]
        r.is_mine = any(a.user_id == request.user.pk for a in people)
    if only_mine:
        responses = [r for r in responses if r.is_mine]

    categories: dict[str, list] = {}
    for r in responses:
        categories.setdefault(r.category or "Umum", []).append(r)
    category_groups = [
        {
            "name": category,
            "items": items,
            "pending": sum(1 for item in items if item.result == ResponseResult.BELUM),
            "problems": sum(1 for item in items if item.is_problem),
        }
        for category, items in categories.items()
    ]

    return render(
        request,
        "checklists/run.html",
        {
            "run": run,
            "categories": categories,
            "category_groups": category_groups,
            "progress": run_progress(run),
            "results": ResponseResult.choices,
            "only_problems": only_problems,
            "only_mine": only_mine,
        },
    )


@login_required
@require_POST
def save_response(request, pk: int):
    response = _accessible_response(request, pk)
    try:
        record_response(
            response,
            user=request.user,
            result=request.POST.get("hasil", ""),
            quantity=request.POST.get("jumlah") or None,
            selection=request.POST.get("pilihan", ""),
            note=request.POST.get("catatan", ""),
            expected_version=int(request.POST.get("versi") or response.version),
            reason=request.POST.get("alasan", ""),
        )
        messages.success(request, f"{response.label} disimpan.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    except ValueError:
        messages.error(request, "Jumlah harus berupa angka.")
    return redirect("checklists:run", run_id=response.run_id)


@login_required
@require_POST
def make_damage(request, pk: int):
    response = _accessible_response(request, pk)
    try:
        issue = create_damage_from_response(
            response, request.user, urgency=request.POST.get("urgensi") or None
        )
        messages.success(request, f"Laporan kerusakan {issue.number} dibuat.")
        return redirect("issues:detail", pk=issue.pk)
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("checklists:run", run_id=response.run_id)


@login_required
@require_POST
def make_action_item(request, pk: int):
    response = _accessible_response(request, pk)
    try:
        create_action_item_from_response(response, request.user)
        messages.success(request, "Tindak lanjut kekurangan dibuat.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("checklists:run", run_id=response.run_id)


@login_required
@require(can_review_checklist)
def review(request):
    day = _current_day(request)
    runs = ChecklistRun.objects.filter(operational_day=day).prefetch_related("responses")
    cards = []
    for run in runs:
        progress = run_progress(run)
        cards.append({"run": run, "progress": progress})
    return render(
        request,
        "checklists/review.html",
        {"day": day, "cards": cards, "can_review": can_review_checklist(request.user)},
    )


@login_required
@require(can_review_checklist)
@require_POST
def review_action(request, run_id: int):
    run = _accessible_run(request, run_id)
    accept = request.POST.get("aksi") == "pengecualian"
    try:
        review_run(
            run,
            request.user,
            accept_with_exception=accept,
            reason=request.POST.get("alasan", ""),
        )
        messages.success(request, "Review checklist disimpan.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("checklists:review")


@login_required
@require(can_manage_templates)
def template_list(request):
    clinic = active_clinic(request.user)
    templates = ChecklistTemplate.objects.filter(clinic=clinic).prefetch_related("items")
    return render(request, "checklists/templates.html", {"templates": templates})
