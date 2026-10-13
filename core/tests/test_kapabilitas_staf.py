"""Kapabilitas tambahan yang membuka rute tertutup untuk staf (13 Okt 2026).

Dibuat untuk staf fasilitas yang mengurus impor absensi dan perlu tahu siapa jaga
kapan, tanpa dijadikan PIC atau Koordinator Shift. Yang diuji di sini bukan "menunya
muncul", melainkan batasnya: kapabilitas membuka persis satu hal dan tidak merembes
ke hal lain, dan staf tanpa kapabilitas tetap tertutup seperti sebelumnya.
"""
from __future__ import annotations

import datetime as dt

import pytest
from django.urls import reverse

from accounts.models import Capability, Role, User, UserCapability, UserRole
from core.models import Clinic

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
    polos = _user(jemur, "polos", Role.STAF)
    izul = _user(jemur, "izul", Role.STAF)
    UserCapability.objects.create(user=izul, capability=Capability.ABSENSI_IMPORT)
    UserCapability.objects.create(user=izul, capability=Capability.ROSTER_VIEW)
    return {"jemur": jemur, "polos": polos, "izul": izul}


def _masuk(client, user):
    assert client.login(username=user.username, password=SANDI)


# --- staf tanpa kapabilitas: tidak berubah ---------------------------------------


@pytest.mark.parametrize("rute", ["absensi:index", "jadwal:roster"])
def test_staf_polos_tetap_ditolak(client, dunia, rute):
    _masuk(client, dunia["polos"])
    assert client.get(reverse(rute)).status_code == 403


def test_menu_staf_polos_tidak_berubah(client, dunia):
    _masuk(client, dunia["polos"])
    body = client.get(reverse("core:today")).content.decode()
    assert f'href="{reverse("jadwal:roster")}"' not in body
    assert f'href="{reverse("absensi:index")}"' not in body


# --- ABSENSI_IMPORT --------------------------------------------------------------


def test_kapabilitas_membuka_halaman_absensi(client, dunia):
    _masuk(client, dunia["izul"])
    assert client.get(reverse("absensi:index")).status_code == 200


def test_kapabilitas_membuka_unggah_berkas(client, dunia):
    """Tanpa berkas form menolak dengan pesan, bukan 403 — artinya haknya lolos."""
    _masuk(client, dunia["izul"])
    resp = client.post(reverse("absensi:unggah"), {}, follow=True)
    assert resp.status_code == 200
    assert "Pilih berkas" in resp.content.decode()


def test_kapabilitas_ikut_membuka_papan_skor(client, dunia):
    """Konsekuensi yang diterima product owner 13 Okt: impor membawa serta hak melihat."""
    from core.permissions import can_view_absensi

    assert can_view_absensi(dunia["izul"]) is True
    _masuk(client, dunia["izul"])
    assert client.get(reverse("absensi:staf", args=[dunia["polos"].pk])).status_code == 200


def test_kapabilitas_TIDAK_membuka_koreksi_cap(client, dunia):
    """Batas terpenting: mengoreksi cap tetap hanya Direktur, Dirut, dan Owner (D4)."""
    from core.permissions import can_correct_absensi

    assert can_correct_absensi(dunia["izul"]) is False
    _masuk(client, dunia["izul"])
    assert client.get(
        reverse("absensi:koreksi", args=[dunia["polos"].pk, "2026-09-04"])
    ).status_code == 403


def test_kapabilitas_absensi_tidak_membuka_jadwal_jaga(client, dunia):
    """Satu kapabilitas membuka satu hal; tidak merembes ke rute lain."""
    hanya_absensi = _user(dunia["jemur"], "hanyaabsensi", Role.STAF)
    UserCapability.objects.create(user=hanya_absensi, capability=Capability.ABSENSI_IMPORT)
    _masuk(client, hanya_absensi)
    assert client.get(reverse("absensi:index")).status_code == 200
    assert client.get(reverse("jadwal:roster")).status_code == 403


# --- ROSTER_VIEW -----------------------------------------------------------------


def test_kapabilitas_membuka_jadwal_jaga_untuk_dibaca(client, dunia):
    _masuk(client, dunia["izul"])
    assert client.get(reverse("jadwal:roster")).status_code == 200


def test_jadwal_jaga_tetap_tidak_bisa_diubah(client, dunia):
    """"Cukup melihat" ditegakkan di server, bukan dengan menyembunyikan tombol."""
    _masuk(client, dunia["izul"])
    assert client.post(
        reverse("jadwal:roster"), {"cabang": dunia["jemur"].pk}
    ).status_code == 403


def test_kapabilitas_jadwal_tidak_membuka_absensi(client, dunia):
    hanya_jadwal = _user(dunia["jemur"], "hanyajadwal", Role.STAF)
    UserCapability.objects.create(user=hanya_jadwal, capability=Capability.ROSTER_VIEW)
    _masuk(client, hanya_jadwal)
    assert client.get(reverse("jadwal:roster")).status_code == 200
    assert client.get(reverse("absensi:index")).status_code == 403


# --- menu ------------------------------------------------------------------------


def test_menu_memuat_keduanya_bagi_pemegang_kapabilitas(client, dunia):
    _masuk(client, dunia["izul"])
    body = client.get(reverse("core:today")).content.decode()
    assert f'href="{reverse("jadwal:roster")}"' in body
    assert f'href="{reverse("absensi:index")}"' in body
    # "Absensi saya" tetap ada; kapabilitas menambah, bukan mengganti
    assert f'href="{reverse("absensi:saya")}"' in body
