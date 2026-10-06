"""Koreksi cap dari halaman (Tahap 4).

Yang diuji di sini bukan "formnya jalan", tetapi empat hal yang kalau salah membuat
modul ini berbahaya: siapa boleh mengoreksi, alasan tidak bisa dilewati, jam dini hari
tetap milik hari kerjanya, dan setiap perubahan meninggalkan jejak audit.
"""
from __future__ import annotations

import datetime as dt

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
    """Satu hari kerja Jemur dengan satu cap saja — kasus `CAP_TUNGGAL` yang nyata.

    Pada September 2026 ada 8 hari seperti ini: orang lupa mengecap masuk, dan sebelum
    Tahap 4 daftar "Perlu dicek" hanya bisa menunjuknya tanpa bisa menutupnya.
    """
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
    tunggal = AttendancePunch.objects.create(
        user=staf, shift_date=TGL, kind=JenisCap.TIDAK_PASTI, tz_mesin="II",
        occurred_at=timezone.make_aware(dt.datetime.combine(TGL, dt.time(22, 10))),
    )
    return {
        "jemur": jemur, "direktur": direktur, "owner": owner, "staf": staf, "tunggal": tunggal,
    }


def _masuk(client, user):
    assert client.login(username=user.username, password=SANDI)


def _url(orang, tanggal=TGL):
    return reverse("absensi:koreksi", args=[orang.pk, tanggal.isoformat()])


def _skor_hari(orang, tanggal=TGL):
    from absensi.perhitungan import hitung_periode

    ringkasan = hitung_periode(tanggal, tanggal, users=[orang])
    return ringkasan[0].hari[0]


# --- siapa boleh (D4) -----------------------------------------------------------


def test_direktur_operasional_boleh_membuka(client, dunia):
    _masuk(client, dunia["direktur"])
    assert client.get(_url(dunia["staf"])).status_code == 200


def test_owner_boleh_mengoreksi_walau_read_only_di_halaman_lain(client, dunia):
    """D4 memberi Owner dan Direktur Utama hak mengoreksi, jadi POST-nya tidak boleh ditolak."""
    _masuk(client, dunia["owner"])
    assert client.get(_url(dunia["staf"])).status_code == 200
    resp = client.post(
        _url(dunia["staf"]),
        {"aksi": "tambah", "jam": "13:55", "jenis": JenisCap.MASUK, "alasan": "lupa cap masuk"},
    )
    assert resp.status_code == 302
    assert AttendancePunch.objects.filter(user=dunia["staf"], source=SumberCap.MANUAL).count() == 1


def test_admin_akses_penuh_boleh_mengimpor_tetapi_tidak_mengoreksi(client, dunia):
    """Batas antara `can_edit_absensi` dan `can_correct_absensi`, ditegakkan di view."""
    admin = _user(dunia["jemur"], "adminpenuh", Role.ADMIN)
    UserCapability.objects.create(user=admin, capability=Capability.ADMIN_FULL_ACCESS)
    _masuk(client, admin)
    assert client.get(reverse("absensi:index")).status_code == 200
    assert client.get(_url(dunia["staf"])).status_code == 403
    assert client.post(_url(dunia["staf"]), {"aksi": "tambah"}).status_code == 403


def test_staf_tidak_boleh_mengoreksi_capnya_sendiri(client, dunia):
    _masuk(client, dunia["staf"])
    assert client.get(_url(dunia["staf"])).status_code == 403
    assert client.post(
        _url(dunia["staf"]),
        {"aksi": "tambah", "jam": "08:00", "jenis": JenisCap.MASUK, "alasan": "datang pagi"},
    ).status_code == 403
    assert not AttendancePunch.objects.filter(source=SumberCap.MANUAL).exists()


def test_belum_login_diarahkan_ke_login(client, dunia):
    resp = client.get(_url(dunia["staf"]))
    assert resp.status_code == 302 and "login" in resp["Location"]


def test_halaman_sendiri_tidak_punya_tombol_koreksi(client, dunia):
    """Yang berhak mengoreksi pun tidak memperbaiki angkanya sendiri dari "Absensi saya"."""
    _masuk(client, dunia["direktur"])
    body = client.get(reverse("absensi:saya"), {"bulan": BULAN}).content.decode()
    assert "absensi/koreksi/" not in body


# --- menutup hari yang kehilangan cap masuk -------------------------------------


