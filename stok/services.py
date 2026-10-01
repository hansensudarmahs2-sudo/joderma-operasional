"""Impor ekspor Omnicare, penggabungan unduhan, dan uji kelengkapan periode.

Penggabungan: setiap unduhan laporan pergerakan bisa kehilangan blok 50 baris. Beberapa
unggahan untuk cabang dan periode yang sama digabung per produk; bila satu produk ada di
dua unggahan, unggahan terbaru yang dipakai (`update` menimpa baris lama).

Uji kelengkapan per cabang per bulan (PRD, dengan penegasan dari audit 30 Sep 2026):
1. Seimbang: stok awal + semua pergerakan = stok akhir, untuk setiap baris.
2. Sambung: stok awal bulan ini = stok akhir terakhir yang diketahui untuk produk itu.
   Laporan pergerakan hanya memuat produk yang bergerak, jadi produk yang absen di suatu
   bulan dianggap tidak bergerak selama stoknya menyambung. Bila putus, bulan-bulan di
   antaranya berstatus Belum lengkap dan produk itu masuk daftar diduga hilang.
3. Cocok dengan Tingkat Persediaan pada hari terakhir bulan. Produk yang ada di laporan
   pergerakan tetapi angkanya beda hanya dicatat sebagai selisih (transaksi di antara dua
   waktu unduh). Produk yang absen dari laporan pergerakan padahal stoknya berubah
   dianggap hilang.
4. Mutasi antarcabang saling menutup per produk per bulan.
"""
from __future__ import annotations

import calendar
import datetime as dt
from collections import defaultdict

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction

from core.models import Clinic

from . import parser
from .models import (
    JenisFile,
    PergerakanBulanan,
    PosisiStok,
    Produk,
    ProdukAlias,
    StatusPeriode,
    Unggahan,
)

TOL = 0.01
KOLOM = parser.KOLOM_PERGERAKAN
GERAK = [k for k in KOLOM if k not in {"stok_awal", "stok_akhir"}]


# --- Cabang ---------------------------------------------------------------

def tebak_cabang(petunjuk: str) -> Clinic | None:
    if not petunjuk:
        return None
    kandidat = [c for c in Clinic.objects.filter(active=True) if petunjuk in c.name.lower()]
    return kandidat[0] if len(kandidat) == 1 else None


# --- Impor ----------------------------------------------------------------

def impor(data: bytes, nama_file: str, user, clinic: Clinic | None = None) -> Unggahan:
    try:
        hasil = parser.baca(data, nama_file)
    except parser.FileTidakDikenal as exc:
        raise ValidationError(str(exc)) from exc
    return impor_hasil(hasil, data, nama_file, user, clinic)


@transaction.atomic
def impor_hasil(hasil: parser.HasilBaca, data: bytes, nama_file: str, user, clinic: Clinic | None = None) -> Unggahan:
    peringatan: list[str] = []
    if hasil.jenis != JenisFile.DAFTAR_PRODUK:
        tebakan = tebak_cabang(hasil.petunjuk_cabang)
        if clinic is None:
            clinic = tebakan
        elif tebakan and tebakan != clinic:
            peringatan.append(f"Judul/nama file menunjuk {tebakan.name}, tetapi diunggah untuk {clinic.name}.")
        if clinic is None:
            raise ValidationError("Cabang tidak bisa ditebak dari file. Pilih cabangnya di formulir unggah.")
        if not Produk.objects.exists():
            raise ValidationError("Unggah Daftar Produk lebih dulu; laporan ini dicocokkan ke daftar itu.")
    if hasil.jenis == JenisFile.TINGKAT_PERSEDIAAN and not hasil.tanggal:
        raise ValidationError("Tanggal tidak terbaca dari judul Tingkat Persediaan.")

    unggahan = Unggahan.objects.create(
        jenis=hasil.jenis, clinic=clinic, tahun=hasil.tahun, bulan=hasil.bulan,
        tanggal=hasil.tanggal, judul=hasil.judul[:200], nama_file=nama_file[:255],
        jumlah_baris=len(hasil.baris), diunggah_oleh=user,
    )
    unggahan.file.save(nama_file, ContentFile(data), save=False)

    if hasil.jenis == JenisFile.DAFTAR_PRODUK:
        cocok = _simpan_produk(hasil.baris, peringatan)
    elif hasil.jenis == JenisFile.TINGKAT_PERSEDIAAN:
        cocok = _simpan_posisi(hasil, clinic, unggahan, peringatan)
    else:
        cocok = _simpan_pergerakan(hasil, clinic, unggahan, peringatan)

    unggahan.jumlah_cocok = cocok
    unggahan.peringatan = peringatan
    unggahan.save()
    if hasil.jenis != JenisFile.DAFTAR_PRODUK:
        perbarui_status_periode()
    return unggahan


