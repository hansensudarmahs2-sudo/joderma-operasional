"""Audit log read-only untuk supervisor/owner/admin berizin (PRD 11.3)."""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render
from django.utils.dateparse import parse_date

from core.permissions import can_view_audit, require

from .models import AuditAction, AuditEvent


@login_required
@require(can_view_audit)
def log_view(request):
    qs = AuditEvent.objects.select_related("actor")

    actor = request.GET.get("aktor") or ""
    action = request.GET.get("aksi") or ""
    entity = request.GET.get("entitas") or ""
    date_from = parse_date(request.GET.get("dari") or "")
    date_to = parse_date(request.GET.get("sampai") or "")

    if actor:
        qs = qs.filter(Q(actor_label__icontains=actor) | Q(actor__username__icontains=actor))
    if action:
        qs = qs.filter(action=action)
    if entity:
        qs = qs.filter(entity_type__icontains=entity)
    if date_from:
        qs = qs.filter(occurred_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(occurred_at__date__lte=date_to)

    page = Paginator(qs, 50).get_page(request.GET.get("hal"))
    return render(
        request,
        "audit/log.html",
        {
            "page": page,
            "actions": AuditAction.choices,
            "filters": {
                "aktor": actor,
                "aksi": action,
                "entitas": entity,
                "dari": request.GET.get("dari", ""),
                "sampai": request.GET.get("sampai", ""),
            },
        },
    )
