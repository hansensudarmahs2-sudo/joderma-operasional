"""Mencatat dan memberi label jejak kehadiran. Tidak pernah menggagalkan aksi pengguna."""
from __future__ import annotations

import datetime as dt
import ipaddress
import logging
import math
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from .models import Confidence, GeoStatus, KnownDevice, Network, PresenceStamp

log = logging.getLogger(__name__)

TAILSCALE_NET = ipaddress.ip_network("100.64.0.0/10")
LEARN_DAYS = 60          # jendela belajar "IP lazim cabang"
LEARN_MIN_STRONG = 3     # minimal jejak Kuat dari kelompok IP yang sama
MAX_TRUSTED_ACCURACY = 500  # akurasi lebih buruk dari ini tidak dipakai untuk label Kuat


def ip_prefix(ip: str | None) -> str:
    """Kelompok IP: /24 untuk IPv4, /64 untuk IPv6. IP Telkomsel berganti tetapi sering di kelompok sama."""
    if not ip:
        return ""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ""
    bits = 24 if addr.version == 4 else 64
    return str(ipaddress.ip_network(f"{addr}/{bits}", strict=False))


def network_of(ip: str | None) -> str:
    if not ip:
        return Network.TIDAK_DIKETAHUI
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return Network.TIDAK_DIKETAHUI
    if addr.version == 4 and addr in TAILSCALE_NET:
        return Network.TAILSCALE
    if addr.is_private or addr.is_loopback:
        return Network.LOKAL
    return Network.PUBLIK


def device_kind(user_agent: str) -> str:
    ua = (user_agent or "").lower()
    if "iphone" in ua:
        return "iPhone"
    if "ipad" in ua:
        return "iPad"
    if "android" in ua:
        return "HP Android"
    if "windows" in ua:
        return "PC Windows"
    if "macintosh" in ua or "mac os x" in ua:
        return "Mac"
    if "linux" in ua:
        return "PC Linux"
    return ""


def distance_m(lat1, lng1, lat2, lng2) -> int:
    """Jarak haversine dalam meter."""
    r = 6371000
    p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
    dphi = p2 - p1
    dl = math.radians(float(lng2) - float(lng1))
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return int(round(2 * r * math.asin(math.sqrt(a))))


def _decimal(raw, places: int) -> Decimal | None:
    try:
        value = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError):
        return None
    if not value.is_finite():
        return None
    return value.quantize(Decimal(1).scaleb(-places))


def geo_from_post(post) -> dict:
    """Baca isian tersembunyi yang diisi JavaScript (base.html) saat formulir bertanda data-jejak dikirim."""
    status = (post.get("geo_status") or "").strip().upper()
    if status not in dict(GeoStatus.choices):
        status = ""
    lat, lng = _decimal(post.get("geo_lat", ""), 4), _decimal(post.get("geo_lng", ""), 4)
    try:
        acc = int(float(post.get("geo_acc") or 0)) or None
    except (TypeError, ValueError):
        acc = None
    if status == GeoStatus.OK and (lat is None or lng is None or not (-90 <= lat <= 90) or not (-180 <= lng <= 180)):
        status, lat, lng, acc = GeoStatus.TIDAK_TERSEDIA, None, None, None
    if status != GeoStatus.OK:
        lat = lng = acc = None
    return {"geo_status": status, "latitude": lat, "longitude": lng, "accuracy_m": acc}


def is_usual_prefix(clinic, prefix: str, *, exclude_pk=None) -> bool:
    """Kelompok IP ini sudah beberapa kali muncul bersama jejak Kuat di cabang yang sama."""
    if not clinic or not prefix:
        return False
    since = timezone.now() - dt.timedelta(days=LEARN_DAYS)
    qs = PresenceStamp.objects.filter(clinic=clinic, ip_prefix=prefix, confidence=Confidence.KUAT,
                                      created_at__gte=since)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return qs.count() >= LEARN_MIN_STRONG


