"""Mengubah jadwal jaga harian dan bulanan (keputusan 3 Oktober 2026).

Direktur Operasional mengubah jadwal siapa pun: dari tabel bulanan (ketuk satu kotak) atau
dari halaman Tugas per tanggal (Siapa bertugas hari ini). Koordinator Shift melakukan hal yang
sama untuk staf yang cabang asalnya cabangnya, termasuk mengirim perbantuan ke cabang lain.
Untuk hari ini ke depan, porsi tugas dan roster giliran perawat ikut menyesuaikan.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest
from django.core.management import call_command
from django.urls import reverse

from accounts.models import Role, User, UserRole
from core.models import Clinic
from core.services import get_or_create_day
from jadwal.models import AssignmentSource, DutyAssignment, DutyRoster, DutyStatus
from jadwal.services import can_edit_duty, home_clinic_for, import_month, plan_month, set_duty
from nurses.models import Availability, NurseRosterEntry

pytestmark = pytest.mark.django_db
DATA = Path(__file__).resolve().parents[1] / "jadwal_bulanan" / "jadwal-2026-10.json"
PASSWORD = "TestPassword123!"


def d(day: int) -> dt.date:
    return dt.date(2026, 10, day)


@pytest.fixture
def cabang(db):
    jmr = Clinic.objects.create(code="jemur-andayani", name="JoDerma Jemur Andayani")
    ctl = Clinic.objects.create(code="JC", name="Joderma Citraland")
    return jmr, ctl


@pytest.fixture
def tim(cabang):
    call_command("seed_staf_cabang", password=PASSWORD, stdout=open("/dev/null", "w"))
    import_month(json.loads(DATA.read_text()))
    call_command("seed_tugas_harian", stdout=open("/dev/null", "w"))
    plan_month(cabang[0], 2026, 10)
    plan_month(cabang[1], 2026, 10)
    return {u.username: u for u in User.objects.all()}


@pytest.fixture
def direktur(cabang):
    user = User.objects.create_user(username="hansen", password=PASSWORD, display_name="dr Hansen")
    UserRole.objects.create(user=user, clinic=cabang[0], role=Role.AOM)
    return user


@pytest.fixture
def today_is(monkeypatch):
    def set_today(day):
        import core.models
        import jadwal.views

        monkeypatch.setattr(core.models, "local_today", lambda: day)
        monkeypatch.setattr(jadwal.views, "local_today", lambda: day)
    return set_today


def _who(clinic, day, code):
    return sorted(a.user.username for a in DutyAssignment.objects.filter(clinic=clinic, date=day, portion__code=code))


def test_permissions(tim, cabang, direktur):
    jmr, ctl = cabang
    assert can_edit_duty(direktur, jmr) and can_edit_duty(direktur, ctl)
    assert can_edit_duty(tim["regitta"], ctl) and not can_edit_duty(tim["regitta"], jmr)
    assert can_edit_duty(tim["heni"], jmr) and not can_edit_duty(tim["heni"], ctl)
    assert not can_edit_duty(tim["desy"], jmr)  # PIC Kasir bukan Koordinator Shift


def test_coordinator_sets_staff_off_today_and_portions_follow(tim, cabang, today_is):
    jmr, ctl = cabang
    today_is(d(3))
    assert _who(ctl, d(3), "opn-ks") == ["regitta"]
    others_before = {(a.portion.code, a.user_id) for a in DutyAssignment.objects.filter(clinic=ctl, date=d(3))
                     if a.user != tim["regitta"]}
    row = set_duty(user=tim["regitta"], day=d(3), status=DutyStatus.OFF, home_clinic=ctl, actor=tim["regitta"],
                   note="Sakit")
    assert row.sync["released"]
    assert not DutyAssignment.objects.filter(user=tim["regitta"], date=d(3)).exists()
    delegate = _who(ctl, d(3), "opn-ks")
    assert delegate and delegate != ["regitta"]
    # Porsi yang sudah dipegang orang lain tidak diacak ulang.
    after = {(a.portion.code, a.user_id) for a in DutyAssignment.objects.filter(clinic=ctl, date=d(3))}
    assert others_before <= after


def test_send_to_other_branch_moves_portions_and_nurse_roster(tim, cabang, today_is):
    jmr, ctl = cabang
    today_is(d(3))
    day_ctl, _ = get_or_create_day(ctl, date=d(3))
    day_jmr, _ = get_or_create_day(jmr, date=d(3))
    from nurses.services import sync_roster_with_duty

    sync_roster_with_duty(day_ctl)
    sync_roster_with_duty(day_jmr)
    silvi = tim["silvi"]
    assert DutyRoster.objects.get(user=silvi, date=d(3)).clinic == ctl
    set_duty(user=silvi, day=d(3), status=DutyStatus.PERBANTUAN, home_clinic=ctl, clinic=jmr,
             actor=tim["regitta"], note="Jemur kurang perawat")
    assert not DutyAssignment.objects.filter(user=silvi, date=d(3), clinic=ctl).exists()
    assert NurseRosterEntry.objects.get(operational_day=day_ctl, nurse=silvi).availability == Availability.OFF_DUTY
    assert NurseRosterEntry.objects.filter(operational_day=day_jmr, nurse=silvi).exists()


def test_past_dates_do_not_touch_portions(tim, cabang, today_is):
    jmr, _ = cabang
    today_is(d(10))
    before = list(DutyAssignment.objects.filter(clinic=jmr, date=d(2)).values_list("portion_id", "user_id"))
    lia = tim["lia"]
    row = set_duty(user=lia, day=d(2), status=DutyStatus.OFF, home_clinic=jmr, actor=tim["heni"])
    assert row.sync == {"released": [], "filled": []}
    assert list(DutyAssignment.objects.filter(clinic=jmr, date=d(2)).values_list("portion_id", "user_id")) == before


def test_manual_portion_of_absent_person_released(tim, cabang, today_is, direktur):
    jmr, _ = cabang
    today_is(d(2))
    a = DutyAssignment.objects.filter(clinic=jmr, date=d(2), user=tim["lia"]).first()
    if a is None:
        pytest.skip("Lia tidak memegang porsi 2 Okt")
    a.source = AssignmentSource.MANUAL
    a.save()
    set_duty(user=tim["lia"], day=d(2), status=DutyStatus.CUTI, home_clinic=jmr, actor=direktur)
    assert not DutyAssignment.objects.filter(user=tim["lia"], date=d(2)).exists()
    assert DutyAssignment.objects.filter(clinic=jmr, date=d(2), portion=a.portion).exists()


def test_home_clinic_kept_when_editing_visitor(tim, cabang):
    jmr, ctl = cabang
    assert home_clinic_for(tim["yani"], d(11)) == jmr  # perbantuan ke Citraland tiap Minggu
    assert home_clinic_for(User.objects.create_user(username="baru"), d(11), default=ctl) == ctl


def test_day_page_director_and_coordinator(client, tim, cabang, direktur, today_is):
    jmr, ctl = cabang
    today_is(d(11))
    url = reverse("jadwal:day", args=["2026-10-11"]) + f"?cabang={ctl.pk}"
    client.force_login(tim["regitta"])
    page = client.get(url).content.decode()
    assert "Siapa bertugas hari ini" in page
    section = page.split('id="bertugas"', 1)[1].split("</section>", 1)[0]
    assert f'name="orang" value="{tim["silvi"].pk}"' in section
    # Yani perbantuan dari Jemur: Regitta melihatnya, tetapi tidak mengubahnya.
    assert "dari JoDerma Jemur Andayani" in section and f'name="orang" value="{tim["yani"].pk}"' not in section
    response = client.post(url, {"aksi": "jadwal", "orang": tim["silvi"].pk, "tanggal": "2026-10-11",
                                 "status": "OFF", "catatan": "tukar"}, follow=True)
    assert DutyRoster.objects.get(user=tim["silvi"], date=d(11)).status == DutyStatus.OFF
    assert "Jadwal Silvi 11/10: Off" in response.content.decode()
    # Regitta tidak bisa mengubah Yani lewat POST langsung.
    client.post(url, {"aksi": "jadwal", "orang": tim["yani"].pk, "tanggal": "2026-10-11", "status": "OFF"})
    assert DutyRoster.objects.get(user=tim["yani"], date=d(11)).status == DutyStatus.PERBANTUAN
    # Direktur bisa, dan cabang asal Yani tetap Jemur.
    client.force_login(direktur)
    section = client.get(url).content.decode().split('id="bertugas"', 1)[1]
    assert f'name="orang" value="{tim["yani"].pk}"' in section
    client.post(url, {"aksi": "jadwal", "orang": tim["yani"].pk, "tanggal": "2026-10-11", "status": "OFF"})
    row = DutyRoster.objects.get(user=tim["yani"], date=d(11))
    assert row.status == DutyStatus.OFF and row.home_clinic == jmr
    # Perbantuan lewat pilihan gabungan.
    client.post(url, {"aksi": "jadwal", "orang": tim["nanda"].pk, "tanggal": "2026-10-11",
                      "status": f"PERBANTUAN:{jmr.pk}"})
    row = DutyRoster.objects.get(user=tim["nanda"], date=d(11))
    assert row.status == DutyStatus.PERBANTUAN and row.clinic == jmr and row.home_clinic == ctl


def test_monthly_grid_cells_editable(client, tim, cabang, direktur):
    jmr, ctl = cabang
    url = reverse("jadwal:roster") + f"?cabang={ctl.pk}&bulan=2026-10"
    client.force_login(tim["regitta"])
    body = client.get(url).content.decode()
    assert 'class="dc-edit"' in body and 'id="ubah-jadwal"' in body
    assert f'data-orang="{tim["silvi"].pk}"' in body and f'data-orang="{tim["yani"].pk}"' not in body
    client.post(reverse("jadwal:roster"), {"cabang": ctl.pk, "bulan": "2026-10", "orang": tim["naya"].pk,
                                           "tanggal": "2026-10-20", "status": "CUTI", "catatan": "cuti tahunan"})
    assert DutyRoster.objects.get(user=tim["naya"], date=d(20)).status == DutyStatus.CUTI
    client.force_login(tim["alya"])
    body = client.get(reverse("jadwal:roster") + f"?cabang={jmr.pk}&bulan=2026-10").content.decode()
    assert 'class="dc-edit"' not in body
    assert client.post(reverse("jadwal:roster"), {"cabang": jmr.pk, "orang": tim["lia"].pk,
                                                  "tanggal": "2026-10-20", "status": "OFF"}).status_code == 403
    client.force_login(direktur)
    body = client.get(url).content.decode()
    assert f'data-orang="{tim["yani"].pk}"' in body


def test_stray_role_in_other_branch_not_listed(client, tim, cabang, direktur):
    """Peran lama yang tertinggal (kasus produksi: Regitta dan Ayu masih punya peran di Jemur)
    tidak membuat mereka muncul di daftar bertugas Jemur."""
    jmr, ctl = cabang
    UserRole.objects.create(user=tim["regitta"], clinic=jmr, role=Role.ONLINE)
    client.force_login(direktur)
    section = client.get(reverse("jadwal:day", args=["2026-10-05"]) + f"?cabang={jmr.pk}").content.decode()
    section = section.split('id="bertugas"', 1)[1].split("</section>", 1)[0]
    assert "Regitta" not in section and "Heni" in section


def test_cleanup_commands_remove_stray_roles_and_replan(tim, cabang, direktur):
    """Perintah perapian 3 Okt: cabut peran yang tertinggal, lalu susun ulang porsi ke depan."""
    from io import StringIO

    from audit.models import AuditAction, AuditEvent

    jmr, ctl = cabang
    UserRole.objects.create(user=tim["elvira"], clinic=jmr, role=Role.SUPERVISOR)
    UserRole.objects.create(user=tim["regitta"], clinic=jmr, role=Role.SUPERVISOR)
    plan_month(jmr, 2026, 10)
    out = StringIO()
    call_command("cabut_peran", "regitta", "jemur", "--semua", "--dry-run", stdout=out)
    assert "[dry-run]" in out.getvalue() and UserRole.objects.filter(user=tim["regitta"], clinic=jmr).exists()
    call_command("cabut_peran", "regitta", "jemur", "--semua", catatan="Memo 002", stdout=out)
    call_command("cabut_peran", "elvira", "jemur", "SUPERVISOR", stdout=out)
    assert not UserRole.objects.filter(user=tim["regitta"], clinic=jmr).exists()
    assert set(tim["elvira"].user_roles.values_list("role", flat=True)) >= {Role.APOTEKER, Role.PIC}
    assert not tim["elvira"].user_roles.filter(role=Role.SUPERVISOR).exists()
    assert UserRole.objects.filter(user=tim["regitta"], clinic=ctl, role=Role.SUPERVISOR).exists()
    assert AuditEvent.objects.filter(action=AuditAction.PERMISSION_CHANGED, entity_label__icontains="regitta").exists()
    call_command("susun_ulang_tugas", "--cabang", "jemur", "--mulai", "2026-10-04", "--sampai", "2026-10-31",
                 stdout=out)
    ks = DutyAssignment.objects.filter(clinic=jmr, date__gte=d(4), portion__code__in=["opn-ks", "cls-ks"])
    assert ks.exists() and not ks.filter(user=tim["elvira"]).exists()
