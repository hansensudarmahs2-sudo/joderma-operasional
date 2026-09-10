"""View inti: dashboard, action item, lampiran privat, admin konfigurasi."""
from __future__ import annotations

import mimetypes

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from audit.models import AuditAction
from audit.services import log_event
from breaks.services import upcoming_breaks
from cash.services import cash_summary
from issues.services import issue_counters
from nurses.models import Availability, NurseRosterEntry
from queueing.services import queue_summary

from .models import (
    ActionItem,
    ActionItemStatus,
    Attachment,
    ClinicConfig,
    DEFAULT_CONFIG,
    OperationalDay,
    local_today,
)
from .permissions import (
    can_close_day,
    can_manage_config,
    can_view_cash_amounts,
    is_owner,
    is_supervisor,
    require,
)
from .services import (
    active_clinic,
    close_day,
    closing_blockers,
    get_or_create_day,
    mark_ready,
    open_day,
    opening_progress,
    reopen_day,
    start_closing,
)


def health(request):
    """Health endpoint privat tanpa data sensitif (PRD 15.5)."""
    return JsonResponse({"status": "ok", "time": timezone.now().isoformat()})


def permission_denied(request, exception=None):
    return render(request, "403.html", {"message": str(exception) or "Akses ditolak."}, status=403)


@login_required
def dashboard(request):
    clinic = active_clinic()
    user = request.user

    date_str = request.GET.get("tanggal")
    day = None
    if date_str and (is_supervisor(user) or is_owner(user)):
        day = OperationalDay.objects.filter(clinic=clinic, date=date_str).first()
    if day is None:
        day = OperationalDay.today_for(clinic)

    if day is None and request.GET.get("buat") == "1":
        day, _ = get_or_create_day(clinic, user=user)
        messages.success(request, "Sesi hari operasional dibuat.")
        return redirect("core:dashboard")

    context = {
        "clinic": clinic,
        "day": day,
        "today": local_today(),
        "can_view_cash": can_view_cash_amounts(user),
        "can_close": can_close_day(user),
        "is_supervisor": is_supervisor(user),
    }

    if day:
        context.update(
            {
                "progress": opening_progress(day),
                "cash": cash_summary(day) if can_view_cash_amounts(user) else None,
                "queue": queue_summary(day),
                "next_nurse": NurseRosterEntry.objects.filter(
                    operational_day=day, availability=Availability.TERSEDIA
                )
                .select_related("nurse")
                .order_by("position")
                .first(),
                "breaks_soon": upcoming_breaks(clinic, timezone.now(), 60)[:8],
                "issues": issue_counters(clinic),
                "closing_blockers": closing_blockers(day) if can_close_day(user) else [],
                "my_actions": ActionItem.objects.filter(
                    clinic=clinic,
                    owner=user,
                    status__in=[ActionItemStatus.BARU, ActionItemStatus.DIKERJAKAN],
                ).order_by("due_at")[:10],
                "my_issues": user.issue_assignments.filter(active=True).select_related("issue")[:10],
            }
        )
    return render(request, "core/dashboard.html", context)


