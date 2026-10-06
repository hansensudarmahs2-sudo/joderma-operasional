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
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import User
from core.models import local_today
from core.permissions import (
    can_correct_absensi,
    can_edit_absensi,
    can_view_absensi,
    require,
)

from jadwal.models import DutyRoster
from jadwal.services import can_edit_roster

from . import koreksi as koreksi_cap
from . import parser, services
from .models import AttendanceDevice, AttendanceImport, AttendancePunch, JenisCap
from .perhitungan import AMBANG_DATANG_AWAL_MENIT, hitung_hari, hitung_periode

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
            "bisa_koreksi": can_correct_absensi(request.user),
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
            "bisa_koreksi": can_correct_absensi(request.user),
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
            # Tidak ada tombol koreksi di halaman sendiri, juga bagi yang berhak
            # mengoreksi: koreksi dikerjakan dari halaman stafnya, supaya tidak ada
            # jalan memperbaiki angka diri sendiri tanpa melewati papan skor.
            "bisa_koreksi": False,
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


# --- koreksi cap dari halaman (Tahap 4) -----------------------------------------


def _hari_satu(orang, tanggal: dt.date):
    """Satu orang, satu hari: cap, jadwal jaga, dan hasil perhitungannya.

    Memanggil `hitung_hari` langsung, bukan `hitung_periode`, karena yang terakhir
    hanya memuat hari yang punya cap atau baris roster — dan halaman koreksi justru
    perlu bekerja pada hari yang belum punya keduanya.
    """
    caps = list(
        AttendancePunch.objects.filter(user=orang, shift_date=tanggal).order_by("occurred_at")
    )
    roster = (
        DutyRoster.objects.filter(user=orang, date=tanggal)
        .select_related("clinic", "home_clinic")
        .first()
    )
    dinilai = not AttendanceDevice.objects.filter(user=orang, recording_only=True).exists()
    return caps, hitung_hari(orang, tanggal, caps, roster, dinilai=dinilai)


def _akibat(hasil) -> str:
    """Apa yang berubah pada angka hari itu, untuk ditempel di pesan sukses.

    Yang mengoreksi harus langsung melihat akibatnya; kalau harus membuka halaman lain
    untuk tahu, koreksi yang keliru arah gampang lolos.
    """
    if hasil.jam_mulai is None:
        return "Hari itu belum punya jam shift, jadi skornya masih belum dihitung."
    return (
        f"Hari itu kini: terlambat {hasil.terlambat} m, lembur {hasil.lembur_pulang} m, "
        f"datang awal {hasil.datang_awal} m, skor {hasil.skor} m."
    )


@login_required
@require(can_correct_absensi)
def koreksi(request, pk: int, tanggal: str):
    """Menambah, mengubah, atau menghapus satu cap pada satu hari kerja (D4).

    Haknya `can_correct_absensi`, lebih sempit daripada hak mengimpor: mengimpor hanya
    memasukkan apa yang dicatat mesin, sedangkan di sini angka yang menilai orang
    diubah tangan. Owner ikut boleh — dan ini satu-satunya tempat Owner mengirim POST
    di modul ini, jadi rutenya terdaftar di `core/peran.py` tanpa masuk
    `OWNER_READ_ONLY`.

    Jam dimasukkan sebagai jam dinding pada hari kerja itu; `services.waktu_cap` yang
    memindahkan cap dini hari ke tanggal kalender berikutnya.
    """
    orang = get_object_or_404(User, pk=pk)
    try:
        hari_kerja = dt.date.fromisoformat(tanggal)
    except ValueError:
        raise Http404("Tanggal tidak sah.")
    kembali = redirect(reverse("absensi:koreksi", args=[orang.pk, hari_kerja.isoformat()]))

    if request.method == "POST":
        aksi = request.POST.get("aksi", "")
        alasan = request.POST.get("alasan", "")
        try:
            if aksi == "tambah":
                cap = koreksi_cap.tambah_cap(
                    user=orang, shift_date=hari_kerja, jam=request.POST.get("jam", ""),
                    jenis=request.POST.get("jenis", ""), alasan=alasan, actor=request.user,
                )
                pesan = (
                    f"Cap {cap.get_kind_display().lower()} "
                    f"{timezone.localtime(cap.occurred_at):%d/%m %H.%M} ditambahkan."
                )
            elif aksi in ("ubah", "hapus"):
                cap = get_object_or_404(
                    AttendancePunch, pk=request.POST.get("cap", 0), user=orang,
                    shift_date=hari_kerja,
                )
                if aksi == "ubah":
                    lama = timezone.localtime(cap.occurred_at)
                    koreksi_cap.ubah_cap(
                        cap=cap, jam=request.POST.get("jam", ""),
                        jenis=request.POST.get("jenis", ""), alasan=alasan, actor=request.user,
                    )
                    pesan = (
                        f"Cap {lama:%d/%m %H.%M} diubah menjadi "
                        f"{timezone.localtime(cap.occurred_at):%d/%m %H.%M}."
                    )
                else:
                    pesan = f"Cap manual {timezone.localtime(cap.occurred_at):%d/%m %H.%M} dihapus."
                    koreksi_cap.hapus_cap(cap=cap, alasan=alasan, actor=request.user)
            else:
                raise koreksi_cap.KoreksiDitolak("Aksi koreksi tidak dikenal.")
        except koreksi_cap.KoreksiDitolak as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"{pesan} {_akibat(_hari_satu(orang, hari_kerja)[1])}")
        return kembali

    caps, hasil = _hari_satu(orang, hari_kerja)
    return render(
        request,
        "absensi/koreksi.html",
        {
            "orang": orang,
            "tanggal": hari_kerja,
            "bulan": _nav(hari_kerja.year, hari_kerja.month),
            "caps": caps,
            "hari": hasil,
            "jenis_pilihan": JenisCap.choices,
            "ambang_awal": AMBANG_DATANG_AWAL_MENIT,
            "batas_dini": services.BATAS_DINI_JAM,
        },
    )
