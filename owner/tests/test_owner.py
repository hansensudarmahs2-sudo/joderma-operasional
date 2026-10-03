"""Fase 4 redefinisi peran: Dashboard Owner, Permintaan Owner, Summary Harian, Jadwal ringkas."""
from __future__ import annotations

import datetime as dt

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User, UserRole
from audit.models import AuditEvent
from core.models import ActionItem, ActionItemStatus, Clinic, local_today
from direktur.models import DailySummary
from jadwal.models import DutyRoster, DutyStatus
from notifications.models import Notification
from owner import services
from owner.models import SOURCE_TYPE, OwnerRequest

pytestmark = pytest.mark.django_db
PASSWORD = "TestPassword123!"


def _user(clinic, name, *roles, **extra):
    u = User.objects.create_user(username=name, password=PASSWORD, **extra)
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


@pytest.fixture
def jemur(db):
    return Clinic.objects.create(code="jemur-andayani", name="Jemur Andayani", open_time="14:00", close_time="22:00")


@pytest.fixture
def citraland(db):
    return Clinic.objects.create(code="JC", name="Citraland")


@pytest.fixture
def yohanes(jemur):
    return _user(jemur, "yohanes", Role.OWNER, display_name="dr. Yohanes")


@pytest.fixture
def jean(jemur):
    return _user(jemur, "jean", Role.OWNER, display_name="Jean")


@pytest.fixture
def hansen(jemur):
    return _user(jemur, "hansen1", Role.AOM, display_name="dr. Hansen")


def _request(owner, title="Rapikan alur pendaftaran", days=7):
    return services.create_request(actor=owner, title=title, target_date=local_today() + dt.timedelta(days=days))


def _task(req, clinic, status=ActionItemStatus.BARU, title="Task"):
    return ActionItem.objects.create(clinic=clinic, title=title, source_type=SOURCE_TYPE, source_id=req.pk,
                                     status=status)


# --- Permintaan ----------------------------------------------------------------


def test_owner_creates_request_and_director_is_notified(client, yohanes, jean, hansen):
    client.force_login(yohanes)
    target = (local_today() + dt.timedelta(days=10)).isoformat()
    response = client.post(reverse("owner:request_new"), {"judul": "Evaluasi harga paket", "rincian": "Bandingkan",
                                                          "target": target})
    req = OwnerRequest.objects.get()
    assert response["Location"] == reverse("owner:request_detail", args=[req.pk])
    assert req.created_by == yohanes and req.target_date.isoformat() == target
    assert AuditEvent.objects.filter(entity_type="ownerrequest", entity_id=str(req.pk)).exists()
    note = Notification.objects.get(user=hansen)
    assert "Evaluasi harga paket" in note.title and note.url == reverse("owner:request_detail", args=[req.pk])
    assert not Notification.objects.filter(user__in=[yohanes, jean]).exists()


@pytest.mark.parametrize(
    ("form", "message"),
    [
        ({"judul": "", "target": "2099-01-01"}, "Tulis apa yang diminta"),
        ({"judul": "X", "target": ""}, "Tanggal target wajib diisi"),
        ({"judul": "X", "target": "2020-01-01"}, "tidak boleh sebelum hari ini"),
        ({"judul": "X" * 201, "target": "2099-01-01"}, "terlalu panjang"),
    ],
)
def test_request_validation(client, yohanes, form, message):
    client.force_login(yohanes)
    body = client.post(reverse("owner:request_new"), form).content.decode()
    assert message in body and not OwnerRequest.objects.exists()


def test_only_owner_creates_requests(client, jemur, hansen):
    for user in (hansen, _user(jemur, "desy", Role.PIC, Role.FRONT_DESK), _user(jemur, "yani", Role.PERAWAT)):
        client.force_login(user)
        assert client.post(reverse("owner:request_new"), {"judul": "X", "target": "2099-01-01"}).status_code == 403
        with pytest.raises(PermissionDenied):
            services.create_request(actor=user, title="X", target_date=dt.date(2099, 1, 1))
    assert not OwnerRequest.objects.exists()


