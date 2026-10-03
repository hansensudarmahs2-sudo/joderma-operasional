"""Halaman Jejak kehadiran: daftar jejak, ringkasan per staf, IP lazim, dan perangkat dikenal."""
from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Max
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from audit.models import AuditAction
from audit.services import log_create, log_event, log_update, snapshot
from core.models import local_today
from core.permissions import is_aom, require, user_clinic_queryset
from direktur.dashboard import can_view_overview

from .models import Confidence, Event, KnownDevice, Network, PresenceStamp
from .services import LEARN_DAYS, LEARN_MIN_STRONG

PAGE_SIZE = 100


def _date(raw, default):
    try:
        return dt.date.fromisoformat((raw or "").strip())
    except ValueError:
        return default


@login_required
@require(can_view_overview)
def index(request):
    user = request.user
    today = local_today()
    clinics = list(user_clinic_queryset(user).order_by("id"))
    start = _date(request.GET.get("dari"), today - dt.timedelta(days=6))
    end = _date(request.GET.get("sampai"), today)
    tz = timezone.get_current_timezone()
    qs = PresenceStamp.objects.filter(
        created_at__gte=timezone.make_aware(dt.datetime.combine(start, dt.time.min), tz),
        created_at__lt=timezone.make_aware(dt.datetime.combine(end + dt.timedelta(days=1), dt.time.min), tz),
    ).select_related("user", "clinic", "device")
    raw = request.GET.get("cabang", "")
    clinic = next((c for c in clinics if raw.isdigit() and c.pk == int(raw)), None)
    if clinic:
        qs = qs.filter(clinic=clinic)
    else:
        from django.db.models import Q

        qs = qs.filter(Q(clinic__in=clinics) | Q(clinic__isnull=True))
    staff_id = request.GET.get("staf", "")
    if staff_id.isdigit():
        qs = qs.filter(user_id=int(staff_id))
    event = request.GET.get("kejadian", "")
    if event in dict(Event.choices):
        qs = qs.filter(event=event)
    if request.GET.get("unduh") == "csv":
        label = request.GET.get("label", "")
        if label in dict(Confidence.choices):
            qs = qs.filter(confidence=label)
        return _csv(request, qs, start, end)
    # Ringkasan per staf memakai saringan yang sama kecuali label.
    per_user: dict = defaultdict(Counter)
    names = {}
    for row in qs.order_by().values("user_id", "user__display_name", "user__username", "confidence").annotate(
            n=Count("id")):
        per_user[row["user_id"]][row["confidence"]] += row["n"]
        names[row["user_id"]] = row["user__display_name"] or row["user__username"]
    summary = []
    for uid, c in per_user.items():
        total = sum(c.values())
        good = c[Confidence.KUAT] + c[Confidence.SEDANG]
        summary.append({"name": names[uid], "id": uid, "total": total, "kuat": c[Confidence.KUAT],
                        "sedang": c[Confidence.SEDANG], "lemah": c[Confidence.LEMAH],
                        "percent": round(good * 100 / total) if total else 0})
    summary.sort(key=lambda r: (r["percent"], r["name"]))
    label = request.GET.get("label", "")
    if label in dict(Confidence.choices):
        qs = qs.filter(confidence=label)

    page = Paginator(qs.order_by("-created_at"), PAGE_SIZE).get_page(request.GET.get("hal"))
    params = request.GET.copy()
    params.pop("hal", None)
    params.pop("unduh", None)
    csv_params = params.copy()
    csv_params["unduh"] = "csv"
    csv_params.setdefault("dari", start.isoformat())
    csv_params.setdefault("sampai", end.isoformat())
    from accounts.models import User

    staff = User.objects.filter(presence_stamps__isnull=False).distinct().order_by("display_name", "username")
    return render(request, "jejak/index.html", {
        "page": page, "summary": summary, "clinics": clinics, "clinic": clinic, "start": start, "end": end,
        "staff": staff, "staff_id": int(staff_id) if staff_id.isdigit() else None,
        "events": Event.choices, "event": event, "labels": Confidence.choices, "label": label,
        "base_query": params.urlencode(), "total": page.paginator.count, "csv_query": csv_params.urlencode(),
    })


def usual_prefixes(clinics) -> list[dict]:
    """Kelompok IP yang sudah 'dipelajari' per cabang dari jejak Kuat."""
    since = timezone.now() - dt.timedelta(days=LEARN_DAYS)
    rows = (
        PresenceStamp.objects.filter(clinic__in=clinics, confidence=Confidence.KUAT, created_at__gte=since)
        .exclude(ip_prefix="")
        .values("clinic__name", "ip_prefix")
        .annotate(n=Count("id"), last=Max("created_at"))
        .order_by("clinic__name", "-n")
    )
    return [{**r, "usual": r["n"] >= LEARN_MIN_STRONG} for r in rows]


