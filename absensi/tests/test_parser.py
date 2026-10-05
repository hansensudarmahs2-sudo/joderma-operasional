"""Parser ekspor mesin sidik jari: bentuk blok, jam lewat tengah malam, sel berisi teks."""
from __future__ import annotations

import datetime as dt

import pytest

from absensi import parser

from .pabrik_xlsx import bangun

JUDUL = "Kartu Laporan 1 - 30 September 2026"


def _berkas(**ubah):
    blok = [
        {
            "uid": "17",
            "label": "Elvira",
            "hari": [
                (1, ["14:02", "22:05"], []),
                (2, [], ["Absen"]),
                (3, ["13:30", "00:28"], []),
                (4, ["21:02"], []),
                (5, [], ["BLOK F"]),
            ],
        },
        {"uid": "8", "label": "Luki", "hari": [(1, ["13:51", "22:05"], [])]},
    ]
    blok[0].update(ubah)
    return bangun(JUDUL, blok)


def test_periode_dan_jumlah_blok():
    hasil = parser.baca(_berkas())
    assert hasil.mulai == dt.date(2026, 9, 1)
    assert hasil.selesai == dt.date(2026, 9, 30)
    assert [k.device_uid for k in hasil.kartu] == ["17", "8"]
    assert hasil.kartu[0].device_label == "Elvira"
    assert hasil.checksum


def test_jam_dikumpulkan_lintas_kolom_dan_diurutkan():
    """Jam pulang ditulis mesin di kolom 'Masuk' timezone berikutnya, bukan kolom 'Keluar'."""
    hari = parser.baca(_berkas()).kartu[0].hari
    assert hari[0].jam == [dt.time(14, 2), dt.time(22, 5)]


def test_kolom_menit_lembur_hitungan_tangan_diabaikan():
    """Angka di kolom Lembur adalah hitungan manual, bukan jam; tidak boleh jadi penanda."""
    hari = parser.baca(_berkas()).kartu[0].hari
    assert hari[0].penanda == []


def test_absen_dikenali_sebagai_libur():
    hari = {h.tanggal.day: h for h in parser.baca(_berkas()).kartu[0].hari}
    assert hari[2].libur is True
    assert hari[2].jam == []
    assert hari[1].libur is False


def test_jam_lewat_tengah_malam_tetap_di_baris_tanggal_shift():
    """00.28 adalah cap pulang shift tanggal 3; parser tidak memindahkannya ke tanggal 4."""
    hari = {h.tanggal.day: h for h in parser.baca(_berkas()).kartu[0].hari}
    assert hari[3].jam == [dt.time(0, 28), dt.time(13, 30)]


def test_teks_lokasi_lain_dikembalikan_sebagai_penanda():
    hari = {h.tanggal.day: h for h in parser.baca(_berkas()).kartu[0].hari}
    assert hari[5].penanda == ["BLOK F"]
    assert hari[5].libur is False


def test_cap_tunggal_tetap_dibaca():
    hari = {h.tanggal.day: h for h in parser.baca(_berkas()).kartu[0].hari}
    assert hari[4].jam == [dt.time(21, 2)]


def test_blok_terakhir_tidak_menelan_kolom_di_kanannya():
    """Tabel skor manual di kanan blok terakhir tidak boleh terbaca sebagai penanda."""
    data = bangun(
        JUDUL,
        [
            {"uid": "17", "label": "Elvira", "hari": [(1, ["14:02", "22:05"], [])]},
            {"uid": "8", "label": "Luki", "hari": [(1, ["13:51", "22:05"], [])]},
        ],
    )
    # Sisipkan kolom tambahan jauh di kanan, seperti tabel skor pada berkas asli.
    import io
    import zipfile

    buf = io.BytesIO()
    lama = zipfile.ZipFile(io.BytesIO(data))
    with zipfile.ZipFile(buf, "w") as baru:
        for item in lama.namelist():
            isi = lama.read(item).decode()
            if item.endswith("sheet1.xml"):
                isi = isi.replace(
                    '<row r="12">', '<row r="12"><c r="BJ12" t="inlineStr"><is><t>Rahayu</t></is></c>'
                )
            baru.writestr(item, isi)
    hasil = parser.baca(buf.getvalue())
    assert hasil.kartu[1].hari[0].penanda == []


@pytest.mark.parametrize(
    "data, pesan",
    [
        (b"bukan zip", "bukan .xlsx"),
        (bangun("Laporan tanpa periode", [{"uid": "1", "label": "X", "hari": []}]), "periode"),
    ],
)
def test_berkas_tidak_dikenali_ditolak_dengan_pesan_jelas(data, pesan):
    with pytest.raises(parser.FileTidakDikenal, match=pesan):
        parser.baca(data)


def test_periode_lintas_bulan():
    """Mesin juga bisa mengekspor rentang yang melewati pergantian bulan."""
    hasil = parser.baca(
        bangun(
            "Kartu Laporan 30 - 29 September 2026",
            [{"uid": "1", "label": "X", "hari": [(30, ["14:00"], []), (1, ["14:00"], [])]}],
        )
    )
    assert [h.tanggal for h in hasil.kartu[0].hari] == [dt.date(2026, 9, 30), dt.date(2026, 10, 1)]
