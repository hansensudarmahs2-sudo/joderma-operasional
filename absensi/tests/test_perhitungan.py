"""Mesin perhitungan: jam shift dari cabang, lewat tengah malam, ambang datang awal."""
from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from absensi import perhitungan
from absensi.models import AttendanceDevice, AttendancePunch, JenisCap
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


def test_tanpa_roster_tetapi_polanya_jelas_cabangnya_diduga(dunia):
    """Jadwal September bukan sumber kebenaran, jadi pola jam dipakai bila roster kosong."""
    _cap(dunia, "14:02", "22:05")
    hari = _hari(dunia)
    assert hari.clinic == dunia["jemur"]
    assert hari.cabang_dari_dugaan is True
    assert (hari.terlambat, hari.lembur_pulang) == (2, 5)
    assert Pengecualian.CABANG_DUGAAN in hari.pengecualian
    assert Pengecualian.TANPA_ROSTER not in hari.pengecualian


def test_tanpa_roster_dan_pola_tidak_jelas_tidak_dihitung(dunia):
    """Datang lima jam lebih awal: tidak mendekati jam buka cabang mana pun."""
    _cap(dunia, "08:55", "22:19")
    hari = _hari(dunia)
    assert hari.skor == 0
    assert hari.clinic is None
    assert Pengecualian.TANPA_ROSTER in hari.pengecualian


def test_tanpa_roster_dan_pola_cocok_dua_cabang_tidak_ditebak(dunia):
    """Masuk 11.39 pulang 22.38 bisa berarti hari Citraland dengan lembur panjang, atau
    hari Jemur dengan datang awal. Menebak salah satunya memilih selisih bayaran secara
    acak, dan arahnya selalu merugikan staf."""
    _cap(dunia, "11:39", "22:38")
    hari = _hari(dunia)
    assert hari.clinic is None
    assert Pengecualian.TANPA_ROSTER in hari.pengecualian
    assert "lebih dari satu" in " ".join(hari.catatan)


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


# --- D1: staf "rekam saja" ------------------------------------------------------


def test_staf_rekam_saja_capnya_tersimpan_tetapi_tidak_dinilai(dunia):
    """Izul/Isya/Lina di luar jadwal dua cabang; menilainya dengan jam Jemur/Citraland
    hanya menghasilkan angka yang tidak berarti, jadi capnya direkam tanpa skor."""
    AttendanceDevice.objects.create(
        device_uid="2", device_label="Izul", user=dunia["user"], recording_only=True
    )
    _cap(dunia, "08:04", "17:03")
    (staf,) = hitung_periode(TGL, TGL, users=[dunia["user"]])
    hari = staf.hari[0]
    assert staf.dinilai is False
    assert staf.skor == 0
    assert hari.masuk is not None and hari.keluar is not None
    assert (hari.terlambat, hari.lembur_pulang, hari.datang_awal) == (0, 0, 0)


def test_staf_rekam_saja_tidak_membanjiri_daftar_pengecualian(dunia):
    """Tanpa jadwal jaga, setiap harinya akan jadi TANPA_ROSTER dan menenggelamkan
    temuan yang benar-benar perlu dilihat."""
    AttendanceDevice.objects.create(
        device_uid="2", device_label="Izul", user=dunia["user"], recording_only=True
    )
    _cap(dunia, "08:04", "17:03")
    assert laporan_pengecualian(TGL, TGL) == []


def test_staf_rekam_saja_selalu_di_bawah_yang_dinilai(dunia):
    AttendanceDevice.objects.create(
        device_uid="2", device_label="Izul", user=dunia["user"], recording_only=True
    )
    _cap(dunia, "08:04", "17:03")
    lain = User.objects.create_user(username="arsi", password="TestPassword123!")
    DutyRoster.objects.create(
        user=lain, date=TGL, home_clinic=dunia["jemur"], clinic=dunia["jemur"],
        status=DutyStatus.MASUK,
    )
    AttendancePunch.objects.create(
        user=lain, shift_date=TGL, kind=JenisCap.MASUK,
        occurred_at=timezone.make_aware(dt.datetime.combine(TGL, dt.time(14, 0))),
    )
    urut = [s.user.username for s in hitung_periode(TGL, TGL)]
    assert urut.index("arsi") < urut.index("elvira")


