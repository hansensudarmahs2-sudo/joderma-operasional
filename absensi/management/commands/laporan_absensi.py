"""Papan skor jam kerja dan laporan pengecualian untuk satu periode."""
from __future__ import annotations

import calendar
import datetime as dt

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from absensi.perhitungan import AMBANG_DATANG_AWAL_MENIT, hitung_periode


def _jam(menit: int) -> str:
    tanda = "-" if menit < 0 else ""
    menit = abs(menit)
    return f"{tanda}{menit // 60}j{menit % 60:02d}m"


class Command(BaseCommand):
    help = "Papan skor absensi dan daftar hari yang perlu dicek, untuk satu bulan."

    def add_arguments(self, parser):
        parser.add_argument("bulan", help="Format YYYY-MM, mis. 2026-09.")
        parser.add_argument(
            "--pengecualian-saja", action="store_true", help="Hanya tampilkan hari yang perlu dicek."
        )

    def handle(self, *args, **options):
        try:
            tahun, bulan = (int(x) for x in options["bulan"].split("-"))
            mulai = dt.date(tahun, bulan, 1)
        except ValueError as exc:
            raise CommandError("Bulan harus berformat YYYY-MM, mis. 2026-09.") from exc
        selesai = dt.date(tahun, bulan, calendar.monthrange(tahun, bulan)[1])

        ringkasan = hitung_periode(mulai, selesai)
        if not ringkasan:
            raise CommandError(f"Tidak ada cap maupun jadwal jaga untuk {mulai:%B %Y}.")

        if not options["pengecualian_saja"]:
            self.stdout.write(self.style.MIGRATE_HEADING(f"Papan skor {mulai:%B %Y}"))
            self.stdout.write(
                f"{'Nama':14}{'hari':>5}{'terlambat':>11}{'lembur plg':>12}"
                f"{'awal>=' + str(AMBANG_DATANG_AWAL_MENIT) + 'm':>12}{'SKOR':>10}{'cek':>5}"
            )
            self.stdout.write("-" * 69)
            for s in ringkasan:
                self.stdout.write(
                    f"{str(s.user):14}{s.hari_kerja:>5}{_jam(-s.terlambat):>11}"
                    f"{_jam(s.lembur_pulang):>12}{_jam(s.datang_awal):>12}"
                    f"{_jam(s.skor):>10}{len(s.pengecualian) or '':>5}"
                )

        perlu = sorted(
            (h for s in ringkasan for h in s.pengecualian), key=lambda h: (h.tanggal, str(h.user))
        )
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(f"Perlu dicek: {len(perlu)} hari"))
        for h in perlu:
            jam = "—"
            if h.masuk or h.keluar:
                # Cap disimpan dalam UTC; tanpa localtime() jam 09.46 WIB tercetak 02.46.
                awal = f"{timezone.localtime(h.masuk):%H:%M}" if h.masuk else "??:??"
                akhir = f"{timezone.localtime(h.keluar):%H:%M}" if h.keluar else "??:??"
                jam = f"{awal}-{akhir}"
            label = ", ".join(str(p) for p in h.pengecualian)
            cabang = h.clinic.name if h.clinic else "—"
            self.stdout.write(f"  {h.tanggal} {str(h.user):10} {jam:12} {cabang:24} {label}")
            for catatan in h.catatan:
                self.stdout.write(f"       {catatan}")
