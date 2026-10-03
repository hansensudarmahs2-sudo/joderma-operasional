"""Tahap 3 paket E: jejak kehadiran (IP, perangkat, lokasi sesaat) dengan label Kuat/Sedang/Lemah."""
from __future__ import annotations

from decimal import Decimal

import pytest
from django.test import RequestFactory
from django.urls import reverse

from accounts.models import Role, User, UserRole
from audit.middleware import client_ip
from core.models import Clinic, TaskAudienceType, local_today
from core.task_services import create_task
from jejak import services
from jejak.models import Confidence, Event, GeoStatus, KnownDevice, Network, PresenceStamp

pytestmark = pytest.mark.django_db
PASSWORD = "TestPassword123!"
JEMUR = (Decimal("-7.320000"), Decimal("112.740000"))


def _user(clinic, name, *roles):
    u = User.objects.create_user(username=name, password=PASSWORD, display_name=name.title())
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


@pytest.fixture
def jemur(db):
    return Clinic.objects.create(code="jemur-andayani", name="JoDerma Jemur Andayani",
                                 latitude=JEMUR[0], longitude=JEMUR[1], radius_m=150)


@pytest.fixture
def people(jemur):
    return {
        "hansen": _user(jemur, "hansen1", Role.AOM),
        "jean": _user(jemur, "jean", Role.OWNER),
        "heni": _user(jemur, "heni", Role.SUPERVISOR, Role.PERAWAT, Role.STAF),
        "yani": _user(jemur, "yani", Role.PERAWAT, Role.STAF),
    }


def _request(user, ip="182.8.65.7", ua="Mozilla/5.0 (Linux; Android 10; K)", **post):
    req = RequestFactory().post("/x/", post, HTTP_CF_CONNECTING_IP=ip, HTTP_USER_AGENT=ua)
    req.user = user
    return req


def test_helpers():
    assert services.ip_prefix("182.8.65.7") == "182.8.65.0/24"
    assert services.ip_prefix("2400:9800:36c:d841:da43:d1f2:64b5:fe2") == "2400:9800:36c:d841::/64"
    assert services.ip_prefix("bukan-ip") == ""
    assert services.network_of("100.90.94.23") == Network.TAILSCALE
    assert services.network_of("192.168.1.5") == Network.LOKAL
    assert services.network_of("182.8.65.7") == Network.PUBLIK
    assert services.device_kind("Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X)") == "iPhone"
    assert services.device_kind("Mozilla/5.0 (Windows NT 10.0; Win64; x64)") == "PC Windows"
    assert 1100 < services.distance_m(-7.32, 112.74, -7.33, 112.74) < 1120


def test_client_ip_prefers_cloudflare_header():
    rf = RequestFactory()
    spoofed = rf.get("/", HTTP_X_FORWARDED_FOR="1.2.3.4, 182.8.65.7", HTTP_CF_CONNECTING_IP="182.8.65.7")
    assert client_ip(spoofed) == "182.8.65.7"
    tailnet = rf.get("/", HTTP_X_FORWARDED_FOR="100.90.94.23")
    assert client_ip(tailnet) == "100.90.94.23"


def test_labels(people, jemur):
    heni = people["heni"]
    inside = services.stamp(_request(heni, geo_status="OK", geo_lat="-7.32050", geo_lng="112.74010", geo_acc="25"),
                            Event.CHECKLIST, clinic=jemur)
    assert inside.confidence == Confidence.KUAT and inside.distance_m < 150
    assert inside.latitude == Decimal("-7.3205")  # dibulatkan 4 desimal
    near = services.stamp(_request(heni, geo_status="OK", geo_lat="-7.32200", geo_lng="112.74000", geo_acc="200"),
                          Event.CHECKLIST, clinic=jemur)
    assert near.confidence == Confidence.SEDANG and "akurasi" in near.reason
    far = services.stamp(_request(heni, geo_status="OK", geo_lat="-7.25", geo_lng="112.75", geo_acc="20"),
                         Event.CHECKLIST, clinic=jemur)
    assert far.confidence == Confidence.LEMAH and "di luar radius" in far.reason
    denied = services.stamp(_request(heni, ip="9.9.9.9", geo_status="DITOLAK"), Event.LOGIN, clinic=jemur)
    assert denied.confidence == Confidence.LEMAH and denied.reason == "izin lokasi ditolak"
    assert denied.latitude is None and denied.geo_status == GeoStatus.DITOLAK
    junk = services.stamp(_request(heni, geo_status="OK", geo_lat="abc", geo_lng="999"), Event.LOGIN, clinic=jemur)
    assert junk.geo_status == GeoStatus.TIDAK_TERSEDIA and junk.latitude is None


