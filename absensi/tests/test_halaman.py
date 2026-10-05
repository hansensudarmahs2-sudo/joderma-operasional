"""Halaman Absensi: izin, papan skor, daftar pengecualian, dan unggah berkas."""
from __future__ import annotations

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from absensi.models import AttendanceDevice, AttendancePunch, JenisCap
from accounts.models import Role, User, UserRole
from core.models import Clinic
from jadwal.models import DutyRoster, DutyStatus

from .pabrik_xlsx import bangun

pytestmark = pytest.mark.django_db

SANDI = "TestPassword123!"
TGL = dt.date(2026, 9, 4)
BULAN = "2026-09"


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
    Clinic.objects.create(
        code="citraland", name="JoDerma Citraland", open_time=dt.time(12, 0), close_time=dt.time(21, 0)
    )
    direktur = _user(jemur, "aom", Role.AOM)
    owner = _user(jemur, "owner", Role.OWNER)
    staf = _user(jemur, "elvira", Role.APOTEKER, Role.STAF)
    DutyRoster.objects.create(
        user=staf, date=TGL, home_clinic=jemur, clinic=jemur, status=DutyStatus.MASUK
    )
    for jam, jenis in ((dt.time(13, 30), JenisCap.MASUK), (dt.time(0, 28), JenisCap.KELUAR)):
        hari = TGL + dt.timedelta(days=1) if jam.hour < 6 else TGL
        AttendancePunch.objects.create(
            user=staf, shift_date=TGL, kind=jenis,
            occurred_at=timezone.make_aware(dt.datetime.combine(hari, jam)),
        )
    return {"jemur": jemur, "direktur": direktur, "owner": owner, "staf": staf}


def _masuk(client, user):
    assert client.login(username=user.username, password=SANDI)


# --- izin -----------------------------------------------------------------------


def test_direktur_boleh_membuka(client, dunia):
    _masuk(client, dunia["direktur"])
    assert client.get(reverse("absensi:index")).status_code == 200


def test_owner_boleh_membaca(client, dunia):
    _masuk(client, dunia["owner"])
    assert client.get(reverse("absensi:index")).status_code == 200


def test_owner_tidak_boleh_mengunggah(client, dunia):
    """Jam kerja seluruh staf: Owner membaca, tidak mengimpor."""
    _masuk(client, dunia["owner"])
    assert client.post(reverse("absensi:unggah"), {}).status_code == 403


def test_staf_biasa_ditolak(client, dunia):
    _masuk(client, dunia["staf"])
    assert client.get(reverse("absensi:index")).status_code == 403


def test_belum_login_diarahkan_ke_login(client, dunia):
    resp = client.get(reverse("absensi:index"))
    assert resp.status_code == 302 and "login" in resp["Location"]


# --- papan skor -----------------------------------------------------------------


def test_papan_skor_menampilkan_angka(client, dunia):
    _masuk(client, dunia["direktur"])
    body = client.get(reverse("absensi:index"), {"bulan": BULAN}).content.decode()
    assert "Elvira" in body
    assert "148" in body            # 00.28 = 148 menit setelah tutup 22.00


def test_bulan_tanpa_data_memberi_petunjuk(client, dunia):
    _masuk(client, dunia["direktur"])
    body = client.get(reverse("absensi:index"), {"bulan": "2026-01"}).content.decode()
    assert "Belum ada data" in body


def test_bulan_tidak_sah_jatuh_ke_bulan_berjalan(client, dunia):
    _masuk(client, dunia["direktur"])
    assert client.get(reverse("absensi:index"), {"bulan": "bukan-bulan"}).status_code == 200


# --- pengecualian ---------------------------------------------------------------


def test_tab_pengecualian_menampilkan_temuan(client, dunia):
    _masuk(client, dunia["direktur"])
    body = client.get(
        reverse("absensi:index"), {"tab": "pengecualian", "bulan": BULAN}
    ).content.decode()
    assert "Cap pulang setelah tengah malam" in body


