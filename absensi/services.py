"""Impor cap absensi dari ekspor mesin sidik jari.

Satu-satunya keputusan yang sulit di lapisan ini adalah menentukan *kapan* sebuah cap
terjadi. Mesin menuliskan jam dinding pada baris tanggal shift, sehingga pulang pukul
00.28 muncul di baris tanggal 4, bukan tanggal 5. Jam di bawah `BATAS_DINI_JAM`
karenanya dianggap milik hari kalender berikutnya, sementara `shift_date` tetap
tanggal baris itu. Tanpa ini, pulang 00.28 terhitung sebagai pulang paling awal
sepanjang bulan, bukan lembur 148 menit.

Jenis cap tidak ditebak-tebak: cap paling awal menjadi MASUK, paling akhir menjadi
KELUAR, dan bila satu hari hanya punya satu cap jenisnya TIDAK_PASTI. Lapisan
perhitungan yang memegang jadwal shift-lah yang menafsirkannya, dan melaporkannya
sebagai pengecualian.

Satu keterangan lagi ikut disimpan apa adanya: `tz_mesin`, jendela shift menurut
kolom tempat mesin menulis jam itu. Mesin mencatatnya sendiri, jadi ia bukan tebakan
dan tidak ditafsirkan di sini.
"""
from __future__ import annotations

import datetime as dt

from django.db import transaction
from django.utils import timezone

from audit.models import AuditAction
from audit.services import log_event

from . import parser
from .models import AttendanceDevice, AttendanceImport, AttendancePunch, JenisCap, SumberCap

# Sejalan dengan `core.models.late_close_cutoff_hour` (bawaan 06.00): penutupan boleh
# molor melewati tengah malam, dan yang terjadi sebelum jam ini masih milik hari kemarin.
BATAS_DINI_JAM = 6


def waktu_cap(tanggal: dt.date, jam: dt.time, batas_dini_jam: int = BATAS_DINI_JAM) -> dt.datetime:
    """Jam dinding pada baris tanggal shift menjadi waktu mutlak.

    Jam sebelum `batas_dini_jam` berarti cap itu jatuh pada hari kalender berikutnya.
    """
    hari = tanggal + dt.timedelta(days=1) if jam.hour < batas_dini_jam else tanggal
    return timezone.make_aware(dt.datetime.combine(hari, jam))


def _jenis(urutan: int, jumlah: int) -> str:
    if jumlah == 1:
        return JenisCap.TIDAK_PASTI
    if urutan == 0:
        return JenisCap.MASUK
    if urutan == jumlah - 1:
        return JenisCap.KELUAR
    return JenisCap.TIDAK_PASTI


@transaction.atomic
def impor_kartu_laporan(
    data: bytes,
    nama_file: str = "",
    *,
    actor=None,
    batas_dini_jam: int = BATAS_DINI_JAM,
) -> AttendanceImport:
    """Baca satu berkas ekspor dan simpan capnya. Aman diulang: cap yang sama dilewati."""
    hasil = parser.baca(data, nama_file)
    peringatan = list(hasil.peringatan)

    sebelumnya = AttendanceImport.objects.filter(checksum=hasil.checksum).first()
    if sebelumnya is not None:
        peringatan.append(
            f"Berkas dengan isi sama sudah diimpor pada {timezone.localtime(sebelumnya.imported_at):%d %b %Y %H:%M}."
        )

    batch = AttendanceImport.objects.create(
        file_name=nama_file or "(tanpa nama)",
        checksum=hasil.checksum,
        period_start=hasil.mulai,
        period_end=hasil.selesai,
        imported_by=actor if actor and getattr(actor, "pk", None) else None,
    )

    perangkat = {d.device_uid: d for d in AttendanceDevice.objects.select_related("user")}
    baris_terbaca = dibuat = dilewati = 0
    calon: list[AttendancePunch] = []

    for kartu in hasil.kartu:
        alat = perangkat.get(kartu.device_uid)
        if alat is None:
            peringatan.append(
                f"ID {kartu.device_uid} ({kartu.device_label or 'tanpa nama'}) belum dipetakan ke staf; "
                f"{sum(1 for h in kartu.hari if h.jam)} hari tidak diimpor."
            )
            continue
        if not alat.active:
            peringatan.append(f"ID {kartu.device_uid} ditandai tidak aktif; dilewati.")
            continue
        if kartu.device_label and alat.device_label and kartu.device_label != alat.device_label:
            peringatan.append(
                f"ID {kartu.device_uid}: nama di berkas '{kartu.device_label}' berbeda dari "
                f"pemetaan '{alat.device_label}' (staf {alat.user}). Periksa apakah ID berpindah orang."
            )

        for harian in kartu.hari:
            if not harian.jam:
                continue
            baris_terbaca += 1
            waktu = sorted(
                (waktu_cap(harian.tanggal, c.jam, batas_dini_jam), c.timezone) for c in harian.cap
            )
            catatan = ", ".join(p for p in harian.penanda if p.strip().lower() != parser.LABEL_ABSEN)
            for urutan, (saat, tz) in enumerate(waktu):
                calon.append(
                    AttendancePunch(
                        user=alat.user,
                        shift_date=harian.tanggal,
                        occurred_at=saat,
                        kind=_jenis(urutan, len(waktu)),
                        tz_mesin=tz,
                        source=SumberCap.FINGERPRINT,
                        device=alat,
                        import_batch=batch,
                        note=catatan[:200],
                    )
                )

    if calon:
        sudah = set(
            AttendancePunch.objects.filter(
                user__in={c.user_id for c in calon},
                occurred_at__in={c.occurred_at for c in calon},
            ).values_list("user_id", "occurred_at")
        )
        baru = [c for c in calon if (c.user_id, c.occurred_at) not in sudah]
        dilewati = len(calon) - len(baru)
        AttendancePunch.objects.bulk_create(baru)
        dibuat = len(baru)

    batch.rows_read = baris_terbaca
    batch.punches_created = dibuat
    batch.punches_skipped = dilewati
    batch.warnings = peringatan
    batch.save(update_fields=["rows_read", "punches_created", "punches_skipped", "warnings"])

    log_event(
        action=AuditAction.MIGRATION_IMPORT,
        entity_type="absensi.AttendanceImport",
        entity_id=batch.pk,
        entity_label=batch.file_name,
        actor=actor,
        after={
            "periode": f"{hasil.mulai} s.d. {hasil.selesai}",
            "baris_hari": baris_terbaca,
            "cap_baru": dibuat,
            "cap_sudah_ada": dilewati,
            "peringatan": len(peringatan),
        },
    )
    return batch