def _simpan_produk(baris: list[dict], peringatan: list[str]) -> int:
    ada = {p.omnicare_id: p for p in Produk.objects.all()}
    pemilik_kunci = {p.kunci: p.omnicare_id for p in ada.values()}
    fields = [k for k in baris[0] if k != "omnicare_id"] if baris else []
    for b in baris:
        lain = pemilik_kunci.get(b["kunci"])
        if lain is not None and lain != b["omnicare_id"]:
            peringatan.append(f"{b['nama']}: nama + dosis sama dengan produk ID {lain}; baris dilewati.")
            continue
        produk = ada.get(b["omnicare_id"])
        if produk is None:
            produk = Produk.objects.create(**b)
        else:
            if produk.kunci != b["kunci"]:
                ProdukAlias.objects.get_or_create(kunci=produk.kunci, defaults={"produk": produk})
                pemilik_kunci.pop(produk.kunci, None)
            for f in fields:
                setattr(produk, f, b[f])
            produk.save()
        pemilik_kunci[b["kunci"]] = b["omnicare_id"]
    return len(baris)


def peta_kunci() -> dict[str, int]:
    peta = dict(ProdukAlias.objects.values_list("kunci", "produk_id"))
    peta.update(Produk.objects.values_list("kunci", "id"))
    return peta


def _cocokkan(baris: list[dict], peringatan: list[str]) -> list[tuple[int, dict]]:
    peta = peta_kunci()
    hasil, tidak = [], []
    for b in baris:
        pid = peta.get(b["kunci"])
        if pid is None:
            tidak.append(b["nama"])
        else:
            hasil.append((pid, b))
    if tidak:
        peringatan.append(
            f"{len(tidak)} baris tidak cocok dengan Daftar Produk (unggah Daftar Produk terbaru): "
            + ", ".join(tidak[:20]) + (" …" if len(tidak) > 20 else "")
        )
    return hasil


def _simpan_posisi(hasil, clinic, unggahan, peringatan) -> int:
    cocok = _cocokkan(hasil.baris, peringatan)
    PosisiStok.objects.filter(clinic=clinic, tanggal=hasil.tanggal).delete()
    PosisiStok.objects.bulk_create(
        [
            PosisiStok(clinic=clinic, produk_id=pid, tanggal=hasil.tanggal, stok=b["stok"],
                       nilai_modal=b["nilai_modal"], unggahan=unggahan)
            for pid, b in cocok
        ]
    )
    return len(cocok)


def _simpan_pergerakan(hasil, clinic, unggahan, peringatan) -> int:
    cocok = _cocokkan(hasil.baris, peringatan)
    lama = {
        r.produk_id: r
        for r in PergerakanBulanan.objects.filter(clinic=clinic, tahun=hasil.tahun, bulan=hasil.bulan)
    }
    baru, ubah = [], []
    for pid, b in cocok:
        nilai = {k: b[k] for k in KOLOM}
        row = lama.get(pid)
        if row is None:
            baru.append(PergerakanBulanan(clinic=clinic, produk_id=pid, tahun=hasil.tahun,
                                          bulan=hasil.bulan, unggahan=unggahan, **nilai))
        else:
            for k, v in nilai.items():
                setattr(row, k, v)
            row.unggahan = unggahan
            ubah.append(row)
    PergerakanBulanan.objects.bulk_create(baru)
    if ubah:
        PergerakanBulanan.objects.bulk_update(ubah, KOLOM + ["unggahan"])
    if lama:
        peringatan.append(
            f"Digabung dengan unggahan sebelumnya untuk periode ini: {len(baru)} produk baru, {len(ubah)} diperbarui."
        )
    return len(cocok)


# --- Uji kelengkapan --------------------------------------------------------

def _hari_terakhir(tahun: int, bulan: int) -> dt.date:
    return dt.date(tahun, bulan, calendar.monthrange(tahun, bulan)[1])


def _nama(pid: int, nama: dict[int, str]) -> str:
    return nama.get(pid, str(pid))


