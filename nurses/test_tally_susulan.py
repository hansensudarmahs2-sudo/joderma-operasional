"""Tally susulan (8 Okt 2026): Koordinator Shift mencatat tally perawat yang lupa menulis,
tanpa RM, pasien, dan tindakan. Alasan wajib, bulan berjalan saja, urutan papan tidak bergeser."""
from __future__ import annotations

import datetime as dt

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from accounts.models import Role, User, UserRole
from audit.models import AuditAction, AuditEvent
from core.models import Clinic, OperationalDay
from core.services import get_or_create_day
from nurses.models import Availability, NurseActionTally, NurseRosterEntry
from nurses.services import correct_tally, daily_tally, monthly_tally, record_backfill_tally

pytestmark = pytest.mark.django_db

TODAY = dt.date(2026, 10, 15)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr("core.models.operational_date", lambda clinic, now=None: TODAY)


@pytest.fixture
def jmr(db):
    return Clinic.objects.create(code="jemur-andayani", name="Jemur", open_time="14:00", close_time="22:00")


@pytest.fixture
def ctl(db):
    return Clinic.objects.create(code="citraland", name="Citraland")


def _user(clinic, name, roles):
    u = User.objects.create_user(username=name, password="TestPassword123!", display_name=name.title())
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


@pytest.fixture
def team(jmr, ctl):
    return {
        "heni": _user(jmr, "heni", [Role.PERAWAT, Role.SUPERVISOR]),
        "lia": _user(jmr, "lia", [Role.PERAWAT]),
        "alya": _user(jmr, "alya", [Role.PERAWAT]),
        "koor_ctl": _user(ctl, "koorctl", [Role.SUPERVISOR]),
    }


@pytest.fixture
def day(jmr, team):
    d, _ = get_or_create_day(jmr, date=TODAY, user=team["heni"])
    for pos, key in enumerate(("lia", "alya"), start=1):
        NurseRosterEntry.objects.create(operational_day=d, nurse=team[key], position=pos)
    return d


def _post(client, user, **data):
    client.force_login(user)
    return client.post(reverse("nurses:tally_backfill"), data)


def test_coordinator_records_backfill_without_patient(client, jmr, team, day):
    lia = team["lia"]
    resp = _post(client, team["heni"], cabang=jmr.pk, tanggal=TODAY.isoformat(), perawat=lia.pk, jumlah=2,
                 alasan="Lupa menulis 2 tindakan sore")
    assert resp.status_code == 302 and "tanggal=2026-10-15" in resp["Location"]
    t = NurseActionTally.objects.get()
    assert t.susulan and t.susulan_reason == "Lupa menulis 2 tindakan sore"
    assert (t.rm_number, t.patient_name, t.action_name) == ("", "", "")
    assert t.tally == 2 and t.nurse == lia and t.entered_by == team["heni"] and t.operational_day == day
    assert daily_tally(day)[lia.pk] == 2
    assert monthly_tally([lia.pk], TODAY)[lia.pk] == 2
    ev = AuditEvent.objects.get(action=AuditAction.CREATE, entity_type="nurseactiontally", entity_id=str(t.pk))
    assert ev.actor == team["heni"] and ev.reason == "Lupa menulis 2 tindakan sore" and "susulan" in ev.entity_label


def test_backfill_does_not_move_board(jmr, team, day):
    lia = team["lia"]
    entry = NurseRosterEntry.objects.get(operational_day=day, nurse=lia)
    entry.availability = Availability.MENANGANI
    entry.save()
    record_backfill_tally(jmr, TODAY, user=team["heni"], nurse=lia, amount=1, reason="Lupa")
    entry.refresh_from_db()
    assert entry.position == 1 and entry.availability == Availability.MENANGANI and entry.turns_taken == 1
    assert NurseRosterEntry.objects.get(operational_day=day, nurse=team["alya"]).position == 2


