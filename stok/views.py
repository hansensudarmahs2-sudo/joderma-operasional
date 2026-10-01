"""Halaman Stok Apotek (`/stok-apotek/`): satu halaman, tiga tab di fase 1.

Hak akses (keputusan product owner 1 Okt 2026): apoteker, asisten apoteker, dan Direktur
Operasional boleh membuka, mengunggah, dan mengubah parameter; Owner hanya membaca.
Pemeriksaan ada di server (`core.permissions.can_view_stok` / `can_edit_stok`), ditambah
`core/peran.py` untuk tampilan Owner.
"""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from audit.models import AuditAction
from audit.services import log_event, snapshot
from core.models import Clinic, local_today
from core.permissions import can_edit_stok, can_view_stok, is_aom, is_owner, require

from . import hitung, parser, services
from .models import JenisFile, Parameter, StatusPeriode, Unggahan

TABS = [("order", "Prioritas Order"), ("transfer", "Transfer"), ("impor", "Impor Data")]
URUT_JENIS = {JenisFile.DAFTAR_PRODUK: 0, JenisFile.TINGKAT_PERSEDIAAN: 1, JenisFile.PERGERAKAN: 2}
BATAS_UKURAN = 5 * 1024 * 1024


def _cabang_awal(user) -> str:
    """Apoteker membuka cabangnya sendiri; Direktur dan Owner membuka kedua cabang."""
    if is_aom(user) or is_owner(user):
        return "semua"
    role = user.user_roles.filter(clinic__active=True).first()
    return str(role.clinic_id) if role else "semua"


@login_required
@require(can_view_stok)
def index(request):
    tab = request.GET.get("tab", "order")
    if tab not in dict(TABS):
        tab = "order"
    pilihan = request.GET.get("cabang") or _cabang_awal(request.user)
    status_filter = request.GET.get("status", "")
    q = request.GET.get("q", "").strip().lower()
    pabrikan = request.GET.get("pabrikan", "")

    hasil = hitung.hitung()
    cabang_semua = hasil.cabang
    dipilih = [c for c in cabang_semua if str(c.clinic.pk) == pilihan] or cabang_semua
    if len(dipilih) == len(cabang_semua):
        pilihan = "semua"

    today = local_today()
    ringkas = []
    for c in dipilih:
        umur = (today - c.tanggal_stok).days if c.tanggal_stok else None
        ringkas.append(
            {
                "data": c,
                "status": hitung.hitung_status(c),
                "basi": umur is None or umur > 2,
                "umur": umur,
            }
        )
    total = {k: sum(r["status"][k] for r in ringkas) for k in hitung.URUT_STATUS}
    id_dipilih = {c.clinic.pk for c in dipilih}
    transfer = [t for t in hasil.transfer if t.ke.clinic.pk in id_dipilih or t.dari.clinic.pk in id_dipilih]

    def cocok(produk) -> bool:
        if q and q not in f"{produk.nama} {produk.dosis}".lower():
            return False
        return not pabrikan or produk.pabrikan == pabrikan

    baris_order = []
    for c in dipilih:
        baris_order.extend(hitung.prioritas(c))
    baris_order.sort(key=lambda b: (hitung.URUT_STATUS[b.status], b.bulan_stok or 0, b.produk.nama))
    if status_filter:
        baris_order = [b for b in baris_order if b.status == status_filter]
    baris_order = [b for b in baris_order if cocok(b.produk)]
    transfer_tampil = [t for t in transfer if cocok(t.produk)]
    daftar_pabrikan = sorted({b.produk.pabrikan for c in dipilih for b in c.baris.values() if b.produk.pabrikan})

    konteks = {
        "tab": tab,
        "tabs": TABS,
        "pilihan": pilihan,
        "cabang_semua": cabang_semua,
        "semua_klinik": Clinic.objects.filter(active=True).order_by("name"),
        "ringkas": ringkas,
        "total_kosong": total[hitung.KOSONG],
        "total_bawah": total[hitung.DI_BAWAH],
        "total_dekat": total[hitung.MENDEKATI],
        "jumlah_transfer": len(transfer),
        "status_filter": status_filter,
        "q": request.GET.get("q", ""),
        "pabrikan": pabrikan,
        "daftar_pabrikan": daftar_pabrikan,
        "baris_order": baris_order,
        "transfer": transfer_tampil,
        "nilai_transfer": sum(t.nilai for t in transfer_tampil),
        "param": hasil.parameter,
        "bisa_ubah": can_edit_stok(request.user),
        "gabungan": len(dipilih) > 1,
        "status_list": [hitung.KOSONG, hitung.DI_BAWAH, hitung.MENDEKATI, hitung.AMAN],
    }
    if tab == "impor":
        konteks["periode"] = StatusPeriode.objects.select_related("clinic").order_by("clinic__name", "-tahun", "-bulan")
        konteks["unggahan"] = Unggahan.objects.select_related("clinic", "diunggah_oleh")[:30]
    return render(request, "stok/index.html", konteks)


