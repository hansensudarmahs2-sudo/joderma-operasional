"""Laporan kegiatan teknisi dengan foto dan lokasi (13 Okt 2026).

Yang diuji terutama janji-janji privasinya, karena justru itu yang paling mudah
dilanggar tanpa ada yang sadar: tanpa IP, koordinat dibulatkan, EXIF dibuang, foto
dihapus setelah 90 hari sementara uraiannya tetap.
"""
from __future__ import annotations

import datetime as dt
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User, UserRole
from core.models import Attachment, Clinic
from reports.models import LaporanKegiatan

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
    return {
        "jemur": jemur,
        "izul": _user(jemur, "izul", Role.TEKNISI),
        "aom": _user(jemur, "aom", Role.AOM),
        "staf": _user(jemur, "polos", Role.STAF),
    }


def _masuk(client, user):
    assert client.login(username=user.username, password=SANDI)


def _foto(nama="selfie.jpg"):
    """JPEG kecil sungguhan: save_photo membukanya dengan Pillow."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (80, 60), (120, 160, 200)).save(buf, format="JPEG")
    return SimpleUploadedFile(nama, buf.getvalue(), content_type="image/jpeg")


def _kirim(client, **extra):
    data = {"uraian": "Ganti seal hydra facial, sudah diuji"}
    data.update(extra)
    return client.post(reverse("reports:kegiatan"), data, follow=True)


# --- siapa boleh -----------------------------------------------------------------


def test_teknisi_bisa_membuka_dan_melapor(client, dunia):
    _masuk(client, dunia["izul"])
    assert client.get(reverse("reports:kegiatan")).status_code == 200
    _kirim(client)
    assert LaporanKegiatan.objects.count() == 1


def test_direktur_membaca_tetapi_tidak_melapor(client, dunia):
    _masuk(client, dunia["aom"])
    assert client.get(reverse("reports:kegiatan")).status_code == 200
    assert client.post(reverse("reports:kegiatan"), {"uraian": "x"}).status_code == 403


def test_staf_biasa_ditolak(client, dunia):
    _masuk(client, dunia["staf"])
    assert client.get(reverse("reports:kegiatan")).status_code == 403


def test_teknisi_hanya_melihat_laporannya_sendiri(client, dunia):
    lain = _user(dunia["jemur"], "teknisi2", Role.TEKNISI)
    punya_lain = LaporanKegiatan.objects.create(user=lain, uraian="punya orang lain")
    _masuk(client, dunia["izul"])
    body = client.get(reverse("reports:kegiatan")).content.decode()
    assert "punya orang lain" not in body
    assert client.get(
        reverse("reports:kegiatan_detail", args=[punya_lain.pk])
    ).status_code == 403


def test_direktur_melihat_laporan_semua_teknisi(client, dunia):
    LaporanKegiatan.objects.create(user=dunia["izul"], uraian="perbaikan IPAL")
    _masuk(client, dunia["aom"])
    assert "perbaikan IPAL" in client.get(reverse("reports:kegiatan")).content.decode()


# --- tempat: cabang atau di luar cabang -------------------------------------------


def test_bisa_melapor_dari_luar_cabang(client, dunia):
    """Ia berpindah antarcabang dan ke vendor; laporan dari vendor tidak boleh kehilangan tempatnya."""
    _masuk(client, dunia["izul"])
    _kirim(client, lokasi_teks="Vendor Triarta")
    l = LaporanKegiatan.objects.get()
    assert l.clinic is None
    assert l.tempat == "Vendor Triarta"


def test_tempat_memakai_nama_cabang_bila_dipilih(client, dunia):
    _masuk(client, dunia["izul"])
    _kirim(client, cabang=dunia["jemur"].pk, lokasi_teks="diabaikan")
    assert LaporanKegiatan.objects.get().tempat == "JoDerma Jemur"


def test_uraian_wajib(client, dunia):
    _masuk(client, dunia["izul"])
    resp = _kirim(client, uraian="   ")
    assert "Tulis dulu apa yang Anda kerjakan" in resp.content.decode()
    assert not LaporanKegiatan.objects.exists()


# --- lokasi ------------------------------------------------------------------------


def test_kolom_koordinat_dibatasi_empat_desimal(dunia):
    """Pembatasnya kolom itu sendiri, bukan hanya pembaca formulir.

    Ini jaminan yang sebenarnya: selebar apa pun angka yang dikirim, yang tersimpan
    tidak pernah lebih presisi dari ~11 m. Test akan gagal bila suatu saat kolomnya
    diperlebar — dan itulah perubahan yang perlu ditinjau manusia.
    """
    kolom = {f.name: f for f in LaporanKegiatan._meta.fields}
    for nama in ("latitude", "longitude"):
        assert kolom[nama].decimal_places == 4, f"{nama} tidak lagi dibatasi 4 desimal"


def test_koordinat_tersimpan_dibulatkan(client, dunia):
    """~11 m: cukup untuk tahu tempatnya, tidak untuk melacak orang."""
    _masuk(client, dunia["izul"])
    _kirim(client, geo_status="OK", geo_lat="-7.3123456", geo_lng="112.7456789", geo_acc="18")
    l = LaporanKegiatan.objects.get()
    assert abs(l.latitude.as_tuple().exponent) <= 4
    assert abs(l.longitude.as_tuple().exponent) <= 4
    assert l.accuracy_m == 18


def test_lokasi_tidak_wajib(client, dunia):
    """Izin lokasi ditolak tidak boleh menggagalkan laporan."""
    _masuk(client, dunia["izul"])
    _kirim(client, geo_status="DITOLAK")
    l = LaporanKegiatan.objects.get()
    assert l.latitude is None and l.longitude is None
    assert l.geo_status == "DITOLAK"


def test_tidak_menyimpan_ip_maupun_user_agent(client, dunia):
    """Keputusan 13 Okt: lokasi ya, IP tidak. Orang yang berpindah-pindah tidak dijelaskan IP."""
    _masuk(client, dunia["izul"])
    _kirim(client, geo_status="OK", geo_lat="-7.3123", geo_lng="112.7457", geo_acc="10")
    kolom = {f.name for f in LaporanKegiatan._meta.fields}
    assert not kolom & {"ip_address", "ip_prefix", "network", "user_agent", "device"}


# --- foto ---------------------------------------------------------------------------


def test_foto_tersimpan_sebagai_lampiran_privat(client, dunia):
    _masuk(client, dunia["izul"])
    _kirim(client, foto=_foto())
    l = LaporanKegiatan.objects.get()
    a = Attachment.objects.get(entity_type="laporan_kegiatan", entity_id=l.pk)
    assert a.sensitive is True
    assert a.mime_type == "image/jpeg"


def test_laporan_tetap_tersimpan_bila_fotonya_ditolak(client, dunia):
    """Teks yang sudah ditulis tidak boleh hilang hanya karena fotonya bermasalah."""
    _masuk(client, dunia["izul"])
    rusak = SimpleUploadedFile("rusak.jpg", b"bukan gambar", content_type="image/jpeg")
    resp = _kirim(client, foto=rusak)
    assert LaporanKegiatan.objects.count() == 1
    assert "tetapi fotonya tidak" in resp.content.decode()


def test_foto_tidak_wajib(client, dunia):
    _masuk(client, dunia["izul"])
    _kirim(client)
    assert LaporanKegiatan.objects.count() == 1
    assert not Attachment.objects.filter(entity_type="laporan_kegiatan").exists()


# --- masa simpan 90 hari --------------------------------------------------------------


def _laporan_lama(user, hari: int, dengan_foto=True):
    l = LaporanKegiatan.objects.create(user=user, uraian=f"kegiatan {hari} hari lalu")
    LaporanKegiatan.objects.filter(pk=l.pk).update(
        created_at=timezone.now() - dt.timedelta(days=hari)
    )
    if dengan_foto:
        Attachment.objects.create(
            entity_type="laporan_kegiatan", entity_id=l.pk, original_name="foto.jpg",
            mime_type="image/jpeg", size_bytes=10, sensitive=True, uploaded_by=user,
            file=SimpleUploadedFile("foto.jpg", b"x" * 10),
        )
    return l


def test_foto_lewat_90_hari_dihapus_uraiannya_tetap(dunia):
    lama = _laporan_lama(dunia["izul"], 100)
    call_command("hapus_foto_kegiatan")
    assert not Attachment.objects.filter(entity_type="laporan_kegiatan", entity_id=lama.pk).exists()
    lama.refresh_from_db()
    assert lama.uraian == "kegiatan 100 hari lalu", "uraian ikut hilang"
    assert lama.foto_dihapus_pada is not None


def test_foto_belum_90_hari_tidak_disentuh(dunia):
    baru = _laporan_lama(dunia["izul"], 80)
    call_command("hapus_foto_kegiatan")
    assert Attachment.objects.filter(entity_type="laporan_kegiatan", entity_id=baru.pk).exists()
    baru.refresh_from_db()
    assert baru.foto_dihapus_pada is None


def test_dry_run_tidak_menghapus_apa_pun(dunia):
    lama = _laporan_lama(dunia["izul"], 100)
    call_command("hapus_foto_kegiatan", "--dry-run")
    assert Attachment.objects.filter(entity_type="laporan_kegiatan", entity_id=lama.pk).exists()
    lama.refresh_from_db()
    assert lama.foto_dihapus_pada is None


def test_aman_dijalankan_ulang(dunia):
    _laporan_lama(dunia["izul"], 100)
    call_command("hapus_foto_kegiatan")
    call_command("hapus_foto_kegiatan")
    assert not Attachment.objects.filter(entity_type="laporan_kegiatan").exists()


def test_halaman_menyebut_foto_sudah_lewat_masa_simpan(client, dunia):
    lama = _laporan_lama(dunia["izul"], 100)
    call_command("hapus_foto_kegiatan")
    _masuk(client, dunia["izul"])
    body = client.get(reverse("reports:kegiatan_detail", args=[lama.pk])).content.decode()
    assert "Foto sudah dihapus" in body, "'tidak ada foto' tidak boleh sama dengan 'sudah lewat masa simpan'"


# --- menu ------------------------------------------------------------------------------


def test_menu_teknisi_memuat_lapor_kegiatan(client, dunia):
    _masuk(client, dunia["izul"])
    body = client.get(reverse("core:today")).content.decode()
    assert f'href="{reverse("reports:kegiatan")}"' in body
