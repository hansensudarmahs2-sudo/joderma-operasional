"""Summary Harian dua arah: tanda baca Owner dan tanggapan Owner ↔ Direktur (7 Okt 2026)."""
from __future__ import annotations

import datetime as dt

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User, UserRole
from core.models import Clinic, local_today
from direktur.models import DailySummary, DailySummaryNote, DailySummaryRead
from notifications.models import Notification
from owner import services

pytestmark = pytest.mark.django_db


def _user(clinic, name, *roles, **extra):
    u = User.objects.create_user(username=name, password="TestPassword123!", **extra)
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


@pytest.fixture
def jemur(db):
    return Clinic.objects.create(code="jemur-andayani", name="Jemur Andayani")


@pytest.fixture
def yohanes(jemur):
    return _user(jemur, "yohanes", Role.OWNER, display_name="dr. Yohanes")


@pytest.fixture
def jean(jemur):
    return _user(jemur, "jean", Role.OWNER, display_name="Jean")


@pytest.fixture
def hansen(jemur):
    return _user(jemur, "hansen1", Role.AOM, display_name="dr. Hansen")


@pytest.fixture
def yani(jemur):
    return _user(jemur, "yani", Role.STAF, display_name="Yani")


def _summary(hansen, day=None):
    return DailySummary.objects.create(date=day or local_today(), sent_by=hansen, sent_at=timezone.now(),
                                       content={"sections": []}, note="Hari ini tenang.")


# --- Task 4: service ----------------------------------------------------------------


def test_read_recorded_for_owner_only(jemur, yohanes, hansen):
    s = _summary(hansen)
    services.record_summary_read(s, hansen)
    assert not DailySummaryRead.objects.exists()
    services.record_summary_read(None, yohanes)
    services.record_summary_read(s, yohanes)
    services.record_summary_read(s, yohanes)
    assert DailySummaryRead.objects.filter(summary=s, user=yohanes).count() == 1


def test_read_states_and_resend(jemur, yohanes, jean, hansen):
    s = _summary(hansen)
    assert not services.summary_is_read(s)
    services.record_summary_read(s, yohanes)
    states = {r["user"]: r["state"] for r in services.summary_reads(s)}
    assert states == {yohanes: "baca", jean: "belum"} and services.summary_is_read(s)
    DailySummary.objects.filter(pk=s.pk).update(sent_at=timezone.now() + dt.timedelta(minutes=5))
    s.refresh_from_db()
    states = {r["user"]: r["state"] for r in services.summary_reads(s)}
    assert states[yohanes] == "lama" and not services.summary_is_read(s)


def test_owner_note_notifies_directors(jemur, yohanes, jean, hansen):
    s = _summary(hansen)
    note = services.add_summary_note(s, actor=yohanes, body="Kenapa kas Citraland selisih lagi?")
    assert DailySummaryNote.objects.get() == note
    n = Notification.objects.get(user=hansen, type_code="SUMMARY_NOTE")
    assert n.title == f"Tanggapan Summary {s.date:%d/%m}: Kenapa kas Citraland selisih lagi?"
    assert n.url == reverse("owner:summary") + f"?tanggal={s.date:%Y-%m-%d}"
    assert not Notification.objects.filter(user__in=[yohanes, jean], type_code="SUMMARY_NOTE").exists()


def test_director_note_notifies_owners(jemur, yohanes, jean, hansen):
    s = _summary(hansen)
    services.add_summary_note(s, actor=hansen, body="Sudah dicek, salah input.")
    assert set(Notification.objects.filter(type_code="SUMMARY_NOTE").values_list("user__username", flat=True)) == {
        "yohanes", "jean"}


def test_note_validation_and_permission(jemur, yohanes, hansen, yani):
    s = _summary(hansen)
    with pytest.raises(ValidationError):
        services.add_summary_note(s, actor=yohanes, body="   ")
    with pytest.raises(PermissionDenied):
        services.add_summary_note(s, actor=yani, body="Halo")
    assert not DailySummaryNote.objects.exists()


# --- Task 5: halaman ----------------------------------------------------------------


def test_page_records_read_and_shows_status(client, jemur, yohanes, jean, hansen):
    s = _summary(hansen)
    client.force_login(hansen)
    client.get(reverse("owner:summary"))
    assert not DailySummaryRead.objects.exists()
    client.force_login(yohanes)
    client.get(reverse("owner:summary"))
    assert DailySummaryRead.objects.filter(summary=s, user=yohanes).exists()
    client.force_login(hansen)
    body = client.get(reverse("owner:summary")).content.decode()
    assert "Dibaca dr. Yohanes" in body and "Jean belum membaca" in body


def test_post_note_and_thread(client, jemur, yohanes, hansen):
    s = _summary(hansen)
    client.force_login(yohanes)
    response = client.post(reverse("owner:summary"), {"tanggal": s.date.isoformat(), "isi": "Kenapa selisih?"})
    assert response["Location"] == reverse("owner:summary") + f"?tanggal={s.date:%Y-%m-%d}"
    client.force_login(hansen)
    client.post(reverse("owner:summary"), {"tanggal": s.date.isoformat(), "isi": "Salah input, sudah dikoreksi."})
    body = client.get(reverse("owner:summary")).content.decode()
    assert body.index("Kenapa selisih?") < body.index("Salah input, sudah dikoreksi.")
    assert "Kirim tanggapan" in body


def test_note_for_day_without_summary_is_refused(client, jemur, yohanes, hansen):
    _summary(hansen)
    client.force_login(yohanes)
    yesterday = local_today() - dt.timedelta(days=1)
    client.post(reverse("owner:summary"), {"tanggal": yesterday.isoformat(), "isi": "Halo"})
    assert not DailySummaryNote.objects.exists()


def test_staff_cannot_post_note(client, jemur, hansen, yani):
    _summary(hansen)
    client.force_login(yani)
    assert client.post(reverse("owner:summary"), {"tanggal": local_today().isoformat(), "isi": "x"}).status_code == 403
    assert not DailySummaryNote.objects.exists()


def test_recent_list_marks(client, jemur, yohanes, hansen):
    s = _summary(hansen)
    services.add_summary_note(s, actor=hansen, body="Satu")
    services.add_summary_note(s, actor=hansen, body="Dua")
    client.force_login(hansen)
    body = client.get(reverse("owner:summary")).content.decode()
    assert "belum dibaca" in body and "2 tanggapan" in body
    services.record_summary_read(s, yohanes)
    assert "belum dibaca" not in client.get(reverse("owner:summary")).content.decode()


def test_admin_cannot_post_summary_note(client, jemur, hansen):
    s = _summary(hansen)
    admin = _user(jemur, "admin1", Role.ADMIN)
    client.force_login(admin)
    response = client.post(reverse("owner:summary"), {"tanggal": s.date.isoformat(), "isi": "Halo"})
    assert response.status_code == 403
    assert not DailySummaryNote.objects.exists()