@login_required
@require(can_edit_stok)
@require_POST
def unggah(request):
    files = request.FILES.getlist("file")
    kembali = redirect(f"{reverse('stok:index')}?tab=impor")
    if not files:
        messages.error(request, "Pilih file ekspor Omnicare (.xls) yang akan diunggah.")
        return kembali
    clinic = None
    if request.POST.get("cabang"):
        clinic = Clinic.objects.filter(pk=request.POST["cabang"], active=True).first()

    dibaca = []
    for f in files:
        if f.size > BATAS_UKURAN:
            messages.error(request, f"{f.name}: lebih dari 5 MB, dilewati.")
            continue
        data = f.read()
        try:
            dibaca.append((parser.baca(data, f.name), data, f.name))
        except parser.FileTidakDikenal as exc:
            messages.error(request, f"{f.name}: {exc}")
    dibaca.sort(key=lambda x: URUT_JENIS[x[0].jenis])  # Daftar Produk lebih dulu

    for hasil, data, nama in dibaca:
        try:
            up = services.impor_hasil(hasil, data, nama, request.user, clinic)
        except ValidationError as exc:
            messages.error(request, f"{nama}: {' '.join(exc.messages)}")
            continue
        log_event(
            action=AuditAction.CREATE, entity_type="stok_unggahan", entity_id=up.pk,
            entity_label=str(up), request=request,
            after={"jenis": up.jenis, "cabang": str(up.clinic or ""), "baris": up.jumlah_baris, "cocok": up.jumlah_cocok},
        )
        keterangan = f"{up.get_jenis_display()}"
        if up.clinic:
            keterangan += f" {up.clinic.name}"
        if up.tahun:
            keterangan += f" {up.bulan:02d}/{up.tahun}"
        elif up.tanggal:
            keterangan += f" {up.tanggal:%d/%m/%Y}"
        messages.success(request, f"{nama}: {keterangan}, {up.jumlah_cocok} dari {up.jumlah_baris} baris tersimpan.")
        for p in up.peringatan:
            messages.warning(request, f"{nama}: {p}")
    return kembali


def _angka(raw: str, minimum: float, maksimum: float, nama: str) -> float:
    try:
        nilai = float((raw or "").replace(",", "."))
    except ValueError as exc:
        raise ValidationError(f"{nama} harus angka.") from exc
    if not minimum <= nilai <= maksimum:
        raise ValidationError(f"{nama} harus antara {minimum:g} dan {maksimum:g}.")
    return nilai


@login_required
@require(can_edit_stok)
@require_POST
def parameter(request):
    param = Parameter.aktif()
    sebelum = snapshot(param)
    try:
        param.bulan_rata_rata = int(_angka(request.POST.get("bulan_rata_rata"), 1, 12, "Jumlah bulan rata-rata"))
        param.bulan_buffer = _angka(request.POST.get("bulan_buffer"), 0.1, 12, "Bulan buffer")
        param.ambang_mendekati = _angka(request.POST.get("ambang_persen"), 0, 200, "Ambang mendekati buffer") / 100
        param.target_bulan = _angka(request.POST.get("target_bulan"), 0.1, 12, "Target stok")
        param.cadangan_bulan = _angka(request.POST.get("cadangan_bulan"), 0, 12, "Cadangan cabang pengirim")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        return redirect("stok:index")
    param.diubah_oleh = request.user
    param.save()
    log_event(
        action=AuditAction.CONFIG_CHANGED, entity_type="stok_parameter", entity_id=param.pk,
        entity_label="Parameter Stok Apotek", before=sebelum, after=snapshot(param), request=request,
    )
    messages.success(request, "Parameter disimpan; semua status dan saran dihitung ulang.")
    return redirect("stok:index")