def test_menambah_cap_masuk_menutup_cap_tunggal_dan_mengubah_skor(client, dunia):
    """Inti Tahap 4: 8 hari September yang kehilangan cap masuk bisa ditutup dari halaman."""
    from absensi.perhitungan import Pengecualian

    sebelum = _skor_hari(dunia["staf"])
    assert Pengecualian.CAP_TUNGGAL in sebelum.pengecualian
    assert sebelum.masuk is None

    _masuk(client, dunia["direktur"])
    client.post(
        _url(dunia["staf"]),
        {"aksi": "tambah", "jam": "13:55", "jenis": JenisCap.MASUK,
         "alasan": "lupa cap masuk, dikonfirmasi Koordinator Shift"},
    )
    sesudah = _skor_hari(dunia["staf"])
    assert Pengecualian.CAP_TUNGGAL not in sesudah.pengecualian
    assert sesudah.terlambat == 0
    assert sesudah.lembur_pulang == 10          # 22.10 pada shift tutup 22.00
    assert sesudah.ada_koreksi_manual is True


def test_cap_hasil_koreksi_bersumber_manual_dan_menyimpan_alasannya(client, dunia):
    _masuk(client, dunia["direktur"])
    client.post(
        _url(dunia["staf"]),
        {"aksi": "tambah", "jam": "13:55", "jenis": JenisCap.MASUK, "alasan": "lupa cap masuk"},
    )
    cap = AttendancePunch.objects.get(user=dunia["staf"], kind=JenisCap.MASUK)
    assert cap.source == SumberCap.MANUAL
    assert cap.note == "lupa cap masuk"
    assert cap.shift_date == TGL


def test_hari_yang_dikoreksi_ditandai_di_halaman(client, dunia):
    """Angka hasil koreksi tangan tidak boleh terlihat sama pastinya dengan angka mesin."""
    _masuk(client, dunia["direktur"])
    client.post(
        _url(dunia["staf"]),
        {"aksi": "tambah", "jam": "13:55", "jenis": JenisCap.MASUK, "alasan": "lupa cap masuk"},
    )
    body = client.get(
        reverse("absensi:staf", args=[dunia["staf"].pk]), {"bulan": BULAN}
    ).content.decode()
    assert "dikoreksi tangan" in body


# --- alasan wajib ---------------------------------------------------------------


@pytest.mark.parametrize("alasan", ["", "   "])
def test_tanpa_alasan_tidak_menyimpan_apa_pun(client, dunia, alasan):
    """`required` di HTML bisa dilewati siapa pun yang mengirim POST sendiri."""
    _masuk(client, dunia["direktur"])
    resp = client.post(
        _url(dunia["staf"]),
        {"aksi": "tambah", "jam": "13:55", "jenis": JenisCap.MASUK, "alasan": alasan},
        follow=True,
    )
    assert "Alasan koreksi wajib diisi" in resp.content.decode()
    assert not AttendancePunch.objects.filter(source=SumberCap.MANUAL).exists()


def test_mengubah_cap_tanpa_alasan_tidak_menggeser_jamnya(client, dunia):
    cap = dunia["tunggal"]
    _masuk(client, dunia["direktur"])
    client.post(
        _url(dunia["staf"]), {"aksi": "ubah", "cap": cap.pk, "jam": "23:30", "jenis": cap.kind}
    )
    cap.refresh_from_db()
    assert timezone.localtime(cap.occurred_at).hour == 22
    assert cap.source == SumberCap.FINGERPRINT


# --- jam dini hari tetap milik hari kerjanya ------------------------------------


def test_cap_dini_hari_disimpan_sebagai_tanggal_berikutnya(client, dunia):
    """Pulang 00.28 pada hari kerja tanggal 4 = lembur 148 menit, bukan −1292."""
    cap = dunia["tunggal"]
    _masuk(client, dunia["direktur"])
    client.post(
        _url(dunia["staf"]),
        {"aksi": "ubah", "cap": cap.pk, "jam": "00:28", "jenis": JenisCap.KELUAR,
         "alasan": "jam pulang terbaca keliru di ekspor"},
    )
    cap.refresh_from_db()
    lokal = timezone.localtime(cap.occurred_at)
    assert cap.shift_date == TGL                      # hari kerjanya tidak berpindah
    assert lokal.date() == TGL + dt.timedelta(days=1)  # waktu mutlaknya dini hari berikutnya
    assert _skor_hari(dunia["staf"]).lembur_pulang == 148


def test_jam_tidak_terbaca_ditolak_dengan_pesan(client, dunia):
    _masuk(client, dunia["direktur"])
    resp = client.post(
        _url(dunia["staf"]),
        {"aksi": "tambah", "jam": "jam dua", "jenis": JenisCap.MASUK, "alasan": "coba"},
        follow=True,
    )
    assert "Jam tidak terbaca" in resp.content.decode()
    assert not AttendancePunch.objects.filter(source=SumberCap.MANUAL).exists()