def test_jam_ditampilkan_dalam_waktu_lokal(client, dunia):
    """Cap disimpan UTC; halaman harus menampilkan 13.30 WIB, bukan 06.30 UTC."""
    _masuk(client, dunia["direktur"])
    body = client.get(
        reverse("absensi:index"), {"tab": "pengecualian", "bulan": BULAN}
    ).content.decode()
    assert "13.30" in body
    assert "06.30" not in body


# --- rincian per staf -----------------------------------------------------------


def test_halaman_staf_merinci_per_hari(client, dunia):
    _masuk(client, dunia["direktur"])
    url = reverse("absensi:staf", args=[dunia["staf"].pk])
    body = client.get(url, {"bulan": BULAN}).content.decode()
    assert "14.00–22.00" in body     # jendela shift cabang hari itu
    assert "148" in body


def test_halaman_staf_bulan_kosong_tidak_error(client, dunia):
    _masuk(client, dunia["direktur"])
    url = reverse("absensi:staf", args=[dunia["staf"].pk])
    resp = client.get(url, {"bulan": "2026-01"})
    assert resp.status_code == 200
    assert "Belum ada cap" in resp.content.decode()


# --- unggah ---------------------------------------------------------------------


def _berkas_uji(nama="sep.xlsx"):
    from django.core.files.uploadedfile import SimpleUploadedFile

    data = bangun(
        "Kartu Laporan 1 - 30 September 2026",
        [{"uid": "17", "label": "Elvira", "hari": [(10, ["14:02", "22:35"], [])]}],
    )
    return SimpleUploadedFile(nama, data, content_type="application/vnd.ms-excel")


def test_unggah_berkas_menyimpan_cap(client, dunia):
    AttendanceDevice.objects.create(device_uid="17", device_label="Elvira", user=dunia["staf"])
    _masuk(client, dunia["direktur"])
    resp = client.post(reverse("absensi:unggah"), {"berkas": _berkas_uji(), "bulan": BULAN})
    assert resp.status_code == 302
    assert AttendancePunch.objects.filter(shift_date=dt.date(2026, 9, 10)).count() == 2


def test_unggah_berkas_bukan_kartu_laporan_memberi_pesan(client, dunia):
    from django.core.files.uploadedfile import SimpleUploadedFile

    _masuk(client, dunia["direktur"])
    rusak = SimpleUploadedFile("rusak.xlsx", b"bukan zip", content_type="application/vnd.ms-excel")
    resp = client.post(reverse("absensi:unggah"), {"berkas": rusak}, follow=True)
    assert "bukan .xlsx" in resp.content.decode()


def test_unggah_tanpa_berkas_memberi_pesan(client, dunia):
    _masuk(client, dunia["direktur"])
    resp = client.post(reverse("absensi:unggah"), {}, follow=True)
    assert "Pilih berkas" in resp.content.decode()


def test_id_belum_dipetakan_muncul_sebagai_peringatan(client, dunia):
    _masuk(client, dunia["direktur"])
    resp = client.post(reverse("absensi:unggah"), {"berkas": _berkas_uji()}, follow=True)
    assert "belum dipetakan" in resp.content.decode()


# --- menu -----------------------------------------------------------------------


def test_menu_direktur_memuat_absensi(client, dunia):
    _masuk(client, dunia["direktur"])
    body = client.get(reverse("absensi:index")).content.decode()
    assert "Evaluasi staf" in body


def test_menu_staf_memuat_absensi_saya_bukan_papan_skor(client, dunia):
    """Staf melihat jam kerjanya sendiri (D5), bukan jam kerja seluruh tim."""
    _masuk(client, dunia["staf"])
    body = client.get(reverse("core:today")).content.decode()
    assert f'href="{reverse("absensi:saya")}"' in body
    assert f'href="{reverse("absensi:index")}"' not in body


# --- absensi saya (D5) ----------------------------------------------------------


def test_staf_boleh_membuka_absensi_saya(client, dunia):
    _masuk(client, dunia["staf"])
    body = client.get(reverse("absensi:saya"), {"bulan": BULAN}).content.decode()
    assert "Absensi saya" in body
    assert "148" in body            # lembur 4 Sep miliknya sendiri