def perbarui_status_periode() -> None:
    """Hitung ulang status semua periode untuk semua cabang (data kecil, cukup cepat)."""
    nama = {p.id: str(p) for p in Produk.objects.all()}
    data: dict[int, dict[tuple[int, int], dict[int, PergerakanBulanan]]] = defaultdict(lambda: defaultdict(dict))
    for r in PergerakanBulanan.objects.all():
        data[r.clinic_id][(r.tahun, r.bulan)][r.produk_id] = r

    per_periode: dict[tuple[int, tuple[int, int]], dict] = {}
    for cid, periode in data.items():
        urut = sorted(periode)
        for p in urut:
            per_periode[(cid, p)] = {"seimbang": [], "sambung": [], "persediaan": [], "mutasi": [],
                                     "hilang": set(), "selisih": []}
        # Uji 1: seimbang
        for p in urut:
            for pid, r in periode[p].items():
                total = r.stok_awal + sum(getattr(r, k) for k in GERAK)
                if abs(total - r.stok_akhir) > TOL:
                    per_periode[(cid, p)]["seimbang"].append(_nama(pid, nama))
        # Uji 2: sambung
        terakhir: dict[int, tuple[tuple[int, int], float]] = {}
        for idx, p in enumerate(urut):
            for pid, r in periode[p].items():
                if pid in terakhir:
                    p_lalu, akhir = terakhir[pid]
                    if abs(akhir - r.stok_awal) > TOL:
                        antara = [q for q in urut if p_lalu < q < p]
                        for q in antara or [p]:
                            per_periode[(cid, q)]["sambung"].append(_nama(pid, nama))
                            per_periode[(cid, q)]["hilang"].add(_nama(pid, nama))
                terakhir[pid] = (p, r.stok_akhir)
        # Uji 3: cocok dengan Tingkat Persediaan di hari terakhir bulan
        for p in urut:
            tgl = _hari_terakhir(*p)
            posisi = dict(PosisiStok.objects.filter(clinic_id=cid, tanggal=tgl).values_list("produk_id", "stok"))
            if not posisi:
                continue
            akhir_sampai_p: dict[int, float] = {}
            for q in urut:
                if q > p:
                    break
                for pid, r in periode[q].items():
                    akhir_sampai_p[pid] = r.stok_akhir
            for pid in set(posisi) | set(periode[p]):
                stok = posisi.get(pid, 0.0)
                if pid in periode[p]:
                    beda = periode[p][pid].stok_akhir - stok
                    if abs(beda) > TOL:
                        per_periode[(cid, p)]["selisih"].append(
                            {"produk": _nama(pid, nama), "pergerakan": periode[p][pid].stok_akhir, "persediaan": stok}
                        )
                elif pid in akhir_sampai_p and abs(akhir_sampai_p[pid] - stok) > TOL:
                    per_periode[(cid, p)]["persediaan"].append(_nama(pid, nama))
                    per_periode[(cid, p)]["hilang"].add(_nama(pid, nama))

    # Uji 4: mutasi saling menutup (lintas cabang, hanya periode yang diunggah semua cabang)
    semua_periode = {p for cid in data for p in data[cid]}
    for p in semua_periode:
        cabang = [cid for cid in data if p in data[cid]]
        if len(cabang) < 2:
            continue
        jumlah: dict[int, float] = defaultdict(float)
        punya: dict[int, set[int]] = defaultdict(set)
        for cid in cabang:
            for pid, r in data[cid][p].items():
                if abs(r.mutasi) > TOL:
                    jumlah[pid] += r.mutasi
                    punya[pid].add(cid)
        for pid, total in jumlah.items():
            if abs(total) <= TOL:
                continue
            kurang = [cid for cid in cabang if pid not in data[cid][p]]
            for cid in kurang or cabang:
                per_periode[(cid, p)]["mutasi"].append(_nama(pid, nama))
                if kurang:
                    per_periode[(cid, p)]["hilang"].add(_nama(pid, nama))

    ada = set()
    for (cid, (tahun, bulan)), h in per_periode.items():
        gagal = h["seimbang"] or h["sambung"] or h["persediaan"] or h["mutasi"]
        StatusPeriode.objects.update_or_create(
            clinic_id=cid, tahun=tahun, bulan=bulan,
            defaults={
                "lengkap": not gagal,
                "hasil": {k: sorted(h[k]) for k in ("seimbang", "sambung", "persediaan", "mutasi")},
                "diduga_hilang": sorted(h["hilang"]),
                "selisih_stok": sorted(h["selisih"], key=lambda x: x["produk"]),
                "jumlah_baris": len(data[cid][(tahun, bulan)]),
            },
        )
        ada.add((cid, tahun, bulan))
    for sp in StatusPeriode.objects.all():
        if (sp.clinic_id, sp.tahun, sp.bulan) not in ada:
            sp.delete()