def test_cap_bentrok_memberi_pesan_bukan_error_server(client, dunia):
    """Constraint (staf, waktu cap) tidak boleh muncul sebagai IntegrityError di layar."""
    _masuk(client, dunia["direktur"])
    resp = client.post(
        _url(dunia["staf"]),
        {"aksi": "tambah", "jam": "22:10", "jenis": JenisCap.KELUAR, "alasan": "cap ganda"},
        follow=True,
    )
    assert "Sudah ada cap" in resp.content.decode()
    assert AttendancePunch.objects.filter(user=dunia["staf"], shift_date=TGL).count() == 1


# --- jenis tidak menyentuh angka ------------------------------------------------


def test_mengubah_jenis_tidak_menggeser_skor(client, dunia):
    """Penjaga: skor dihitung dari urutan waktu, bukan dari label masuk/keluar.

    Tanpa test ini, mudah mengira hari `CAP_TUNGGAL` bisa ditutup dengan membetulkan
    labelnya saja — padahal yang kurang adalah capnya.
    """
    cap = dunia["tunggal"]
    sebelum = _skor_hari(dunia["staf"]).skor
    _masuk(client, dunia["direktur"])
    client.post(
        _url(dunia["staf"]),
        {"aksi": "ubah", "cap": cap.pk, "jam": "22:10", "jenis": JenisCap.KELUAR,
         "alasan": "merapikan label, jamnya sudah benar"},
    )
    assert _skor_hari(dunia["staf"]).skor == sebelum


# --- hapus: hanya cap manual ----------------------------------------------------


def test_cap_mesin_tidak_bisa_dihapus_dari_halaman(client, dunia):
    """Cap mesin adalah bukti apa yang dicatat alat; jamnya boleh diubah, tidak dihapus."""
    cap = dunia["tunggal"]
    _masuk(client, dunia["direktur"])
    resp = client.post(
        _url(dunia["staf"]), {"aksi": "hapus", "cap": cap.pk, "alasan": "salah orang"}, follow=True
    )
    assert "tidak dihapus dari halaman ini" in resp.content.decode()
    assert AttendancePunch.objects.filter(pk=cap.pk).exists()


def test_cap_manual_yang_keliru_bisa_dihapus(client, dunia):
    """Halaman yang bisa membuat cap harus bisa membereskan capnya sendiri."""
    _masuk(client, dunia["direktur"])
    client.post(
        _url(dunia["staf"]),
        {"aksi": "tambah", "jam": "13:55", "jenis": JenisCap.MASUK, "alasan": "lupa cap masuk"},
    )
    cap = AttendancePunch.objects.get(user=dunia["staf"], source=SumberCap.MANUAL)
    client.post(
        _url(dunia["staf"]), {"aksi": "hapus", "cap": cap.pk, "alasan": "salah tanggal, dibatalkan"}
    )
    assert not AttendancePunch.objects.filter(pk=cap.pk).exists()


def test_cap_orang_lain_tidak_bisa_diubah_dari_halaman_seseorang(client, dunia):
    """Rute memuat pemilik dan tanggalnya, jadi id cap dari hari lain tidak boleh dilayani."""
    lain = _user(dunia["jemur"], "naya", Role.PERAWAT, Role.STAF)
    cap_lain = AttendancePunch.objects.create(
        user=lain, shift_date=TGL, kind=JenisCap.MASUK,
        occurred_at=timezone.make_aware(dt.datetime.combine(TGL, dt.time(14, 2))),
    )
    _masuk(client, dunia["direktur"])
    resp = client.post(
        _url(dunia["staf"]),
        {"aksi": "ubah", "cap": cap_lain.pk, "jam": "15:00", "jenis": JenisCap.MASUK,
         "alasan": "coba tembus"},
    )
    assert resp.status_code == 404
    cap_lain.refresh_from_db()
    assert timezone.localtime(cap_lain.occurred_at).hour == 14


# --- audit ----------------------------------------------------------------------


def test_penambahan_tercatat_di_audit_beserta_alasannya(client, dunia):
    _masuk(client, dunia["direktur"])
    client.post(
        _url(dunia["staf"]),
        {"aksi": "tambah", "jam": "13:55", "jenis": JenisCap.MASUK,
         "alasan": "lupa cap masuk, dikonfirmasi Koordinator Shift"},
    )
    jejak = AuditEvent.objects.get(entity_type="absensi.AttendancePunch")
    assert jejak.action == AuditAction.CORRECTION
    assert jejak.actor == dunia["direktur"]
    assert "dikonfirmasi Koordinator Shift" in jejak.reason
    assert jejak.after_json["source"] == SumberCap.MANUAL


