"""Permintaan koreksi dari staf (Tahap 5).

Yang diuji bukan "formnya jalan", tetapi batas-batas yang membuat fitur ini aman:
staf tidak bisa mengubah angkanya sendiri, tidak bisa mengirim atas nama orang
lain, jam usulannya tidak pernah terpakai otomatis, menolak wajib beralasan, dan
staf benar-benar melihat jawabannya.
"""
from __future__ import annotations

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from absensi.models import (
    AttendancePunch,
    JenisCap,
    PermintaanKoreksi,
    StatusPermintaan,
    SumberCap,
)
from accounts.models import Capability, Role, User, UserCapability, UserRole
from audit.models import AuditEvent
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
    """Hari kerja dengan satu cap saja — staf lupa cap masuk."""
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
    AttendancePunch.objects.create(
        user=staf, shift_date=TGL, kind=JenisCap.TIDAK_PASTI,
        occurred_at=timezone.make_aware(dt.datetime.combine(TGL, dt.time(22, 10))),
    )
    return {"jemur": jemur, "direktur": direktur, "owner": owner, "staf": staf}


def _masuk(client, user):
    assert client.login(username=user.username, password=SANDI)


def _kirim(client, tanggal=TGL, alasan="lupa cap masuk, saya datang 13.55", **extra):
    data = {"tanggal": tanggal.isoformat(), "alasan": alasan}
    data.update(extra)
    return client.post(reverse("absensi:minta_koreksi"), data, follow=True)


# --- staf mengirim permintaan --------------------------------------------------


def test_staf_bisa_mengirim_permintaan(client, dunia):
    _masuk(client, dunia["staf"])
    resp = _kirim(client, usul_masuk="13:55")
    assert resp.status_code == 200
    p = PermintaanKoreksi.objects.get()
    assert p.user == dunia["staf"]
    assert p.shift_date == TGL
    assert p.status == StatusPermintaan.MENUNGGU
    assert p.usul_masuk == dt.time(13, 55)


def test_permintaan_tidak_mengubah_angka_apa_pun(client, dunia):
    """Inti D4: staf melapor, tidak mengoreksi."""
    from absensi.perhitungan import hitung_periode

    sebelum = hitung_periode(TGL, TGL, users=[dunia["staf"]])[0].skor
    _masuk(client, dunia["staf"])
    _kirim(client, usul_masuk="13:55")
    assert hitung_periode(TGL, TGL, users=[dunia["staf"]])[0].skor == sebelum
    assert not AttendancePunch.objects.filter(source=SumberCap.MANUAL).exists()


def test_alasan_wajib(client, dunia):
    _masuk(client, dunia["staf"])
    resp = _kirim(client, alasan="   ")
    assert "Alasan koreksi wajib diisi" in resp.content.decode()
    assert not PermintaanKoreksi.objects.exists()


def test_jam_usulan_boleh_kosong(client, dunia):
    _masuk(client, dunia["staf"])
    _kirim(client)
    p = PermintaanKoreksi.objects.get()
    assert p.usul_masuk is None and p.usul_keluar is None


def test_jam_usulan_tidak_terbaca_ditolak(client, dunia):
    _masuk(client, dunia["staf"])
    resp = _kirim(client, usul_masuk="pagi")
    assert "Jam tidak terbaca" in resp.content.decode()
    assert not PermintaanKoreksi.objects.exists()


def test_tidak_bisa_mengirim_dua_kali_untuk_hari_yang_sama(client, dunia):
    _masuk(client, dunia["staf"])
    _kirim(client)
    resp = _kirim(client, alasan="lupa lagi")
    assert "masih menunggu ditinjau" in resp.content.decode()
    assert PermintaanKoreksi.objects.count() == 1


def test_boleh_mengirim_lagi_setelah_dijawab(client, dunia):
    """Hari yang sudah dijawab tetapi masih keliru harus bisa dilaporkan ulang."""
    _masuk(client, dunia["staf"])
    _kirim(client)
    PermintaanKoreksi.objects.update(status=StatusPermintaan.DITOLAK, tanggapan="tidak ada jadwal")
    _kirim(client, alasan="ada jadwalnya, tukar shift dengan Yani")
    assert PermintaanKoreksi.objects.count() == 2


def test_tanggal_tidak_sah_jadi_404(client, dunia):
    _masuk(client, dunia["staf"])
    assert client.post(
        reverse("absensi:minta_koreksi"), {"tanggal": "bukan-tanggal", "alasan": "x"}
    ).status_code == 404


