"""Persona teknisi/fasilitas (13 Okt 2026).

Dibuat untuk staf yang berpindah antarcabang dan ke vendor: menerima kerusakan,
mengerjakannya, melapor balik ke pelapor, dan mengurus absensi seluruh tim. Menu staf
operasional tidak cocok untuknya — tidak satu pun isinya ia kerjakan.

Yang diuji di sini terutama apa yang **tidak** bisa ia buka. Persona memakai daftar
yang BOLEH, jadi kekeliruan paling mungkin adalah daftar yang terlalu longgar.
"""
from __future__ import annotations

import datetime as dt

import pytest
from django.urls import reverse

from accounts.models import Capability, Role, User, UserCapability, UserRole
from core.models import Clinic
from core.peran import TEKNISI, persona

pytestmark = pytest.mark.django_db

SANDI = "TestPassword123!"


def _user(clinic, username, *roles):
    u = User.objects.create_user(username=username, password=SANDI, display_name=username.title())
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


@pytest.fixture
def dunia(db):
    jemur = Clinic.objects.create(
        code="jemur", name="JoDerma Jemur", open_time=dt.time(14, 0), close_time=dt.time(22, 0)
    )
    izul = _user(jemur, "izul", Role.TEKNISI)
    UserCapability.objects.create(user=izul, capability=Capability.ABSENSI_IMPORT)
    staf = _user(jemur, "polos", Role.STAF)
    return {"jemur": jemur, "izul": izul, "staf": staf}


def _masuk(client, user):
    assert client.login(username=user.username, password=SANDI)


# --- persona ---------------------------------------------------------------------


def test_peran_teknisi_menghasilkan_persona_sendiri(dunia):
    assert persona(dunia["izul"]) == TEKNISI
    assert persona(dunia["staf"]) != TEKNISI


def test_halaman_pertama_sesudah_login(client, dunia):
    _masuk(client, dunia["izul"])
    assert client.get(reverse("core:dashboard")).status_code in (200, 302)
    assert client.get(reverse("core:today")).status_code == 200


# --- yang BOLEH ------------------------------------------------------------------


@pytest.mark.parametrize("rute", ["core:today", "jadwal:roster", "absensi:index",
                                  "issues:list", "reports:laporan_page"])
def test_rute_pekerjaannya_terbuka(client, dunia, rute):
    _masuk(client, dunia["izul"])
    assert client.get(reverse(rute)).status_code == 200


def test_absensi_butuh_kapabilitas_meski_rutenya_terbuka(client, dunia):
    """Rute terbuka untuk persona ini, tetapi view tetap yang menjaga."""
    tanpa = _user(dunia["jemur"], "teknisi2", Role.TEKNISI)
    _masuk(client, tanpa)
    assert client.get(reverse("absensi:index")).status_code == 403


# --- yang TIDAK boleh ------------------------------------------------------------


@pytest.mark.parametrize("rute", [
    "jadwal:mine",        # Jadwal saya
    "absensi:saya",       # Absensi saya
    "breaks:mine",        # Istirahat saya
    "reports:policies",   # Kebijakan
    "reports:masukan_page",  # Masukan Saya (jalur privat)
    "checklists:index",   # Checklist shift
    "cash:index",         # Kas
    "nurses:mine",        # Tindakan saya
])
def test_menu_staf_operasional_tertutup(client, dunia, rute):
    _masuk(client, dunia["izul"])
    assert client.get(reverse(rute)).status_code == 403, f"{rute} seharusnya tertutup"


@pytest.mark.parametrize("rute", [
    "direktur:overview", "owner:dashboard", "reports:inbox", "accounts:user_list",
    "jejak:index", "direktur:kpi",
])
def test_halaman_pimpinan_dan_admin_tertutup(client, dunia, rute):
    _masuk(client, dunia["izul"])
    assert client.get(reverse(rute)).status_code == 403, f"{rute} seharusnya tertutup"


def test_tidak_bisa_mengoreksi_cap(client, dunia):
    """Mengurus absensi bukan berarti boleh mengubah angka orang (D4)."""
    _masuk(client, dunia["izul"])
    assert client.get(
        reverse("absensi:koreksi", args=[dunia["staf"].pk, "2026-09-04"])
    ).status_code == 403


def test_tidak_bisa_mengubah_jadwal_jaga(client, dunia):
    _masuk(client, dunia["izul"])
    assert client.post(
        reverse("jadwal:roster"), {"cabang": dunia["jemur"].pk}
    ).status_code == 403


# --- menu -------------------------------------------------------------------------


def test_menu_memuat_yang_dikerjakannya(client, dunia):
    _masuk(client, dunia["izul"])
    body = client.get(reverse("core:today")).content.decode()
    for rute in ("core:today", "jadwal:roster", "absensi:index", "reports:laporan_page"):
        assert f'href="{reverse(rute)}"' in body, f"{rute} hilang dari menu"
    assert "Kerusakan" in body and "Masukan" in body


def test_menu_tidak_memuat_yang_tidak_dikerjakannya(client, dunia):
    _masuk(client, dunia["izul"])
    body = client.get(reverse("core:today")).content.decode()
    for rute in ("jadwal:mine", "absensi:saya", "breaks:mine", "reports:policies",
                 "reports:masukan_page", "checklists:index"):
        assert f'href="{reverse(rute)}"' not in body, f"{rute} masih muncul di menu"
    assert "Komplain" not in body


def test_menu_absensi_hilang_bila_tanpa_kapabilitas(client, dunia):
    """Menu tidak boleh menawarkan halaman yang akan menolaknya."""
    tanpa = _user(dunia["jemur"], "teknisi3", Role.TEKNISI)
    _masuk(client, tanpa)
    body = client.get(reverse("core:today")).content.decode()
    assert f'href="{reverse("absensi:index")}"' not in body
    assert f'href="{reverse("jadwal:roster")}"' in body


# --- staf lain tidak ikut berubah --------------------------------------------------


def test_persona_staf_tidak_terpengaruh(client, dunia):
    _masuk(client, dunia["staf"])
    body = client.get(reverse("core:today")).content.decode()
    assert f'href="{reverse("absensi:saya")}"' in body
    assert f'href="{reverse("reports:policies")}"' in body
