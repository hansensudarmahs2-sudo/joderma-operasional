"""Koreksi satu cap dari halaman (Tahap 4).

Sebelum ini koreksi hanya bisa lewat Django admin. Yang mendorongnya: pada September
2026 ada 8 hari dengan satu cap saja — orang lupa mengecap masuk — dan daftar "Perlu
dicek" hanya bisa menunjuknya, tidak bisa menutupnya. Django admin bisa, tetapi ia
meminta `occurred_at` sebagai waktu mutlak, yaitu justru bagian yang paling mudah
salah: cap pulang 00.28 untuk shift tanggal 4 harus ditulis sebagai tanggal 5.

Karena itu lapisan ini hanya menerima **jam dinding + tanggal shift**, lalu
menjalankannya lewat `services.waktu_cap` — persis jalur yang dipakai importer. Yang
mengoreksi memasukkan "00:28" pada hari kerja tanggal 4 dan tidak perlu tahu bahwa
yang tersimpan adalah tanggal 5 pukul 00.28.

Tiga hal yang dijaga di sini, bukan di tampilan:

Alasan wajib
    Angka di modul ini dipakai menilai orang dan menghitung lembur. Perubahan tanpa
    alasan tertulis tidak bisa dipertanggungjawabkan sebulan kemudian, jadi alasan
    kosong ditolak di lapisan ini — bukan hanya `required` di HTML, yang bisa
    dilewati siapa pun yang mengirim POST sendiri.

Setiap perubahan masuk audit
    `AuditAction.CORRECTION` dengan snapshot sebelum dan sesudah, ditambah alasannya
    apa adanya. Audit menyimpan alasan utuh; `AttendancePunch.note` hanya memuat 200
    karakter pertama.

Hanya cap MANUAL yang boleh dihapus
    Cap mesin adalah bukti apa yang dicatat alat, dan menghapusnya dari halaman
    membuat bukti itu hilang tanpa jejak di tabelnya sendiri. Jamnya tetap boleh
    diubah (tercatat di audit lengkap dengan nilai lamanya). Penghapusan cap mesin
    yang benar-benar perlu — misalnya cap ganda dari alat yang rusak — tetap lewat
    Django admin, dengan hak yang sama (D4).

Satu hal yang sengaja TIDAK dikerjakan di sini: `jenis` cap tidak memengaruhi skor.
`perhitungan.hitung_hari` mengurutkan cap menurut waktunya lalu memakai yang pertama
sebagai masuk dan yang terakhir sebagai pulang; ia tidak pernah membaca `kind`. Jadi
memperbaiki `jenis` TIDAK_PASTI menjadi KELUAR merapikan catatan, bukan angkanya.
Yang menutup hari `CAP_TUNGGAL` adalah menambah cap yang hilang.
"""
from __future__ import annotations

import datetime as dt

from django.db import transaction
from django.utils import timezone

from audit.models import AuditAction
from audit.services import log_event, snapshot

from .models import (
    AttendancePunch,
    JenisCap,
    PermintaanKoreksi,
    StatusPermintaan,
    SumberCap,
)
from .services import waktu_cap

#: Sepanjang `AttendancePunch.note`. Alasan yang lebih panjang tetap utuh di audit.
BATAS_CATATAN = 200


class KoreksiDitolak(Exception):
    """Koreksi tidak dijalankan. Pesannya ditulis untuk dibaca pengguna, bukan pengembang."""


# --- pembacaan masukan ----------------------------------------------------------


def bersihkan_alasan(teks: str) -> str:
    alasan = (teks or "").strip()
    if not alasan:
        raise KoreksiDitolak(
            "Alasan koreksi wajib diisi. Angka ini dipakai menilai orang, jadi harus "
            "bisa ditelusuri sebulan kemudian mengapa diubah."
        )
    return alasan


def bersihkan_jam(teks: str) -> dt.time:
    try:
        return dt.time.fromisoformat((teks or "").strip())
    except ValueError:
        raise KoreksiDitolak(
            "Jam tidak terbaca. Isi dalam bentuk JJ:MM, misalnya 14:02."
        ) from None


