"""Kembalikan akun standar ke peran dan PIC default (sama dengan tombol di halaman Admin).

    manage.py seed_staf_cabang --dry-run
    manage.py seed_staf_cabang --password klinik123 --prune

Definisi akun ada di `accounts/peran_standar.py` (manajemen) dan `jadwal/staff.py` (staf).
- Akun yang belum ada dibuat dengan `--password` dan wajib ganti password saat login.
- Password akun yang sudah ada tidak diubah; data tidak disentuh.
- Tanpa `--prune` hanya menambah yang kurang. Dengan `--prune` peran di luar definisi
  dicabut dan PIC di luar definisi diakhiri (reset penuh, sama dengan tombol Admin).
"""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.peran_standar import DEFAULT_PASSWORD, apply_plan, build_plan, describe


class Command(BaseCommand):
    help = "Peran, cabang, dan PIC akun standar (staf dua cabang, Owner, Direktur Utama, Direktur, Admin)."

    def add_arguments(self, parser):
        parser.add_argument("--password", default=DEFAULT_PASSWORD, help="Password awal untuk akun baru.")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--prune", action="store_true", help="Cabut peran dan akhiri PIC di luar definisi.")

    def handle(self, *args, password=DEFAULT_PASSWORD, dry_run=False, prune=False, **opts):
        try:
            plans, clinics = build_plan(remove_extras=prune)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages))
        for key, clinic in clinics.items():
            self.stdout.write(f"cabang {key} = {clinic.code} ({clinic.name})")
        for plan in plans:
            lines = describe(plan)
            if lines:
                self.stdout.write(f"{plan.username}:")
                for line in lines:
                    self.stdout.write(f"  {line}")
        if dry_run:
            self.stdout.write(self.style.WARNING("Dry-run: tidak ada yang disimpan."))
            return
        with transaction.atomic():
            n = apply_plan(plans, password=password)
        self.stdout.write(self.style.SUCCESS(f"Selesai: {n} akun berubah."))