@login_required
@require(can_view_overview)
def devices(request):
    user = request.user
    can_edit = is_aom(user)
    clinics = list(user_clinic_queryset(user).order_by("id"))
    if request.method == "POST":
        if not can_edit:
            raise PermissionDenied("Hanya Direktur Operasional yang mengatur perangkat.")
        try:
            _save_device(request, clinics)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        return redirect("jejak:devices")
    known = list(KnownDevice.objects.select_related("clinic"))
    known_ips = {d.ip_address for d in known}
    # IP Tailscale yang pernah tercatat tetapi belum diberi nama: kandidat perangkat klinik.
    seen = (
        PresenceStamp.objects.filter(network=Network.TAILSCALE)
        .exclude(ip_address__in=known_ips)
        .values("ip_address", "device_kind")
        .annotate(n=Count("id"), last=Max("created_at"))
        .order_by("-last")
    )
    candidates = []
    for row in seen[:50]:
        users = list(
            PresenceStamp.objects.filter(ip_address=row["ip_address"]).values_list("user__username", flat=True)
            .distinct()[:6]
        )
        candidates.append({**row, "users": users})
    return render(request, "jejak/devices.html", {
        "known": known, "candidates": candidates, "clinics": clinics, "can_edit": can_edit,
        "prefixes": usual_prefixes(clinics), "learn_min": LEARN_MIN_STRONG, "learn_days": LEARN_DAYS,
    })


def _save_device(request, clinics):
    import ipaddress

    post = request.POST
    if post.get("aksi") == "hapus":
        device = get_object_or_404(KnownDevice, pk=post.get("id"))
        log_event(action=AuditAction.CANCEL, entity_type="knowndevice", entity_id=device.pk,
                  entity_label=str(device), actor=request.user, before={"ip": device.ip_address})
        device.delete()
        messages.warning(request, "Perangkat dihapus dari daftar.")
        return
    ip = (post.get("ip") or "").strip()
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        raise ValidationError("Alamat IP tidak valid.")
    name = (post.get("nama") or "").strip()
    if not name:
        raise ValidationError("Nama perangkat wajib diisi.")
    raw = post.get("cabang", "")
    clinic = next((c for c in clinics if raw.isdigit() and c.pk == int(raw)), None)
    device = KnownDevice.objects.filter(ip_address=ip).first()
    data = {"name": name[:80], "clinic": clinic, "is_clinic_device": post.get("klinik") == "1",
            "note": (post.get("catatan") or "").strip()[:200]}
    if device:
        before = snapshot(device)
        for k, v in data.items():
            setattr(device, k, v)
        device.save()
        log_update(device, before, actor=request.user)
        messages.success(request, f"Perangkat {device.name} diperbarui.")
    else:
        device = KnownDevice.objects.create(ip_address=ip, **data)
        log_create(device, actor=request.user)
        messages.success(request, f"Perangkat {device.name} ditambahkan.")


def _csv(request, qs, start, end):
    """Unduh jejak sesuai saringan (UTF-8 dengan BOM, terbuka di Excel). Tercatat EXPORT di audit."""
    import csv

    from django.http import StreamingHttpResponse

    from audit.views import _cell, _Echo

    total = qs.count()
    log_event(action=AuditAction.EXPORT, entity_type="presencestamp",
              entity_label=f"Ekspor jejak {total} baris", actor=request.user,
              after={"filter": {k: v for k, v in request.GET.items() if k != "unduh"}, "rows": total},
              request=request)
    writer = csv.writer(_Echo())

    def rows():
        yield "\ufeff"
        yield writer.writerow([
            "Waktu (WIB)", "Username", "Nama", "Cabang", "Kejadian", "Label", "Alasan label", "Alamat IP",
            "Kelompok IP", "Jaringan", "Perangkat dikenal", "Jenis perangkat", "Status lokasi", "Lintang",
            "Bujur", "Akurasi (m)", "Jarak ke klinik (m)", "Jenis data", "ID data", "Perangkat (user agent)",
        ])
        for s in qs.order_by("created_at", "id").iterator(chunk_size=500):
            yield writer.writerow([
                timezone.localtime(s.created_at).strftime("%Y-%m-%d %H:%M:%S"), _cell(s.user.username),
                _cell(str(s.user)), _cell(s.clinic.name if s.clinic else ""), s.get_event_display(),
                s.get_confidence_display(), _cell(s.reason), s.ip_address or "", s.ip_prefix,
                s.get_network_display() if s.network else "", _cell(s.device.name if s.device else ""),
                _cell(s.device_kind), s.get_geo_status_display() if s.geo_status else "",
                s.latitude if s.latitude is not None else "", s.longitude if s.longitude is not None else "",
                s.accuracy_m if s.accuracy_m is not None else "", s.distance_m if s.distance_m is not None else "",
                s.entity_type, s.entity_id or "", _cell(s.user_agent),
            ])

    stamp = timezone.localtime().strftime("%Y%m%d-%H%M")
    response = StreamingHttpResponse(rows(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="jejak_{start:%Y-%m-%d}_{end:%Y-%m-%d}_{stamp}.csv"'
    )
    return response
