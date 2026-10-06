"""Menyusun jadwal jaga dari data absensi, untuk bulan yang rosternya belum terisi.

Logikanya ada di `absensi.services.susun_jadwal_dari_absensi`; perintah ini hanya
menampilkannya di terminal. Tindakan yang sama tersedia di halaman Absensi, tab
"Impor berkas", untuk yang tidak memakai terminal.

Bawaannya hanya menampilkan rencana. Tambahkan `--simpan` untuk benar-benar menulis.
"""
from __future__ import annotations

import calendar
import datetime as dt

from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from absensi.services import susun_jadwal_dari_absensi
from accounts.models import User


class Command(BaseCommand):
    help = "Menyusun jadwal jaga satu bulan dari data absensi."

    def add_arguments(self, parser):
        parser.add_argument("bulan", help="Format YYYY-MM, mis. 2026-09.")
        parser.add_argument("--simpan", action="store_true", help="Tulis ke jadwal jaga.")
        parser.add_argument("--actor", default=None, help="Username yang dicatat di audit.")

    def handle(self, *args, **options):
        try:
            tahun, bulan = (int(x) for x in options["bulan"].split("-"))
            mulai = dt.date(tahun, bulan, 1)
        except ValueError as exc:
            raise CommandError("Bulan harus berformat YYYY-MM, mis. 2026-09.") from exc
        selesai = dt.date(tahun, bulan, calendar.monthrange(tahun, bulan)[1])
        actor = User.objects.filter(username=options["actor"]).first() if options["actor"] else None

        hasil = susun_jadwal_dari_absensi(
            mulai, selesai, simpan=options["simpan"], actor=actor
        )
        if not hasil.hari_bercap:
            raise CommandError(f"Tidak ada cap absensi untuk {mulai:%B %Y}.")

        self.stdout.write(self.style.MIGRATE_HEADING(f"Jadwal jaga dari absensi {mulai:%B %Y}"))
        self.stdout.write(f"  Hari dengan cap        : {hasil.hari_bercap}")
        self.stdout.write(f"  Sudah ada di jadwal    : {hasil.dilewati} (tidak disentuh)")
        self.stdout.write(f"  Terbaca dari mesin     : {hasil.dari_mesin}")
        self.stdout.write(f"  Diduga dari pola jam   : {hasil.dari_pola}")
        self.stdout.write(f"  Tidak bisa ditentukan  : {len(hasil.gagal)}")

        # Rincian per staf adalah yang paling layak diperiksa sebelum menulis: di sinilah
        # terlihat bila seseorang ditaruh di cabang yang tidak masuk akal.
        per_orang = Counter((str(u.user), u.clinic.name) for u in hasil.usul)
        if per_orang:
            self.stdout.write("\n  Rencana per staf:")
            for (nama, cab), n in sorted(per_orang.items()):
                self.stdout.write(f"    {nama:14} {cab:24} {n:2} hari")

        if hasil.gagal:
            self.stdout.write(self.style.WARNING("\n  Dibiarkan kosong:"))
            for user, tanggal, masuk, keluar, alasan in hasil.gagal:
                mk = timezone.localtime(masuk).strftime("%H.%M")
                kl = timezone.localtime(keluar).strftime("%H.%M") if keluar else "--"
                sebab = "cocok lebih dari satu cabang" if alasan == "GANDA" else "tidak cocok cabang mana pun"
                self.stdout.write(f"    {str(user):12} {tanggal} {mk}-{kl}  {sebab}")

        if not options["simpan"]:
            self.stdout.write(self.style.SUCCESS("\nRencana saja. Tambahkan --simpan untuk menulis."))
            return
        self.stdout.write(self.style.SUCCESS(f"\n{hasil.disimpan} baris jadwal jaga dibuat."))
        self.stdout.write('Setiap baris bercatat "belum dikonfirmasi". Tinjau di Jadwal Jaga.')
