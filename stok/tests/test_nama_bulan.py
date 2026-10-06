"""6 Okt 2026: judul ekspor Omnicare memakai nama bulan Indonesia, Inggris, atau singkatan."""
from __future__ import annotations

import datetime as dt

import pytest

from stok.parser import FileTidakDikenal, _pergerakan, _tanggal


@pytest.mark.parametrize("judul, tanggal", [
    ("DAFTAR PRODUK 05 OKTOBER 2026 / BAGIAN: 1", dt.date(2026, 10, 5)),
    ("PENJUALAN PRODUK PER 01 OCTOBER 2026 S/D 01 OCTOBER 2026", dt.date(2026, 10, 1)),
    ("PENJUALAN FARMASI PER 01 SEP 2026 S/D 30 SEP 2026", dt.date(2026, 9, 1)),
    ("Tingkat Persediaan per 17 Agustus 2026", dt.date(2026, 8, 17)),
    ("PER 3 MEI 2026", dt.date(2026, 5, 3)),
    ("PER 3 MAY 2026", dt.date(2026, 5, 3)),
    ("PER 24 DES 2026", dt.date(2026, 12, 24)),
    ("PER 24 DECEMBER 2026", dt.date(2026, 12, 24)),
])
def test_month_names_in_any_language(judul, tanggal):
    assert _tanggal(judul) == tanggal


def test_unknown_month_in_movement_title_is_a_clear_error():
    with pytest.raises(FileTidakDikenal, match="Nama bulan"):
        _pergerakan("PERGERAKAN STOK 01 FOO 2026 S/D 30 FOO 2026", [], "x.xls")
