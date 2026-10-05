"""Pembaca ekspor .xlsx mesin sidik jari ("Kartu Laporan").

Bentuk berkasnya tidak biasa, jadi aturan bacanya ditulis di sini:

- Satu sheet memuat banyak staf dalam grid 4 blok melintang. Blok dikenali dari sel
  "Minggu Tgl"; batas kanan satu blok adalah kolom "Minggu Tgl" blok berikutnya.
- Nama dan ID dibaca dari label "Nama"/"ID" di dalam blok, bukan dari posisi tetap,
  karena lebar blok berubah antar ekspor.
- Jam pulang tidak selalu berada di kolom berlabel "Keluar": mesin kerap menaruhnya
  di kolom "Masuk" milik timezone berikutnya. Karena itu semua sel berisi pola jam
  dalam satu baris dikumpulkan lalu diurutkan, bukan dibaca per kolom.
- Sel bisa berisi teks, bukan jam: "Absen" (libur terjadwal), atau nama tempat seperti
  "Citraland"/"BLOK F" (bertugas di tempat lain). Teks semacam itu dikembalikan apa
  adanya sebagai penanda, tidak dibuang diam-diam.
- Jam dikembalikan sebagai jam dinding mentah. Penentuan tanggal sebenarnya untuk cap
  lewat tengah malam dilakukan di `services`, yang tahu batas dini hari cabang.

Berkas dibaca dengan zipfile + ElementTree dari pustaka standar; .xlsx adalah zip
berisi XML. `xlrd` di requirements hanya membaca .xls lama (dipakai modul stok) dan
tidak bisa membuka berkas ini.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

BULAN = {
    "JANUARI": 1, "JANUARY": 1, "FEBRUARI": 2, "FEBRUARY": 2, "MARET": 3, "MARCH": 3,
    "APRIL": 4, "MEI": 5, "MAY": 5, "JUNI": 6, "JUNE": 6, "JULI": 7, "JULY": 7,
    "AGUSTUS": 8, "AUGUST": 8, "SEPTEMBER": 9, "OKTOBER": 10, "OCTOBER": 10,
    "NOVEMBER": 11, "DESEMBER": 12, "DECEMBER": 12,
}

_JAM = re.compile(r"^(\d{1,2}):(\d{2})$")
_HARI = re.compile(r"^(\d{1,2})\s+\S+$")
_PERIODE = re.compile(r"(\d{1,2})\s*[-~]\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})")

LABEL_ABSEN = "absen"


class FileTidakDikenal(ValueError):
    """Berkas bukan ekspor Kartu Laporan yang dikenali."""


@dataclass
class BarisHarian:
    tanggal: dt.date
    jam: list[dt.time] = field(default_factory=list)
    penanda: list[str] = field(default_factory=list)
    baris_sumber: int = 0

    @property
    def libur(self) -> bool:
        return any(p.strip().lower() == LABEL_ABSEN for p in self.penanda)


@dataclass
class KartuStaf:
    device_uid: str
    device_label: str
    hari: list[BarisHarian] = field(default_factory=list)


@dataclass
class HasilBaca:
    mulai: dt.date | None = None
    selesai: dt.date | None = None
    kartu: list[KartuStaf] = field(default_factory=list)
    peringatan: list[str] = field(default_factory=list)
    checksum: str = ""


def _kolom(ref: str) -> int:
    n = 0
    for ch in re.match(r"([A-Z]+)", ref).group(1):
        n = n * 26 + ord(ch) - 64
    return n


def _sel(data: bytes) -> dict[tuple[int, int], str]:
    """Isi sheet pertama sebagai {(baris, kolom): teks}. Sel kosong tidak dimasukkan."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise FileTidakDikenal("Berkas bukan .xlsx yang sah.") from exc

    nama_sheet = next((n for n in zf.namelist() if n.startswith("xl/worksheets/sheet")), None)
    if nama_sheet is None:
        raise FileTidakDikenal("Berkas .xlsx tidak memuat sheet.")

    teks_bersama: list[str] = []
    if "xl/sharedStrings.xml" in zf.namelist():
        akar = ET.fromstring(zf.read("xl/sharedStrings.xml"))
        teks_bersama = ["".join(t.text or "" for t in si.iter(NS + "t")) for si in akar]

    hasil: dict[tuple[int, int], str] = {}
    for baris in ET.fromstring(zf.read(nama_sheet)).iter(NS + "row"):
        r = int(baris.get("r"))
        for c in baris.iter(NS + "c"):
            tipe = c.get("t")
            nilai = c.find(NS + "v")
            if tipe == "s" and nilai is not None:
                teks = teks_bersama[int(nilai.text)]
            elif tipe == "inlineStr":
                simpul = c.find(NS + "is")
                teks = "".join(t.text or "" for t in simpul.iter(NS + "t")) if simpul is not None else ""
            elif nilai is not None:
                teks = nilai.text or ""
            else:
                continue
            teks = teks.strip()
            if teks:
                hasil[(r, _kolom(c.get("r")))] = teks
    return hasil


def _nilai_setelah(sel: dict, baris: int, kolom: int, batas_kanan: int) -> str:
    """Isi sel tak kosong pertama di kanan (label dan nilainya terpisah sel kosong)."""
    for k in range(kolom + 1, batas_kanan + 1):
        if (baris, k) in sel:
            return sel[(baris, k)]
    return ""