def classify(stamp: PresenceStamp) -> tuple[str, str]:
    """Label Kuat / Sedang / Lemah beserta alasannya.

    Kuat  : perangkat milik klinik (IP tetap terdaftar), atau lokasi di dalam radius cabang.
    Sedang: lokasi dekat tetapi akurasinya longgar, atau IP dari kelompok yang lazim di cabang itu.
    Lemah : di luar radius, atau tidak ada petunjuk.
    """
    clinic = stamp.clinic
    device = stamp.device
    if device and device.is_clinic_device and (device.clinic_id is None or clinic is None
                                               or device.clinic_id == clinic.pk):
        return Confidence.KUAT, f"perangkat klinik: {device.name}"[:120]
    has_coords = bool(clinic and clinic.latitude is not None and clinic.longitude is not None)
    if stamp.geo_status == GeoStatus.OK and has_coords and stamp.distance_m is not None:
        radius = clinic.radius_m or 150
        acc = stamp.accuracy_m or 0
        if stamp.distance_m <= radius and acc <= MAX_TRUSTED_ACCURACY:
            return Confidence.KUAT, f"lokasi {stamp.distance_m} m dari klinik"
        if stamp.distance_m <= radius + acc:
            return Confidence.SEDANG, f"lokasi {stamp.distance_m} m, akurasi ±{acc} m"
        return Confidence.LEMAH, f"di luar radius: {stamp.distance_m} m dari klinik"
    if is_usual_prefix(clinic, stamp.ip_prefix, exclude_pk=stamp.pk):
        return Confidence.SEDANG, "IP lazim di cabang ini"
    if stamp.geo_status == GeoStatus.OK and not has_coords:
        return Confidence.LEMAH, "koordinat cabang belum diisi"
    return Confidence.LEMAH, {
        GeoStatus.DITOLAK: "izin lokasi ditolak",
        GeoStatus.TIDAK_TERSEDIA: "lokasi tidak tersedia",
    }.get(stamp.geo_status, "tanpa petunjuk lokasi")


def stamp(request, event: str, *, clinic=None, entity=None, user=None) -> PresenceStamp | None:
    """Catat satu jejak. Kesalahan apa pun hanya dicatat di log; aksi pengguna tetap berhasil."""
    from audit.middleware import client_ip

    try:
        user = user or request.user
        if not getattr(user, "is_authenticated", False):
            return None
        ip = client_ip(request) or None
        try:
            ipaddress.ip_address(ip) if ip else None
        except ValueError:
            ip = None
        ua = (request.META.get("HTTP_USER_AGENT") or "")[:255]
        geo = geo_from_post(request.POST)
        obj = PresenceStamp(
            user=user, clinic=clinic, event=event,
            entity_type=entity._meta.model_name if entity is not None else "",
            entity_id=getattr(entity, "pk", None),
            ip_address=ip, network=network_of(ip),
            # Hanya IP internet umum yang dipelajari polanya; Tailscale dikenali lewat daftar perangkat,
            # IP lokal/loopback (mis. 127.0.0.1 di balik proxy) tidak bermakna sebagai petunjuk lokasi.
            ip_prefix=ip_prefix(ip) if network_of(ip) == Network.PUBLIK else "",
            device=KnownDevice.objects.filter(ip_address=ip).first() if ip else None,
            device_kind=device_kind(ua), user_agent=ua, **geo,
        )
        if obj.geo_status == GeoStatus.OK and clinic and clinic.latitude is not None and clinic.longitude is not None:
            obj.distance_m = distance_m(obj.latitude, obj.longitude, clinic.latitude, clinic.longitude)
        obj.confidence, obj.reason = classify(obj)
        with transaction.atomic():  # savepoint: kegagalan di sini tidak merusak transaksi pemanggil
            obj.save()
        return obj
    except Exception:  # noqa: BLE001 - jejak tidak boleh menggagalkan pekerjaan staf
        log.exception("Gagal mencatat jejak %s", event)
        return None
