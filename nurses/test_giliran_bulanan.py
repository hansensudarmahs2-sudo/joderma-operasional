"""Aturan giliran tally bulanan (ketetapan product owner 29 September 2026)."""
from __future__ import annotations

import datetime as dt

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from accounts.models import Role, User, UserRole
from core.models import Clinic
from core.services import get_or_create_day
from jadwal.models import DutyRoster, DutyStatus
from nurses.models import Availability, NurseActionTally, NurseRosterEntry
from nurses.services import (
    after_tally,
    hand_over,
    monthly_tally,
    move_entry,
    next_nurse,
    rotation_board,
    sync_roster_with_duty,
)

pytestmark = pytest.mark.django_db


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
    t = {
        "heni": _user(jmr, "heni", [Role.PERAWAT, Role.SUPERVISOR]),
        "lia": _user(jmr, "lia", [Role.PERAWAT]),
        "alya": _user(jmr, "alya", [Role.PERAWAT]),
        "yani": _user(jmr, "yani", [Role.PERAWAT]),
        "arsi": _user(jmr, "arsi", [Role.ASISTEN_APOTEKER]),
    }
    UserRole.objects.create(user=t["yani"], clinic=ctl, role=Role.PERAWAT)
    return t


def _tally(clinic, date, nurse, n, by):
    day, _ = get_or_create_day(clinic, date=date)
    NurseActionTally.objects.create(operational_day=day, nurse=nurse, rm_number="JJ-1", patient_name="Pasien",
                                    action_name="Facial", tally=n, entered_by=by)


def _roster(clinic, date, nurses):
    day, _ = get_or_create_day(clinic, date=date)
    for pos, n in enumerate(nurses, start=1):
        NurseRosterEntry.objects.create(operational_day=day, nurse=n, position=pos)
    return day


def _give_next(day, heni):
    """Serahkan pasien ke perawat berikutnya lalu catat tally saat selesai."""
    entry = next_nurse(day)
    hand_over(entry, user=heni)
    NurseActionTally.objects.create(operational_day=day, nurse=entry.nurse, rm_number="JJ-2",
                                    patient_name="Pasien", action_name="Peeling", tally=1, entered_by=heni)
    after_tally(day, entry.nurse_id, amount=1, user=heni)
    return entry.nurse.username


def test_catch_up_stops_at_total_minus_one(jmr, team):
    # Contoh product owner: Lia 11, Alya 10, Yani 6 (habis off).
    heni = team["heni"]
    _tally(jmr, dt.date(2026, 10, 18), team["lia"], 11, heni)
    _tally(jmr, dt.date(2026, 10, 18), team["alya"], 10, heni)
    _tally(jmr, dt.date(2026, 10, 18), team["yani"], 6, heni)
    day = _roster(jmr, dt.date(2026, 10, 20), [team["lia"], team["alya"], team["yani"]])
    order = [_give_next(day, heni) for _ in range(6)]
    # Yani 6→7→8→9 (sampai 1 di bawah Alya), lalu bergantian menurut papan.
    assert order[:3] == ["yani", "yani", "yani"]
    assert order[3:] == ["lia", "alya", "yani"]
    assert monthly_tally([team["yani"].pk], dt.date(2026, 10, 20))[team["yani"].pk] == 10


def _scenario(jmr, team, counts, date, *, cuti=()):
    """Roster hari itu dari jadwal jaga; total bulanan diisi pada tanggal 1."""
    heni = team["heni"]
    if "desy" not in team:
        team["desy"] = _user(jmr, "desy", [Role.PERAWAT, Role.FRONT_DESK])
    for name, n in counts.items():
        _tally(jmr, dt.date(2026, 10, 1), team[name], n, heni)
        DutyRoster.objects.create(user=team[name], date=date, home_clinic=jmr, clinic=jmr, status=DutyStatus.MASUK)
    for name in cuti:
        DutyRoster.objects.create(user=team[name], date=dt.date(2026, 10, 20), home_clinic=jmr,
                                  status=DutyStatus.CUTI)
    day, _ = get_or_create_day(jmr, date=date)
    sync_roster_with_duty(day)
    return day