def test_belum_login_diarahkan(client, dunia):
    resp = client.post(reverse("absensi:minta_koreksi"), {"tanggal": TGL.isoformat(), "alasan": "x"})
    assert resp.status_code == 302 and "login" in resp["Location"]


def test_permintaan_selalu_atas_nama_pengirim(client, dunia):
    """Rute ini tidak punya parameter staf; kirim apa pun, pemiliknya tetap pengirim."""
    _masuk(client, dunia["staf"])
    _kirim(client, user=dunia["direktur"].pk, staf=dunia["direktur"].pk)
    assert PermintaanKoreksi.objects.get().user == dunia["staf"]


# --- staf melihat jawabannya ---------------------------------------------------


def test_staf_melihat_status_di_halaman_sendiri(client, dunia):
    _masuk(client, dunia["staf"])
    _kirim(client)
    body = client.get(reverse("absensi:saya"), {"bulan": BULAN}).content.decode()
    assert "menunggu ditinjau" in body


def test_staf_melihat_jawaban_penolakan(client, dunia):
    """Permintaan yang ditolak tanpa kabar adalah yang membuat orang berhenti melapor."""
    _masuk(client, dunia["staf"])
    _kirim(client)
    PermintaanKoreksi.objects.update(
        status=StatusPermintaan.DITOLAK, tanggapan="Hari itu Anda tidak ada di jadwal jaga"
    )
    body = client.get(reverse("absensi:saya"), {"bulan": BULAN}).content.decode()
    assert "tidak dikoreksi" in body
    assert "tidak ada di jadwal jaga" in body


def test_halaman_sendiri_menawarkan_tombol_bila_belum_ada_permintaan(client, dunia):
    _masuk(client, dunia["staf"])
    body = client.get(reverse("absensi:saya"), {"bulan": BULAN}).content.decode()
    assert "Cap saya kurang" in body


# --- yang mengoreksi menjawab ---------------------------------------------------


def _buat_permintaan(dunia, **extra):
    return PermintaanKoreksi.objects.create(
        user=dunia["staf"], shift_date=TGL, alasan="lupa cap masuk", **extra
    )


def test_permintaan_muncul_di_perlu_dicek(client, dunia):
    _buat_permintaan(dunia)
    _masuk(client, dunia["direktur"])
    body = client.get(
        reverse("absensi:index"), {"tab": "pengecualian", "bulan": BULAN}
    ).content.decode()
    assert "Permintaan dari staf" in body
    assert reverse("absensi:koreksi", args=[dunia["staf"].pk, TGL.isoformat()]) in body


def test_direktur_bisa_menandai_sudah_dikoreksi(client, dunia):
    p = _buat_permintaan(dunia)
    _masuk(client, dunia["direktur"])
    client.post(
        reverse("absensi:koreksi", args=[dunia["staf"].pk, TGL.isoformat()]),
        {"aksi": "tanggapi", "permintaan": p.pk, "status": "DIKOREKSI", "tanggapan": "cap 13.55 ditambahkan"},
    )
    p.refresh_from_db()
    assert p.status == StatusPermintaan.DIKOREKSI
    assert p.ditangani_oleh == dunia["direktur"]
    assert p.ditangani_pada is not None


def test_menolak_wajib_beralasan(client, dunia):
    p = _buat_permintaan(dunia)
    _masuk(client, dunia["direktur"])
    resp = client.post(
        reverse("absensi:koreksi", args=[dunia["staf"].pk, TGL.isoformat()]),
        {"aksi": "tanggapi", "permintaan": p.pk, "status": "DITOLAK", "tanggapan": "  "},
        follow=True,
    )
    assert "wajib disertai alasan" in resp.content.decode()
    p.refresh_from_db()
    assert p.status == StatusPermintaan.MENUNGGU


def test_permintaan_yang_sudah_dijawab_tidak_bisa_dijawab_lagi(client, dunia):
    p = _buat_permintaan(dunia, status=StatusPermintaan.DIKOREKSI, tanggapan="sudah")
    _masuk(client, dunia["direktur"])
    resp = client.post(
        reverse("absensi:koreksi", args=[dunia["staf"].pk, TGL.isoformat()]),
        {"aksi": "tanggapi", "permintaan": p.pk, "status": "DITOLAK", "tanggapan": "berubah pikiran"},
        follow=True,
    )
    assert "sudah dijawab" in resp.content.decode()
    p.refresh_from_db()
    assert p.status == StatusPermintaan.DIKOREKSI