def test_progress_comes_from_tasks(jemur, yohanes):
    req = _request(yohanes)
    assert services.progress(req)["state"] == "waiting"
    a = _task(req, jemur)
    _task(req, jemur, status=ActionItemStatus.BATAL)  # dibatalkan tidak dihitung
    row = services.progress(req)
    assert (row["state"], row["done"], row["total"]) == ("running", 0, 1)
    b = _task(req, jemur, status=ActionItemStatus.SELESAI)
    assert services.progress(req)["percent"] == 50
    a.status = ActionItemStatus.SELESAI
    a.save()
    row = services.progress(req)
    assert (row["state"], row["label"], row["late"]) == ("done", "Selesai", False)
    assert b.pk


def test_late_request_is_flagged_and_listed_first(client, jemur, yohanes):
    ok = _request(yohanes, "Masih lama", days=20)
    late = _request(yohanes, "Sudah lewat", days=1)
    OwnerRequest.objects.filter(pk=late.pk).update(target_date=local_today() - dt.timedelta(days=3))
    rows = services.request_rows(yohanes)
    assert [r["request"].pk for r in rows] == [late.pk, ok.pk]
    assert rows[0]["late"] and rows[0]["days_late"] == 3
    client.force_login(yohanes)
    body = client.get(reverse("owner:dashboard")).content.decode()
    assert "Sudah lewat" in body and "Lewat target" in body and "lewat 3 hari" in body


def test_done_requests_drop_off_after_two_weeks(jemur, yohanes):
    req = _request(yohanes)
    task = _task(req, jemur, status=ActionItemStatus.SELESAI)
    assert services.request_rows(yohanes)
    old = timezone.now() - dt.timedelta(days=30)
    OwnerRequest.objects.filter(pk=req.pk).update(updated_at=old)
    ActionItem.objects.filter(pk=task.pk).update(updated_at=old)
    assert services.request_rows(yohanes) == []


def test_notes_go_both_ways(client, yohanes, jean, hansen):
    req = _request(yohanes)
    Notification.objects.all().delete()
    client.force_login(yohanes)
    client.post(reverse("owner:request_detail", args=[req.pk]), {"catatan": "Tolong prioritaskan"})
    assert Notification.objects.filter(user=hansen).count() == 1
    client.force_login(hansen)
    body = client.get(reverse("owner:request_detail", args=[req.pk])).content.decode()
    assert "Tolong prioritaskan" in body
    client.post(reverse("owner:request_detail", args=[req.pk]), {"catatan": "Target mundur 3 hari, menunggu vendor"})
    assert set(Notification.objects.exclude(user=hansen).values_list("user__username", flat=True)) == {
        "yohanes", "jean"}
    assert req.notes.count() == 2
    with pytest.raises(ValidationError):
        services.add_note(req, actor=hansen, body="  ")


def test_staff_cannot_open_requests(client, jemur, yohanes):
    req = _request(yohanes)
    for user in (_user(jemur, "yani", Role.PERAWAT), _user(jemur, "heni", Role.SUPERVISOR, Role.PERAWAT),
                 _user(jemur, "superadmin", Role.ADMIN)):
        client.force_login(user)
        assert client.get(reverse("owner:request_detail", args=[req.pk])).status_code == 403
        assert client.post(reverse("owner:request_detail", args=[req.pk]), {"catatan": "x"}).status_code == 403
        assert client.get(reverse("owner:dashboard")).status_code == 403
    assert not req.notes.exists()


# --- Dashboard -----------------------------------------------------------------


def test_owner_dashboard_has_overview_and_requests(client, jemur, yohanes):
    client.force_login(yohanes)
    body = client.get(reverse("owner:dashboard")).content.decode()
    for text in ("Dashboard", "Permintaan dan temuan", "+ Permintaan", "+ Catat temuan", "Yang belum selesai", "Per cabang",
                 "Keputusan menggantung", reverse("direktur:matrix"), reverse("direktur:team")):
        assert text in body
    assert "Belum ada permintaan atau temuan" in body


def test_director_sees_owner_dashboard_without_create_button(client, hansen, yohanes):
    _request(yohanes, "Permintaan terlihat")
    client.force_login(hansen)
    body = client.get(reverse("owner:dashboard")).content.decode()
    assert "Permintaan terlihat" in body and "+ Permintaan baru" not in body