def _periode(sel: dict) -> tuple[dt.date | None, dt.date | None]:
    for (baris, _), teks in sorted(sel.items())[:40]:
        if baris > 3:
            break
        m = _PERIODE.search(teks)
        if m and m.group(3).upper() in BULAN:
            bulan, tahun = BULAN[m.group(3).upper()], int(m.group(4))
            return dt.date(tahun, bulan, int(m.group(1))), dt.date(tahun, bulan, int(m.group(2)))
    return None, None


def baca(data: bytes, nama_file: str = "") -> HasilBaca:
    """Baca satu berkas ekspor. Melempar `FileTidakDikenal` bila bentuknya tak cocok."""
    sel = _sel(data)
    hasil = HasilBaca(checksum=hashlib.sha256(data).hexdigest())
    hasil.mulai, hasil.selesai = _periode(sel)
    if hasil.mulai is None:
        raise FileTidakDikenal(
            "Judul berkas tidak memuat periode seperti 'Kartu Laporan 1 - 30 September 2026'."
        )

    jangkar = sorted(rc for rc, teks in sel.items() if teks.lower().startswith("minggu tgl"))
    if not jangkar:
        raise FileTidakDikenal("Tidak ada sel 'Minggu Tgl'; berkas bukan Kartu Laporan.")
    kolom_maks = max(k for _, k in sel)

    pita: dict[int, list[int]] = {}
    for baris, kolom in jangkar:
        pita.setdefault(baris, []).append(kolom)

    for baris_jangkar, kolom_kolom in sorted(pita.items()):
        kolom_kolom.sort()
        # Blok terakhir di satu pita tidak punya tetangga kanan sebagai pembatas. Memakai
        # kolom terjauh sheet membuatnya menelan tabel skor manual di sebelah kanan, jadi
        # lebarnya disamakan dengan blok tersempit di pita yang sama.
        lebar = min(
            (b - a for a, b in zip(kolom_kolom, kolom_kolom[1:])),
            default=kolom_maks - kolom_kolom[-1] + 1,
        )
        for i, kiri in enumerate(kolom_kolom):
            kanan = kolom_kolom[i + 1] - 1 if i + 1 < len(kolom_kolom) else min(kolom_maks, kiri + lebar - 1)
            kartu = _baca_blok(sel, baris_jangkar, kiri, kanan, hasil)
            if kartu is not None:
                hasil.kartu.append(kartu)

    if not hasil.kartu:
        raise FileTidakDikenal("Tidak ada blok staf yang terbaca.")
    return hasil


def _baca_blok(sel: dict, baris_jangkar: int, kiri: int, kanan: int, hasil: HasilBaca) -> KartuStaf | None:
    nama = uid = ""
    for baris in range(max(1, baris_jangkar - 12), baris_jangkar):
        for kolom in range(kiri, kanan + 1):
            teks = sel.get((baris, kolom), "").strip().lower()
            if teks == "nama":
                nama = _nilai_setelah(sel, baris, kolom, kanan)
            elif teks == "id":
                uid = _nilai_setelah(sel, baris, kolom, kanan)
    if not uid:
        hasil.peringatan.append(f"Blok pada baris {baris_jangkar} kolom {kiri} tidak punya ID; dilewati.")
        return None

    kartu = KartuStaf(device_uid=uid, device_label=nama)
    # Baris tanggal mulai dua baris di bawah "Minggu Tgl" (di antaranya sub-header Masuk/Keluar).
    baris = baris_jangkar + 2
    while True:
        m = _HARI.match(sel.get((baris, kiri), ""))
        if not m:
            break
        harian = BarisHarian(tanggal=_tanggal(hasil, int(m.group(1))), baris_sumber=baris)
        for kolom in range(kiri + 1, kanan + 1):
            teks = sel.get((baris, kolom))
            if not teks:
                continue
            jam = _JAM.match(teks)
            if jam:
                j, mnt = int(jam.group(1)), int(jam.group(2))
                if j > 23 or mnt > 59:
                    hasil.peringatan.append(f"ID {uid} baris {baris}: jam '{teks}' tidak sah, dilewati.")
                    continue
                harian.jam.append(dt.time(j, mnt))
            elif not _angka(teks):
                harian.penanda.append(teks)
        harian.jam.sort()
        kartu.hari.append(harian)
        baris += 1
    return kartu


def _tanggal(hasil: HasilBaca, hari: int) -> dt.date:
    """Nomor hari di kolom tanggal menjadi tanggal penuh.

    Periode biasanya satu bulan penuh, tetapi mesin juga bisa mengekspor rentang yang
    melintasi bulan (mis. 30 September ~ 29 Oktober). Nomor hari yang lebih kecil dari
    hari awal periode berarti sudah masuk bulan berikutnya.
    """
    mulai = hasil.mulai
    if hari >= mulai.day:
        return dt.date(mulai.year, mulai.month, hari)
    bulan = mulai.month % 12 + 1
    tahun = mulai.year + (1 if bulan == 1 else 0)
    return dt.date(tahun, bulan, hari)


def _angka(teks: str) -> bool:
    """Kolom 'Lembur' ekspor berisi angka menit hitungan tangan; bukan penanda."""
    try:
        float(teks.replace(",", "."))
    except ValueError:
        return False
    return True
