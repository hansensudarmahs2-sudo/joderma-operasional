"""Membuat berkas .xlsx tiruan berbentuk "Kartu Laporan" untuk test.

Dibuat sintetis, bukan menyalin ekspor asli, supaya tidak ada jam kerja staf nyata di
dalam repository. Bentuknya mengikuti ciri yang membuat parser ini perlu ada:
blok-blok melintang, label "Nama"/"ID" terpisah dari nilainya, jam pulang yang jatuh
di kolom "Masuk" timezone berikutnya, serta kolom angka menit hitungan tangan.
"""
from __future__ import annotations

import io
import zipfile

NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'


def _huruf(n: int) -> str:
    s = ""
    while n:
        n, sisa = divmod(n - 1, 26)
        s = chr(65 + sisa) + s
    return s


def bangun(judul: str, blok: list[dict], *, kolom_blok=(1, 16)) -> bytes:
    """`blok`: [{"uid", "label", "hari": [(nomor_hari, [jam...], [penanda...])]}]."""
    sel: dict[tuple[int, int], str] = {(1, 1): judul}
    for ke, (kiri, isi) in enumerate(zip(kolom_blok, blok)):
        sel[(3, kiri + 8)] = "Nama"
        sel[(3, kiri + 9)] = isi["label"]
        sel[(4, kiri + 8)] = "ID"
        sel[(4, kiri + 9)] = isi["uid"]
        sel[(10, kiri)] = "Minggu Tgl"
        sel[(11, kiri + 1)] = "Masuk"
        sel[(11, kiri + 3)] = "Keluar"
        for urut, (hari, jam, penanda) in enumerate(isi["hari"]):
            baris = 12 + urut
            sel[(baris, kiri)] = f"{hari:02d} SEL"
            # Jam masuk di kolom Timezone I, jam pulang di kolom "Masuk" Timezone II:
            # justru begitulah mesin menulisnya.
            for i, j in enumerate(jam):
                sel[(baris, kiri + 1 + i * 5)] = j
            for i, p in enumerate(penanda):
                sel[(baris, kiri + 1 + i)] = p
            # Kolom menit lembur hitungan tangan; parser harus mengabaikannya.
            sel[(baris, kiri + 10)] = "0"
            sel[(baris, kiri + 12)] = "45"

    unik: list[str] = []
    indeks: dict[str, int] = {}
    for teks in sel.values():
        if teks not in indeks:
            indeks[teks] = len(unik)
            unik.append(teks)

    baris_xml = []
    for r in sorted({r for r, _ in sel}):
        sel_xml = "".join(
            f'<c r="{_huruf(c)}{r}" t="s"><v>{indeks[sel[(r, c)]]}</v></c>'
            for c in sorted(c for rr, c in sel if rr == r)
        )
        baris_xml.append(f'<row r="{r}">{sel_xml}</row>')

    sheet = f'<?xml version="1.0"?><worksheet {NS}><sheetData>{"".join(baris_xml)}</sheetData></worksheet>'
    shared = (
        f'<?xml version="1.0"?><sst {NS} count="{len(unik)}" uniqueCount="{len(unik)}">'
        + "".join(f"<si><t>{t}</t></si>" for t in unik)
        + "</sst>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("xl/worksheets/sheet1.xml", sheet)
        zf.writestr("xl/sharedStrings.xml", shared)
    return buf.getvalue()