def bersihkan_jenis(teks: str) -> str:
    if teks not in JenisCap.values:
        raise KoreksiDitolak("Jenis cap tidak dikenal.")
    return teks


def _bentrok(user, waktu: dt.datetime, kecuali: AttendancePunch | None = None) -> None:
    """Satu orang tidak bisa punya dua cap pada detik yang sama (constraint di model).

    Diperiksa lebih dulu supaya pesannya bisa dibaca, bukan muncul sebagai IntegrityError.
    """
    lain = AttendancePunch.objects.filter(user=user, occurred_at=waktu)
    if kecuali is not None:
        lain = lain.exclude(pk=kecuali.pk)
    if lain.exists():
        raise KoreksiDitolak(
            f"Sudah ada cap {timezone.localtime(waktu):%d/%m %H.%M} untuk orang ini; "
            "ubah cap itu, jangan menambah yang kedua."
        )


# --- tiga operasi ---------------------------------------------------------------


@transaction.atomic
def tambah_cap(*, user, shift_date: dt.date, jam: str, jenis: str, alasan: str, actor) -> AttendancePunch:
    """Cap yang hilang, dimasukkan tangan. Jam dinding pada hari kerja `shift_date`."""
    catatan = bersihkan_alasan(alasan)
    waktu = waktu_cap(shift_date, bersihkan_jam(jam))
    _bentrok(user, waktu)

    cap = AttendancePunch.objects.create(
        user=user, shift_date=shift_date, occurred_at=waktu, kind=bersihkan_jenis(jenis),
        source=SumberCap.MANUAL, note=catatan[:BATAS_CATATAN],
    )
    log_event(
        action=AuditAction.CORRECTION,
        entity_type="absensi.AttendancePunch",
        entity_id=cap.pk,
        entity_label=f"{user} {shift_date} cap ditambahkan",
        actor=actor,
        after=snapshot(cap),
        reason=catatan,
    )
    return cap


@transaction.atomic
def ubah_cap(*, cap: AttendancePunch, jam: str, jenis: str, alasan: str, actor) -> AttendancePunch:
    """Jam atau jenis satu cap yang sudah ada. Nilai lamanya tersimpan di audit."""
    catatan = bersihkan_alasan(alasan)
    waktu = waktu_cap(cap.shift_date, bersihkan_jam(jam))
    _bentrok(cap.user, waktu, kecuali=cap)
    sebelum = snapshot(cap)

    cap.occurred_at = waktu
    cap.kind = bersihkan_jenis(jenis)
    # Sumbernya berubah menjadi MANUAL: jam yang sudah disentuh tangan bukan lagi apa
    # yang dicatat mesin, dan papan skor menandainya sebagai hari yang pernah dikoreksi.
    cap.source = SumberCap.MANUAL
    cap.note = catatan[:BATAS_CATATAN]
    cap.save(update_fields=["occurred_at", "kind", "source", "note"])

    log_event(
        action=AuditAction.CORRECTION,
        entity_type="absensi.AttendancePunch",
        entity_id=cap.pk,
        entity_label=f"{cap.user} {cap.shift_date} cap diubah",
        actor=actor,
        before=sebelum,
        after=snapshot(cap),
        reason=catatan,
    )
    return cap


@transaction.atomic
def hapus_cap(*, cap: AttendancePunch, alasan: str, actor) -> None:
    """Hanya cap MANUAL. Cap mesin adalah bukti; lihat docstring modul."""
    catatan = bersihkan_alasan(alasan)
    if cap.source != SumberCap.MANUAL:
        raise KoreksiDitolak(
            "Cap dari mesin sidik jari tidak dihapus dari halaman ini — ia bukti apa yang "
            "dicatat alat. Jamnya boleh diubah, dan nilai lamanya tersimpan di audit."
        )
    sebelum = snapshot(cap)
    label = f"{cap.user} {cap.shift_date} cap manual dihapus"
    cap.delete()
    log_event(
        action=AuditAction.CORRECTION,
        entity_type="absensi.AttendancePunch",
        entity_id=sebelum.get("id", ""),
        entity_label=label,
        actor=actor,
        before=sebelum,
        reason=catatan,
    )


