"""View checklist pembukaan dan review (PRD 8.2)."""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.permissions import can_manage_templates, can_review_checklist, require
from core.services import active_clinic, get_or_create_day, opening_progress

from .models import ChecklistResponse, ChecklistRun, ChecklistTemplate, PROBLEM_RESULTS, ResponseResult
from .services import (
    create_action_item_from_response,
    create_damage_from_response,
    record_response,
    review_run,
    run_progress,
)


def _current_day(request):
    clinic = active_clinic()
    day, _ = get_or_create_day(clinic, user=request.user)
    return day


@login_required
def opening_index(request):
    day = _current_day(request)
    runs = ChecklistRun.objects.filter(operational_day=day).prefetch_related("responses")
    cards = [{"run": run, "progress": run_progress(run)} for run in runs]
    return render(
        request,
        "checklists/index.html",
        {"day": day, "cards": cards, "progress": opening_progress(day)},
    )


@login_required
def run_detail(request, run_id: int):
    run = get_object_or_404(ChecklistRun, pk=run_id)
    responses = run.responses.select_related("checked_by").all()
    only_problems = request.GET.get("masalah") == "1"
    if only_problems:
        responses = [r for r in responses if r.is_problem or r.result == ResponseResult.BELUM]

    categories: dict[str, list] = {}
    for r in responses:
        categories.setdefault(r.category or "Umum", []).append(r)

    return render(
        request,
        "checklists/run.html",
        {
            "run": run,
            "categories": categories,
            "progress": run_progress(run),
            "results": ResponseResult.choices,
            "only_problems": only_problems,
        },
    )


@login_required
@require_POST
def save_response(request, pk: int):
    response = get_object_or_404(ChecklistResponse, pk=pk)
    try:
        record_response(
            response,
            user=request.user,
            result=request.POST.get("hasil", ""),
            quantity=request.POST.get("jumlah") or None,
            note=request.POST.get("catatan", ""),
            expected_version=int(request.POST.get("versi") or response.version),
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
    response = get_object_or_404(ChecklistResponse, pk=pk)
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
    response = get_object_or_404(ChecklistResponse, pk=pk)
    try:
        create_action_item_from_response(response, request.user)
        messages.success(request, "Tindak lanjut kekurangan dibuat.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("checklists:run", run_id=response.run_id)


@login_required
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
    run = get_object_or_404(ChecklistRun, pk=run_id)
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
    clinic = active_clinic()
    templates = ChecklistTemplate.objects.filter(clinic=clinic).prefetch_related("items")
    return render(request, "checklists/templates.html", {"templates": templates})