# --- Summary harian --------------------------------------------------------------


def test_summary_empty_then_filled(client, yohanes, hansen):
    client.force_login(yohanes)
    body = client.get(reverse("owner:summary")).content.decode()
    assert "Belum ada summary untuk tanggal ini" in body
    today = local_today()
    DailySummary.objects.create(
        date=today, sent_by=hansen, sent_at=timezone.now(), send_count=2, note="Hari ini tenang.",
        content={"sections": [
            {"title": "Checklist Direktur", "items": [{"text": "Limbah Jemur", "meta": "sesuai", "tag": "Sesuai",
                                                       "tone": "ok"}]},
            {"title": "Keputusan", "items": [], "empty": "Tidak ada keputusan hari ini."},
        ]},
    )
    body = client.get(reverse("owner:summary")).content.decode()
    for text in ("Hari ini tenang.", "Limbah Jemur", "Tidak ada keputusan hari ini.", "diperbarui 2 kali",
                 "dr. Hansen"):
        assert text in body
    assert 'aria-label="Hari berikutnya"' not in body  # tidak bisa melihat hari esok
    past = client.get(reverse("owner:summary") + f"?tanggal={today - dt.timedelta(days=1)}").content.decode()
    assert "Belum ada summary" in past and 'aria-label="Hari berikutnya"' in past


def test_summary_access(client, jemur, hansen):
    client.force_login(hansen)
    assert client.get(reverse("owner:summary")).status_code == 200
    client.force_login(_user(jemur, "yani", Role.PERAWAT))
    assert client.get(reverse("owner:summary")).status_code == 403


# --- Jadwal ringkas ----------------------------------------------------------------


def test_jadwal_shows_who_is_on_duty(client, jemur, citraland, yohanes):
    today = local_today()
    yani = _user(jemur, "yani", Role.PERAWAT, display_name="Yani", job_title="Perawat")
    desy = _user(jemur, "desy", Role.PERAWAT, display_name="Desy")
    lia = _user(citraland, "lia", Role.PERAWAT, display_name="Lia")
    heni = _user(jemur, "heni", Role.PERAWAT, display_name="Heni")
    DutyRoster.objects.create(user=yani, date=today, home_clinic=jemur, clinic=jemur, status=DutyStatus.MASUK)
    DutyRoster.objects.create(user=desy, date=today, home_clinic=jemur, status=DutyStatus.CUTI)
    DutyRoster.objects.create(user=lia, date=today, home_clinic=citraland, clinic=jemur,
                              status=DutyStatus.PERBANTUAN)
    DutyRoster.objects.create(user=heni, date=today, home_clinic=jemur, clinic=citraland,
                              status=DutyStatus.PERBANTUAN)
    client.force_login(yohanes)
    body = client.get(reverse("owner:jadwal") + f"?cabang={jemur.pk}").content.decode()
    working = body.split("Bertugas", 1)[1].split("Tidak di cabang ini", 1)[0]
    assert "Yani" in working and "Lia" in working and "perbantuan dari Citraland" in working
    assert "Desy" not in working and "Heni" not in working
    away = body.split("Tidak di cabang ini", 1)[1]
    assert "Desy" in away and "Cuti" in away and "Heni" in away and "di Citraland" in away
    assert "Jam buka 14.00–22.00" in body
    assert f"{reverse('jadwal:roster')}?cabang={jemur.pk}" in body  # Lihat jadwal penuh
    other = client.get(reverse("owner:jadwal") + f"?cabang={citraland.pk}").content.decode()
    assert "Heni" in other.split("Bertugas", 1)[1]


def test_jadwal_unfilled_day(client, jemur, yohanes):
    client.force_login(yohanes)
    body = client.get(reverse("owner:jadwal") + "?tanggal=2030-01-01").content.decode()
    assert "Jadwal jaga tanggal ini belum diisi" in body


def test_owner_full_roster_is_read_only(client, jemur, yohanes):
    client.force_login(yohanes)
    body = client.get(reverse("jadwal:roster") + f"?cabang={jemur.pk}").content.decode()
    assert "Ubah satu tanggal" not in body and "Pembagian tugas bulan ini" not in body
