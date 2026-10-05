"""Impor cap absensi: penentuan waktu lewat tengah malam, pemetaan ID, dan impor ulang."""
from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from absensi import services
from absensi.models import AttendanceDevice, AttendanceImport, AttendancePunch, JenisCap, SumberCap
from accounts.models import User
from audit.models import AuditEvent

from .pabrik_xlsx import bangun

pytestmark = pytest.mark.django_db

JUDUL = "Kartu Laporan 1 - 30 September 2026"


@pytest.fixture
def elvira(db):
    user = User.objects.create_user(username="elvira", password="TestPassword123!", display_name="Elvira")
    AttendanceDevice.objects.create(device_uid="17", device_label="Elvira", user=user)
    return user


def _berkas(hari, uid="17", label="Elvira"):
    return bangun(JUDUL, [{"uid": uid, "label": label, "hari": hari}])


def _lokal(punch):
    return timezone.localtime(punch.occurred_at)


# --- aturan waktu ---------------------------------------------------------------


@pytest.mark.parametrize(
    "jam, hari_diharapkan",
    [
        (dt.time(14, 2), 4),    # siang: hari yang sama
        (dt.time(23, 43), 4),   # malam sebelum tengah malam: hari yang sama
        (dt.time(0, 28), 5),    # setelah tengah malam: hari kalender berikutnya
        (dt.time(5, 59), 5),    # masih sebelum batas dini hari
        (dt.time(6, 0), 4),     # tepat di batas: sudah hari baru menurut mesin
    ],
)
def test_waktu_cap_menangani_lewat_tengah_malam(jam, hari_diharapkan):
    saat = services.waktu_cap(dt.date(2026, 9, 4), jam)
    assert timezone.localtime(saat).day == hari_diharapkan


def test_pulang_lewat_tengah_malam_jadi_lembur_bukan_pulang_awal(elvira):
    """Inti dari seluruh modul: 00.28 harus 148 menit setelah 22.00, bukan 1292 menit sebelumnya."""
    services.impor_kartu_laporan(_berkas([(4, ["13:30", "00:28"], [])]), "sep.xlsx")

    masuk, keluar = AttendancePunch.objects.order_by("occurred_at")
    assert masuk.shift_date == keluar.shift_date == dt.date(2026, 9, 4)
    assert _lokal(keluar).date() == dt.date(2026, 9, 5)

    tutup = services.waktu_cap(dt.date(2026, 9, 4), dt.time(22, 0))
    assert (keluar.occurred_at - tutup).total_seconds() / 60 == 148


# --- jenis cap ------------------------------------------------------------------


def test_cap_pertama_masuk_terakhir_keluar(elvira):
    services.impor_kartu_laporan(_berkas([(1, ["14:02", "22:05"], [])]), "sep.xlsx")
    assert [p.kind for p in AttendancePunch.objects.order_by("occurred_at")] == [
        JenisCap.MASUK,
        JenisCap.KELUAR,
    ]


def test_cap_tunggal_tidak_ditebak(elvira):
    """Importer tidak tahu jadwal shift, jadi tidak boleh memutuskan ini masuk atau keluar."""
    services.impor_kartu_laporan(_berkas([(4, ["21:02"], [])]), "sep.xlsx")
    (cap,) = AttendancePunch.objects.all()
    assert cap.kind == JenisCap.TIDAK_PASTI


def test_hari_libur_tidak_menghasilkan_cap(elvira):
    batch = services.impor_kartu_laporan(_berkas([(2, [], ["Absen"])]), "sep.xlsx")
    assert AttendancePunch.objects.count() == 0
    assert batch.rows_read == 0


def test_penanda_lokasi_lain_disimpan_sebagai_catatan(elvira):
    services.impor_kartu_laporan(_berkas([(5, ["09:04", "17:03"], ["Citraland"])]), "sep.xlsx")
    assert {p.note for p in AttendancePunch.objects.all()} == {"Citraland"}


# --- pemetaan ID ----------------------------------------------------------------


def test_id_belum_dipetakan_diperingatkan_dan_tidak_diimpor(db):
    batch = services.impor_kartu_laporan(_berkas([(1, ["14:02", "22:05"], [])], uid="99"), "sep.xlsx")
    assert AttendancePunch.objects.count() == 0
    assert any("99" in p and "belum dipetakan" in p for p in batch.warnings)


def test_nama_berbeda_dari_pemetaan_diperingatkan(elvira):
    """ID yang berpindah orang adalah kesalahan mahal; harus terlihat, bukan diam-diam."""
    batch = services.impor_kartu_laporan(
        _berkas([(1, ["14:02", "22:05"], [])], label="Nadiya"), "sep.xlsx"
    )
    assert any("berbeda dari pemetaan" in p for p in batch.warnings)
    assert AttendancePunch.objects.count() == 2  # tetap diimpor, hanya diperingatkan


def test_id_tidak_aktif_dilewati(elvira):
    AttendanceDevice.objects.filter(device_uid="17").update(active=False)
    batch = services.impor_kartu_laporan(_berkas([(1, ["14:02", "22:05"], [])]), "sep.xlsx")
    assert AttendancePunch.objects.count() == 0
    assert any("tidak aktif" in p for p in batch.warnings)


# --- impor ulang ----------------------------------------------------------------


def test_impor_ulang_berkas_sama_tidak_menggandakan_cap(elvira):
    data = _berkas([(1, ["14:02", "22:05"], []), (2, ["13:33", "23:43"], [])])
    pertama = services.impor_kartu_laporan(data, "sep.xlsx")
    kedua = services.impor_kartu_laporan(data, "sep.xlsx")

    assert (pertama.punches_created, pertama.punches_skipped) == (4, 0)
    assert (kedua.punches_created, kedua.punches_skipped) == (0, 4)
    assert AttendancePunch.objects.count() == 4
    assert any("sudah diimpor" in p for p in kedua.warnings)


def test_berkas_diperbaiki_menambah_cap_yang_kurang_saja(elvira):
    services.impor_kartu_laporan(_berkas([(1, ["14:02", "22:05"], [])]), "sep.xlsx")
    lanjutan = services.impor_kartu_laporan(
        _berkas([(1, ["14:02", "22:05"], []), (2, ["13:33", "23:43"], [])]), "sep-revisi.xlsx"
    )
    assert (lanjutan.punches_created, lanjutan.punches_skipped) == (2, 2)
    assert AttendancePunch.objects.count() == 4


# --- jejak impor ----------------------------------------------------------------


def test_batch_mencatat_periode_pelaku_dan_hitungan(elvira):
    actor = User.objects.create_user(username="aom", password="TestPassword123!")
    batch = services.impor_kartu_laporan(
        _berkas([(1, ["14:02", "22:05"], [])]), "SEPTEMBER 2026.xlsx", actor=actor
    )
    assert batch.file_name == "SEPTEMBER 2026.xlsx"
    assert (batch.period_start, batch.period_end) == (dt.date(2026, 9, 1), dt.date(2026, 9, 30))
    assert batch.imported_by == actor
    assert AttendanceImport.objects.count() == 1
    assert AttendancePunch.objects.filter(import_batch=batch, source=SumberCap.FINGERPRINT).count() == 2


def test_impor_tercatat_di_audit(elvira):
    services.impor_kartu_laporan(_berkas([(1, ["14:02", "22:05"], [])]), "sep.xlsx")
    assert AuditEvent.objects.filter(entity_type="absensi.AttendanceImport").exists()