@pytest.mark.parametrize("kwargs, message", [
    ({"reason": "  "}, "alasan"),
    ({"amount": 0}, "antara 1 dan 20"),
    ({"amount": 21}, "antara 1 dan 20"),
    ({"amount": "x"}, "tidak valid"),
    ({"nurse": None}, "Pilih perawat"),
])
def test_backfill_validation(jmr, team, day, kwargs, message):
    args = {"user": team["heni"], "nurse": team["lia"], "amount": 1, "reason": "Lupa", **kwargs}
    with pytest.raises(ValidationError, match=message):
        record_backfill_tally(jmr, TODAY, **args)
    assert not NurseActionTally.objects.exists()


def test_backfill_only_current_month_up_to_today(jmr, team, day):
    heni, lia = team["heni"], team["lia"]
    for date in (dt.date(2026, 9, 30), dt.date(2026, 10, 16), None):
        if date:
            OperationalDay.objects.create(clinic=jmr, date=date)
        with pytest.raises(ValidationError, match="bulan berjalan"):
            record_backfill_tally(jmr, date, user=heni, nurse=lia, amount=1, reason="Lupa")
    with pytest.raises(ValidationError, match="Tidak ada sesi"):
        record_backfill_tally(jmr, dt.date(2026, 10, 10), user=heni, nurse=lia, amount=1, reason="Lupa")
    past = OperationalDay.objects.create(clinic=jmr, date=dt.date(2026, 10, 1))
    t = record_backfill_tally(jmr, past.date, user=heni, nurse=lia, amount=3, reason="Ketahuan saat rekap")
    assert t.operational_day == past
    assert monthly_tally([lia.pk], TODAY)[lia.pk] == 3
    assert NurseActionTally.objects.count() == 1


def test_backfill_today_creates_session_when_missing(jmr, team):
    record_backfill_tally(jmr, TODAY, user=team["heni"], nurse=team["lia"], amount=1, reason="Lupa")
    assert OperationalDay.objects.filter(clinic=jmr, date=TODAY).exists()


def test_only_tally_correctors_of_that_branch(client, jmr, team, day):
    for user in (team["lia"], team["koor_ctl"]):
        with pytest.raises(PermissionDenied):
            record_backfill_tally(jmr, TODAY, user=user, nurse=team["alya"], amount=1, reason="Lupa")
    resp = _post(client, team["lia"], cabang=jmr.pk, tanggal=TODAY.isoformat(), perawat=team["lia"].pk,
                 jumlah=5, alasan="Tambah sendiri")
    assert resp.status_code == 403
    assert not NurseActionTally.objects.exists()


def test_backfill_route_needs_post(client, team):
    client.force_login(team["heni"])
    assert client.get(reverse("nurses:tally_backfill")).status_code == 405


def test_regular_tally_form_still_requires_patient(client, jmr, team, day):
    client.force_login(team["heni"])
    full = {"nurse": team["lia"].pk, "rm_number": "0108", "patient_name": "Pasien A", "action_name": "Sculptra",
            "tally": 1}
    for missing in ("rm_number", "patient_name", "action_name"):
        client.post(reverse("nurses:tally_create"), {**full, missing: " "})
        assert not NurseActionTally.objects.exists(), missing
    client.post(reverse("nurses:tally_create"), full)
    t = NurseActionTally.objects.get()
    assert not t.susulan and t.patient_name == "Pasien A"


def test_backfill_nurse_must_belong_to_branch_or_roster(ctl, jmr, team, day):
    vivi = _user(ctl, "vivi", [Role.PERAWAT])
    with pytest.raises(ValidationError, match="bukan perawat cabang ini"):
        record_backfill_tally(jmr, TODAY, user=team["heni"], nurse=vivi, amount=1, reason="Lupa")
    NurseRosterEntry.objects.create(operational_day=day, nurse=vivi, position=3)  # dipinjam hari ini
    assert record_backfill_tally(jmr, TODAY, user=team["heni"], nurse=vivi, amount=1, reason="Lupa").nurse == vivi


