"""Fase 8: PIC mengganti pelaksana hanya untuk porsi fungsinya di cabangnya."""
from __future__ import annotations

import datetime as dt

import pytest
from django.urls import reverse

from accounts.models import PicAssignment, PicFunction, Role, User, UserRole
from core.models import Clinic, local_today
from jadwal import services
from jadwal.models import DutyAssignment, DutyGroup, DutyPortion, DutyRoster, DutyStatus

pytestmark = pytest.mark.django_db


def _user(clinic, name, *roles, pic=()):
    u = User.objects.create_user(username=name, password="TestPassword123!", display_name=name.title())
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    for function in pic:
        PicAssignment.objects.create(user=u, clinic=clinic, function=function, starts_on="2026-09-01")
    return u


@pytest.fixture
def setup(db):
    today = local_today()
    jmr = Clinic.objects.create(code="jemur", name="JoDerma Jemur")
    ctl = Clinic.objects.create(code="citraland", name="JoDerma Citraland")
    p = {
        "koor": _user(jmr, "heni", Role.PERAWAT, Role.SUPERVISOR, Role.PIC, pic=[PicFunction.SHIFT_COORDINATOR]),
        "desy": _user(jmr, "desy", Role.PERAWAT, Role.FRONT_DESK, Role.PIC, pic=[PicFunction.CASHIER, PicFunction.ONLINE]),
        "elvira": _user(jmr, "elvira", Role.APOTEKER, Role.FRONT_DESK, Role.PIC,
                        pic=[PicFunction.PHARMACY, PicFunction.CLEANLINESS]),
        "arsi": _user(jmr, "arsi", Role.ASISTEN_APOTEKER, Role.FRONT_DESK, Role.STAF),
        "lia": _user(jmr, "lia", Role.PERAWAT, Role.STAF),
    }
    for u in p.values():
        DutyRoster.objects.create(user=u, date=today, home_clinic=jmr, clinic=jmr, status=DutyStatus.MASUK)

    def portion(clinic, code, group, roles=(), pic=""):
        return DutyPortion.objects.create(clinic=clinic, code=code, name=code, group=group,
                                          eligible_roles=list(roles), pic_function=pic)

    portions = {
        "kas": portion(jmr, "kas", DutyGroup.KAS, [Role.FRONT_DESK], PicFunction.CASHIER),
        "apt": portion(jmr, "apt-harian", DutyGroup.APOTEK, [Role.APOTEKER, Role.ASISTEN_APOTEKER]),
        "kbr": portion(jmr, "kbr-piket", DutyGroup.KEBERSIHAN),
        "lmb": portion(jmr, "lmb-ruang", DutyGroup.LIMBAH),
        "opn": portion(jmr, "opn-akses", DutyGroup.OPENING),
        "kas_ctl": portion(ctl, "kas", DutyGroup.KAS, [Role.FRONT_DESK], PicFunction.CASHIER),
    }
    DutyAssignment.objects.create(portion=portions["kas"], clinic=jmr, date=today, user=p["desy"])
    return {"today": today, "jmr": jmr, "ctl": ctl, **p, "portions": portions}


def test_swap_rights_follow_pic_function(setup):
    P, today = setup["portions"], setup["today"]
    allowed = {name: {key for key, portion in P.items() if services.can_swap_portion(setup[name], portion, today)}
               for name in ("koor", "desy", "elvira", "arsi")}
    assert allowed["koor"] == {"kas", "apt", "kbr", "lmb", "opn"}  # semua porsi cabangnya, bukan Citraland
    assert allowed["desy"] == {"kas"}  # PIC Kasir; Layanan Daring tidak punya porsi
    assert allowed["elvira"] == {"apt", "kbr", "lmb"}  # PIC Apotek + PJ Kebersihan
    assert allowed["arsi"] == set()
    # Penugasan PIC yang sudah berakhir tidak memberi hak.
    PicAssignment.objects.filter(user=setup["desy"]).update(ends_on=today - dt.timedelta(days=1))
    assert not services.can_swap_portion(setup["desy"], P["kas"], today)


def test_pic_cashier_swaps_cashier_over_http(client, setup):
    P, today, jmr = setup["portions"], setup["today"], setup["jmr"]
    url = reverse("jadwal:day", args=[today.isoformat()]) + f"?cabang={jmr.pk}"
    client.force_login(setup["desy"])
    page = client.get(url).content.decode()
    assert page.count("<summary>Ganti pelaksana</summary>") == 1 and "porsi fungsi Anda" in page
    resp = client.post(url, {"cabang": jmr.pk, "porsi": P["kas"].pk, "orang": [setup["arsi"].pk],
                             "catatan": "Desy sakit"})
    assert resp.status_code == 302
    assert list(DutyAssignment.objects.filter(portion=P["kas"], date=today).values_list("user__username", flat=True)) \
        == ["arsi"]
    # Porsi di luar fungsinya ditolak di server.
    resp = client.post(url, {"cabang": jmr.pk, "porsi": P["opn"].pk, "orang": [setup["lia"].pk]})
    assert resp.status_code == 403
    assert not DutyAssignment.objects.filter(portion=P["opn"]).exists()
    # Dengan porsi kasir pindah ke Arsi, Arsi (staf) kini membuka Kas hari ini.
    client.force_login(setup["arsi"])
    assert client.get(reverse("cash:index")).status_code == 200


def test_shift_coordinator_still_swaps_everything(client, setup):
    P, today, jmr = setup["portions"], setup["today"], setup["jmr"]
    url = reverse("jadwal:day", args=[today.isoformat()]) + f"?cabang={jmr.pk}"
    client.force_login(setup["koor"])
    page = client.get(url).content.decode()
    assert page.count("<summary>Ganti pelaksana</summary>") == 5 and "porsi fungsi Anda" not in page
    client.post(url, {"cabang": jmr.pk, "porsi": P["opn"].pk, "orang": [setup["lia"].pk]})
    assert DutyAssignment.objects.filter(portion=P["opn"], user=setup["lia"]).exists()
