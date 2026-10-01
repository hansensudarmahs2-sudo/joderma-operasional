"""Pembaca ekspor .xls Omnicare (LokaDok).

Aturan (lihat PRD bagian Impor):
- File .xls lama; `xlrd` menolaknya kecuali ``ignore_workbook_corruption=True``.
- Jenis file dikenali dari judul di sel A1, bukan dari nama file.
- Kolom dibaca menurut posisi, bukan label (header pergerakan memuat salah ketik "DJIUAL").
- Angka dibulatkan 2 desimal karena file memuat sisa pecahan (mis. 7,499994).
"""
from __future__ import annotations

import datetime as dt
import io
import re
from dataclasses import dataclass, field

import xlrd

from .models import JenisFile

BULAN = {
    "JANUARI": 1, "FEBRUARI": 2, "MARET": 3, "APRIL": 4, "MEI": 5, "JUNI": 6, "JULI": 7,
    "AGUSTUS": 8, "SEPTEMBER": 9, "OKTOBER": 10, "NOVEMBER": 11, "DESEMBER": 12,
}
KODE_CABANG = {"30376": "jemur", "31281": "citra"}

_TANGGAL = r"(\d{1,2})\s+([A-Z]+)\s+(\d{4})"


class FileTidakDikenal(ValueError):
    pass


def kunci(nama: str, dosis: str = "") -> str:
    """Kunci pencocokan: huruf kecil tanpa spasi, nama + dosis bila dosis diisi."""
    dosis = (dosis or "").strip()
    if dosis in {"-", "~"}:
        dosis = ""
    return re.sub(r"\s+", "", f"{nama}{dosis}").lower()


def angka(value) -> float:
    if isinstance(value, (int, float)):
        return round(float(value), 2) + 0.0  # + 0.0 membuang -0.0
    try:
        return round(float(str(value).replace(",", ".")), 2) + 0.0
    except ValueError:
        return 0.0


def _teks(value) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _tanggal(teks: str) -> dt.date | None:
    m = re.search(_TANGGAL, teks.upper())
    if not m or m.group(2) not in BULAN:
        return None
    return dt.date(int(m.group(3)), BULAN[m.group(2)], int(m.group(1)))


@dataclass
class HasilBaca:
    jenis: str
    judul: str
    baris: list[dict] = field(default_factory=list)
    tanggal: dt.date | None = None  # tingkat persediaan
    tahun: int | None = None  # pergerakan
    bulan: int | None = None
    petunjuk_cabang: str = ""  # "jemur"/"citra" dari judul atau nama file


def _sheet(data: bytes):
    book = xlrd.open_workbook(
        file_contents=data, ignore_workbook_corruption=True, logfile=io.StringIO()
    )
    return book.sheet_by_index(0)


def petunjuk_dari_nama_file(nama_file: str) -> str:
    for kode, cabang in KODE_CABANG.items():
        if kode in nama_file:
            return cabang
    return ""


def baca(data: bytes, nama_file: str = "") -> HasilBaca:
    try:
        sheet = _sheet(data)
    except Exception as exc:  # xlrd melempar beragam jenis error untuk file rusak
        raise FileTidakDikenal(f"File tidak bisa dibaca sebagai .xls Omnicare ({exc}).") from exc
    if sheet.nrows == 0:
        raise FileTidakDikenal("File kosong.")
    judul = _teks(sheet.cell_value(0, 0))
    atas = judul.upper()
    rows = [sheet.row_values(i) for i in range(sheet.nrows)]
    if atas.startswith("DAFTAR PRODUK"):
        return _daftar_produk(judul, rows)
    if atas.startswith("TINGKAT PERSEDIAAN"):
        return _tingkat_persediaan(judul, rows, nama_file)
    if atas.startswith("PERGERAKAN STOK"):
        return _pergerakan(judul, rows, nama_file)
    raise FileTidakDikenal(
        f"Judul \"{judul[:60]}\" bukan Daftar Produk, Tingkat Persediaan, atau Ringkasan Pergerakan Stok."
    )


