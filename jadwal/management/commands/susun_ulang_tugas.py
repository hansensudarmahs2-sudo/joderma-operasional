"""Susun ulang porsi tugas otomatis untuk rentang tanggal; porsi manual dipertahankan.

    python manage.py susun_ulang_tugas --cabang jemur --mulai 2026-10-04 --sampai 2026-10-31

Dipakai sesudah peran staf berubah (mis. peran Koordinator Shift dicabut), supaya porsi yang
butuh peran itu tidak lagi jatuh ke orang tersebut. Sama dengan tombol Susun ulang otomatis,
tetapi bisa dibatasi mulai tanggal tertentu.
"""
import datetime as dt

from django.core.management.base import BaseCommand, CommandError

from core.models import Clinic
from core.services import clinic_key
from jadwal.services import plan_range


class Command(BaseCommand):
    help = "Susun ulang porsi tugas otomatis untuk satu cabang dan rentang tanggal."

    def add_arguments(self, parser):
        parser.add_argument("--cabang", required=True, help="jemur, citraland, atau kode cabang")
        parser.add_argument("--mulai", required=True)
        parser.add_argument("--sampai", required=True)

    def handle(self, cabang, mulai, sampai, **opts):
        key = cabang.lower()
        clinics = [c for c in Clinic.objects.all()
                   if key in (c.code.lower(), clinic_key(c)) or clinic_key(c).startswith(key)]
        if len(clinics) != 1:
            raise CommandError(f"Cabang '{cabang}' cocok dengan {len(clinics)} cabang.")
        try:
            start, end = dt.date.fromisoformat(mulai), dt.date.fromisoformat(sampai)
        except ValueError:
            raise CommandError("Tanggal harus YYYY-MM-DD.")
        if end < start:
            raise CommandError("Tanggal sampai sebelum tanggal mulai.")
        n = plan_range(clinics[0], start, end)
        self.stdout.write(f"{clinics[0].name} {start}–{end}: {n} porsi otomatis disusun ulang.")
