"""Laporan kegiatan teknisi: apa yang dikerjakan, dengan foto dan lokasi (13 Okt 2026).

Dipisah dari `reports/views.py` yang sudah panjang, dan karena alurnya memang berdiri
sendiri: satu halaman, satu formulir, satu daftar miliknya sendiri.

Lokasi datang dari isian tersembunyi yang diisi `base.html` pada formulir bertanda
`data-jejak`, dibaca dengan `jejak.services.geo_from_post` — fungsi yang sama dengan
jejak kehadiran, supaya tidak ada dua cara membaca koordinat yang bisa berbeda diam-diam.
Lokasi hanya diminta saat formulir dikirim; tidak ada pelacakan.

Foto lewat `core.photos.save_photo`, yang mengompresnya dan **membuang EXIF termasuk
GPS**. Jadi koordinat yang tersimpan hanya yang dari browser saat mengirim — bukan yang
menempel diam-diam di berkas fotonya.
"""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from core.models import Attachment, Clinic
from core.photos import save_photo
from jejak.services import geo_from_post

from .models import LaporanKegiatan

#: Masa simpan foto. Keputusan product owner 13 Okt 2026; teksnya tidak ikut dihapus.
HARI_SIMPAN_FOTO = 90


def _boleh(user) -> bool:
    """Siapa yang memakai halaman ini.

    Teknisi memakainya sebagai pekerjaan sehari-hari; Direktur Operasional dan Owner
    membacanya. Pemeriksaan per laporan ada di `detail`: orang hanya melihat miliknya
    sendiri kecuali ia berhak membaca semua.
    """
    from core.permissions import is_aom, is_owner

    return is_aom(user) or is_owner(user) or _teknisi(user)


def _teknisi(user) -> bool:
    from accounts.models import Role
    from core.permissions import has_role

    return has_role(user, Role.TEKNISI)


def _boleh_baca_semua(user) -> bool:
    from core.permissions import is_aom, is_owner

    return is_aom(user) or is_owner(user)


@login_required
def daftar(request):
    """Laporan kegiatan: daftar dan formulir pembuatannya pada satu halaman."""
    if not _boleh(request.user):
        raise PermissionDenied("Halaman ini untuk teknisi dan Direktur Operasional.")

    if request.method == "POST":
        if not _teknisi(request.user):
            raise PermissionDenied("Hanya teknisi yang membuat laporan kegiatan di sini.")
        return _simpan(request)

    qs = LaporanKegiatan.objects.select_related("user", "clinic")
    if not _boleh_baca_semua(request.user):
        qs = qs.filter(user=request.user)
    laporan = list(qs[:50])
    # Ditempelkan di sini, bukan dicari dari template: template Django tidak bisa
    # mengindeks dict dengan kunci variabel tanpa filter buatan sendiri.
    foto = _foto_per_laporan(laporan)
    for satu in laporan:
        satu.foto_list = foto.get(satu.pk, [])
    return render(request, "reports/kegiatan.html", {
        "laporan": laporan,
        "clinics": Clinic.objects.filter(active=True),
        "bisa_lapor": _teknisi(request.user),
        "hari_simpan": HARI_SIMPAN_FOTO,
    })


def _foto_per_laporan(laporan) -> dict:
    if not laporan:
        return {}
    lampiran = Attachment.objects.filter(
        entity_type="laporan_kegiatan", entity_id__in=[l.pk for l in laporan]
    )
    hasil: dict[int, list] = {}
    for a in lampiran:
        hasil.setdefault(a.entity_id, []).append(a)
    return hasil


def _simpan(request):
    kembali = redirect(reverse("reports:kegiatan"))
    uraian = (request.POST.get("uraian") or "").strip()
    if not uraian:
        messages.error(request, "Tulis dulu apa yang Anda kerjakan.")
        return kembali

    clinic = None
    kode = request.POST.get("cabang") or ""
    if kode:
        clinic = Clinic.objects.filter(pk=kode, active=True).first()

    geo = geo_from_post(request.POST)
    laporan = LaporanKegiatan.objects.create(
        user=request.user,
        clinic=clinic,
        lokasi_teks=(request.POST.get("lokasi_teks") or "").strip()[:120],
        uraian=uraian[:500],
        geo_status=geo["geo_status"],
        latitude=geo["latitude"],
        longitude=geo["longitude"],
        accuracy_m=geo["accuracy_m"],
    )

    foto = request.FILES.get("foto")
    if foto:
        try:
            save_photo(
                foto, entity_type="laporan_kegiatan", entity_id=laporan.pk,
                user=request.user, sensitive=True,
            )
        except ValidationError as exc:
            # Laporannya tetap tersimpan: teks yang sudah ditulis tidak boleh hilang
            # hanya karena fotonya ditolak.
            messages.warning(request, f"Laporan tersimpan, tetapi fotonya tidak: {' '.join(exc.messages)}")
            return kembali

    messages.success(request, "Laporan kegiatan tersimpan.")
    return kembali


@login_required
def detail(request, pk: int):
    laporan = get_object_or_404(LaporanKegiatan.objects.select_related("user", "clinic"), pk=pk)
    if not _boleh(request.user):
        raise PermissionDenied("Halaman ini untuk teknisi dan Direktur Operasional.")
    if laporan.user_id != request.user.pk and not _boleh_baca_semua(request.user):
        raise PermissionDenied("Anda hanya dapat membuka laporan kegiatan Anda sendiri.")
    return render(request, "reports/kegiatan_detail.html", {
        "laporan": laporan,
        "foto": Attachment.objects.filter(entity_type="laporan_kegiatan", entity_id=laporan.pk),
        "hari_simpan": HARI_SIMPAN_FOTO,
    })
