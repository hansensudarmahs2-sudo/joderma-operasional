"""Unduh CSV papan skor dan daftar "Perlu dicek" (Tahap 6).

Mengikuti pola unduh yang sudah ada di `direktur:kpi` dan `direktur:tasks`: satu
`HttpResponse` ber-BOM supaya Excel membaca UTF-8 dengan benar, nilai teks dilewatkan
`audit.views._cell` supaya sel yang diawali `=`, `+`, `-`, atau `@` tidak dijalankan
sebagai rumus, dan setiap unduhan tercatat di audit sebagai `AuditAction.EXPORT`.

Dua hal yang ditulis berbeda dari tampilan layar, dan keduanya disengaja.

**Yang "rekam saja" ikut diekspor, dengan penanda.** Di layar mereka dipisah ke
bagian "Direkam tanpa penilaian" (keputusan D1). Pada CSV mereka tetap satu tabel
dengan kolom `dinilai` bernilai `tidak`, karena berkas yang diam-diam menghilangkan
orang lebih berbahaya daripada berkas yang memuat kolom tambahan — yang membacanya
belum tentu tahu ada orang yang tidak ikut.

**Angka tetap menit, bukan jam.** Seluruh modul ini memakai menit, dan mengubahnya
hanya di titik ekspor membuat angka CSV tidak bisa dicocokkan dengan layar.
"""
from __future__ import annotations

import csv
import datetime as dt

from django.http import HttpResponse
from django.utils import timezone

from audit.models import AuditAction
from audit.services import log_event
from audit.views import _cell

from .perhitungan import hitung_periode

KOLOM_SKOR = [
    "Nama", "Username", "Dinilai", "Hari kerja", "Terlambat (menit)",
    "Lembur pulang (menit)", "Datang awal (menit)", "Skor (menit)", "Hari perlu dicek",
]

KOLOM_PENGECUALIAN = [
    "Tanggal", "Nama", "Username", "Cabang", "Cabang dari dugaan", "Jadwal",
    "Shift mulai", "Shift selesai", "Cap masuk", "Cap pulang",
    "Terlambat (menit)", "Lembur pulang (menit)", "Datang awal (menit)", "Skor (menit)",
    "Dikoreksi tangan", "Temuan", "Catatan",
]


def _jam(waktu: dt.datetime | None) -> str:
    return timezone.localtime(waktu).strftime("%H:%M") if waktu else ""


def _tanggal_jam(waktu: dt.datetime | None) -> str:
    """Cap pulang bisa jatuh pada tanggal berikutnya; tanggalnya ikut ditulis agar
    00:28 tidak terbaca sebagai pulang paling awal sepanjang bulan."""
    return timezone.localtime(waktu).strftime("%Y-%m-%d %H:%M") if waktu else ""


def _tanggapan(nama_berkas: str, kolom: list[str], baris) -> HttpResponse:
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{nama_berkas}"'
    response.write("﻿")
    writer = csv.writer(response)
    writer.writerow(kolom)
    for satu in baris:
        writer.writerow([_cell(v) if isinstance(v, str) else v for v in satu])
    return response


def csv_papan_skor(request, mulai: dt.date, selesai: dt.date) -> HttpResponse:
    semua = hitung_periode(mulai, selesai)
    baris = [
        [
            str(s.user), s.user.username, "ya" if s.dinilai else "tidak",
            s.hari_kerja, s.terlambat, s.lembur_pulang, s.datang_awal, s.skor,
            len(s.pengecualian),
        ]
        for s in semua
    ]
    log_event(
        action=AuditAction.EXPORT, entity_type="absensi.papan_skor",
        entity_label=f"Ekspor papan skor absensi {mulai:%Y-%m}",
        actor=request.user, after={"bulan": f"{mulai:%Y-%m}", "baris": len(baris)},
        request=request,
    )
    return _tanggapan(f"absensi-papan-skor-{mulai:%Y-%m}.csv", KOLOM_SKOR, baris)


def csv_pengecualian(request, mulai: dt.date, selesai: dt.date) -> HttpResponse:
    semua = hitung_periode(mulai, selesai)
    hari = sorted(
        (h for s in semua for h in s.pengecualian), key=lambda h: (h.tanggal, str(h.user))
    )
    baris = [
        [
            h.tanggal.isoformat(), str(h.user), h.user.username,
            h.clinic.name if h.clinic else "", "ya" if h.cabang_dari_dugaan else "",
            h.status_label, _jam(h.jam_mulai), _jam(h.jam_selesai),
            _tanggal_jam(h.masuk), _tanggal_jam(h.keluar),
            h.terlambat, h.lembur_pulang, h.datang_awal, h.skor,
            "ya" if h.ada_koreksi_manual else "",
            # Label, bukan kode: berkas ini dibaca manusia, dan kodenya sendiri
            # (TANPA_ROSTER dsb.) tidak berarti apa-apa di luar repo.
            "; ".join(str(p.label) for p in h.pengecualian),
            " ".join(h.catatan),
        ]
        for h in hari
    ]
    log_event(
        action=AuditAction.EXPORT, entity_type="absensi.pengecualian",
        entity_label=f"Ekspor daftar perlu dicek absensi {mulai:%Y-%m}",
        actor=request.user, after={"bulan": f"{mulai:%Y-%m}", "baris": len(baris)},
        request=request,
    )
    return _tanggapan(f"absensi-perlu-dicek-{mulai:%Y-%m}.csv", KOLOM_PENGECUALIAN, baris)
