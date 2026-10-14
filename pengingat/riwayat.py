"""Riwayat Pengingat Harian DO (kebutuhan 3.4): log "Sudah diingatkan", disaring dan diekspor CSV.

Riwayat ini juga bukti sosialisasi untuk akreditasi, jadi hanya berisi yang benar-benar
diingatkan; Tunda dan Lewati tidak masuk (keduanya ada di jejak audit). CSV mengikuti pola
unduh lain di repo: BOM untuk Excel, sel teks lewat `audit.views._cell`, dan tercatat di audit.
"""
from __future__ import annotations

import csv
import datetime as dt

from django.db.models import Q
from django.http import HttpResponse

from audit.models import AuditAction
from audit.services import log_event
from audit.views import _cell
from core.models import Clinic

from .models import Diingatkan, Materi

KOLOM = ["Tanggal", "Kode", "Materi", "Cabang", "Saluran", "Catatan", "Oleh"]


def parse_filters(params) -> dict:
    """Saringan dari query string; nilai tak dikenal diabaikan (tidak menyaring)."""
    out = {"materi": None, "cabang": None, "bulan": None}
    raw = params.get("materi", "")
    if raw.isdigit():
        out["materi"] = Materi.objects.filter(pk=int(raw)).first()
    raw = params.get("cabang", "")
    if raw.isdigit():
        out["cabang"] = Clinic.objects.filter(pk=int(raw)).first()
    raw = params.get("bulan", "")
    try:
        out["bulan"] = dt.datetime.strptime(raw, "%Y-%m").date()
    except ValueError:
        pass
    return out


def query(filters: dict):
    qs = Diingatkan.objects.select_related("materi", "clinic", "oleh")
    if filters["materi"]:
        qs = qs.filter(materi=filters["materi"])
    if filters["cabang"]:
        # Pengingat untuk kedua cabang juga berlaku di cabang yang disaring.
        qs = qs.filter(Q(clinic=filters["cabang"]) | Q(clinic__isnull=True))
    if filters["bulan"]:
        qs = qs.filter(tanggal__year=filters["bulan"].year, tanggal__month=filters["bulan"].month)
    return qs.order_by("-tanggal", "-id")


def cabang_label(log: Diingatkan) -> str:
    return log.clinic.name if log.clinic else "Jemur dan Citraland"


def csv_response(request, filters: dict) -> HttpResponse:
    rows = list(query(filters))
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    suffix = f"-{filters['bulan']:%Y-%m}" if filters["bulan"] else ""
    response["Content-Disposition"] = f'attachment; filename="riwayat-pengingat{suffix}.csv"'
    response.write("﻿")
    writer = csv.writer(response)
    writer.writerow(KOLOM)
    for log in rows:
        writer.writerow([log.tanggal.isoformat()] + [_cell(v) for v in (
            log.materi.kode, log.materi.judul, cabang_label(log), log.get_saluran_display(), log.catatan, str(log.oleh),
        )])
    log_event(action=AuditAction.EXPORT, entity_type="pengingat.riwayat", entity_label="Ekspor riwayat pengingat",
              actor=request.user, after={
                  "materi": filters["materi"].kode if filters["materi"] else "",
                  "cabang": filters["cabang"].name if filters["cabang"] else "",
                  "bulan": f"{filters['bulan']:%Y-%m}" if filters["bulan"] else "", "baris": len(rows)})
    return response
