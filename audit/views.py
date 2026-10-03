"""Audit log read-only untuk supervisor/owner/admin berizin (PRD 11.3), dan ekspor CSV."""
from __future__ import annotations

import csv
import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import StreamingHttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date

from core.permissions import can_view_audit, has_admin_full_access, is_aom, require

from .models import AuditAction, AuditEvent
from .services import log_event

FILTER_KEYS = ("aktor", "aksi", "entitas", "dari", "sampai")


def can_export_audit(user) -> bool:
    """Ekspor audit: Direktur Operasional dan admin berakses penuh (keputusan 3 Okt 2026).

    Supervisor tetap dapat membaca audit di layar, tetapi tidak mengunduh seluruh isinya, karena
    nilai sebelum/sesudah dapat memuat nominal kas dan nama pasien.
    """
    return is_aom(user) or has_admin_full_access(user)


def _filtered(request):
    qs = AuditEvent.objects.select_related("actor")
    f = {k: (request.GET.get(k) or "").strip() for k in FILTER_KEYS}
    if f["aktor"]:
        qs = qs.filter(Q(actor_label__icontains=f["aktor"]) | Q(actor__username__icontains=f["aktor"])
                       | Q(actor__display_name__icontains=f["aktor"]))
    if f["aksi"]:
        qs = qs.filter(action=f["aksi"])
    if f["entitas"]:
        qs = qs.filter(Q(entity_type__icontains=f["entitas"]) | Q(entity_label__icontains=f["entitas"]))
    date_from, date_to = parse_date(f["dari"]), parse_date(f["sampai"])
    if date_from:
        qs = qs.filter(occurred_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(occurred_at__date__lte=date_to)
    return qs, f


def _query(filters: dict) -> str:
    from urllib.parse import urlencode

    return urlencode({k: v for k, v in filters.items() if v})


@login_required
@require(can_view_audit)
def log_view(request):
    qs, filters = _filtered(request)
    page = Paginator(qs, 50).get_page(request.GET.get("hal"))
    return render(
        request,
        "audit/log.html",
        {
            "page": page,
            "actions": AuditAction.choices,
            "filters": filters,
            "query": _query(filters),
            "can_export": can_export_audit(request.user),
            "total": page.paginator.count,
        },
    )


def _cell(value) -> str:
    """Teks aman untuk spreadsheet: nilai yang diawali = + - @ tidak dijalankan sebagai rumus."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


def _json(value) -> str:
    return "" if value in (None, {}, []) else json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


class _Echo:
    def write(self, value):
        return value


@login_required
def export_view(request):
    """Unduh audit sesuai saringan halaman Audit sebagai CSV (UTF-8, terbuka di Excel)."""
    if not can_export_audit(request.user):
        raise PermissionDenied("Ekspor audit hanya untuk Direktur Operasional dan admin berakses penuh.")
    qs, filters = _filtered(request)
    total = qs.count()
    log_event(action=AuditAction.EXPORT, entity_type="audit", entity_label=f"Ekspor audit {total} baris",
              actor=request.user, after={"filter": {k: v for k, v in filters.items() if v}, "rows": total},
              request=request)
    labels = dict(AuditAction.choices)
    writer = csv.writer(_Echo())

    def rows():
        yield "﻿"  # BOM: Excel membaca UTF-8 dengan benar
        yield writer.writerow(["Waktu (WIB)", "Pengguna", "Username", "Aksi", "Kode aksi", "Jenis data",
                               "ID data", "Data", "Alasan", "Sebelum", "Sesudah", "Alamat IP", "Perangkat",
                               "ID permintaan"])
        for e in qs.order_by("occurred_at", "id").iterator(chunk_size=500):
            yield writer.writerow([
                timezone.localtime(e.occurred_at).strftime("%Y-%m-%d %H:%M:%S"),
                _cell(e.actor_label or (str(e.actor) if e.actor else "")),
                _cell(e.actor.username if e.actor else ""),
                labels.get(e.action, e.action), e.action, _cell(e.entity_type), _cell(e.entity_id),
                _cell(e.entity_label), _cell(e.reason), _cell(_json(e.before_json)), _cell(_json(e.after_json)),
                e.ip_address or "", _cell(e.user_agent), e.correlation_id,
            ])

    stamp = timezone.localtime().strftime("%Y%m%d-%H%M")
    span = "_".join(v for v in (filters["dari"], filters["sampai"]) if v) or "semua"
    response = StreamingHttpResponse(rows(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="audit_{span}_{stamp}.csv"'
    return response
