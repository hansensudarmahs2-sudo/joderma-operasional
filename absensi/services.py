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
from dataclasses import dataclass, field

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


@dataclass
class UsulJadwal:
    """Satu baris jadwal jaga yang diusulkan dari data absensi."""

    user: object
    tanggal: dt.date
    clinic: object
    dari_mesin: bool


@dataclass
class HasilSusunJadwal:
    usul: list[UsulJadwal] = field(default_factory=list)
    gagal: list[tuple] = field(default_factory=list)   # (user, tanggal, masuk, keluar, alasan)
    hari_bercap: int = 0
    dilewati: int = 0          # sudah ada di jadwal jaga, tidak disentuh
    disimpan: int = 0

    @property
    def dari_mesin(self) -> int:
        return sum(1 for u in self.usul if u.dari_mesin)

    @property
    def dari_pola(self) -> int:
        return len(self.usul) - self.dari_mesin


def susun_jadwal_dari_absensi(
    mulai: dt.date, selesai: dt.date, *, simpan: bool = False, actor=None
) -> HasilSusunJadwal:
    """Menyusun jadwal jaga dari cap absensi untuk hari yang belum ada di jadwal.

    Urutan sumbernya: jendela shift yang dicatat mesin lebih dulu, baru dugaan pola
    jam. Baris jadwal jaga yang sudah ada **tidak pernah** disentuh — yang diisi
    manusia tetap menang. Hari yang tidak bisa ditentukan dibiarkan kosong supaya
    tetap terlihat sebagai lubang, bukan ditutup dengan tebakan.
    """
    from collections import Counter, defaultdict

    from core.models import Clinic
    from jadwal.models import DutyRoster, DutyStatus

    from .perhitungan import cabang_dari_timezone, duga_cabang

    cabang = list(Clinic.objects.filter(active=True))
    hasil = HasilSusunJadwal()
    if len(cabang) < 2:
        return hasil

    rekam_saja = set(
        AttendanceDevice.objects.filter(recording_only=True).values_list("user_id", flat=True)
    )
    sudah_ada = {
        (r.user_id, r.date)
        for r in DutyRoster.objects.filter(date__range=(mulai, selesai)).only("user_id", "date")
    }

    per_hari: dict[tuple[int, dt.date], list[AttendancePunch]] = defaultdict(list)
    orang: dict[int, object] = {}
    for p in AttendancePunch.objects.filter(
        shift_date__range=(mulai, selesai)
    ).select_related("user"):
        if p.user_id in rekam_saja:
            continue
        per_hari[(p.user_id, p.shift_date)].append(p)
        orang[p.user_id] = p.user
    hasil.hari_bercap = len(per_hari)

    for (uid, tanggal), caps in sorted(per_hari.items(), key=lambda kv: (kv[0][1], str(kv[0][0]))):
        if (uid, tanggal) in sudah_ada:
            hasil.dilewati += 1
            continue
        caps.sort(key=lambda c: c.occurred_at)
        masuk = caps[0].occurred_at
        keluar = caps[-1].occurred_at if len(caps) > 1 else None
        tz = next((c.tz_mesin for c in reversed(caps) if c.tz_mesin), "")
        pilih = cabang_dari_timezone(tz, cabang)
        dari_mesin = pilih is not None
        alasan = "MESIN"
        if pilih is None:
            pilih, alasan = duga_cabang(masuk, keluar, tanggal, cabang)
        if pilih is None:
            hasil.gagal.append((orang[uid], tanggal, masuk, keluar, alasan))
            continue
        hasil.usul.append(UsulJadwal(orang[uid], tanggal, pilih, dari_mesin))

    if not simpan or not hasil.usul:
        return hasil

    # Cabang asal diambil dari cabang tersering orang itu pada bulan tersebut; hanya
    # dipakai bila ia mengecap pada hari off, jadi perkiraan sudah cukup.
    asal: dict[int, object] = {}
    for u in hasil.usul:
        asal.setdefault(u.user.pk, Counter())[u.clinic.pk] += 1
    asal = {
        uid: next(c for c in cabang if c.pk == hitung.most_common(1)[0][0])
        for uid, hitung in asal.items()
    }
    DutyRoster.objects.bulk_create([
        DutyRoster(
            user=u.user, date=u.tanggal, clinic=u.clinic, home_clinic=asal[u.user.pk],
            status=DutyStatus.MASUK,
            note="Dari absensi (jendela shift mesin / pola jam); belum dikonfirmasi.",
        )
        for u in hasil.usul
    ])
    hasil.disimpan = len(hasil.usul)
    log_event(
        action=AuditAction.CREATE,
        entity_type="jadwal.DutyRoster",
        entity_label=f"disusun dari absensi {mulai:%Y-%m}",
        actor=actor,
        after={
            "dibuat": hasil.disimpan, "dari_mesin": hasil.dari_mesin,
            "dari_pola": hasil.dari_pola, "dilewati": hasil.dilewati, "gagal": len(hasil.gagal),
        },
    )
    return hasil
