"""Halaman Absensi (`/absensi/`): papan skor, hari yang perlu dicek, dan impor berkas.

Satu halaman dengan tiga tab, mengikuti pola Stok Apotek. Hak akses sempit karena
isinya jam kerja seluruh staf dan dasar penilaian lembur: Direktur Operasional dan
Admin berakses penuh boleh mengimpor; Owner hanya membaca
(`core.permissions.can_view_absensi` / `can_edit_absensi`, ditambah `core/peran.py`).

Angka papan skor tidak disimpan. Setiap kali halaman dibuka, `perhitungan` membacanya
ulang dari cap dan jadwal jaga terkini, sehingga koreksi roster langsung terlihat.
"""
from __future__ import annotations

import calendar
import datetime as dt
from collections import Counter

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.models import User
from core.models import local_today
from core.permissions import can_edit_absensi, can_view_absensi, require

from jadwal.services import can_edit_roster

from . import parser, services
from .models import AttendanceImport
from .perhitungan import AMBANG_DATANG_AWAL_MENIT, hitung_periode

TABS = [("skor", "Papan skor"), ("pengecualian", "Perlu dicek"), ("impor", "Impor berkas")]
MONTHS = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September",
          "Oktober", "November", "Desember"]
BATAS_UKURAN = 5 * 1024 * 1024


def _bulan(request) -> tuple[int, int]:
    raw = request.GET.get("bulan") or request.POST.get("bulan") or ""
    try:
        tahun, bulan = (int(x) for x in raw.split("-"))
        dt.date(tahun, bulan, 1)
        return tahun, bulan
    except ValueError:
        hari = local_today()
        return hari.year, hari.month


def _nav(tahun: int, bulan: int) -> dict:
    sebelum = (tahun - 1, 12) if bulan == 1 else (tahun, bulan - 1)
    sesudah = (tahun + 1, 1) if bulan == 12 else (tahun, bulan + 1)
    return {
        "label": f"{MONTHS[bulan - 1]} {tahun}",
        "value": f"{tahun:04d}-{bulan:02d}",
        "prev": f"{sebelum[0]:04d}-{sebelum[1]:02d}",
        "next": f"{sesudah[0]:04d}-{sesudah[1]:02d}",
    }


def _rentang(tahun: int, bulan: int) -> tuple[dt.date, dt.date]:
    return dt.date(tahun, bulan, 1), dt.date(tahun, bulan, calendar.monthrange(tahun, bulan)[1])


@login_required
@require(can_view_absensi)
def index(request):
    tab = request.GET.get("tab", "skor")
    if tab not in dict(TABS):
        tab = "skor"
    tahun, bulan = _bulan(request)
    mulai, selesai = _rentang(tahun, bulan)

    rencana = (
        services.susun_jadwal_dari_absensi(mulai, selesai)
        if tab == "impor" and can_edit_roster(request.user)
        else None
    )
    semua = hitung_periode(mulai, selesai)
    ringkasan = [s for s in semua if s.dinilai]
    rekam_saja = [s for s in semua if not s.dinilai]
    perlu = sorted(
        (h for s in semua for h in s.pengecualian), key=lambda h: (h.tanggal, str(h.user))
    )
    return render(
        request,
        "absensi/index.html",
        {
            "tab": tab,
            "tabs": TABS,
            "bulan": _nav(tahun, bulan),
            "ringkasan": ringkasan,
            "rekam_saja": rekam_saja,
            "perlu": perlu,
            "ambang_awal": AMBANG_DATANG_AWAL_MENIT,
            "bisa_impor": can_edit_absensi(request.user),
            "impor_terakhir": AttendanceImport.objects.select_related("imported_by")[:10],
            "pemetaan_nama": services.daftar_pemetaan_nama() if tab == "impor" else None,
            "rencana_jadwal": rencana,
            "rincian_jadwal": sorted(
                (nama, cabang, n)
                for (nama, cabang), n in Counter(
                    (str(u.user), u.clinic.name) for u in rencana.usul
                ).items()
            ) if rencana else None,
        },
    )