def test_usual_ip_prefix_is_learned(people, jemur):
    heni = people["heni"]
    for _ in range(3):
        services.stamp(_request(heni, ip="182.8.65.7", geo_status="OK", geo_lat="-7.3200", geo_lng="112.7400",
                                geo_acc="20"), Event.CHECKLIST, clinic=jemur)
    other = services.stamp(_request(people["yani"], ip="182.8.65.99", geo_status="DITOLAK"),
                           Event.CHECKLIST, clinic=jemur)
    assert other.confidence == Confidence.SEDANG and other.reason == "IP lazim di cabang ini"
    stranger = services.stamp(_request(people["yani"], ip="103.1.2.3"), Event.CHECKLIST, clinic=jemur)
    assert stranger.confidence == Confidence.LEMAH
    # IP lokal (mis. 127.0.0.1 di balik proxy) tidak pernah dipelajari.
    for _ in range(3):
        services.stamp(_request(heni, ip="127.0.0.1", geo_status="OK", geo_lat="-7.3200", geo_lng="112.7400",
                                geo_acc="20"), Event.CHECKLIST, clinic=jemur)
    local = services.stamp(_request(people["yani"], ip="127.0.0.1"), Event.LOGIN, clinic=jemur)
    assert local.ip_prefix == "" and local.confidence == Confidence.LEMAH


def test_clinic_device_is_strong_and_missing_coords(people, jemur):
    KnownDevice.objects.create(ip_address="100.90.94.23", name="PC Jemur", clinic=jemur, is_clinic_device=True)
    s = services.stamp(_request(people["heni"], ip="100.90.94.23", ua="Windows NT 10.0"), Event.BUKA_HARI,
                       clinic=jemur)
    assert s.confidence == Confidence.KUAT and s.device.name == "PC Jemur" and s.network == Network.TAILSCALE
    bare = Clinic.objects.create(code="JC", name="Citraland")
    b = services.stamp(_request(people["heni"], geo_status="OK", geo_lat="-7.3", geo_lng="112.6"), Event.LOGIN,
                       clinic=bare)
    assert b.confidence == Confidence.LEMAH and b.reason == "koordinat cabang belum diisi"