# --- D2: hari Minggu adalah hari biasa ------------------------------------------


def test_hari_minggu_diperlakukan_sama_dengan_hari_kerja_lain(dunia):
    """Keputusan product owner (D2): Minggu hari biasa, penggantinya hari off di roster.
    Jadi tidak boleh ada premi atau perlakuan khusus di perhitungan."""
    minggu = dt.date(2026, 9, 6)
    senin = dt.date(2026, 9, 7)
    assert minggu.weekday() == 6 and senin.weekday() == 0
    for tanggal in (minggu, senin):
        _roster(dunia, tanggal=tanggal)
        _cap(dunia, "14:10", "22:40", tanggal=tanggal)
    (staf,) = hitung_periode(minggu, senin, users=[dunia["user"]])
    hari_minggu, hari_senin = staf.hari
    assert (hari_minggu.terlambat, hari_minggu.lembur_pulang) == (10, 40)
    assert hari_minggu.skor == hari_senin.skor


def test_off_tetapi_mengecap_tetap_dibayar(dunia):
    """D2: dibayar. Tetap ditandai karena jam shift-nya diambil dari cabang asal."""
    _roster(dunia, DutyStatus.OFF)
    _cap(dunia, "14:00", "22:40")
    hari = _hari(dunia)
    assert hari.skor == 40
    assert Pengecualian.LIBUR_TAPI_NGECAP in hari.pengecualian


# --- D3: lembur panjang tanpa persetujuan ---------------------------------------


def test_lembur_panjang_hanya_informasi_tidak_memotong(dunia):
    """D3: tidak perlu persetujuan saat ini, jadi tandanya tidak boleh mengubah angka."""
    _roster(dunia)
    _cap(dunia, "14:00", "03:00")
    hari = _hari(dunia)
    assert Pengecualian.LEMBUR_PANJANG in hari.pengecualian
    assert hari.lembur_pulang == 300 and hari.skor == 300


def test_ambang_penandaan_tidak_pernah_mengubah_angka(dunia, monkeypatch):
    """Penjaga D6: CABANG_BEDA dan LEMBUR_PANJANG hanya menandai.

    Mengubah kedua ambang itu boleh menambah atau mengurangi tanda, tetapi pada hari
    yang cabangnya datang dari jadwal jaga tidak boleh menggeser terlambat, lembur,
    datang awal, atau skor satu menit pun.
    """
    _roster(dunia, DutyStatus.MASUK, "citra")
    _cap(dunia, "13:48", "22:39")
    asli = _hari(dunia)
    angka = (asli.terlambat, asli.lembur_pulang, asli.datang_awal, asli.skor)
    assert asli.pengecualian  # pada ambang bawaan hari ini memang tertandai

    monkeypatch.setattr(perhitungan, "TOLERANSI_POLA_MENIT", 10_000)
    monkeypatch.setattr(perhitungan, "AMBANG_LEMBUR_PANJANG_MENIT", 10_000)
    longgar = _hari(dunia)
    assert (longgar.terlambat, longgar.lembur_pulang, longgar.datang_awal, longgar.skor) == angka
    assert longgar.pengecualian == []


# --- dugaan pola cabang ---------------------------------------------------------


@pytest.mark.parametrize(
    "masuk, keluar, diharapkan, alasan",
    [
        ("14:02", "22:05", "jemur", "COCOK"),       # hari biasa Jemur
        ("11:57", "21:51", "citra", "COCOK"),       # hari biasa Citraland
        ("13:30", "00:28", "jemur", "COCOK"),       # lembur lewat tengah malam tetap terbaca
        ("13:48", "22:39", "jemur", "COCOK"),       # lembur 39 menit
        ("11:44", "21:21", "citra", "COCOK"),
        ("08:55", "22:19", None, "GANDA"),          # datang 5 jam awal: bisa dua-duanya
        ("13:00", "21:30", "citra", "COCOK"),       # pulang 21.30: terlalu awal untuk Jemur
        ("11:39", "22:38", None, "GANDA"),          # Citraland lembur, atau Jemur datang awal?
        ("11:50", "17:00", None, "TIDAK_COCOK"),    # pulang 4 jam sebelum tutup
    ],
)
def test_duga_cabang_dari_pola_jam(dunia, masuk, keluar, diharapkan, alasan):
    from absensi.perhitungan import duga_cabang

    def saat(teks):
        j, m = (int(x) for x in teks.split(":"))
        hari = TGL + dt.timedelta(days=1) if j < 6 else TGL
        return timezone.make_aware(dt.datetime.combine(hari, dt.time(j, m)))

    cabang = [dunia["jemur"], dunia["citra"]]
    hasil, sebab = duga_cabang(saat(masuk), saat(keluar), TGL, cabang)
    assert sebab == alasan
    assert hasil == (dunia[diharapkan] if diharapkan else None)


