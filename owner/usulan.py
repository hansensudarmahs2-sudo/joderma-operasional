"""Usulan Direktur Operasional ke Owner atas inisiatif sendiri (tahap 4, 7 Okt 2026).

Aturan di sini ditegakkan server-side; tombol yang disembunyikan di tampilan bukan kontrol akses.
"""
from __future__ import annotations

import datetime as dt

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from audit.models import AuditAction
from audit.services import log_create, log_event, log_update, snapshot
from core.models import local_today
from core.permissions import is_aom, is_owner

from .models import Usulan, UsulanCatatan, UsulanKind, UsulanStatus
from .services import TITLE_MAX, _directors, _owners

BODY_MAX = 300
VERDICTS = ("setuju", "tolak", "rapat")


def can_view_usulan(user) -> bool:
    return is_owner(user) or is_aom(user)


def _notify(people, *, actor, usulan: Usulan, type_code: str, title: str, body: str = "") -> None:
    from notifications.services import notify_user

    seen = set()
    for person in people:
        if person is None or person.pk in seen or person.pk == getattr(actor, "pk", None):
            continue
        seen.add(person.pk)
        notify_user(
            person, type_code=type_code, title=title, body=(body or "")[:BODY_MAX],
            entity_ref=f"usulan#{usulan.pk}", url_name="owner:usulan_detail", url_args=[usulan.pk],
        )


def _rupiah(amount: int) -> str:
    return f"Rp{amount:,}".replace(",", ".")


@transaction.atomic
def create_usulan(*, actor, kind: str, title: str, description: str, amount: int | None = None,
                  clinic=None, needed_by: dt.date | None = None) -> Usulan:
    if not is_aom(actor):
        raise PermissionDenied("Usulan dibuat oleh Direktur Operasional.")
    if kind not in dict(UsulanKind.choices):
        raise ValidationError("Jenis usulan tidak dikenal.")
    title = (title or "").strip()
    if not title:
        raise ValidationError("Judul wajib diisi.")
    if len(title) > TITLE_MAX:
        raise ValidationError(f"Judul terlalu panjang (maks. {TITLE_MAX} karakter); uraiannya tulis di kolom uraian.")
    description = (description or "").strip()
    if not description:
        raise ValidationError("Uraian wajib diisi.")
    if kind == UsulanKind.LAPORAN:
        amount = None
    elif amount is not None and amount < 0:
        raise ValidationError("Nominal tidak boleh negatif.")
    if needed_by is not None and needed_by < local_today():
        raise ValidationError("Tanggal tidak boleh sebelum hari ini.")
    usulan = Usulan.objects.create(
        kind=kind, title=title, description=description, amount=amount, clinic=clinic, needed_by=needed_by,
        status=UsulanStatus.MENUNGGU if kind == UsulanKind.PERSETUJUAN else UsulanStatus.TERKIRIM,
        created_by=actor,
    )
    log_create(usulan, actor=actor, label=title)
    detail = [UsulanKind(kind).label] + ([_rupiah(amount)] if amount else []) + [f"dari {actor}"]
    _notify(_owners(), actor=actor, usulan=usulan, type_code="USULAN_NEW",
            title=f"Usulan Direktur: {title}", body=" · ".join(detail))
    return usulan


@transaction.atomic
def decide_usulan(usulan: Usulan, *, actor, verdict: str, note: str = "") -> Usulan:
    """Owner menjawab usulan persetujuan: setuju, tolak (alasan wajib), atau bahas di rapat."""
    from direktur.models import Decider, Decision

    if not is_owner(actor):
        raise PermissionDenied("Hanya Owner / Direktur Utama yang memutuskan usulan.")
    if verdict not in VERDICTS:
        raise ValidationError("Pilihan keputusan tidak dikenal.")
    usulan = Usulan.objects.select_for_update().get(pk=usulan.pk)
    if usulan.kind != UsulanKind.PERSETUJUAN:
        raise ValidationError("Laporan tidak diputuskan; cukup ditandai sudah dibaca.")
    if usulan.status != UsulanStatus.MENUNGGU:
        raise ValidationError("Usulan ini sudah diputuskan atau dibatalkan.")
    note = (note or "").strip()
    if verdict == "tolak" and not note:
        raise ValidationError("Tulis alasan penolakan.")
    before = snapshot(usulan)
    if verdict == "rapat":
        parts = [usulan.description]
        if usulan.amount:
            parts.append(f"Nominal: {_rupiah(usulan.amount)}")
        if note:
            parts.append(f"Catatan Owner ({actor}): {note}")
        decision = Decision.objects.create(
            clinic=usulan.clinic, reference=f"US-{usulan.pk}", title=usulan.title,
            background="\n\n".join(parts), decider=Decider.RAPAT_BERSAMA, created_by=usulan.created_by,
        )
        log_create(decision, actor=actor)
        usulan.decision = decision
        usulan.status = UsulanStatus.RAPAT
    else:
        usulan.status = UsulanStatus.DISETUJUI if verdict == "setuju" else UsulanStatus.DITOLAK
    usulan.decided_by = actor
    usulan.decided_at = timezone.now()
    usulan.decision_note = note
    usulan.save()
    log_update(usulan, before, actor=actor,
               action=AuditAction.APPROVE if verdict == "setuju" else AuditAction.UPDATE)
    _notify([usulan.created_by, *_directors()], actor=actor, usulan=usulan, type_code="USULAN_DECIDED",
            title=f"Usulan {UsulanStatus(usulan.status).label.lower()}: {usulan.title}", body=note)
    return usulan


