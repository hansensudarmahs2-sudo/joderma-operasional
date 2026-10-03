"""Dua cabang, Jemur Andayani dan Citraland (masalah nyata 2-3 Oktober 2026).

Laporan Regitta (Koordinator Shift Citraland):

- akunnya tampil sebagai Jemur saat ia off: cabang aktif jatuh ke cabang pertama;
- kode Citraland di mini PC adalah ``JC``, sehingga prefix RM dan butir khusus cabang salah;
- tally yang sudah tersimpan tidak bisa dikoreksi;
- hari tidak bisa ditutup karena kas akhir harus diverifikasi Direktur dulu.
"""
from __future__ import annotations

import datetime as dt

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from accounts.models import Role, User, UserRole
from audit.models import AuditAction, AuditEvent
from cash.models import CashSessionType, CashStatus
from cash.services import get_or_create_session, pending_verification, save_count, submit_for_verification, verify
from core.models import Clinic, DayStatus, OperationalDay, local_today
from core.services import active_clinic, clinic_key, close_day, closing_blockers, get_or_create_day, rm_prefix
from jadwal.models import DutyRoster, DutyStatus
from nurses.models import NurseActionTally, NurseRosterEntry
from nurses.services import can_correct_tally, correct_tally

pytestmark = pytest.mark.django_db
PASSWORD = "TestPassword123!"


def _user(name, roles, **extra):
    u = User.objects.create_user(username=name, password=PASSWORD, display_name=name.title(), **extra)
    for clinic, role in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=role)
    return u


@pytest.fixture
def jemur(db):
    return Clinic.objects.create(code="JJ", name="Jemur Andayani")


@pytest.fixture
def citraland(db):
    return Clinic.objects.create(code="JC", name="Citraland")


@pytest.fixture
def regita(jemur, citraland):
    # Persis seperti di produksi: masih memegang peran lama di Jemur (id lebih kecil).
    return _user("regita", [(jemur, Role.ONLINE), (citraland, Role.SUPERVISOR), (citraland, Role.PERAWAT)])


@pytest.fixture
def hansen(jemur):
    return _user("hansen1", [(jemur, Role.AOM)])


# --- Kunci cabang ------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "name", "key", "prefix"),
    [
        ("JC", "Citraland", "citraland", "JC-"),
        ("citraland", "JoDerma Citraland", "citraland", "JC-"),
        ("JJ", "Jemur Andayani", "jemur-andayani", "JJ-"),
        ("jemur-andayani", "Jemur", "jemur-andayani", "JJ-"),
        ("XX", "Cabang baru", "xx", "J_-"),
    ],
)
def test_clinic_key_and_rm_prefix(code, name, key, prefix):
    clinic = Clinic(code=code, name=name)
    assert clinic_key(clinic) == key
    assert rm_prefix(clinic) == prefix


def test_rm_number_uses_branch_prefix(citraland):
    from orders.services import normalize_rm_number

    assert normalize_rm_number(citraland, "0108") == "JC-0108"


# --- Cabang aktif --------------------------------------------------------------


def test_off_day_uses_home_clinic_not_first_clinic(regita, jemur, citraland):
    today = local_today()
    DutyRoster.objects.create(user=regita, date=today, home_clinic=citraland, status=DutyStatus.OFF)
    assert active_clinic(regita) == citraland


def test_no_roster_today_uses_latest_home_clinic(regita, citraland):
    DutyRoster.objects.create(user=regita, date=local_today() - dt.timedelta(days=3), home_clinic=citraland,
                              clinic=citraland, status=DutyStatus.MASUK)
    assert active_clinic(regita) == citraland


def test_perbantuan_today_wins_over_home(regita, jemur, citraland):
    DutyRoster.objects.create(user=regita, date=local_today(), home_clinic=citraland, clinic=jemur,
                              status=DutyStatus.PERBANTUAN)
    assert active_clinic(regita) == jemur


def test_switcher_changes_branch_for_today_only(client, regita, jemur, citraland):
    DutyRoster.objects.create(user=regita, date=local_today(), home_clinic=citraland, status=DutyStatus.OFF)
    client.force_login(regita)
    body = client.get(reverse("core:dashboard")).content.decode()
    assert 'class="clinic-switch"' in body and "Citraland" in body
    response = client.post(reverse("accounts:switch_clinic"), {"cabang": jemur.pk, "next": "/hari-ini/"})
    assert response.status_code == 302
    assert client.session["active_clinic"] == {"id": jemur.pk, "date": local_today().isoformat()}
    body = client.get(reverse("core:dashboard")).content.decode()
    assert f'<option value="{jemur.pk}" selected>' in body
    # Pilihan kemarin tidak berlaku lagi.
    session = client.session
    session["active_clinic"] = {"id": jemur.pk, "date": "2000-01-01"}
    session.save()
    body = client.get(reverse("core:dashboard")).content.decode()
    assert f'<option value="{citraland.pk}" selected>' in body