def test_scenario_off_catches_up_to_minus_one_then_board(jmr, team):
    # Skenario product owner 30 Sep: Yani 8 (habis off), Lia 11, Heni 11, Desy 12, Alya 11.
    day = _scenario(jmr, team, {"yani": 8, "lia": 11, "heni": 11, "desy": 12, "alya": 11}, dt.date(2026, 10, 25))
    names = [e.nurse.username for e in NurseRosterEntry.objects.filter(operational_day=day).order_by("position")]
    assert names[0] == "yani" and names[-1] == "desy"  # papan awal: total terkecil dulu
    # Koordinator Shift menata yang seri: Lia, Heni, Alya.
    lia = NurseRosterEntry.objects.get(operational_day=day, nurse=team["lia"])
    move_entry(lia, direction="naik", user=team["heni"])
    move_entry(lia, direction="naik", user=team["heni"])
    move_entry(NurseRosterEntry.objects.get(operational_day=day, nurse=team["heni"]), direction="naik",
               user=team["heni"])
    order = [_give_next(day, team["heni"]) for _ in range(7)]
    # Yani 8→10, lalu papan. Sesudah Lia/Heni/Alya jadi 12, Yani (10) kembali 2 di bawah
    # total terkecil rekan (Desy 12), jadi ia didahulukan lagi sebelum Desy; akhir: Yani 11.
    assert order == ["yani", "yani", "lia", "heni", "alya", "yani", "desy"]


def test_scenario_next_day_lowest_starts_first_without_streak(jmr, team):
    # Esoknya Yani 11, lainnya 12: Yani urutan pertama, tanpa keistimewaan mengejar.
    day = _scenario(jmr, team, {"yani": 11, "lia": 12, "heni": 12, "desy": 12, "alya": 12}, dt.date(2026, 10, 26))
    board = rotation_board(day)
    assert board["next"].nurse == team["yani"] and board["reason"] == "urutan papan"
    order = [_give_next(day, team["heni"]) for _ in range(2)]
    assert order[0] == "yani" and order[1] != "yani"


def test_scenario_leave_gets_first_place_but_no_streak(jmr, team):
    # Yani cuti bulan ini: tetap urutan pertama, tetapi tidak didahulukan berturut-turut.
    day = _scenario(jmr, team, {"yani": 7, "lia": 10, "heni": 10, "desy": 11, "alya": 10}, dt.date(2026, 10, 25),
                    cuti=["yani"])
    order = [_give_next(day, team["heni"]) for _ in range(5)]
    assert order[0] == "yani" and "yani" not in order[1:] and order[-1] == "desy"
    assert not any(r["lagging"] for r in rotation_board(day)["rows"])


def test_busy_and_off_nurses_are_skipped(jmr, team):
    heni = team["heni"]
    day = _roster(jmr, dt.date(2026, 10, 2), [team["lia"], team["alya"], team["yani"]])
    first = next_nurse(day)
    hand_over(first, user=heni)
    assert next_nurse(day) != first  # sedang menangani tidak diberi pasien lagi
    alya = NurseRosterEntry.objects.get(operational_day=day, nurse=team["alya"])
    alya.availability = Availability.OFF_DUTY
    alya.save()
    assert next_nurse(day).nurse == team["yani"]
    after_tally(day, first.nurse_id, amount=1, user=heni)
    first.refresh_from_db()
    assert first.availability == Availability.TERSEDIA and first.position == 3