def test_jam_pulang_boleh_selarut_apa_pun_tetapi_tidak_boleh_terlalu_awal(dunia):
    """Lembur menggeser jam pulang, jadi hanya pulang terlalu awal yang membatalkan dugaan."""
    from absensi.perhitungan import duga_cabang

    def saat(teks, hari_berikutnya=False):
        j, m = (int(x) for x in teks.split(":"))
        return timezone.make_aware(
            dt.datetime.combine(TGL + dt.timedelta(days=1 if hari_berikutnya else 0), dt.time(j, m))
        )

    cabang = [dunia["jemur"], dunia["citra"]]
    larut, _ = duga_cabang(saat("14:00"), saat("03:00", True), TGL, cabang)
    assert larut == dunia["jemur"]
    terlalu_awal, sebab = duga_cabang(saat("14:00"), saat("19:00"), TGL, cabang)
    assert terlalu_awal is None and sebab == "TIDAK_COCOK"


def test_roster_menang_atas_dugaan_bila_ada(dunia):
    """Untuk bulan yang rosternya terisi, jadwal jaga tetap sumber kebenaran."""
    _roster(dunia, DutyStatus.MASUK, "citra")
    _cap(dunia, "13:48", "22:39")        # polanya Jemur
    hari = _hari(dunia)
    assert hari.clinic == dunia["citra"]
    assert hari.cabang_dari_dugaan is False
    assert Pengecualian.CABANG_BEDA in hari.pengecualian


def test_dugaan_menangkap_rahayu_18_september(dunia):
    """Kasus yang lolos pada aturan selisih-biaya lama (selisih 78, ambang 90)."""
    _roster(dunia, DutyStatus.MASUK, "jemur")
    _cap(dunia, "11:57", "21:51")
    hari = _hari(dunia)
    assert Pengecualian.CABANG_BEDA in hari.pengecualian
    assert "Citraland" in " ".join(hari.catatan)


def test_jam_pulang_yang_membedakan_citraland_dari_jemur_datang_awal(dunia):
    """Inti aturan dugaan.

    Jam kerja Citraland (12-21) seluruhnya termuat di "hari Jemur yang datang dua jam
    lebih awal", dan datang awal itu dibayar. Jam masuk karena itu tidak pernah bisa
    membedakan keduanya; jam pulang bisa.
    """
    from absensi.perhitungan import duga_cabang

    def saat(teks):
        j, m = (int(x) for x in teks.split(":"))
        return timezone.make_aware(dt.datetime.combine(TGL, dt.time(j, m)))

    cabang = [dunia["jemur"], dunia["citra"]]
    # Jam masuk sama persis, jam pulang berbeda satu jam.
    pulang_21, _ = duga_cabang(saat("11:45"), saat("21:10"), TGL, cabang)
    pulang_22, alasan = duga_cabang(saat("11:45"), saat("22:10"), TGL, cabang)
    assert pulang_21 == dunia["citra"]          # pulang dekat tutup Citraland
    assert pulang_22 is None and alasan == "GANDA"   # bisa Citraland lembur, bisa Jemur awal


def test_dugaan_tidak_pernah_menukar_hari_perbantuan_jadi_datang_awal(dunia):
    """Hari Citraland Luki (11.42-21.39) tidak boleh terbaca sebagai hari Jemur."""
    from absensi.perhitungan import duga_cabang

    def saat(teks):
        j, m = (int(x) for x in teks.split(":"))
        return timezone.make_aware(dt.datetime.combine(TGL, dt.time(j, m)))

    duga, _ = duga_cabang(saat("11:42"), saat("21:39"), TGL, [dunia["jemur"], dunia["citra"]])
    assert duga == dunia["citra"]