def test_perubahan_menyimpan_nilai_lama_di_audit(client, dunia):
    """Tanpa nilai lamanya, koreksi tidak bisa diperiksa ulang sebulan kemudian."""
    cap = dunia["tunggal"]
    _masuk(client, dunia["direktur"])
    client.post(
        _url(dunia["staf"]),
        {"aksi": "ubah", "cap": cap.pk, "jam": "22:35", "jenis": JenisCap.KELUAR,
         "alasan": "jam di ekspor terbaca 22.10, mesin menunjukkan 22.35"},
    )
    jejak = AuditEvent.objects.get(entity_type="absensi.AttendancePunch")
    assert jejak.before_json["occurred_at"] != jejak.after_json["occurred_at"]
    assert jejak.before_json["source"] == SumberCap.FINGERPRINT


def test_penghapusan_tetap_meninggalkan_jejak(client, dunia):
    _masuk(client, dunia["direktur"])
    client.post(
        _url(dunia["staf"]),
        {"aksi": "tambah", "jam": "13:55", "jenis": JenisCap.MASUK, "alasan": "lupa cap masuk"},
    )
    cap = AttendancePunch.objects.get(user=dunia["staf"], source=SumberCap.MANUAL)
    client.post(_url(dunia["staf"]), {"aksi": "hapus", "cap": cap.pk, "alasan": "salah tanggal"})
    hapus = AuditEvent.objects.filter(entity_label__contains="dihapus").get()
    assert hapus.action == AuditAction.CORRECTION
    assert hapus.before_json["id"] == cap.pk
    assert hapus.after_json is None


# --- tombol dan tautan ----------------------------------------------------------


def test_baris_perlu_dicek_punya_tombol_koreksi(client, dunia):
    _masuk(client, dunia["direktur"])
    body = client.get(
        reverse("absensi:index"), {"tab": "pengecualian", "bulan": BULAN}
    ).content.decode()
    assert _url(dunia["staf"]) in body


def test_yang_hanya_boleh_membaca_tidak_melihat_tombol_koreksi(client, dunia):
    """Admin berakses penuh membaca papan skor, tetapi tombolnya tidak boleh muncul."""
    admin = _user(dunia["jemur"], "adminpenuh", Role.ADMIN)
    UserCapability.objects.create(user=admin, capability=Capability.ADMIN_FULL_ACCESS)
    _masuk(client, admin)
    body = client.get(
        reverse("absensi:index"), {"tab": "pengecualian", "bulan": BULAN}
    ).content.decode()
    assert "Cap pulang setelah tengah malam" in body or "hanya satu cap" in body.lower()
    assert "absensi/koreksi/" not in body


def test_tanggal_tidak_sah_jadi_404(client, dunia):
    _masuk(client, dunia["direktur"])
    url = reverse("absensi:koreksi", args=[dunia["staf"].pk, "2026-09-04"])
    assert client.get(url.replace("2026-09-04", "bukan-tanggal")).status_code == 404


def test_hari_tanpa_cap_dan_tanpa_jadwal_tetap_bisa_dibuka(client, dunia):
    """Halaman koreksi harus bekerja justru pada hari yang belum punya apa pun."""
    _masuk(client, dunia["direktur"])
    resp = client.get(_url(dunia["staf"], dt.date(2026, 9, 20)))
    assert resp.status_code == 200
    assert "Belum ada cap pada hari ini" in resp.content.decode()


def test_staf_rekam_saja_tetap_bisa_dikoreksi(client, dunia):
    """D1: capnya tidak dinilai, tetapi tetap boleh dibetulkan bila jamnya keliru."""
    izul = User.objects.create_user(username="izul", password=SANDI, display_name="Izul")
    AttendanceDevice.objects.create(
        device_uid="2", device_label="Izul", user=izul, recording_only=True
    )
    _masuk(client, dunia["direktur"])
    resp = client.post(
        _url(izul),
        {"aksi": "tambah", "jam": "08:04", "jenis": JenisCap.MASUK, "alasan": "cap hilang di ekspor"},
        follow=True,
    )
    assert resp.status_code == 200
    assert AttendancePunch.objects.filter(user=izul, source=SumberCap.MANUAL).count() == 1
