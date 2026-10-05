"""Mesin perhitungan: jam shift dari cabang, lewat tengah malam, ambang datang awal."""
from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from absensi import perhitungan
from absensi.models import AttendancePunch, JenisCap
from absensi.perhitungan import Pengecualian, hitung_periode, laporan_pengecualian
from accounts.models import User
from core.models import Clinic
from jadwal.models import DutyRoster, DutyStatus

pytestmark = pytest.mark.django_db

TGL = dt.date(2026, 9, 4)


@pytest.fixture
def dunia(db):
    jemur = Clinic.objects.create(
        code="jemur", name="JoDerma Jemur", open_time=dt.time(14, 0), close_time=dt.time(22, 0)
    )
    citra = Clinic.objects.create(
        code="citraland", name="JoDerma Citraland", open_time=dt.time(12, 0), close_time=dt.time(21, 0)
    )
    user = User.objects.create_user(username="elvira", password="TestPassword123!", display_name="Elvira")
    return {"jemur": jemur, "citra": citra, "user": user}


def _roster(dunia, status=DutyStatus.MASUK, clinic="jemur", tanggal=TGL):
    return DutyRoster.objects.create(
        user=dunia["user"],
        date=tanggal,
        home_clinic=dunia["jemur"],
        clinic=dunia[clinic] if status in (DutyStatus.MASUK, DutyStatus.PERBANTUAN) else None,
        status=status,
    )


def _cap(dunia, *jam, tanggal=TGL):
    """`jam` berupa "HH:MM"; jam sebelum 06.00 dianggap hari berikutnya, seperti importer."""
    for teks in jam:
        j, m = (int(x) for x in teks.split(":"))
        hari = tanggal + dt.timedelta(days=1) if j < 6 else tanggal
        AttendancePunch.objects.create(
            user=dunia["user"],
            shift_date=tanggal,
            occurred_at=timezone.make_aware(dt.datetime.combine(hari, dt.time(j, m))),
            kind=JenisCap.MASUK,
        )


def _hari(dunia, tanggal=TGL):
    (staf,) = hitung_periode(tanggal, tanggal, users=[dunia["user"]])
    return staf.hari[0]


# --- jam shift mengikuti cabang hari itu ----------------------------------------


def test_jam_shift_diambil_dari_cabang_bertugas_bukan_cabang_asal(dunia):
    """Hari perbantuan memakai jam cabang tujuan; itulah inti aturannya."""
    _roster(dunia, DutyStatus.PERBANTUAN, "citra")
    _cap(dunia, "12:00", "21:30")
    hari = _hari(dunia)
    assert hari.clinic == dunia["citra"]
    assert hari.terlambat == 0
    assert hari.lembur_pulang == 30


def test_jam_cabang_asal_dipakai_saat_tidak_perbantuan(dunia):
    _roster(dunia)
    _cap(dunia, "14:05", "22:20")
    hari = _hari(dunia)
    assert (hari.terlambat, hari.lembur_pulang) == (5, 20)


# --- lewat tengah malam ---------------------------------------------------------


def test_pulang_lewat_tengah_malam_jadi_lembur_bukan_minus(dunia):
    """00.28 pada shift tutup 22.00 adalah +148 menit, bukan -1292."""
    _roster(dunia)
    _cap(dunia, "13:30", "00:28")
    hari = _hari(dunia)
    assert hari.lembur_pulang == 148
    assert hari.terlambat == 0
    assert Pengecualian.LEWAT_TENGAH_MALAM in hari.pengecualian


# --- ambang datang awal ---------------------------------------------------------


@pytest.mark.parametrize(
    "masuk, awal_dibayar",
    [
        ("13:01", 0),    # 59 menit: belum lolos ambang
        ("13:00", 60),   # tepat 60 menit: lolos, dibayar penuh
        ("08:55", 305),  # jauh lebih awal: seluruh menitnya
    ],
)
def test_datang_awal_gerbang_60_menit(dunia, masuk, awal_dibayar):
    _roster(dunia)
    _cap(dunia, masuk, "22:00")
    hari = _hari(dunia)
    assert hari.datang_awal == awal_dibayar