def test_absensi_saya_tidak_bisa_diminta_untuk_orang_lain(client, dunia):
    """Tidak ada parameter staf di rute ini, jadi tidak ada cara meminta data orang lain."""
    _masuk(client, dunia["staf"])
    body = client.get(
        reverse("absensi:saya"), {"bulan": BULAN, "orang": dunia["direktur"].pk, "pk": 1}
    ).content.decode()
    assert str(dunia["direktur"].display_name) not in body


def test_absensi_saya_tanpa_login_diarahkan(client, dunia):
    resp = client.get(reverse("absensi:saya"))
    assert resp.status_code == 302 and "login" in resp["Location"]


def test_staf_tetap_ditolak_membuka_rincian_orang_lain(client, dunia):
    _masuk(client, dunia["staf"])
    assert client.get(reverse("absensi:staf", args=[dunia["direktur"].pk])).status_code == 403


def test_papan_skor_memisahkan_staf_rekam_saja(client, dunia):
    """D1: capnya terlihat, tetapi tidak ikut diperingkat bersama yang dinilai."""
    from absensi.models import AttendanceDevice

    izul = User.objects.create_user(username="izul", password=SANDI, display_name="Izul")
    AttendanceDevice.objects.create(
        device_uid="2", device_label="Izul", user=izul, recording_only=True
    )
    AttendancePunch.objects.create(
        user=izul, shift_date=TGL, kind=JenisCap.MASUK,
        occurred_at=timezone.make_aware(dt.datetime.combine(TGL, dt.time(8, 4))),
    )
    _masuk(client, dunia["direktur"])
    body = client.get(reverse("absensi:index"), {"bulan": BULAN}).content.decode()
    assert "Direkam tanpa penilaian" in body
    papan, rekam = body.split("Direkam tanpa penilaian", 1)
    assert "Izul" in rekam and "Izul" not in papan


# --- D4: siapa boleh mengoreksi cap ---------------------------------------------


def _admin_absensi(model):
    from django.contrib import admin as dj

    return dj.site._registry[model]


@pytest.mark.parametrize("model", [AttendancePunch, AttendanceDevice])
def test_direktur_operasional_boleh_mengoreksi_cap(rf, dunia, model):
    """D4: mengoreksi cap mengubah skor orang, jadi haknya lebih sempit dari mengimpor."""
    situs = _admin_absensi(model)
    permintaan = rf.get("/")
    permintaan.user = dunia["direktur"]
    assert situs.has_change_permission(permintaan) is True
    assert situs.has_add_permission(permintaan) is True


@pytest.mark.parametrize("model", [AttendancePunch, AttendanceDevice])
def test_owner_dan_direktur_utama_boleh_mengoreksi_cap(rf, dunia, model):
    situs = _admin_absensi(model)
    permintaan = rf.get("/")
    permintaan.user = dunia["owner"]
    assert situs.has_change_permission(permintaan) is True


@pytest.mark.parametrize("model", [AttendancePunch, AttendanceDevice])
def test_admin_sistem_tidak_boleh_mengoreksi_cap(rf, dunia, model):
    """Admin boleh mengubah jadwal jaga, tetapi bukan angka yang menilai orang."""
    situs = _admin_absensi(model)
    permintaan = rf.get("/")
    permintaan.user = _user(dunia["jemur"], "adminsistem", Role.ADMIN)
    assert situs.has_change_permission(permintaan) is False
    assert situs.has_add_permission(permintaan) is False
    assert situs.has_delete_permission(permintaan) is False


def test_riwayat_impor_tidak_bisa_diubah_siapa_pun(rf, dunia):
    """Catatan apa yang pernah diimpor, bukan data yang boleh dirapikan belakangan."""
    from absensi.models import AttendanceImport

    situs = _admin_absensi(AttendanceImport)
    permintaan = rf.get("/")
    permintaan.user = dunia["direktur"]
    assert situs.has_add_permission(permintaan) is False
    assert situs.has_change_permission(permintaan) is False
    assert situs.has_delete_permission(permintaan) is False