def test_switcher_rejects_branch_without_access(client, jemur, citraland):
    yani = _user("yani", [(jemur, Role.PERAWAT), (jemur, Role.STAF)])
    client.force_login(yani)
    client.post(reverse("accounts:switch_clinic"), {"cabang": citraland.pk})
    assert "active_clinic" not in client.session
    assert 'class="clinic-switch"' not in client.get(reverse("core:dashboard")).content.decode()


def test_switcher_ignores_external_next(client, regita, citraland):
    client.force_login(regita)
    response = client.post(reverse("accounts:switch_clinic"),
                           {"cabang": citraland.pk, "next": "https://contoh.invalid/"})
    assert response["Location"] == reverse("home")


def test_citraland_director_items_match_code_jc(citraland, jemur):
    from direktur.models import AuditItem

    item = AuditItem(clinic_codes=["citraland"])
    assert item.applies_to(citraland)
    assert not item.applies_to(jemur)
    assert AuditItem(clinic_codes=[]).applies_to(jemur)


# --- Koreksi tally -------------------------------------------------------------


@pytest.fixture
def tally_day(citraland, regita):
    day, _ = get_or_create_day(citraland, user=regita)
    return day


@pytest.fixture
def nurses(citraland):
    return (_user("vivi", [(citraland, Role.PERAWAT)]), _user("elvira", [(citraland, Role.PERAWAT)]))


def _tally(day, nurse, by, amount=1):
    return NurseActionTally.objects.create(operational_day=day, nurse=nurse, rm_number="JC-0108",
                                           patient_name="Pasien A", action_name="Sculptra", tally=amount,
                                           entered_by=by)


def test_coordinator_and_director_can_correct(regita, hansen, citraland, jemur, nurses):
    assert can_correct_tally(regita, citraland)
    assert not can_correct_tally(regita, jemur)  # peran ONLINE di Jemur bukan koordinator
    assert can_correct_tally(hansen, citraland)
    assert not can_correct_tally(nurses[0], citraland)


def test_duplicate_tally_cancelled_with_reason(regita, tally_day, nurses):
    vivi, elvira = nurses
    entry = NurseRosterEntry.objects.create(operational_day=tally_day, nurse=vivi, turns_taken=2)
    dup = _tally(tally_day, vivi, regita)
    with pytest.raises(ValidationError):
        correct_tally(dup, user=regita, amount=0, reason="")
    correct_tally(dup, user=regita, amount=0, reason="Dobel input Sculptra JC-0108")
    dup.refresh_from_db()
    entry.refresh_from_db()
    assert dup.tally == 0 and dup.corrected_by == regita and "Dobel" in dup.correction_reason
    assert entry.turns_taken == 1
    assert AuditEvent.objects.filter(action=AuditAction.CORRECTION, entity_type="nurseactiontally",
                                     entity_id=dup.pk).exists()


def test_move_tally_to_other_nurse(regita, tally_day, nurses):
    vivi, elvira = nurses
    NurseRosterEntry.objects.create(operational_day=tally_day, nurse=vivi, turns_taken=1)
    target = NurseRosterEntry.objects.create(operational_day=tally_day, nurse=elvira, turns_taken=0)
    t = _tally(tally_day, vivi, regita)
    correct_tally(t, user=regita, amount=1, nurse=elvira, reason="Salah pilih perawat")
    target.refresh_from_db()
    assert t.nurse == elvira and target.turns_taken == 1


def test_limits_and_permission(regita, tally_day, nurses):
    vivi, _ = nurses
    t = _tally(tally_day, vivi, regita)
    with pytest.raises(ValidationError):
        correct_tally(t, user=regita, amount=21, reason="x")
    with pytest.raises(ValidationError):
        correct_tally(t, user=regita, amount=1, reason="tidak berubah")
    with pytest.raises(PermissionDenied):
        correct_tally(t, user=vivi, amount=0, reason="x")


def test_tally_pages(client, regita, tally_day, nurses, citraland):
    vivi, elvira = nurses
    t = _tally(tally_day, vivi, regita)
    client.force_login(regita)
    url = f"{reverse('nurses:tally_day')}?cabang={citraland.pk}&tanggal={tally_day.date.isoformat()}"
    body = client.get(url).content.decode()
    assert "JC-0108" in body and reverse("nurses:tally_correct", args=[t.pk]) in body
    assert client.get(f"{reverse('nurses:tally_day')}?cabang=abc").status_code == 404
    response = client.post(reverse("nurses:tally_correct", args=[t.pk]),
                           {"jumlah": "2", "perawat": vivi.pk, "tindakan": "Sculptra", "alasan": "2 vial"})
    assert response.status_code == 302
    t.refresh_from_db()
    assert t.tally == 2
    client.force_login(vivi)
    assert client.get(reverse("nurses:tally_correct", args=[t.pk])).status_code == 403
    assert client.get(url).status_code == 403