def test_datang_awal_mentah_tetap_terlihat_walau_belum_lolos(dunia):
    """Angka mentahnya disimpan supaya hari di bawah ambang masih bisa ditinjau."""
    _roster(dunia)
    _cap(dunia, "13:01", "22:00")
    hari = _hari(dunia)
    assert (hari.datang_awal_mentah, hari.datang_awal) == (59, 0)


def test_skor_menjumlah_tiga_komponen(dunia):
    _roster(dunia)
    _cap(dunia, "12:30", "22:45")   # awal 90, lembur 45, telat 0
    hari = _hari(dunia)
    assert (hari.datang_awal, hari.lembur_pulang, hari.terlambat) == (90, 45, 0)
    assert hari.skor == 135


def test_terlambat_mengurangi_skor(dunia):
    _roster(dunia)
    _cap(dunia, "14:30", "22:10")
    assert _hari(dunia).skor == 10 - 30


def test_lembur_tidak_diplafon(dunia):
    """Keputusan product owner: tidak ada plafon pada cap pulang."""
    _roster(dunia)
    _cap(dunia, "14:00", "03:00")
    hari = _hari(dunia)
    assert hari.lembur_pulang == 300
    assert Pengecualian.LEMBUR_PANJANG in hari.pengecualian


# --- pengecualian ---------------------------------------------------------------


def test_cap_tanpa_roster_tidak_dihitung_dan_ditandai(dunia):
    _cap(dunia, "14:02", "22:05")
    hari = _hari(dunia)
    assert hari.skor == 0
    assert Pengecualian.TANPA_ROSTER in hari.pengecualian


def test_dijadwalkan_masuk_tetapi_tidak_ada_cap(dunia):
    _roster(dunia)
    hari = _hari(dunia)
    assert Pengecualian.TANPA_CAP in hari.pengecualian
    assert hari.skor == 0


def test_hari_off_tanpa_cap_bukan_pengecualian(dunia):
    _roster(dunia, DutyStatus.OFF)
    hari = _hari(dunia)
    assert hari.pengecualian == []
    assert hari.skor == 0


def test_off_tetapi_mengecap_tetap_dihitung_dan_ditandai(dunia):
    """Lemburnya tidak boleh hilang diam-diam, tetapi shift-nya memang tidak terjadwal."""
    _roster(dunia, DutyStatus.OFF)
    _cap(dunia, "14:00", "22:40")
    hari = _hari(dunia)
    assert hari.lembur_pulang == 40
    assert Pengecualian.LIBUR_TAPI_NGECAP in hari.pengecualian


def test_cap_tunggal_hanya_menghitung_sisi_yang_ada(dunia):
    _roster(dunia)
    _cap(dunia, "22:28")
    hari = _hari(dunia)
    assert Pengecualian.CAP_TUNGGAL in hari.pengecualian
    assert hari.masuk is None and hari.keluar is not None
    assert (hari.lembur_pulang, hari.terlambat, hari.datang_awal) == (28, 0, 0)


def test_cap_tunggal_dekat_jam_masuk_ditafsir_cap_masuk(dunia):
    _roster(dunia)
    _cap(dunia, "14:10")
    hari = _hari(dunia)
    assert hari.masuk is not None and hari.keluar is None
    assert (hari.terlambat, hari.lembur_pulang) == (10, 0)


def test_jam_cap_yang_lebih_cocok_ke_cabang_lain_ditandai(dunia):
    """Salah cabang di roster menggeser bayaran sekitar dua jam, jadi harus terlihat."""
    _roster(dunia, DutyStatus.MASUK, "citra")
    _cap(dunia, "13:48", "22:39")   # pola Jemur, padahal roster bilang Citraland
    hari = _hari(dunia)
    assert Pengecualian.CABANG_BEDA in hari.pengecualian
    assert "Jemur" in " ".join(hari.catatan)


