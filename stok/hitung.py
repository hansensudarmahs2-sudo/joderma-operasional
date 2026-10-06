"""Perhitungan status, buffer, moving, dan saran transfer (rumus = workbook Analisa Persediaan).

Dihitung saat halaman dibuka; sekitar 420 produk x 2 cabang.

Sumber stok per cabang: Tingkat Persediaan terbaru. Bila ada laporan pergerakan yang
periodenya berakhir di tanggal yang sama, stok akhir laporan pergerakan yang dipakai untuk
produk yang ada di laporan itu (laporan pergerakan biasanya diunduh belakangan dan memuat
transaksi terakhir hari itu). Ini aturan yang sama dengan workbook (16 produk Jemur 30 Sep).
"""
from __future__ import annotations

import calendar
import datetime as dt
import math
from collections import defaultdict
from dataclasses import dataclass, field

from core.models import Clinic

from .models import Parameter, PergerakanBulanan, PosisiStok, Produk, StatusPeriode

KOSONG = "Kosong"
DI_BAWAH = "Di bawah buffer"
MENDEKATI = "Mendekati buffer"
AMAN = "Aman"
TANPA_PAKAI = "Tanpa pemakaian"
URUT_STATUS = {KOSONG: 0, DI_BAWAH: 1, MENDEKATI: 2, AMAN: 3, TANPA_PAKAI: 4}
PERLU_ORDER = {KOSONG, DI_BAWAH, MENDEKATI}
NAMA_BULAN = ["", "Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def lantai_setengah(x: float) -> float:
    return math.floor(x * 2 + 1e-9) / 2


def label_periode(p: tuple[int, int]) -> str:
    return f"{NAMA_BULAN[p[1]]} {p[0]}"


@dataclass
class Baris:
    produk: Produk
    clinic: Clinic
    pakai: list[float]
    rata: float
    bulan_aktif: int
    stok: float
    buffer: float
    status: str
    moving: str
    bulan_stok: float | None
    kebutuhan: float
    kelebihan: float
    transfer_masuk: float = 0.0
    transfer_dari: list[tuple[Clinic, float]] = field(default_factory=list)

    @property
    def pakai_total(self) -> float:
        return sum(self.pakai)

    @property
    def sisa_order(self) -> float:
        return round(max(0.0, self.kebutuhan - self.transfer_masuk), 1)

    @property
    def tindakan(self) -> str:
        return "Produksi sendiri" if self.produk.produksi_sendiri else "Order distributor"


@dataclass
class Transfer:
    produk: Produk
    dari: Baris
    ke: Baris
    jumlah: float


@dataclass
class DataCabang:
    clinic: Clinic
    tanggal_stok: dt.date | None
    periode: list[tuple[int, int]]
    periode_belum_lengkap: list[tuple[int, int]]
    baris: dict[int, Baris]

    @property
    def label_periode(self) -> str:
        if not self.periode:
            return "belum ada periode lengkap"
        return f"{label_periode(self.periode[0])} s/d {label_periode(self.periode[-1])}"


@dataclass
class Hasil:
    parameter: Parameter
    cabang: list[DataCabang]
    transfer: list[Transfer]


def _stok_cabang(clinic: Clinic) -> tuple[dt.date | None, dict[int, float]]:
    tanggal = (
        PosisiStok.objects.filter(clinic=clinic).order_by("-tanggal").values_list("tanggal", flat=True).first()
    )
    if tanggal is None:
        return None, {}
    stok = dict(PosisiStok.objects.filter(clinic=clinic, tanggal=tanggal).values_list("produk_id", "stok"))
    if tanggal.day == calendar.monthrange(tanggal.year, tanggal.month)[1]:
        for pid, akhir in PergerakanBulanan.objects.filter(
            clinic=clinic, tahun=tanggal.year, bulan=tanggal.month
        ).values_list("produk_id", "stok_akhir"):
            stok[pid] = akhir
    return tanggal, stok


def _periode_cabang(clinic: Clinic, n: int, tanggal: dt.date | None):
    semua = list(StatusPeriode.objects.filter(clinic=clinic).order_by("tahun", "bulan"))
    if tanggal:
        semua = [s for s in semua if (s.tahun, s.bulan) <= (tanggal.year, tanggal.month)]
    lengkap = [(s.tahun, s.bulan) for s in semua if s.lengkap][-n:]
    belum = [(s.tahun, s.bulan) for s in semua if not s.lengkap and (not lengkap or (s.tahun, s.bulan) >= lengkap[0])]
    return lengkap, belum


def hitung(param: Parameter | None = None) -> Hasil:
    param = param or Parameter.aktif()
    produk = {p.id: p for p in Produk.objects.filter(non_stok=False)}
    cabang: list[DataCabang] = []
    for clinic in Clinic.objects.filter(active=True).order_by("name"):
        tanggal, stok = _stok_cabang(clinic)
        periode, belum = _periode_cabang(clinic, param.bulan_rata_rata, tanggal)
        if tanggal is None and not periode:
            continue
        pakai: dict[int, list[float]] = defaultdict(lambda: [0.0] * len(periode))
        indeks = {p: i for i, p in enumerate(periode)}
        if periode:
            for r in PergerakanBulanan.objects.filter(clinic=clinic, tahun__gte=periode[0][0]):
                i = indeks.get((r.tahun, r.bulan))
                if i is not None:
                    pakai[r.produk_id][i] = r.pemakaian
        baris = {}
        for pid, p in produk.items():
            daftar = pakai[pid] if periode else []
            s = stok.get(pid, 0.0)
            rata = max(0.0, sum(daftar) / len(daftar)) if daftar else 0.0
            aktif = sum(1 for x in daftar if x > 0)
            buffer = rata * param.bulan_buffer
            if rata <= 0:
                status = TANPA_PAKAI if s > 0 else ""
            elif s <= 0:
                status = KOSONG
            elif s < buffer:
                status = DI_BAWAH
            elif s <= buffer * (1 + param.ambang_mendekati):
                status = MENDEKATI
            else:
                status = AMAN
            if daftar and aktif == len(daftar):
                moving = "Fast"
            elif aktif > 0:
                moving = "Slow"
            elif s > 0:
                moving = "Diam"
            else:
                moving = ""
            kebutuhan = round(max(0.0, param.target_bulan * rata - s), 1) if status in PERLU_ORDER else 0.0
            kelebihan = round(max(0.0, s - param.cadangan_bulan * rata), 1)
            baris[pid] = Baris(
                produk=p, clinic=clinic, pakai=list(daftar), rata=rata, bulan_aktif=aktif, stok=s,
                buffer=buffer, status=status, moving=moving,
                bulan_stok=(s / rata) if rata > 0 else None, kebutuhan=kebutuhan, kelebihan=kelebihan,
            )
        cabang.append(DataCabang(clinic, tanggal, periode, belum, baris))

    transfer: list[Transfer] = []
    for pid, p in produk.items():
        sisa_lebih = {c.clinic.pk: c.baris[pid].kelebihan for c in cabang}
        penerima = sorted(
            (c.baris[pid] for c in cabang if c.baris[pid].kebutuhan > 0), key=lambda b: -b.kebutuhan
        )
        for ke in penerima:
            perlu = ke.kebutuhan
            for dari in sorted((c.baris[pid] for c in cabang if c.clinic != ke.clinic), key=lambda b: -b.kelebihan):
                jumlah = lantai_setengah(min(perlu, sisa_lebih[dari.clinic.pk]))
                if jumlah <= 0:
                    continue
                transfer.append(Transfer(p, dari, ke, jumlah))
                ke.transfer_masuk += jumlah
                ke.transfer_dari.append((dari.clinic, jumlah))
                sisa_lebih[dari.clinic.pk] = round(sisa_lebih[dari.clinic.pk] - jumlah, 1)
                perlu -= jumlah
                if perlu <= 0:
                    break
    # Urutan: penerima paling mendesak dulu (Kosong, lalu Di bawah, lalu Mendekati), lalu jumlah terbesar.
    transfer.sort(key=lambda t: (URUT_STATUS.get(t.ke.status, 9), -t.jumlah, t.produk.nama))
    return Hasil(param, cabang, transfer)


def prioritas(data: DataCabang) -> list[Baris]:
    rows = [b for b in data.baris.values() if b.status in URUT_STATUS and b.status != TANPA_PAKAI]
    return sorted(rows, key=lambda b: (URUT_STATUS[b.status], b.bulan_stok if b.bulan_stok is not None else 0, b.produk.nama))


def hitung_status(data: DataCabang) -> dict[str, int]:
    hasil = {k: 0 for k in URUT_STATUS}
    for b in data.baris.values():
        if b.status in hasil:
            hasil[b.status] += 1
    return hasil
