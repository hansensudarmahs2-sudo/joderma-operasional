"""Impor satu berkas ekspor .xlsx mesin sidik jari ("Kartu Laporan")."""
from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from absensi.parser import FileTidakDikenal
from absensi.services import impor_kartu_laporan
from accounts.models import User


class Command(BaseCommand):
    help = "Impor cap absensi dari ekspor .xlsx mesin sidik jari."

    def add_arguments(self, parser):
        parser.add_argument("berkas", help="Lokasi berkas .xlsx hasil ekspor mesin.")
        parser.add_argument("--actor", help="Username yang dicatat sebagai pengimpor.", default=None)

    def handle(self, *args, **options):
        jalur = Path(options["berkas"])
        if not jalur.is_file():
            raise CommandError(f"Berkas tidak ditemukan: {jalur}")
        actor = User.objects.filter(username=options["actor"]).first() if options["actor"] else None

        try:
            batch = impor_kartu_laporan(jalur.read_bytes(), jalur.name, actor=actor)
        except FileTidakDikenal as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(f"Periode     : {batch.period_start} s.d. {batch.period_end}")
        self.stdout.write(f"Baris hari  : {batch.rows_read}")
        self.stdout.write(f"Cap baru    : {batch.punches_created}")
        self.stdout.write(f"Sudah ada   : {batch.punches_skipped}")
        for pesan in batch.warnings:
            self.stdout.write(self.style.WARNING(f"  ! {pesan}"))
        self.stdout.write(self.style.SUCCESS("Impor selesai."))