@login_required
@require(can_view_absensi)
def staf(request, pk: int):
    """Rincian harian satu staf: dari mana angka di papan skor berasal."""
    orang = get_object_or_404(User, pk=pk)
    tahun, bulan = _bulan(request)
    mulai, selesai = _rentang(tahun, bulan)
    ringkasan = hitung_periode(mulai, selesai, users=[orang])
    return render(
        request,
        "absensi/staf.html",
        {
            "orang": orang,
            "bulan": _nav(tahun, bulan),
            "staf": ringkasan[0] if ringkasan else None,
            "ambang_awal": AMBANG_DATANG_AWAL_MENIT,
        },
    )


@login_required
def saya(request):
    """Jam kerja sendiri (keputusan D5).

    Terbuka untuk siapa pun yang login, tetapi hanya menampilkan data dirinya: tidak
    ada parameter staf, jadi tidak ada cara meminta data orang lain dari sini. Staf
    yang paling cepat tahu capnya hilang adalah staf itu sendiri.
    """
    tahun, bulan = _bulan(request)
    mulai, selesai = _rentang(tahun, bulan)
    ringkasan = hitung_periode(mulai, selesai, users=[request.user])
    return render(
        request,
        "absensi/staf.html",
        {
            "orang": request.user,
            "bulan": _nav(tahun, bulan),
            "staf": ringkasan[0] if ringkasan else None,
            "ambang_awal": AMBANG_DATANG_AWAL_MENIT,
            "milik_sendiri": True,
        },
    )


@login_required
@require(can_edit_absensi)
@require_POST
def susun_jadwal(request):
    """Mengisi jadwal jaga bulan itu dari data absensi (lihat services).

    Menulis `jadwal.DutyRoster`, jadi haknya hak jadwal jaga — Direktur Operasional,
    Admin, atau Koordinator Shift — bukan hak absensi.
    """
    if not can_edit_roster(request.user):
        raise PermissionDenied("Menyusun jadwal jaga dilakukan Direktur Operasional atau Admin.")
    tahun, bulan = _bulan(request)
    mulai, selesai = _rentang(tahun, bulan)
    hasil = services.susun_jadwal_dari_absensi(mulai, selesai, simpan=True, actor=request.user)

    if hasil.disimpan:
        messages.success(
            request,
            f"{hasil.disimpan} hari jadwal jaga dibuat dari absensi "
            f"({hasil.dari_mesin} dari jendela shift mesin, {hasil.dari_pola} dari pola jam). "
            'Semuanya bercatat "belum dikonfirmasi"; tinjau di Jadwal Jaga.',
        )
    else:
        messages.info(request, "Tidak ada hari baru yang bisa diisi dari absensi.")
    if hasil.gagal:
        messages.warning(
            request,
            f"{len(hasil.gagal)} hari dibiarkan kosong karena tidak bisa ditentukan dari capnya; "
            "isi sendiri di Jadwal Jaga.",
        )
    return redirect(f"{reverse('absensi:index')}?tab=impor&bulan={tahun:04d}-{bulan:02d}")


@login_required
@require(can_edit_absensi)
@require_POST
def unggah(request):
    berkas = request.FILES.getlist("berkas")
    kembali = redirect(f"{reverse('absensi:index')}?tab=impor&bulan={request.POST.get('bulan', '')}")
    if not berkas:
        messages.error(request, "Pilih berkas ekspor mesin sidik jari (.xlsx) yang akan diunggah.")
        return kembali

    for f in berkas:
        if f.size > BATAS_UKURAN:
            messages.error(request, f"{f.name}: lebih dari 5 MB, dilewati.")
            continue
        try:
            batch = services.impor_kartu_laporan(f.read(), f.name, actor=request.user)
        except parser.FileTidakDikenal as exc:
            messages.error(request, f"{f.name}: {exc}")
            continue
        messages.success(
            request,
            f"{f.name}: periode {batch.period_start:%d/%m/%Y}–{batch.period_end:%d/%m/%Y}, "
            f"{batch.punches_created} cap baru, {batch.punches_skipped} sudah ada.",
        )
        for pesan in batch.warnings:
            messages.warning(request, f"{f.name}: {pesan}")
    return kembali