def _daftar_produk(judul: str, rows: list[list]) -> HasilBaca:
    hasil = HasilBaca(JenisFile.DAFTAR_PRODUK, judul, tanggal=_tanggal(judul))
    for r in rows[4:]:
        if len(r) < 21 or not isinstance(r[0], float) or not _teks(r[4]):
            continue
        dosis = _teks(r[7])
        hasil.baris.append(
            {
                "omnicare_id": int(r[0]),
                "sediaan": _teks(r[3]),
                "nama": _teks(r[4]),
                "generik": "" if _teks(r[5]) == "-" else _teks(r[5]),
                "pabrikan": "" if _teks(r[6]) == "-" else _teks(r[6]),
                "dosis": "" if dosis == "-" else dosis,
                "kategori": "" if _teks(r[9]) == "-" else _teks(r[9]),
                "harga_modal": angka(r[10]),
                "harga_jual": angka(r[12]),
                "non_stok": _teks(r[14]) == "~",
                "satuan": "" if _teks(r[15]) in {"~", "-"} else _teks(r[15]),
                "min_omnicare": angka(r[19]),
                "max_omnicare": angka(r[20]),
                "aktif": _teks(r[22]).lower() != "nonaktif" if len(r) > 22 else True,
                "kunci": kunci(_teks(r[4]), dosis),
            }
        )
    return hasil


def _tingkat_persediaan(judul: str, rows: list[list], nama_file: str) -> HasilBaca:
    atas = judul.upper()
    petunjuk = "jemur" if "JEMUR" in atas else "citra" if "CITRA" in atas else petunjuk_dari_nama_file(nama_file)
    hasil = HasilBaca(JenisFile.TINGKAT_PERSEDIAAN, judul, tanggal=_tanggal(judul), petunjuk_cabang=petunjuk)
    for r in rows[3:]:
        if len(r) < 9 or not _teks(r[2]) or not _teks(r[0]):
            continue  # baris TOTAL tidak punya kolom TIPE
        hasil.baris.append({"nama": _teks(r[2]), "kunci": kunci(_teks(r[2])), "stok": angka(r[6]), "nilai_modal": angka(r[8])})
    return hasil


KOLOM_PERGERAKAN = [
    "stok_awal", "diterima", "dijual", "dipakai", "fabrikasi", "retur_jual",
    "retur_beli", "rusak", "mutasi", "penyesuaian", "gabung", "stok_akhir",
]


def _pergerakan(judul: str, rows: list[list], nama_file: str) -> HasilBaca:
    tanggal = re.findall(_TANGGAL, judul.upper())
    if len(tanggal) != 2:
        raise FileTidakDikenal("Periode laporan pergerakan tidak terbaca dari judul.")
    (d1, m1, y1), (d2, m2, y2) = tanggal
    awal = dt.date(int(y1), BULAN[m1], int(d1))
    akhir = dt.date(int(y2), BULAN[m2], int(d2))
    besok = akhir + dt.timedelta(days=1)
    if awal.day != 1 or (awal.year, awal.month) != (akhir.year, akhir.month) or besok.month == akhir.month:
        raise FileTidakDikenal(
            f"Laporan pergerakan harus satu bulan penuh (tanggal 1 sampai akhir bulan); file ini {awal:%d/%m/%Y} s/d {akhir:%d/%m/%Y}."
        )
    hasil = HasilBaca(
        JenisFile.PERGERAKAN, judul, tahun=awal.year, bulan=awal.month,
        petunjuk_cabang=petunjuk_dari_nama_file(nama_file),
    )
    for r in rows[4:]:
        if len(r) < 18 or not _teks(r[2]):
            continue
        baris = {"nama": _teks(r[2]), "kunci": kunci(_teks(r[2]))}
        for i, nama in enumerate(KOLOM_PERGERAKAN):
            baris[nama] = angka(r[6 + i])
        hasil.baris.append(baris)
    return hasil
