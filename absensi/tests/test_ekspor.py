"""Unduh CSV papan skor dan daftar "Perlu dicek" (Tahap 6).

Yang diuji: siapa boleh mengunduh, isinya cocok dengan layar, orang tidak hilang
diam-diam dari berkas, sel tidak bisa dijadikan rumus spreadsheet, dan unduhan
tercatat di audit.
"""
from __future__ import annotations

import csv
import datetime as dt
import io

import pytest
from django.urls import reverse
from django.utils import timezone

from absensi.models import AttendanceDevice, AttendancePunch, JenisCap, SumberCap
from accounts.models import Capability, Role, User, UserCapability, UserRole
from audit.models import AuditAction, AuditEvent
from core.models import Clinic
from jadwal.models import DutyRoster, DutyStatus

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


def _unduh(client, tab):
    return client.get(reverse("absensi:index"), {"tab": tab, "bulan": BULAN, "unduh": "csv"})


def _baca(resp):
    isi = resp.content.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(isi)))


# --- izin -----------------------------------------------------------------------


@pytest.mark.parametrize("tab", ["skor", "pengecualian"])
def test_direktur_bisa_mengunduh(client, dunia, tab):
    _masuk(client, dunia["direktur"])
    resp = _unduh(client, tab)
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("text/csv")
    assert "attachment" in resp["Content-Disposition"]


@pytest.mark.parametrize("tab", ["skor", "pengecualian"])
def test_owner_bisa_mengunduh(client, dunia, tab):
    """Owner membaca papan skor, jadi ia boleh mengunduhnya juga (lewat GET)."""
    _masuk(client, dunia["owner"])
    assert _unduh(client, tab).status_code == 200


def test_staf_tidak_bisa_mengunduh(client, dunia):
    _masuk(client, dunia["staf"])
    assert _unduh(client, "skor").status_code == 403


def test_belum_login_diarahkan(client, dunia):
    resp = _unduh(client, "skor")
    assert resp.status_code == 302 and "login" in resp["Location"]


# --- isi berkas -----------------------------------------------------------------


def test_papan_skor_memuat_angka_yang_sama_dengan_layar(client, dunia):
    _masuk(client, dunia["direktur"])
    baris = _baca(_unduh(client, "skor"))
    assert baris[0][0] == "Nama"
    isi = {b[0]: b for b in baris[1:]}
    assert "Elvira" in isi
    # 00.28 pada shift tutup 22.00 = lembur 148 menit, sama dengan papan skor
    assert isi["Elvira"][baris[0].index("Lembur pulang (menit)")] == "148"
    assert isi["Elvira"][baris[0].index("Skor (menit)")] == "148"


def test_berkas_diawali_bom_agar_excel_membaca_utf8(client, dunia):
    _masuk(client, dunia["direktur"])
    assert _unduh(client, "skor").content.startswith(b"\xef\xbb\xbf")


def test_nama_berkas_memuat_bulannya(client, dunia):
    _masuk(client, dunia["direktur"])
    assert "absensi-papan-skor-2026-09.csv" in _unduh(client, "skor")["Content-Disposition"]
    assert "absensi-perlu-dicek-2026-09.csv" in _unduh(client, "pengecualian")["Content-Disposition"]


def test_staf_rekam_saja_tetap_ikut_dengan_penanda(client, dunia):
    """Berkas yang diam-diam menghilangkan orang lebih berbahaya daripada kolom tambahan."""
    izul = User.objects.create_user(username="izul", password=SANDI, display_name="Izul")
    AttendanceDevice.objects.create(
        device_uid="2", device_label="Izul", user=izul, recording_only=True
    )
    AttendancePunch.objects.create(
        user=izul, shift_date=TGL, kind=JenisCap.MASUK,
        occurred_at=timezone.make_aware(dt.datetime.combine(TGL, dt.time(8, 4))),
    )
    _masuk(client, dunia["direktur"])
    baris = _baca(_unduh(client, "skor"))
    kolom = baris[0].index("Dinilai")
    isi = {b[0]: b for b in baris[1:]}
    assert "Izul" in isi, "staf rekam-saja hilang dari berkas"
    assert isi["Izul"][kolom] == "tidak"
    assert isi["Elvira"][kolom] == "ya"