def test_stamp_never_breaks_the_action(people, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(services, "classify", boom)
    assert services.stamp(_request(people["heni"]), Event.LOGIN) is None


def test_actions_leave_stamps(client, people, jemur):
    heni = people["heni"]
    geo = {"geo_status": "OK", "geo_lat": "-7.32010", "geo_lng": "112.74010", "geo_acc": "30"}
    res = client.post(reverse("accounts:login"), {"username": "heni", "password": PASSWORD, **geo},
                      HTTP_CF_CONNECTING_IP="182.8.65.7")
    assert res.status_code == 302
    login = PresenceStamp.objects.get(event=Event.LOGIN, user=heni)
    assert login.ip_address == "182.8.65.7" and login.confidence == Confidence.KUAT and login.clinic == jemur
    item = create_task(clinic=jemur, actor=people["hansen"], title="Cek APAR", audience_type=TaskAudienceType.USER,
                       user_ids=[heni.pk])
    a = item.task_assignments.get()
    client.post(reverse("core:assignment_progress", args=[a.pk]), {"catatan": "Sudah dicek 2 tabung", **geo})
    client.post(reverse("core:assignment_submit", args=[a.pk]), {"catatan": "Semua tabung aman", **geo})
    assert set(PresenceStamp.objects.filter(user=heni).values_list("event", flat=True)) == {
        Event.LOGIN, Event.PROGRES, Event.AJUKAN}
    # Gagal (tanpa catatan) tidak meninggalkan jejak.
    other = create_task(clinic=jemur, actor=people["hansen"], title="Cek wastafel",
                        audience_type=TaskAudienceType.USER, user_ids=[heni.pk])
    client.post(reverse("core:assignment_submit", args=[other.task_assignments.get().pk]), geo)
    assert PresenceStamp.objects.filter(user=heni, event=Event.AJUKAN).count() == 1
    # Formulir terkait memakai penanda data-jejak (lokasi diisi JavaScript saat dikirim).
    home = client.get(reverse("core:dashboard")).content.decode()
    assert home.count("data-jejak") >= 2  # lapor progres + ajukan selesai
    client.logout()
    assert 'method="post" data-jejak' in client.get(reverse("accounts:login")).content.decode()


def test_day_open_close_stamp(client, people, jemur):
    from core.services import get_or_create_day

    from core.models import DayStatus

    day, _ = get_or_create_day(jemur, date=local_today())
    day.status = DayStatus.READY
    day.save()
    client.force_login(people["heni"])
    client.post(reverse("core:day_action", args=[day.pk]), {"aksi": "open", "geo_status": "DITOLAK"},
                HTTP_CF_CONNECTING_IP="182.8.65.7")
    day.refresh_from_db()
    assert day.opened_at is not None
    s = PresenceStamp.objects.get(event=Event.BUKA_HARI, entity_id=day.pk)
    assert s.user == people["heni"] and s.clinic == jemur and s.reason == "izin lokasi ditolak"


def test_pages_and_permissions(client, people, jemur):
    services.stamp(_request(people["heni"], ip="100.90.94.23", ua="Windows NT 10.0"), Event.CHECKLIST, clinic=jemur)
    services.stamp(_request(people["yani"], geo_status="OK", geo_lat="-7.3200", geo_lng="112.7400", geo_acc="10"),
                   Event.CHECKLIST, clinic=jemur)
    client.force_login(people["hansen"])
    body = client.get(reverse("jejak:index")).content.decode()
    assert "Jejak kehadiran" in body and "Heni" in body and "Yani" in body and "100%" in body
    assert 'href="/jejak/">Jejak</a>' in body
    page = client.get(reverse("jejak:devices")).content.decode()
    assert "IP Tailscale yang belum diberi nama" in page and "100.90.94.23" in page
    client.post(reverse("jejak:devices"), {"ip": "100.90.94.23", "nama": "PC Jemur", "cabang": jemur.pk, "klinik": "1"})
    assert KnownDevice.objects.get(ip_address="100.90.94.23").is_clinic_device
    client.post(reverse("jejak:devices"), {"ip": "bukan", "nama": "x"})
    assert KnownDevice.objects.count() == 1
    client.force_login(people["jean"])
    owner_page = client.get(reverse("jejak:index")).content.decode()
    assert 'href="/jejak/">Jejak</a>' in owner_page  # menu Owner
    client.post(reverse("jejak:devices"), {"ip": "100.1.1.1", "nama": "Owner"})
    assert KnownDevice.objects.count() == 1
    for who in ("heni", "yani"):
        client.force_login(people[who])
        assert client.get(reverse("jejak:index")).status_code in (302, 403)


def test_clinic_coordinates_form(client, people, jemur):
    client.force_login(people["hansen"])
    base = {"klinik": jemur.pk, "nama": jemur.name, "buka": "12:00", "tutup": "21:00"}
    client.post(reverse("core:clinic_profile"), {**base, "lintang": "-7,312345", "bujur": "112.745678", "radius": "200"})
    jemur.refresh_from_db()
    assert jemur.latitude == Decimal("-7.312345") and jemur.longitude == Decimal("112.745678") and jemur.radius_m == 200
    client.post(reverse("core:clinic_profile"), {**base, "lintang": "-95", "bujur": "112", "radius": "200"})
    jemur.refresh_from_db()
    assert jemur.latitude == Decimal("-7.312345")


def test_initial_branch_coordinates_migration(db):
    """Data migration core 0008: koordinat Google Maps kedua cabang, tanpa menimpa yang sudah diisi."""
    import importlib

    from django.apps import apps

    fill = importlib.import_module("core.migrations.0008_koordinat_cabang").fill
    jemur = Clinic.objects.create(code="jemur-andayani", name="JoDerma Jemur Andayani")
    citraland = Clinic.objects.create(code="JC", name="Joderma Citraland")
    manual = Clinic.objects.create(code="x", name="Cabang Jemur Lama", latitude=Decimal("-7.1"),
                                   longitude=Decimal("112.1"))
    fill(apps, None)
    for c in (jemur, citraland, manual):
        c.refresh_from_db()
    assert (jemur.latitude, jemur.longitude) == (Decimal("-7.328501"), Decimal("112.739425"))
    assert (citraland.latitude, citraland.longitude) == (Decimal("-7.286665"), Decimal("112.655565"))
    assert manual.latitude == Decimal("-7.1")  # tidak ditimpa