def test_hari_tak_terduga_tetap_menampilkan_capnya(dunia):
    """Hari ini harus diisi manusia, dan yang mengisinya butuh melihat jamnya."""
    _cap(dunia, "11:39", "22:38")          # ambigu: Citraland lembur atau Jemur datang awal
    hari = _hari(dunia)
    assert hari.masuk is not None and hari.keluar is not None
    assert hari.skor == 0
    assert Pengecualian.TANPA_ROSTER in hari.pengecualian


# --- jendela shift yang dicatat mesin -------------------------------------------


def _cap_tz(dunia, *pasangan, tanggal=TGL):
    """`pasangan`: ("HH:MM", tz) — tz "I"/"II"/"" seperti kolom di ekspor mesin."""
    for teks, tz in pasangan:
        j, m = (int(x) for x in teks.split(":"))
        hari = tanggal + dt.timedelta(days=1) if j < 6 else tanggal
        AttendancePunch.objects.create(
            user=dunia["user"], shift_date=tanggal, kind=JenisCap.MASUK, tz_mesin=tz,
            occurred_at=timezone.make_aware(dt.datetime.combine(hari, dt.time(j, m))),
        )


def test_timezone_mesin_dipetakan_ke_cabang_menurut_jam_tutup(dunia):
    from absensi.perhitungan import cabang_dari_timezone

    cabang = [dunia["jemur"], dunia["citra"]]
    assert cabang_dari_timezone("I", cabang) == dunia["citra"]    # tutup lebih awal
    assert cabang_dari_timezone("II", cabang) == dunia["jemur"]
    assert cabang_dari_timezone("", cabang) is None


def test_timezone_mesin_diabaikan_bila_cabang_bukan_dua(dunia):
    """Urutan jam tutup hanya cukup memetakan dua cabang; lebih dari itu perlu aturan lain."""
    from absensi.perhitungan import cabang_dari_timezone

    ketiga = Clinic.objects.create(
        code="ketiga", name="Cabang ketiga", open_time=dt.time(10, 0), close_time=dt.time(19, 0)
    )
    assert cabang_dari_timezone("I", [dunia["jemur"], dunia["citra"], ketiga]) is None


def test_keterangan_mesin_menjawab_hari_yang_tidak_bisa_ditebak_dari_jam(dunia):
    """Datang lima jam lebih awal: polanya buntu, tetapi mesin tahu shift-nya."""
    _cap_tz(dunia, ("08:55", ""), ("22:19", "II"))
    hari = _hari(dunia)
    assert hari.clinic == dunia["jemur"]
    assert hari.datang_awal == 305        # inilah hari yang hilang bila hanya menebak pola
    assert "mesin" in " ".join(hari.catatan)


def test_keterangan_mesin_menjawab_baris_cap_tunggal(dunia):
    """Satu cap saja tidak punya pola untuk dibaca, tetapi kolomnya tetap menandakan shift."""
    _cap_tz(dunia, ("21:02", "I"))
    hari = _hari(dunia)
    assert hari.clinic == dunia["citra"]
    assert hari.lembur_pulang == 2


def test_keterangan_mesin_dipakai_sebelum_dugaan_pola(dunia):
    """Hari yang polanya mengarah ke Citraland, tetapi mesin bilang Timezone II."""
    _cap_tz(dunia, ("11:39", ""), ("22:38", "II"))
    hari = _hari(dunia)
    assert hari.clinic == dunia["jemur"]          # dugaan pola akan menyebutnya ambigu
    assert hari.datang_awal == 141


def test_dugaan_pola_dipakai_bila_mesin_tidak_memberi_keterangan(dunia):
    _cap_tz(dunia, ("14:02", ""), ("22:05", ""))
    hari = _hari(dunia)
    assert hari.clinic == dunia["jemur"]
    assert "pola" in " ".join(hari.catatan)


def test_roster_tetap_menang_atas_keterangan_mesin(dunia):
    """Jadwal jaga yang sudah diisi manusia tidak boleh ditimpa keterangan mesin."""
    _roster(dunia, DutyStatus.MASUK, "citra")
    _cap_tz(dunia, ("13:48", ""), ("22:39", "II"))
    hari = _hari(dunia)
    assert hari.clinic == dunia["citra"]
    assert hari.cabang_dari_dugaan is False
    assert Pengecualian.CABANG_BEDA in hari.pengecualian