@transaction.atomic
def mark_read(usulan: Usulan, *, actor) -> Usulan:
    """Owner menandai laporan sudah dibaca. Pembaca pertama yang tercatat."""
    if not is_owner(actor):
        raise PermissionDenied("Hanya Owner / Direktur Utama yang menandai laporan dibaca.")
    usulan = Usulan.objects.select_for_update().get(pk=usulan.pk)
    if usulan.kind != UsulanKind.LAPORAN:
        raise ValidationError("Hanya laporan yang ditandai dibaca.")
    if usulan.status == UsulanStatus.DIBACA:
        return usulan
    if usulan.status != UsulanStatus.TERKIRIM:
        raise ValidationError("Laporan ini sudah dibatalkan.")
    before = snapshot(usulan)
    usulan.status = UsulanStatus.DIBACA
    usulan.read_by = actor
    usulan.read_at = timezone.now()
    usulan.save()
    log_update(usulan, before, actor=actor)
    _notify([usulan.created_by], actor=actor, usulan=usulan, type_code="USULAN_READ",
            title=f"Laporan dibaca Owner: {usulan.title}", body=f"oleh {actor}")
    return usulan


@transaction.atomic
def add_usulan_note(usulan: Usulan, *, actor, note: str) -> UsulanCatatan:
    if not can_view_usulan(actor):
        raise PermissionDenied("Catatan hanya dari Owner atau Direktur Operasional.")
    note = (note or "").strip()
    if not note:
        raise ValidationError("Catatan kosong.")
    row = UsulanCatatan.objects.create(usulan=usulan, author=actor, note=note)
    log_event(action=AuditAction.CREATE, entity_type="usulancatatan", entity_id=row.pk, entity_label=usulan.title,
              actor=actor, after={"usulan": usulan.pk, "note": note[:300]})
    # Owner menulis -> pembuat + semua Direktur; Direktur menulis -> semua Owner.
    if is_owner(actor) and not is_aom(actor):
        people = [usulan.created_by, *_directors()]
    else:
        people = list(_owners())
    _notify(people, actor=actor, usulan=usulan, type_code="USULAN_NOTE",
            title=f"Catatan di usulan: {usulan.title}", body=f"{actor}: {note}")
    return row


@transaction.atomic
def cancel_usulan(usulan: Usulan, *, actor, reason: str) -> Usulan:
    if not is_aom(actor):
        raise PermissionDenied("Hanya Direktur Operasional yang membatalkan usulan.")
    usulan = Usulan.objects.select_for_update().get(pk=usulan.pk)
    if not usulan.is_open:
        raise ValidationError("Usulan ini sudah diputuskan atau dibatalkan.")
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("Tulis alasan pembatalan.")
    before = snapshot(usulan)
    usulan.status = UsulanStatus.DIBATALKAN
    usulan.cancelled_by = actor
    usulan.cancelled_at = timezone.now()
    usulan.cancel_reason = reason
    usulan.save()
    log_update(usulan, before, actor=actor, reason=reason)
    _notify(_owners(), actor=actor, usulan=usulan, type_code="USULAN_CANCELLED",
            title=f"Usulan dibatalkan: {usulan.title}", body=reason)
    return usulan


def usulan_awaiting(user) -> list[dict]:
    """Kartu Owner "Usulan Direktur": usulan yang masih terbuka, terlambat dulu lalu yang terlama."""
    if not is_owner(user):
        return []
    today = local_today()
    rows = [
        {"usulan": u, "late": u.is_overdue(today),
         "age_days": (today - timezone.localtime(u.created_at).date()).days}
        for u in Usulan.objects.filter(status__in=(UsulanStatus.MENUNGGU, UsulanStatus.TERKIRIM))
        .select_related("created_by", "clinic")
    ]
    rows.sort(key=lambda r: (not r["late"], r["usulan"].created_at))
    return rows