def test_owner_boleh_menjawab(client, dunia):
    """D4: Owner termasuk yang boleh mengoreksi, jadi ia juga boleh menjawab."""
    p = _buat_permintaan(dunia)
    _masuk(client, dunia["owner"])
    client.post(
        reverse("absensi:koreksi", args=[dunia["staf"].pk, TGL.isoformat()]),
        {"aksi": "tanggapi", "permintaan": p.pk, "status": "DIKOREKSI", "tanggapan": "beres"},
    )
    p.refresh_from_db()
    assert p.status == StatusPermintaan.DIKOREKSI


def test_staf_tidak_bisa_menjawab_permintaannya_sendiri(client, dunia):
    """Kalau ini lolos, staf bisa menyatakan capnya sendiri sudah benar."""
    p = _buat_permintaan(dunia)
    _masuk(client, dunia["staf"])
    assert client.post(
        reverse("absensi:koreksi", args=[dunia["staf"].pk, TGL.isoformat()]),
        {"aksi": "tanggapi", "permintaan": p.pk, "status": "DIKOREKSI", "tanggapan": "beres"},
    ).status_code == 403
    p.refresh_from_db()
    assert p.status == StatusPermintaan.MENUNGGU


def test_admin_akses_penuh_tidak_bisa_menjawab(client, dunia):
    p = _buat_permintaan(dunia)
    admin = _user(dunia["jemur"], "adminpenuh", Role.ADMIN)
    UserCapability.objects.create(user=admin, capability=Capability.ADMIN_FULL_ACCESS)
    _masuk(client, admin)
    assert client.post(
        reverse("absensi:koreksi", args=[dunia["staf"].pk, TGL.isoformat()]),
        {"aksi": "tanggapi", "permintaan": p.pk, "status": "DIKOREKSI", "tanggapan": "beres"},
    ).status_code == 403


def test_permintaan_orang_lain_tidak_bisa_dijawab_dari_halaman_seseorang(client, dunia):
    lain = _user(dunia["jemur"], "naya", Role.PERAWAT, Role.STAF)
    p = PermintaanKoreksi.objects.create(user=lain, shift_date=TGL, alasan="lupa")
    _masuk(client, dunia["direktur"])
    assert client.post(
        reverse("absensi:koreksi", args=[dunia["staf"].pk, TGL.isoformat()]),
        {"aksi": "tanggapi", "permintaan": p.pk, "status": "DIKOREKSI", "tanggapan": "x"},
    ).status_code == 404


def test_jam_usulan_tidak_pernah_terpakai_otomatis(client, dunia):
    """Angka yang menentukan bayaran tidak boleh berasal dari orang yang dibayar."""
    p = _buat_permintaan(dunia, usul_masuk=dt.time(10, 0), usul_keluar=dt.time(23, 59))
    _masuk(client, dunia["direktur"])
    client.post(
        reverse("absensi:koreksi", args=[dunia["staf"].pk, TGL.isoformat()]),
        {"aksi": "tanggapi", "permintaan": p.pk, "status": "DIKOREKSI", "tanggapan": "beres"},
    )
    assert not AttendancePunch.objects.filter(source=SumberCap.MANUAL).exists()
    assert AttendancePunch.objects.filter(user=dunia["staf"], shift_date=TGL).count() == 1


# --- audit ----------------------------------------------------------------------


def test_pengiriman_dan_jawaban_tercatat_di_audit(client, dunia):
    _masuk(client, dunia["staf"])
    _kirim(client)
    p = PermintaanKoreksi.objects.get()
    _masuk(client, dunia["direktur"])
    client.post(
        reverse("absensi:koreksi", args=[dunia["staf"].pk, TGL.isoformat()]),
        {"aksi": "tanggapi", "permintaan": p.pk, "status": "DITOLAK", "tanggapan": "tidak ada jadwal"},
    )
    jejak = AuditEvent.objects.filter(entity_type="absensi.PermintaanKoreksi").order_by("id")
    assert jejak.count() == 2
    assert jejak[0].actor == dunia["staf"]
    assert jejak[1].actor == dunia["direktur"]
    assert "tidak ada jadwal" in jejak[1].reason
    assert jejak[1].before_json["status"] == "MENUNGGU"
    assert jejak[1].after_json["status"] == "DITOLAK"
