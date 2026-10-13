"""Hapus foto laporan kegiatan yang lewat masa simpan; uraiannya tetap.

Foto wajah adalah data pribadi. Menyimpannya selamanya tanpa alasan sulit
dipertanggungjawabkan, dan `docs/absensi-jam-kerja.md` bagian 8 sudah menetapkan bahwa
fitur berfoto perlu masa simpan beserta penghapusan otomatis. Masa simpannya **90 hari**
(keputusan product owner 13 Okt 2026).

Yang dihapus hanya berkas fotonya dan baris lampirannya; `LaporanKegiatan` beserta
uraian, waktu, dan lokasinya tetap, supaya riwayat pekerjaan tidak ikut hilang. Laporan
yang fotonya sudah dihapus ditandai `foto_dihapus_pada`, sehingga "tidak ada foto" bisa
dibedakan dari "fotonya sudah lewat masa simpan".

Dijalankan berkala, mis. lewat cron harian:

    0 3 * * * cd ~/joderma-ops && docker compose exec -T app python manage.py hapus_foto_kegiatan

Aman diulang: laporan yang sudah ditandai tidak diperiksa lagi.
"""
from __future__ import annotations

import datetime as dt

from django.core.management.base import BaseCommand
from django.utils import timezone

from audit.models import AuditAction
from audit.services import log_event
from core.models import Attachment
from reports.kegiatan import HARI_SIMPAN_FOTO
from reports.models import LaporanKegiatan


class Command(BaseCommand):
    help = "Hapus foto laporan kegiatan yang lebih tua dari masa simpan (bawaan 90 hari)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hari", type=int, default=HARI_SIMPAN_FOTO,
            help=f"Masa simpan foto dalam hari (bawaan {HARI_SIMPAN_FOTO}).",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Tampilkan yang akan dihapus tanpa menghapus apa pun.",
        )

    def handle(self, *args, **options):
        hari = options["hari"]
        batas = timezone.now() - dt.timedelta(days=hari)
        lama = LaporanKegiatan.objects.filter(
            created_at__lt=batas, foto_dihapus_pada__isnull=True
        )
        if not lama.exists():
            self.stdout.write(f"Tidak ada laporan kegiatan lebih tua dari {hari} hari yang masih berfoto.")
            return

        total_laporan = total_foto = 0
        for laporan in lama:
            lampiran = list(
                Attachment.objects.filter(entity_type="laporan_kegiatan", entity_id=laporan.pk)
            )
            if options["dry_run"]:
                if lampiran:
                    self.stdout.write(
                        f"  akan dihapus: {len(lampiran)} foto · {laporan.created_at:%Y-%m-%d} · {laporan.user}"
                    )
                    total_laporan += 1
                    total_foto += len(lampiran)
                continue

            for a in lampiran:
                a.file.delete(save=False)
                a.delete()
            # Ditandai walau tidak berfoto, supaya tidak diperiksa ulang tiap hari.
            laporan.foto_dihapus_pada = timezone.now()
            laporan.save(update_fields=["foto_dihapus_pada"])
            if lampiran:
                total_laporan += 1
                total_foto += len(lampiran)

        if options["dry_run"]:
            self.stdout.write(f"Rencana: {total_foto} foto dari {total_laporan} laporan (tidak ada yang dihapus).")
            return

        if total_foto:
            log_event(
                action=AuditAction.ARCHIVE,
                entity_type="reports.LaporanKegiatan",
                entity_label=f"Hapus {total_foto} foto laporan kegiatan lewat {hari} hari",
                after={"foto": total_foto, "laporan": total_laporan, "hari": hari},
            )
        self.stdout.write(
            self.style.SUCCESS(f"{total_foto} foto dari {total_laporan} laporan dihapus; uraiannya tetap.")
        )
