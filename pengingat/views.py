"""Aksi kartu "Pengingat hari ini" di Ringkasan Direktur. Semua aksi hanya Direktur Operasional."""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.models import Clinic, local_today
from core.permissions import can_manage_pengingat, can_view_pengingat_history, require

from . import katalog as kat
from . import riwayat as rw
from . import services
from .models import SASARAN, Butir, Jenis, Kelas, Materi, Paksa, Pengaturan


def _back():
    return redirect(reverse("direktur:overview") + "#pengingat")


def _butir(pk: int) -> Butir:
    return get_object_or_404(Butir.objects.select_related("kartu", "materi"), pk=pk)


@login_required
@require(can_manage_pengingat)
@require_POST
def butir_diingatkan(request, pk: int):
    butir = _butir(pk)
    try:
        services.tandai_diingatkan(butir, user=request.user, cabang=request.POST.get("cabang", ""),
                                   saluran=request.POST.get("saluran", ""), catatan=request.POST.get("catatan", ""))
        messages.success(request, f"{butir.materi.kode} dicatat sudah diingatkan.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return _back()


@login_required
@require(can_manage_pengingat)
@require_POST
def butir_tunda(request, pk: int):
    butir = _butir(pk)
    try:
        p = services.tunda(butir, user=request.user)
        messages.success(request, f"{butir.materi.kode} ditunda; muncul lagi {p.tanggal:%d/%m}.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return _back()


@login_required
@require(can_manage_pengingat)
@require_POST
def butir_lewati(request, pk: int):
    butir = _butir(pk)
    try:
        services.lewati(butir, user=request.user, alasan=request.POST.get("alasan", ""))
        messages.warning(request, f"{butir.materi.kode} dilewati; kembali ke giliran berikutnya.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return _back()


# --- Katalog (Tahap 2) ---------------------------------------------------------------------------


@login_required
@require(can_manage_pengingat)
def katalog(request):
    status = request.GET.get("status", "aktif")
    qs = Materi.objects.select_related("clinic")
    if status == "aktif":
        qs = qs.filter(aktif=True)
    elif status == "nonaktif":
        qs = qs.filter(aktif=False)
    today = local_today()
    anchors = services.anchors_until(today)
    pending = {}
    for p in Paksa.objects.filter(selesai_pada__isnull=True).order_by("tanggal"):
        pending.setdefault(p.materi_id, p)
    rows = [{"m": m, "terakhir": anchors.get(m.pk), "paksa": pending.get(m.pk)} for m in qs]
    cfg = Pengaturan.get()
    return render(request, "pengingat/katalog.html", {
        "rows": rows, "status": status, "cfg": cfg, "kap": kat.kapasitas(cfg),
        "hari": list(enumerate(kat.HARI)), "besok": services.next_workday(today, cfg),
        "jumlah": {"semua": Materi.objects.count(), "aktif": Materi.objects.filter(aktif=True).count(),
                   "nonaktif": Materi.objects.filter(aktif=False).count()},
    })


def _to_row(materi: Materi):
    """Kembali ke baris materi di katalog (tujuan tetap, bukan dari isian formulir)."""
    return redirect(reverse("pengingat:katalog") + ("" if materi.aktif else "?status=nonaktif") + f"#m-{materi.pk}")


def _form_page(request, materi: Materi | None):
    if request.method == "POST":
        try:
            m = kat.simpan_materi(kat.parse_form(request.POST, materi=materi), user=request.user, materi=materi)
            messages.success(request, f"{m.kode} disimpan.")
            return redirect("pengingat:katalog")
        except ValidationError as exc:
            for msg in exc.messages:
                messages.error(request, msg)
        form = request.POST
        values = {
            "kode": form.get("kode", ""), "judul": form.get("judul", ""), "jenis": form.get("jenis", ""),
            "sasaran": form.getlist("sasaran"), "cabang": form.get("cabang", ""), "kelas": form.get("kelas", ""),
            "poin": (form.getlist("poin") + ["", "", ""])[:3], "teks_wa": form.get("teks_wa", ""),
            "rujukan": form.get("rujukan", ""), "kebijakan": form.get("kebijakan", ""),
            "aktif": form.get("aktif") == "1", "tanggal_sosialisasi": form.get("tanggal_sosialisasi", ""),
            "catatan": form.get("catatan", ""), "urutan": form.get("urutan", ""),
        }
    elif materi:
        values = {
            "kode": materi.kode, "judul": materi.judul, "jenis": materi.jenis, "sasaran": materi.sasaran,
            "cabang": str(materi.clinic_id or ""), "kelas": materi.kelas, "poin": (materi.poin + ["", "", ""])[:3],
            "teks_wa": materi.teks_wa, "rujukan": materi.rujukan, "kebijakan": str(materi.kebijakan_id or ""),
            "aktif": materi.aktif,
            "tanggal_sosialisasi": materi.tanggal_sosialisasi.isoformat() if materi.tanggal_sosialisasi else "",
            "catatan": materi.catatan, "urutan": materi.urutan,
        }
    else:
        # Materi baru: tanggal sosialisasi hari ini (ulangan 1/3/7/14/30), bisa diubah atau dikosongkan.
        values = {"kode": "", "judul": "", "jenis": Jenis.ALUR, "sasaran": [], "cabang": "", "kelas": Kelas.B,
                  "poin": ["", "", ""], "teks_wa": "", "rujukan": "", "kebijakan": "", "aktif": True,
                  "tanggal_sosialisasi": local_today().isoformat(), "catatan": "",
                  "urutan": (Materi.objects.order_by("-urutan").values_list("urutan", flat=True).first() or 0) + 1}
    return render(request, "pengingat/materi_form.html", {
        "materi": materi, "v": values, "sasaran": SASARAN, "jenis": Jenis.choices, "kelas": Kelas.choices,
        "clinics": Clinic.objects.order_by("id"), "policies": kat.policies(),
    })


@login_required
@require(can_manage_pengingat)
def materi_baru(request):
    return _form_page(request, None)


@login_required
@require(can_manage_pengingat)
def materi_ubah(request, pk: int):
    return _form_page(request, get_object_or_404(Materi, pk=pk))


@login_required
@require(can_manage_pengingat)
@require_POST
def materi_aktif(request, pk: int):
    materi = get_object_or_404(Materi, pk=pk)
    aktif = request.POST.get("aktif") == "1"
    kat.set_aktif(materi, aktif, user=request.user)
    messages.success(request, f"{materi.kode} {'diaktifkan' if aktif else 'dinonaktifkan; riwayatnya tetap tersimpan'}.")
    return _to_row(materi)


@login_required
@require(can_manage_pengingat)
@require_POST
def materi_besok(request, pk: int):
    materi = get_object_or_404(Materi, pk=pk)
    try:
        p = kat.ingatkan_besok(materi, user=request.user)
        messages.success(request, f"{materi.kode} masuk kartu {p.tanggal:%d/%m}, di luar kuota.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return _to_row(materi)


@login_required
@require(can_manage_pengingat)
@require_POST
def pengaturan(request):
    try:
        kat.simpan_pengaturan(request.POST, user=request.user)
        messages.success(request, "Pengaturan pengingat disimpan. Kartu yang sudah terbentuk hari ini tidak berubah.")
    except ValidationError as exc:
        for msg in exc.messages:
            messages.error(request, msg)
    return redirect(reverse("pengingat:katalog") + "#pengaturan")


# --- Riwayat (Tahap 3) ---------------------------------------------------------------------------


@login_required
@require(can_view_pengingat_history)
def riwayat(request):
    """Riwayat Sudah diingatkan: Direktur Operasional, Direktur Utama, dan Owner (baca saja)."""
    filters = rw.parse_filters(request.GET)
    if request.GET.get("unduh") == "csv":
        return rw.csv_response(request, filters)
    logs = list(rw.query(filters)[:500])
    for log in logs:
        log.cabang = rw.cabang_label(log)
    params = request.GET.copy()
    params.pop("unduh", None)
    params["unduh"] = "csv"
    return render(request, "pengingat/riwayat.html", {
        "logs": logs, "f": filters, "csv_query": params.urlencode(),
        "materi": Materi.objects.order_by("kode"), "clinics": Clinic.objects.order_by("id"),
        "can_manage": can_manage_pengingat(request.user),
        "total": rw.query(filters).count(),
    })
