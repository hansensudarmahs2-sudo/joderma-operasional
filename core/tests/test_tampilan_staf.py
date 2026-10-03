"""Fase 7: tampilan staf sederhana (Tugas hari ini, Jadwal saya, Istirahat saya, Tindakan saya, Kas hari kasir)."""
from __future__ import annotations

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from accounts.models import PicAssignment, PicFunction, Role, User, UserRole
from breaks.models import BreakSchedule, BreakType
from checklists.models import ChecklistArea, ChecklistResponse, ChecklistRun, ChecklistSession, ChecklistTemplate
from checklists.models import ResponseResult
from core.models import OperationalDay, local_today
from jadwal.models import DutyAssignment, DutyGroup, DutyPortion, DutyRoster, DutyStatus
from nurses.models import Availability, NurseActionTally, NurseRosterEntry

pytestmark = pytest.mark.django_db


def _user(clinic, name, *roles):
    u = User.objects.create_user(username=name, password="TestPassword123!", display_name=name.title())
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


def _at(day, hh, mm=0):
    return timezone.make_aware(dt.datetime.combine(day, dt.time(hh, mm)), timezone.get_current_timezone())


@pytest.fixture
def team(clinic):
    return {
        "ani": _user(clinic, "ani", Role.PERAWAT, Role.STAF),
        "budi": _user(clinic, "budi", Role.PERAWAT, Role.STAF),
        "nanda": _user(clinic, "nanda", Role.ASISTEN_APOTEKER, Role.FRONT_DESK, Role.STAF),
        "koor": _user(clinic, "koor", Role.SUPERVISOR, Role.PERAWAT),
    }


def test_today_page_lists_my_portion_items(client, clinic, team):
    ani, today = team["ani"], local_today()
    client.force_login(ani)
    page = client.get(reverse("core:today")).content.decode()
    assert "Buat sesi hari ini" in page
    assert client.get(reverse("core:today") + "?buat=1").status_code == 302
    day = OperationalDay.objects.get(clinic=clinic, date=today)

    portion = DutyPortion.objects.create(clinic=clinic, code="opening-1", name="Opening · Pintu", group=DutyGroup.OPENING)
    other = DutyPortion.objects.create(clinic=clinic, code="limbah", name="Limbah", group=DutyGroup.LIMBAH)
    DutyAssignment.objects.create(portion=portion, clinic=clinic, date=today, user=ani)
    DutyAssignment.objects.create(portion=other, clinic=clinic, date=today, user=team["budi"])
    DutyRoster.objects.create(user=ani, date=today, home_clinic=clinic, clinic=clinic, status=DutyStatus.MASUK)
    tpl = ChecklistTemplate.objects.create(clinic=clinic, name="Akses umum", area=ChecklistArea.AKSES_UMUM, version=1)
    run = ChecklistRun.objects.create(operational_day=day, template=tpl, area=tpl.area,
                                      session=ChecklistSession.OPENING, template_snapshot={})
    ChecklistResponse.objects.create(run=run, item_snapshot={}, label="Pintu", portion="opening-1",
                                     result=ResponseResult.OK, checked_by=ani, checked_at=timezone.now())
    ChecklistResponse.objects.create(run=run, item_snapshot={}, label="Lampu", portion="opening-1")
    ChecklistResponse.objects.create(run=run, item_snapshot={}, label="Limbah", portion="limbah")

    page = client.get(reverse("core:today")).content.decode()
    assert "Opening · Pintu" in page and "Limbah" not in page
    assert "1/2" in page and f"{reverse('checklists:run', args=[run.pk])}?saya=1" in page
    assert "Masuk" in page and "Tugas saya" in page
    # Halaman pengisian tetap bisa dibuka staf, hanya tidak ada di menu.
    assert client.get(reverse("checklists:run", args=[run.pk]) + "?saya=1").status_code == 200
    assert client.get(reverse("core:dashboard")).status_code == 200