# --- Tutup hari dengan kas menunggu verifikasi -------------------------------------


@pytest.fixture
def kasir_jc(citraland):
    return _user("lia", [(citraland, Role.FRONT_DESK), (citraland, Role.STAF)])


def _submitted_closing(day, kasir):
    s = get_or_create_session(day, CashSessionType.CLOSING, user=kasir)
    save_count(s, user=kasir, quantities={100000: 5}, expected_total=500000)
    return submit_for_verification(s, kasir)


def test_close_from_opening_in_progress_with_pending_cash(regita, kasir_jc, tally_day, hansen):
    assert tally_day.status == DayStatus.OPENING_IN_PROGRESS
    blockers = closing_blockers(tally_day)
    assert any("Kas akhir" in b for b in blockers)
    with pytest.raises(ValidationError) as exc:
        close_day(tally_day, regita)
    assert "Koordinator Shift" in " ".join(exc.value.messages)
    session = _submitted_closing(tally_day, kasir_jc)
    assert closing_blockers(tally_day) == []
    close_day(tally_day, regita)
    tally_day.refresh_from_db()
    assert tally_day.status == DayStatus.CLOSED
    # Direktur memverifikasi sesudah hari ditutup.
    assert list(pending_verification(hansen)) == [session]
    verify(session, verifier=hansen)
    session.refresh_from_db()
    assert session.status == CashStatus.SESUAI
    assert list(pending_verification(hansen)) == []


def test_close_override_with_reason(regita, tally_day):
    close_day(tally_day, regita, override_reason="Kas akhir dihitung manual, diinput besok")
    tally_day.refresh_from_db()
    assert tally_day.status == DayStatus.CLOSED


def test_dashboard_closed_day_only_offers_reopen(client, regita, tally_day, citraland):
    close_day(tally_day, regita, override_reason="uji")
    DutyRoster.objects.create(user=regita, date=local_today(), home_clinic=citraland, clinic=citraland,
                              status=DutyStatus.MASUK)
    client.force_login(regita)
    body = client.get(reverse("core:dashboard")).content.decode()
    assert "Buka kembali" in body
    assert "Mulai penutupan" not in body


def test_director_sees_pending_cash_list(client, hansen, kasir_jc, tally_day):
    _submitted_closing(tally_day, kasir_jc)
    client.force_login(hansen)
    body = client.get(reverse("cash:index")).content.decode()
    assert "Menunggu verifikasi" in body and "Citraland" in body


def test_cash_session_other_branch_forbidden(client, kasir_jc, tally_day, jemur):
    session = _submitted_closing(tally_day, kasir_jc)
    other = _user("heni", [(jemur, Role.SUPERVISOR)])
    client.force_login(other)
    assert client.get(reverse("cash:review", args=[session.pk])).status_code in (403, 404)
    client.post(reverse("cash:verify", args=[session.pk]), {})
    session.refresh_from_db()
    assert session.status == CashStatus.MENUNGGU_VERIFIKASI


def test_operational_day_untouched_elsewhere(jemur, citraland, regita):
    get_or_create_day(citraland, user=regita)
    assert not OperationalDay.objects.filter(clinic=jemur).exists()


# --- Hak khusus koreksi tally (permintaan 3 Okt: untuk Regitta) ---------------------


def test_tally_capability_grants_correction_in_accessible_branch(tally_day, nurses, citraland, jemur, regita):
    from django.core.management import call_command

    from accounts.models import Capability, UserCapability

    vivi, elvira = nurses
    assert not can_correct_tally(vivi, citraland)
    call_command("beri_hak", "vivi", "tally.correct", catatan="uji", stdout=open("/dev/null", "w"))
    vivi = User.objects.get(pk=vivi.pk)  # buang cache kapabilitas
    assert can_correct_tally(vivi, citraland)
    assert not can_correct_tally(vivi, jemur)  # tidak punya akses ke Jemur
    t = _tally(tally_day, elvira, regita)
    correct_tally(t, user=vivi, amount=0, reason="dobel")
    assert AuditEvent.objects.filter(entity_type="user", entity_label="vivi").exists()
    # Hak khusus bertahan walau peran Koordinator Shift dicabut (mis. Reset peran).
    UserRole.objects.filter(user=regita, role=Role.SUPERVISOR).delete()
    call_command("beri_hak", "regita", "tally.correct", stdout=open("/dev/null", "w"))
    assert can_correct_tally(User.objects.get(pk=regita.pk), citraland)
    call_command("beri_hak", "regita", "tally.correct", "--cabut", stdout=open("/dev/null", "w"))
    assert not UserCapability.objects.filter(user=regita, capability=Capability.TALLY_CORRECT).exists()
    assert not can_correct_tally(User.objects.get(pk=regita.pk), citraland)