def test_cabang_yang_cocok_tidak_ditandai(dunia):
    _roster(dunia, DutyStatus.MASUK, "citra")
    _cap(dunia, "12:05", "21:10")
    assert Pengecualian.CABANG_BEDA not in _hari(dunia).pengecualian


# --- ringkasan periode ----------------------------------------------------------


def test_ringkasan_menjumlah_dan_mengurut_skor(dunia):
    lain = User.objects.create_user(username="arsi", password="TestPassword123!")
    for hari_ke in (4, 5):
        tanggal = dt.date(2026, 9, hari_ke)
        _roster(dunia, tanggal=tanggal)
        _cap(dunia, "14:00", "22:30", tanggal=tanggal)
        DutyRoster.objects.create(
            user=lain, date=tanggal, home_clinic=dunia["jemur"], clinic=dunia["jemur"],
            status=DutyStatus.MASUK,
        )
        AttendancePunch.objects.create(
            user=lain, shift_date=tanggal, kind=JenisCap.MASUK,
            occurred_at=timezone.make_aware(dt.datetime.combine(tanggal, dt.time(14, 0))),
        )
        AttendancePunch.objects.create(
            user=lain, shift_date=tanggal, kind=JenisCap.KELUAR,
            occurred_at=timezone.make_aware(dt.datetime.combine(tanggal, dt.time(22, 10))),
        )

    ringkasan = hitung_periode(dt.date(2026, 9, 1), dt.date(2026, 9, 30))
    assert [s.user.username for s in ringkasan] == ["elvira", "arsi"]
    assert ringkasan[0].lembur_pulang == 60
    assert ringkasan[0].hari_kerja == 2
    assert ringkasan[1].skor == 20


def test_laporan_pengecualian_urut_tanggal(dunia):
    _roster(dunia, tanggal=dt.date(2026, 9, 5))
    _cap(dunia, "14:00", tanggal=dt.date(2026, 9, 5))
    _cap(dunia, "14:00", "22:00", tanggal=dt.date(2026, 9, 2))   # tanpa roster
    perlu = laporan_pengecualian(dt.date(2026, 9, 1), dt.date(2026, 9, 30))
    assert [h.tanggal.day for h in perlu] == [2, 5]


def test_jendela_shift_menangani_shift_lintas_tengah_malam(dunia):
    """Belum dipakai kedua cabang, tetapi jam tutup <= jam buka harus tetap benar."""
    malam = Clinic.objects.create(
        code="malam", name="Shift malam", open_time=dt.time(22, 0), close_time=dt.time(6, 0)
    )
    mulai, selesai = perhitungan.jendela_shift(malam, TGL)
    assert timezone.localtime(mulai).date() == TGL
    assert timezone.localtime(selesai).date() == TGL + dt.timedelta(days=1)


def test_hari_libur_memakai_jam_cabang_asal_bukan_cabang_terakhir(dunia):
    """Hari off tidak punya `clinic`, jadi fallback-nya `home_clinic`.

    Bukan detail sepele: pada data September 2026 satu baris off dengan `home_clinic`
    basi menggeser skor 127 menit, karena jam kedua cabang berbeda dua jam.
    """
    DutyRoster.objects.create(
        user=dunia["user"], date=TGL, home_clinic=dunia["citra"], clinic=None, status=DutyStatus.OFF
    )
    _cap(dunia, "11:53", "21:01")
    hari = _hari(dunia)
    assert hari.clinic == dunia["citra"]
    assert (hari.datang_awal, hari.lembur_pulang) == (0, 1)   # 7 menit awal: belum lolos ambang
    assert Pengecualian.LIBUR_TAPI_NGECAP in hari.pengecualian


def test_hari_off_menyebut_statusnya(dunia):
    """Baris hari libur tidak boleh tampil sebagai deretan tanda hubung tanpa keterangan."""
    _roster(dunia, DutyStatus.CUTI)
    assert _hari(dunia).status_label == "Cuti"


def test_hari_tanpa_roster_menyebut_ketiadaannya(dunia):
    _cap(dunia, "14:02", "22:05")
    assert _hari(dunia).status_label == "Tidak ada di jadwal"