def test_perlu_dicek_memuat_temuan_dan_cap_lewat_tengah_malam(client, dunia):
    _masuk(client, dunia["direktur"])
    baris = _baca(_unduh(client, "pengecualian"))
    assert baris[0][0] == "Tanggal"
    assert len(baris) > 1
    satu = baris[1]
    assert satu[baris[0].index("Tanggal")] == "2026-09-04"
    assert "Cap pulang setelah tengah malam" in satu[baris[0].index("Temuan")]
    # Cap pulang jatuh tanggal berikutnya; tanggalnya ikut ditulis agar tidak
    # terbaca sebagai pulang paling awal sepanjang bulan.
    assert satu[baris[0].index("Cap pulang")] == "2026-09-05 00:28"


def test_hari_yang_dikoreksi_tangan_ditandai(client, dunia):
    AttendancePunch.objects.filter(user=dunia["staf"]).update(source=SumberCap.MANUAL)
    _masuk(client, dunia["direktur"])
    baris = _baca(_unduh(client, "pengecualian"))
    assert baris[1][baris[0].index("Dikoreksi tangan")] == "ya"


def test_bulan_kosong_menghasilkan_berkas_berisi_judul_saja(client, dunia):
    _masuk(client, dunia["direktur"])
    baris = _baca(client.get(
        reverse("absensi:index"), {"tab": "pengecualian", "bulan": "2026-01", "unduh": "csv"}
    ))
    assert len(baris) == 1 and baris[0][0] == "Tanggal"


def test_tab_impor_tidak_mengunduh_apa_pun(client, dunia):
    """Tanpa penjagaan ini, ?tab=impor&unduh=csv diam-diam mengirim papan skor."""
    _masuk(client, dunia["direktur"])
    resp = client.get(reverse("absensi:index"), {"tab": "impor", "bulan": BULAN, "unduh": "csv"})
    assert resp.status_code == 200
    assert "text/csv" not in resp["Content-Type"]


# --- keamanan sel ---------------------------------------------------------------


def test_sel_tidak_bisa_dijadikan_rumus_spreadsheet(client, dunia):
    """Nama atau catatan yang diawali = + - @ tidak boleh dijalankan Excel."""
    jahat = User.objects.create_user(
        username="jahat", password=SANDI, display_name="=HYPERLINK(\"http://x\",\"klik\")"
    )
    DutyRoster.objects.create(
        user=jahat, date=TGL, home_clinic=dunia["jemur"], clinic=dunia["jemur"],
        status=DutyStatus.MASUK,
    )
    _masuk(client, dunia["direktur"])
    isi = _unduh(client, "skor").content.decode("utf-8-sig")
    assert "'=HYPERLINK" in isi
    assert '\n=HYPERLINK' not in isi and ',=HYPERLINK' not in isi


# --- audit ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "tab, entity", [("skor", "absensi.papan_skor"), ("pengecualian", "absensi.pengecualian")]
)
def test_unduhan_tercatat_di_audit(client, dunia, tab, entity):
    """Ini data penilaian staf yang keluar dari sistem; harus bisa ditelusuri."""
    _masuk(client, dunia["direktur"])
    _unduh(client, tab)
    jejak = AuditEvent.objects.get(entity_type=entity)
    assert jejak.action == AuditAction.EXPORT
    assert jejak.actor == dunia["direktur"]
    assert jejak.after_json["bulan"] == "2026-09"


# --- tombol di halaman ----------------------------------------------------------


def test_tombol_unduh_muncul_di_kedua_tab(client, dunia):
    _masuk(client, dunia["direktur"])
    skor = client.get(reverse("absensi:index"), {"tab": "skor", "bulan": BULAN}).content.decode()
    assert "Unduh CSV papan skor" in skor
    perlu = client.get(
        reverse("absensi:index"), {"tab": "pengecualian", "bulan": BULAN}
    ).content.decode()
    assert "Unduh CSV perlu dicek" in perlu