def test_director_can_backfill_other_branch(client, ctl, team):
    aom = _user(ctl, "dirop", [Role.AOM])
    nina = _user(ctl, "nina", [Role.PERAWAT])
    resp = _post(client, aom, cabang=ctl.pk, tanggal=TODAY.isoformat(), perawat=nina.pk, jumlah=1, alasan="Lupa")
    assert resp.status_code == 302
    assert NurseActionTally.objects.get().operational_day.clinic == ctl


def test_capability_holder_can_backfill(jmr, team, day):
    from accounts.models import Capability, UserCapability

    lia = team["lia"]
    UserCapability.objects.create(user=lia, capability=Capability.TALLY_CORRECT)
    lia = User.objects.get(pk=lia.pk)
    assert record_backfill_tally(jmr, TODAY, user=lia, nurse=team["alya"], amount=1, reason="Lupa").susulan


@pytest.mark.parametrize("data", [
    {"cabang": "", "tanggal": "2026-10-15"},
    {"cabang": "abc", "tanggal": "2026-10-15"},
    {"cabang": "9999", "tanggal": "2026-10-15"},
])
def test_backfill_bad_branch_is_404(client, team, day, data):
    resp = _post(client, team["heni"], perawat=team["lia"].pk, jumlah=1, alasan="Lupa", **data)
    assert resp.status_code == 404 and not NurseActionTally.objects.exists()


def test_backfill_bad_date_or_nurse_shows_error(client, jmr, team, day):
    for extra in ({"tanggal": "kemarin", "perawat": team["lia"].pk}, {"tanggal": TODAY.isoformat(), "perawat": "x"}):
        resp = _post(client, team["heni"], cabang=jmr.pk, jumlah=1, alasan="Lupa", **extra)
        assert resp.status_code == 302
    assert not NurseActionTally.objects.exists()


def test_backfill_on_closed_day_is_allowed(jmr, team):
    from core.models import DayStatus

    closed = OperationalDay.objects.create(clinic=jmr, date=dt.date(2026, 10, 2), status=DayStatus.CLOSED)
    assert record_backfill_tally(jmr, closed.date, user=team["heni"], nurse=team["lia"], amount=1,
                                 reason="Lupa").operational_day == closed


def test_tally_day_defaults_to_operational_date(client, jmr, team, day):
    client.force_login(team["heni"])
    resp = client.get(reverse("nurses:tally_day"), {"cabang": jmr.pk})
    assert resp.context["date"] == TODAY and resp.context["can_backfill"]


def test_corrected_backfill_has_readable_audit_label(jmr, team, day):
    t = record_backfill_tally(jmr, TODAY, user=team["heni"], nurse=team["lia"], amount=2, reason="Lupa")
    correct_tally(t, user=team["heni"], amount=1, reason="Hanya satu")
    ev = AuditEvent.objects.get(action=AuditAction.CORRECTION, entity_type="nurseactiontally")
    assert ev.entity_label == "Tally susulan · Lia"


def test_pages_show_backfill_form_and_tag(client, jmr, team, day):
    record_backfill_tally(jmr, TODAY, user=team["heni"], nurse=team["lia"], amount=1, reason="Lupa menulis")
    client.force_login(team["heni"])
    html = client.get(reverse("nurses:tally_day"), {"cabang": jmr.pk, "tanggal": TODAY.isoformat()}).content.decode()
    assert "Tambah tally susulan" in html and reverse("nurses:tally_backfill") in html
    assert "susulan</span>" in html and "Lupa menulis" in html
    html = client.get(reverse("nurses:tally_day"), {"cabang": jmr.pk, "tanggal": "2026-09-30"}).content.decode()
    assert reverse("nurses:tally_backfill") not in html and "bulan berjalan" in html


def test_backfill_can_be_corrected_to_zero(jmr, team, day):
    t = record_backfill_tally(jmr, TODAY, user=team["heni"], nurse=team["lia"], amount=2, reason="Lupa")
    correct_tally(t, user=team["heni"], amount=0, reason="Ternyata sudah tercatat")
    assert monthly_tally([team["lia"].pk], TODAY)[team["lia"].pk] == 0