@login_required
@require_POST
def day_action(request, pk: int):
    day = get_object_or_404(OperationalDay, pk=pk)
    action = request.POST.get("aksi")
    reason = request.POST.get("alasan", "")
    user = request.user

    try:
        if action == "ready":
            mark_ready(day, user)
            messages.success(request, "Hari ditandai siap.")
        elif action == "ready_issues":
            if not is_supervisor(user):
                raise PermissionDenied("Hanya supervisor yang dapat menetapkan siap dengan catatan.")
            mark_ready(day, user, with_issues=True, reason=reason)
            messages.warning(request, "Hari ditandai siap dengan catatan.")
        elif action == "open":
            open_day(day, user)
            messages.success(request, "Klinik dibuka.")
        elif action == "closing":
            if not can_close_day(user):
                raise PermissionDenied("Hanya supervisor yang dapat memulai penutupan.")
            start_closing(day, user)
            messages.info(request, "Proses penutupan dimulai.")
        elif action == "close":
            if not can_close_day(user):
                raise PermissionDenied("Hanya supervisor yang dapat menutup hari.")
            close_day(day, user, override_reason=reason)
            messages.success(request, "Hari operasional ditutup.")
        elif action == "reopen":
            if not can_close_day(user):
                raise PermissionDenied("Hanya supervisor yang dapat membuka kembali hari.")
            reopen_day(day, user, reason=reason)
            messages.warning(request, "Hari operasional dibuka kembali.")
        else:
            messages.error(request, "Aksi tidak dikenali.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("core:dashboard")


@login_required
def action_items(request):
    clinic = active_clinic()
    status = request.GET.get("status", "")
    qs = ActionItem.objects.filter(clinic=clinic).select_related("owner")
    if status:
        qs = qs.filter(status=status)
    if not (is_supervisor(request.user) or is_owner(request.user)):
        qs = qs.filter(owner=request.user)
    return render(
        request,
        "core/action_items.html",
        {"items": qs[:200], "status": status, "statuses": ActionItemStatus.choices},
    )


@login_required
@require_POST
def action_item_update(request, pk: int):
    item = get_object_or_404(ActionItem, pk=pk)
    if not (is_supervisor(request.user) or item.owner_id == request.user.pk):
        raise PermissionDenied("Anda bukan penanggung jawab action item ini.")
    from audit.services import log_update, snapshot

    before = snapshot(item)
    item.status = request.POST.get("status", item.status)
    item.progress_note = request.POST.get("catatan", item.progress_note)
    item.save()
    log_update(item, before, actor=request.user)
    messages.success(request, "Action item diperbarui.")
    return redirect("core:action_items")


@login_required
def attachment_download(request, pk: int):
    """Lampiran selalu melewati pemeriksaan izin aplikasi (PRD 9.3, 20.7)."""
    attachment = get_object_or_404(Attachment, pk=pk)

    if attachment.entity_type == "issue":
        from issues.models import Issue

        issue = Issue.objects.filter(pk=attachment.entity_id).first()
        if issue is None:
            raise Http404
        from .permissions import can_view_restricted_issue

        if not can_view_restricted_issue(request.user, issue):
            raise PermissionDenied("Anda tidak memiliki akses ke lampiran catatan terbatas ini.")

    log_event(
        action=AuditAction.DOWNLOAD_ATTACHMENT,
        entity_type="attachment",
        entity_id=attachment.pk,
        entity_label=attachment.original_name,
        actor=request.user,
        request=request,
    )
    content_type = attachment.mime_type or mimetypes.guess_type(attachment.original_name)[0]
    return FileResponse(
        attachment.file.open("rb"),
        as_attachment=True,
        filename=attachment.original_name,
        content_type=content_type or "application/octet-stream",
    )


@login_required
@require(can_manage_config)
def config_page(request):
    clinic = active_clinic()
    if request.method == "POST":
        key = request.POST.get("kunci", "").strip()
        raw = request.POST.get("nilai", "").strip()
        if key:
            import json

            try:
                value = json.loads(raw)
            except ValueError:
                value = raw
            before = {"key": key, "value": ClinicConfig.get(clinic, key)}
            ClinicConfig.set(clinic, key, value, user=request.user)
            log_event(
                action=AuditAction.CONFIG_CHANGED,
                entity_type="clinicconfig",
                entity_id=key,
                entity_label=key,
                actor=request.user,
                before=before,
                after={"key": key, "value": value},
            )
            messages.success(request, f"Konfigurasi {key} disimpan.")
        return redirect("core:config")

    overrides = {c.key: c.value for c in ClinicConfig.objects.filter(clinic=clinic)}
    rows = []
    for key, default in DEFAULT_CONFIG.items():
        rows.append(
            {
                "key": key,
                "default": default,
                "value": overrides.get(key, default),
                "overridden": key in overrides,
            }
        )
    return render(request, "core/config.html", {"rows": rows, "clinic": clinic})