def test_month_total_combines_branches_and_resets(jmr, ctl, team):
    heni = team["heni"]
    _tally(jmr, dt.date(2026, 10, 10), team["yani"], 5, heni)
    _tally(ctl, dt.date(2026, 10, 11), team["yani"], 3, heni)
    assert monthly_tally([team["yani"].pk], dt.date(2026, 10, 31))[team["yani"].pk] == 8
    assert monthly_tally([team["yani"].pk], dt.date(2026, 11, 1))[team["yani"].pk] == 0


def test_off_rest_day_counts_so_returning_nurse_catches_up(jmr, team):
    """Off pengganti hari libur tetap dihitung: yang baru masuk didahulukan."""
    heni = team["heni"]
    _tally(jmr, dt.date(2026, 10, 5), team["lia"], 4, heni)
    _tally(jmr, dt.date(2026, 10, 5), team["alya"], 4, heni)
    day = _roster(jmr, dt.date(2026, 10, 6), [team["lia"], team["alya"], team["yani"]])
    board = rotation_board(day)
    assert board["next"].nurse == team["yani"] and "mengejar" in board["reason"]


def test_ks_arrows_reorder_board(jmr, team):
    day = _roster(jmr, dt.date(2026, 10, 2), [team["lia"], team["alya"], team["yani"]])
    yani = NurseRosterEntry.objects.get(operational_day=day, nurse=team["yani"])
    move_entry(yani, direction="naik", user=team["heni"])
    move_entry(yani, direction="naik", user=team["heni"])
    assert next_nurse(day).nurse == team["yani"]
    with pytest.raises(PermissionDenied):
        move_entry(yani, direction="turun", user=team["lia"])


def test_sync_roster_uses_duty_schedule(jmr, ctl, team):
    date = dt.date(2026, 10, 11)
    for name in ("lia", "alya", "heni", "arsi"):
        DutyRoster.objects.create(user=team[name], date=date, home_clinic=jmr, clinic=jmr, status=DutyStatus.MASUK)
    DutyRoster.objects.create(user=team["yani"], date=date, home_clinic=jmr, clinic=ctl,
                              status=DutyStatus.PERBANTUAN)
    day, _ = get_or_create_day(jmr, date=date)
    result = sync_roster_with_duty(day)
    names = set(NurseRosterEntry.objects.filter(operational_day=day).values_list("nurse__username", flat=True))
    assert result["synced"] and names == {"lia", "alya", "heni"}  # Yani di Citraland, Arsi bukan perawat
    ctl_day, _ = get_or_create_day(ctl, date=date)
    sync_roster_with_duty(ctl_day)
    assert list(NurseRosterEntry.objects.filter(operational_day=ctl_day).values_list("nurse__username", flat=True)) == ["yani"]


def test_board_page_hand_over_and_tally(client, jmr, team):
    day = _roster(jmr, __import__("core.models", fromlist=["local_today"]).local_today(),
                  [team["lia"], team["alya"]])
    client.force_login(team["heni"])
    body = client.get(reverse("nurses:board")).content.decode()
    assert "Pasien berikutnya untuk" in body and "Bulan ini" in body
    lia = NurseRosterEntry.objects.get(operational_day=day, nurse=team["lia"])
    client.post(reverse("nurses:hand_over", args=[lia.pk]))
    lia.refresh_from_db()
    assert lia.availability == Availability.MENANGANI
    client.post(reverse("nurses:tally_create"), {"nurse": team["lia"].pk, "rm_number": "123",
                                                 "patient_name": "Pasien", "action_name": "Facial", "tally": 2})
    lia.refresh_from_db()
    assert lia.availability == Availability.TERSEDIA and lia.turns_taken == 2 and lia.position == 2
    client.force_login(team["lia"])
    # Fase 7: staf tidak membuka papan tim; menggeser urutan ditolak di server.
    assert client.post(reverse("nurses:move", args=[lia.pk]), {"arah": "naik"}).status_code == 403
    lia.refresh_from_db()
    assert lia.position == 2  # perawat biasa tidak dapat menggeser urutan