def test_cash_only_on_cashier_day(client, clinic, team):
    nanda, today = team["nanda"], local_today()
    client.force_login(nanda)
    assert client.get(reverse("cash:index")).status_code == 403
    page = client.get(reverse("core:today")).content.decode()
    assert "Buka Kas" not in page and ">Kas<" not in page
    OperationalDay.objects.create(clinic=clinic, date=today)
    hari_ini = client.get(reverse("core:dashboard")).content.decode()
    assert "Status kas" not in hari_ini and f'href="{reverse("nurses:board")}"' not in hari_ini
    assert reverse("breaks:mine") in hari_ini

    kas = DutyPortion.objects.create(clinic=clinic, code="kas", name="Kasir hari ini", group=DutyGroup.KAS)
    DutyAssignment.objects.create(portion=kas, clinic=clinic, date=today - dt.timedelta(days=1), user=nanda)
    assert client.get(reverse("cash:index")).status_code == 403  # kasir kemarin, bukan hari ini
    DutyAssignment.objects.create(portion=kas, clinic=clinic, date=today, user=nanda)
    assert client.get(reverse("cash:index")).status_code == 200
    page = client.get(reverse("core:today")).content.decode()
    assert "Anda kasir hari ini" in page and "Buka Kas" in page and ">Kas<" in page
    assert "Status kas" in client.get(reverse("core:dashboard")).content.decode()

    # PIC Kasir (bukan tampilan staf) tetap membuka Kas tanpa porsi.
    desy = _user(clinic, "desy", Role.PIC, Role.FRONT_DESK)
    PicAssignment.objects.create(user=desy, clinic=clinic, function=PicFunction.CASHIER, starts_on="2026-09-01")
    client.force_login(desy)
    assert client.get(reverse("cash:index")).status_code == 200


def test_my_schedule_and_breaks_only_show_me(client, clinic, team):
    ani, budi, today = team["ani"], team["budi"], local_today()
    DutyRoster.objects.create(user=ani, date=today, home_clinic=clinic, clinic=clinic, status=DutyStatus.MASUK)
    DutyRoster.objects.create(user=budi, date=today, home_clinic=clinic, clinic=None, status=DutyStatus.OFF)
    BreakSchedule.objects.create(clinic=clinic, user=ani, date=today, break_type=BreakType.MAKAN,
                                 start_at=_at(today, 15), end_at=_at(today, 15, 30))
    BreakSchedule.objects.create(clinic=clinic, user=budi, date=today, break_type=BreakType.IBADAH,
                                 start_at=_at(today, 16), end_at=_at(today, 16, 15))
    client.force_login(ani)
    body = client.get(reverse("jadwal:mine")).content.decode()
    assert "Jadwal saya" in body and "1 hari masuk" in body and "Budi" not in body
    body = client.get(reverse("breaks:mine")).content.decode()
    assert "Makan" in body and "15.00–15.30" in body and "Ibadah" not in body
    assert "Istirahat hari ini" in client.get(reverse("core:today")).content.decode()
    for route in ("jadwal:roster", "breaks:list", "breaks:create", "nurses:board", "nurses:ledger"):
        assert client.get(reverse(route)).status_code == 403, route
    client.force_login(team["koor"])  # Koordinator Shift tetap membuka grid tim
    assert client.get(reverse("jadwal:roster")).status_code == 200
    assert client.get(reverse("breaks:list")).status_code == 200


def test_my_procedures_tally_only_for_myself(client, clinic, team):
    ani, budi, today = team["ani"], team["budi"], local_today()
    for u in (ani, budi):
        DutyRoster.objects.create(user=u, date=today, home_clinic=clinic, clinic=clinic, status=DutyStatus.MASUK)
    client.force_login(ani)
    page = client.get(reverse("nurses:mine")).content.decode()
    assert "Tindakan saya" in page and "Tally hari ini" in page
    me = NurseRosterEntry.objects.get(operational_day__date=today, nurse=ani)

    mine_url = reverse("nurses:mine")
    resp = client.post(reverse("nurses:tally_create"), {"next": mine_url, "nurse": ani.pk, "rm_number": "1109",
                                                        "patient_name": "Pasien", "action_name": "Facial", "tally": 2})
    assert resp["Location"] == mine_url
    assert NurseActionTally.objects.get(nurse=ani).entered_by == ani
    # Mencatat tally untuk perawat lain ditolak bagi staf.
    client.post(reverse("nurses:tally_create"), {"next": mine_url, "nurse": budi.pk, "rm_number": "1110",
                                                 "patient_name": "Pasien", "action_name": "Laser", "tally": 1})
    assert not NurseActionTally.objects.filter(nurse=budi).exists()
    page = client.get(mine_url).content.decode()
    assert "Facial" in page and "Laser" not in page

    resp = client.post(reverse("nurses:availability", args=[me.pk]), {"next": mine_url, "ketersediaan": "ISTIRAHAT"})
    assert resp["Location"] == mine_url
    me.refresh_from_db()
    assert me.availability == Availability.ISTIRAHAT
    budi_entry = NurseRosterEntry.objects.get(operational_day__date=today, nurse=budi)
    client.post(reverse("nurses:availability", args=[budi_entry.pk]), {"next": mine_url, "ketersediaan": "OFF_DUTY"})
    budi_entry.refresh_from_db()
    assert budi_entry.availability != Availability.OFF_DUTY  # perawat lain tidak bisa diubah
