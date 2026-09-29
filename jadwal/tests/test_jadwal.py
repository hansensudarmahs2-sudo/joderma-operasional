"""Jadwal jaga Oktober 2026, pembagian tugas, dan hubungannya dengan checklist."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.urls import reverse

from accounts.models import PicAssignment, PicFunction, Role, User, UserRole
from checklists.models import ChecklistRun, ChecklistTemplate, InputType, ResponseResult
from checklists.services import record_response
from core.models import Clinic
from core.permissions import can_edit_checklist_response
from core.services import active_clinic, get_or_create_day
from jadwal.models import AssignmentSource, DutyAssignment, DutyPortion, DutyRoster, DutyStatus
from jadwal.services import (
    import_month,
    plan_month,
    set_duty,
    set_portion_people,
    staff_on_duty,
)

pytestmark = pytest.mark.django_db
DATA = Path(__file__).resolve().parents[1] / "data" / "jadwal-2026-10.json"
PASSWORD = "TestPassword123!"


def d(day: int) -> dt.date:
    return dt.date(2026, 10, day)


@pytest.fixture
def cabang(db):
    jmr = Clinic.objects.create(code="jemur-andayani", name="JoDerma Jemur Andayani",
                                open_time="14:00", close_time="22:00")
    ctl = Clinic.objects.create(code="citraland", name="JoDerma Citraland", open_time="12:00", close_time="21:00")
    return jmr, ctl


@pytest.fixture
def tim(cabang):
    call_command("seed_staf_cabang", password=PASSWORD, stdout=open("/dev/null", "w"))
    import_month(json.loads(DATA.read_text()))
    call_command("seed_tugas_harian", stdout=open("/dev/null", "w"))
    return {u.username: u for u in User.objects.all()}


@pytest.fixture
def direktur(cabang):
    user = User.objects.create_user(username="hansen", password=PASSWORD, display_name="dr Hansen")
    UserRole.objects.create(user=user, clinic=cabang[0], role=Role.AOM)
    return user


# --- Jadwal jaga -------------------------------------------------------------------

def test_october_import_counts_and_assist_days(tim, cabang):
    jmr, ctl = cabang
    assert DutyRoster.objects.filter(date__month=10).count() == 13 * 31
    working = lambda name: DutyRoster.objects.filter(user=tim[name], status__in=["MASUK", "PERBANTUAN"]).count()
    assert working("heni") == 26 and working("elvira") == 27 and working("alya") == 26
    # Yani di Citraland tiap Minggu 11, 18, 25 Oktober; Luki 10 hari.
    yani = DutyRoster.objects.filter(user=tim["yani"], status=DutyStatus.PERBANTUAN)
    assert sorted(r.date.day for r in yani) == [11, 18, 25] and all(r.clinic == ctl for r in yani)
    assert DutyRoster.objects.filter(user=tim["luki"], status=DutyStatus.PERBANTUAN, clinic=ctl).count() == 10
    assert DutyRoster.objects.get(user=tim["heni"], date=d(1)).status == DutyStatus.OFF


def test_import_reports_inconsistent_tables(tim):
    data = json.loads(DATA.read_text())
    row = list(data["clinics"]["citraland"]["yani"])
    row[10] = "P"  # Minggu 11 Okt: tabel Jemur bilang ke Citraland, tabel Citraland bilang ke Jemur
    data["clinics"]["citraland"]["yani"] = "".join(row)
    result = import_month(data)
    assert any("yani 11/10" in w for w in result["warnings"])


def test_staff_on_duty_follows_roster(tim, cabang):
    jmr, ctl = cabang
    on_jmr = {u.username for u in staff_on_duty(jmr, d(11))}
    on_ctl = {u.username for u in staff_on_duty(ctl, d(11))}
    assert "yani" in on_ctl and "yani" not in on_jmr
    assert "desy" not in {u.username for u in staff_on_duty(jmr, d(12))}  # libur tetap Senin


def test_only_director_edits_roster(tim, cabang, direktur):
    jmr, _ = cabang
    with pytest.raises(PermissionDenied):
        set_duty(user=tim["lia"], day=d(2), status=DutyStatus.OFF, home_clinic=jmr, actor=tim["heni"])
    row = set_duty(user=tim["lia"], day=d(2), status=DutyStatus.OFF, home_clinic=jmr, actor=direktur)
    assert row.clinic is None
    with pytest.raises(ValidationError):
        set_duty(user=tim["lia"], day=d(2), status=DutyStatus.PERBANTUAN, home_clinic=jmr, actor=direktur)


def test_active_clinic_follows_assist_day(tim, cabang, monkeypatch):
    jmr, ctl = cabang
    import core.services

    monkeypatch.setattr(core.services, "local_today", lambda: d(11))
    assert active_clinic(tim["yani"]) == ctl
    monkeypatch.setattr(core.services, "local_today", lambda: d(12))
    assert active_clinic(tim["yani"]) == jmr


# --- Seed checklist dan porsi -------------------------------------------------------

def test_seed_is_idempotent_and_retires_old_templates(tim, cabang):
    jmr, _ = cabang
    keys = set(ChecklistTemplate.objects.filter(clinic=jmr, active=True).values_list("audience_key", flat=True))
    assert keys == {"OPENING", "KEBERSIHAN", "LIMBAH", "CLOSING", "APOTEK"}
    before = ChecklistTemplate.objects.count()
    call_command("seed_tugas_harian", stdout=open("/dev/null", "w"))
    assert ChecklistTemplate.objects.count() == before


def test_apotek_items_belong_to_pharmacy_roles_only(tim, cabang):
    jmr, _ = cabang
    t = ChecklistTemplate.objects.get(clinic=jmr, audience_key="APOTEK", active=True)
    assert set(t.target_roles) == {Role.APOTEKER, Role.ASISTEN_APOTEKER}
    assert all(set(i.performer_roles) == {Role.APOTEKER, Role.ASISTEN_APOTEKER} for i in t.items.all())
    assert not any(i.portion.startswith("apt") for i in ChecklistTemplate.objects.get(
        clinic=jmr, audience_key="OPENING", active=True).items.all())


def test_closing_follows_product_owner_request(tim, cabang):
    jmr, _ = cabang
    labels = [i.label for i in ChecklistTemplate.objects.get(clinic=jmr, audience_key="CLOSING", active=True)
              .items.order_by("sort_order")]
    text = " | ".join(labels)
    for needle in ("panggilan terakhir", "pasien terakhir selesai", "total bulanan", "Resepsionis dirapikan",
                   "Ruang konsultasi dirapikan", "Ruang facial dan estetik dirapikan", "log limbah", "Pintu dikunci"):
        assert needle.lower() in text.lower(), needle
    kebersihan = ChecklistTemplate.objects.get(clinic=jmr, audience_key="KEBERSIHAN", active=True)
    resepsionis = kebersihan.items.get(portion="kbr-resepsionis")
    assert resepsionis.min_quantity == 8  # 14.00–22.00, tiap jam
    assert kebersihan.items.filter(label__icontains="19.00").exists()


# --- Pembagian tugas ------------------------------------------------------------------

def _who(clinic, day, code):
    return sorted(a.user.username for a in DutyAssignment.objects.filter(clinic=clinic, date=day, portion__code=code))


def test_plan_gives_pic_their_portion_and_delegates_when_off(tim, cabang):
    jmr, ctl = cabang
    plan_month(jmr, 2026, 10)
    plan_month(ctl, 2026, 10)
    assert _who(jmr, d(2), "opn-ks") == ["heni"] and _who(jmr, d(2), "kas") == ["desy"]
    assert _who(jmr, d(2), "kbr-pj") == ["elvira"] and _who(jmr, d(2), "apt-harian") == ["elvira"]
    # 1 Okt Heni off → opening KS didelegasikan ke perawat yang bertugas.
    delegate = _who(jmr, d(1), "opn-ks")
    assert delegate and delegate != ["heni"]
    # 4 Okt Desy off → kasir dari cadangan (Arsi, Luki, atau Elvira).
    assert _who(jmr, d(4), "kas")[0] in {"arsi", "luki", "elvira"}
    assert _who(ctl, d(3), "opn-ks") == ["regitta"] and _who(ctl, d(3), "apt-harian") == ["ayu"]


def test_plan_respects_roles_off_days_and_weekly(tim, cabang):
    jmr, _ = cabang
    plan_month(jmr, 2026, 10)
    for a in DutyAssignment.objects.filter(clinic=jmr).select_related("portion", "user"):
        duty = DutyRoster.objects.get(user=a.user, date=a.date)
        assert duty.clinic == jmr, f"{a} diberikan ke orang yang tidak bertugas"
        if a.portion.group == "APOTEK":
            assert a.user.role_codes() & {Role.APOTEKER, Role.ASISTEN_APOTEKER}
    assert {a.date.weekday() for a in DutyAssignment.objects.filter(clinic=jmr, portion__code="apt-opname")} == {0}
    assert all(len(_who(jmr, d(n), "kbr-piket")) == 2 for n in range(1, 32))


def test_plan_spreads_open_portions(tim, cabang):
    jmr, _ = cabang
    plan_month(jmr, 2026, 10)
    from collections import Counter

    counts = Counter(DutyAssignment.objects.filter(clinic=jmr, portion__code="kbr-piket").values_list(
        "user__username", flat=True))
    # Piket bergilir: semua yang bertugas kebagian, tidak menumpuk pada satu orang.
    assert len(counts) >= 6 and max(counts.values()) - min(counts.values()) <= 6


def test_manual_swap_survives_replan_and_is_checked(tim, cabang, direktur):
    jmr, _ = cabang
    plan_month(jmr, 2026, 10)
    piket = DutyPortion.objects.get(clinic=jmr, code="kbr-piket")
    set_portion_people(piket, d(2), [tim["lia"], tim["arsi"]], actor=tim["heni"], note="tukar")
    plan_month(jmr, 2026, 10, actor=direktur)
    assert _who(jmr, d(2), "kbr-piket") == ["arsi", "lia"]
    assert set(DutyAssignment.objects.filter(portion=piket, date=d(2)).values_list("source", flat=True)) == {
        AssignmentSource.MANUAL}
    with pytest.raises(ValidationError):  # Heni off 1 Okt
        set_portion_people(piket, d(1), [tim["heni"]], actor=direktur)
    apt = DutyPortion.objects.get(clinic=jmr, code="apt-coldchain")
    with pytest.raises(ValidationError):  # perawat bukan peran apotek
        set_portion_people(apt, d(2), [tim["lia"]], actor=direktur)
    with pytest.raises(PermissionDenied):  # perawat biasa tidak menukar
        set_portion_people(piket, d(2), [tim["lia"]], actor=tim["alya"])
    with pytest.raises(PermissionDenied):  # Koordinator Shift Jemur tidak menukar di Citraland
        set_portion_people(DutyPortion.objects.get(clinic=cabang[1], code="kbr-piket"), d(2),
                           [tim["silvi"]], actor=tim["heni"])


def test_delegate_can_fill_ks_items_only_when_assigned(tim, cabang, monkeypatch):
    jmr, _ = cabang
    plan_month(jmr, 2026, 10)
    day, _ = get_or_create_day(jmr, date=d(1))
    run = ChecklistRun.objects.get(operational_day=day, template__audience_key="OPENING")
    ks_item = run.responses.filter(portion="opn-ks").first()
    delegate = DutyAssignment.objects.get(clinic=jmr, date=d(1), portion__code="opn-ks").user
    other = next(u for u in staff_on_duty(jmr, d(1))
                 if u != delegate and Role.SUPERVISOR not in u.role_codes())
    assert Role.SUPERVISOR not in delegate.role_codes()
    assert can_edit_checklist_response(delegate, ks_item)
    assert not can_edit_checklist_response(other, ks_item)


def test_jam_item_requires_time(tim, cabang):
    jmr, _ = cabang
    day, _ = get_or_create_day(jmr, date=d(2))
    run = ChecklistRun.objects.get(operational_day=day, template__audience_key="CLOSING")
    item = run.responses.filter(input_type=InputType.JAM).first()
    with pytest.raises(ValidationError):
        record_response(item, user=tim["heni"], result=ResponseResult.OK, selection="")
    record_response(item, user=tim["heni"], result=ResponseResult.OK, selection="21:40")
    item.refresh_from_db()
    assert item.selection == "21:40"


# --- Halaman ----------------------------------------------------------------------

def test_pages_render_and_permissions(client, tim, cabang, direktur):
    jmr, ctl = cabang
    plan_month(jmr, 2026, 10)
    client.force_login(tim["alya"])
    body = client.get(reverse("jadwal:roster") + f"?cabang={jmr.pk}&bulan=2026-10").content.decode()
    assert "Heni" in body and "Ubah satu tanggal" not in body
    assert client.get(reverse("jadwal:roster") + f"?cabang={ctl.pk}").status_code == 403
    assert client.post(reverse("jadwal:plan") + f"?cabang={jmr.pk}&bulan=2026-10").status_code == 403
    page = client.get(reverse("jadwal:day", args=["2026-10-02"]) + f"?cabang={jmr.pk}").content.decode()
    assert "Kasir hari ini" in page and "Ganti pelaksana" not in page
    client.force_login(tim["heni"])
    page = client.get(reverse("jadwal:day", args=["2026-10-02"]) + f"?cabang={jmr.pk}").content.decode()
    assert "Ganti pelaksana" in page
    client.force_login(direktur)
    body = client.get(reverse("jadwal:plan") + f"?cabang={ctl.pk}&bulan=2026-10").content.decode()
    assert "Susun ulang otomatis" in body
    assert client.post(reverse("jadwal:plan"), {"cabang": ctl.pk, "bulan": "2026-10"}).status_code == 302
    assert DutyAssignment.objects.filter(clinic=ctl).exists()


def test_checklist_index_shows_my_duties(client, tim, cabang, monkeypatch):
    jmr, _ = cabang
    plan_month(jmr, 2026, 10)
    import checklists.views
    import core.services

    monkeypatch.setattr(core.services, "local_today", lambda: d(2))
    get_or_create_day(jmr, date=d(2))
    monkeypatch.setattr(checklists.views, "_current_day", lambda request: get_or_create_day(jmr, date=d(2))[0])
    client.force_login(tim["desy"])
    body = client.get(reverse("checklists:index")).content.decode()
    assert "Tugas saya hari ini" in body and "Kasir hari ini" in body


def test_seed_staff_command(cabang):
    jmr, ctl = cabang
    old = User.objects.create_user(username="heny", password=PASSWORD)
    UserRole.objects.create(user=User.objects.create_user(username="naya", password=PASSWORD), clinic=jmr,
                            role=Role.PERAWAT)
    call_command("seed_staf_cabang", password=PASSWORD, prune=True, stdout=open("/dev/null", "w"))
    old.refresh_from_db()
    assert old.username == "heni"
    assert not UserRole.objects.filter(user__username="naya", clinic=jmr).exists()
    regitta = User.objects.get(username="regitta")
    assert regitta.must_change_password
    assert set(PicAssignment.objects.filter(user=regitta).values_list("function", flat=True)) == {
        PicFunction.SHIFT_COORDINATOR, PicFunction.ONLINE}
    assert PicAssignment.objects.filter(user__username="ayu", clinic=ctl, function=PicFunction.PHARMACY).exists()
    assert set(UserRole.objects.filter(user__username="yani").values_list("clinic__code", flat=True)) == {
        "jemur-andayani", "citraland"}
