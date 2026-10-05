"""Menyusun jadwal jaga dari pola jam cap, untuk bulan yang rosternya belum terisi.

Dipakai untuk bulan seperti September 2026: capnya ada, tetapi jadwal jaganya tidak
ada di sistem dan PDF jadwal awal bulan terbukti tidak bisa dipercaya (17 hari Naya
tercatat di Jemur padahal jam capnya Citraland sepanjang bulan).

Perintah ini **tidak pernah menimpa** baris jadwal jaga yang sudah ada: roster tetap
sumber kebenaran bila ada. Ia hanya mengisi hari yang kosong, dan hanya bila polanya
mengarah ke satu cabang tanpa ragu. Hari yang tidak bisa diduga dibiarkan kosong
supaya tetap terlihat sebagai lubang, bukan ditutup dengan tebakan.

Bawaannya hanya menampilkan rencana. Tambahkan `--simpan` untuk benar-benar menulis.
"""
from __future__ import annotations

import calendar
import datetime as dt
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from absensi.models import AttendanceDevice, AttendancePunch
from absensi.perhitungan import duga_cabang
from audit.models import AuditAction
from audit.services import log_event
from core.models import Clinic
from jadwal.models import DutyRoster, DutyStatus


class Command(BaseCommand):
    help = "Menduga jadwal jaga satu bulan dari pola jam cap absensi."

    def add_arguments(self, parser):
        parser.add_argument("bulan", help="Format YYYY-MM, mis. 2026-09.")
        parser.add_argument(
            "--simpan", action="store_true",
            help="Tulis ke jadwal jaga. Tanpa ini hanya menampilkan rencana.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            tahun, bulan = (int(x) for x in options["bulan"].split("-"))
            mulai = dt.date(tahun, bulan, 1)
        except ValueError as exc:
            raise CommandError("Bulan harus berformat YYYY-MM, mis. 2026-09.") from exc
        selesai = dt.date(tahun, bulan, calendar.monthrange(tahun, bulan)[1])

        cabang = list(Clinic.objects.filter(active=True))
        if len(cabang) < 2:
            raise CommandError("Dugaan pola butuh minimal dua cabang aktif dengan jam berbeda.")

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

        usul: list[tuple[int, dt.date, Clinic]] = []
        gagal: list[tuple[str, dt.date, str, str, str]] = []
        dilewati = 0

        for (uid, tanggal), caps in sorted(per_hari.items(), key=lambda kv: (kv[0][1], str(kv[0][0]))):
            if (uid, tanggal) in sudah_ada:
                dilewati += 1
                continue
            caps.sort(key=lambda c: c.occurred_at)
            masuk = caps[0].occurred_at
            keluar = caps[-1].occurred_at if len(caps) > 1 else None
            duga, alasan = duga_cabang(masuk, keluar, tanggal, cabang)
            if duga is None:
                gagal.append((
                    orang[uid].username, tanggal,
                    timezone.localtime(masuk).strftime("%H.%M"),
                    timezone.localtime(keluar).strftime("%H.%M") if keluar else "--",
                    alasan,
                ))
                continue
            usul.append((uid, tanggal, duga))

        # Cabang asal ditebak dari cabang yang paling sering muncul pada bulan itu.
        # Hanya dipakai saat seseorang mengecap di hari off, jadi perkiraan cukup.
        asal: dict[int, Clinic] = {}
        for uid in {u for u, _, _ in usul}:
            hitung = Counter(c.pk for u, _, c in usul if u == uid)
            asal[uid] = next(c for c in cabang if c.pk == hitung.most_common(1)[0][0])

        self.stdout.write(self.style.MIGRATE_HEADING(f"Dugaan jadwal jaga {mulai:%B %Y}"))
        self.stdout.write(f"  Hari dengan cap        : {len(per_hari)}")
        self.stdout.write(f"  Sudah ada di jadwal    : {dilewati} (tidak disentuh)")
        self.stdout.write(f"  Bisa diduga            : {len(usul)}")
        self.stdout.write(f"  Tidak bisa diduga      : {len(gagal)}")

        per_orang = Counter()
        for uid, _, duga in usul:
            per_orang[(orang[uid].username, duga.name)] += 1
        if per_orang:
            self.stdout.write("\n  Rencana per staf:")
            for (nama, cab), n in sorted(per_orang.items()):
                self.stdout.write(f"    {nama:10} {cab:24} {n:2} hari")

        if gagal:
            self.stdout.write(self.style.WARNING(f"\n  {len(gagal)} hari dibiarkan kosong:"))
            for nama, tanggal, mk, kl, alasan in gagal:
                sebab = "cocok lebih dari satu cabang" if alasan == "GANDA" else "polanya tidak cocok cabang mana pun"
                self.stdout.write(f"    {nama:10} {tanggal} {mk}-{kl}  {sebab}")

        if not options["simpan"]:
            self.stdout.write(self.style.SUCCESS("\nRencana saja. Tambahkan --simpan untuk menulis."))
            transaction.set_rollback(True)
            return

        DutyRoster.objects.bulk_create([
            DutyRoster(
                user_id=uid, date=tanggal, clinic=duga, home_clinic=asal[uid],
                status=DutyStatus.MASUK,
                note="Diduga dari pola jam cap absensi; belum dikonfirmasi.",
            )
            for uid, tanggal, duga in usul
        ])
        log_event(
            action=AuditAction.CREATE,
            entity_type="jadwal.DutyRoster",
            entity_label=f"dugaan dari absensi {mulai:%Y-%m}",
            after={"dibuat": len(usul), "dilewati": dilewati, "gagal": len(gagal)},
        )
        self.stdout.write(self.style.SUCCESS(f"\n{len(usul)} baris jadwal jaga dibuat dari dugaan."))
        self.stdout.write(
            "Setiap baris bercatat \"belum dikonfirmasi\". Tinjau di Jadwal Jaga sebelum "
            "papan skor dipakai menilai."
        )