# --- permintaan koreksi dari staf (Tahap 5) -------------------------------------


def _jam_opsional(teks: str):
    """Jam usulan boleh kosong; yang diisi tetap harus terbaca."""
    teks = (teks or "").strip()
    if not teks:
        return None
    return bersihkan_jam(teks)


@transaction.atomic
def ajukan_permintaan(*, user, shift_date: dt.date, alasan: str,
                      usul_masuk: str = "", usul_keluar: str = "") -> PermintaanKoreksi:
    """Staf melaporkan capnya sendiri hilang atau keliru.

    Tidak mengubah satu angka pun: yang dibuat hanya permintaan. Pemeriksaan hak
    ada di view (`saya` tidak punya parameter staf), dan `user` di sini selalu
    pengirimnya sendiri.
    """
    catatan = bersihkan_alasan(alasan)
    masuk, keluar = _jam_opsional(usul_masuk), _jam_opsional(usul_keluar)

    if PermintaanKoreksi.objects.filter(
        user=user, shift_date=shift_date, status=StatusPermintaan.MENUNGGU
    ).exists():
        raise KoreksiDitolak(
            f"Permintaan untuk {shift_date:%d/%m/%Y} sudah dikirim dan masih menunggu "
            "ditinjau. Tunggu jawabannya dulu."
        )

    permintaan = PermintaanKoreksi.objects.create(
        user=user, shift_date=shift_date, alasan=catatan[:300],
        usul_masuk=masuk, usul_keluar=keluar,
    )
    log_event(
        action=AuditAction.CREATE,
        entity_type="absensi.PermintaanKoreksi",
        entity_id=permintaan.pk,
        entity_label=f"{user} {shift_date} minta koreksi",
        actor=user,
        after=snapshot(permintaan),
        reason=catatan,
    )
    return permintaan


@transaction.atomic
def tanggapi_permintaan(*, permintaan: PermintaanKoreksi, status: str,
                        tanggapan: str, actor) -> PermintaanKoreksi:
    """Yang berhak mengoreksi menjawab permintaan staf.

    Menolak **wajib** disertai tanggapan: permintaan yang ditolak tanpa alasan
    tidak bisa dipahami staf, dan justru itu yang membuat orang berhenti melapor.
    Menyatakan sudah dikoreksi tidak mewajibkannya, karena perubahan capnya sendiri
    sudah tercatat di audit dengan alasannya.
    """
    if permintaan.status != StatusPermintaan.MENUNGGU:
        raise KoreksiDitolak("Permintaan ini sudah dijawab.")
    if status not in (StatusPermintaan.DIKOREKSI, StatusPermintaan.DITOLAK):
        raise KoreksiDitolak("Jawaban tidak dikenal.")

    catatan = (tanggapan or "").strip()
    if status == StatusPermintaan.DITOLAK and not catatan:
        raise KoreksiDitolak(
            "Menolak permintaan wajib disertai alasan: staf perlu tahu mengapa "
            "capnya tidak jadi dikoreksi."
        )

    sebelum = snapshot(permintaan)
    permintaan.status = status
    permintaan.tanggapan = catatan[:300]
    permintaan.ditangani_oleh = actor
    permintaan.ditangani_pada = timezone.now()
    permintaan.save(update_fields=["status", "tanggapan", "ditangani_oleh", "ditangani_pada"])

    log_event(
        action=AuditAction.CORRECTION,
        entity_type="absensi.PermintaanKoreksi",
        entity_id=permintaan.pk,
        entity_label=f"{permintaan.user} {permintaan.shift_date} permintaan {permintaan.get_status_display().lower()}",
        actor=actor,
        before=sebelum,
        after=snapshot(permintaan),
        reason=catatan,
    )
    return permintaan
