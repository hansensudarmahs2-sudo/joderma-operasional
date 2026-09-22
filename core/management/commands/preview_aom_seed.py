"""Preview seed organisasi AOM tanpa membuat akun produksi."""
from __future__ import annotations

from django.core.management.base import BaseCommand

from accounts.models import Role, User
from core.models import Clinic


REFERENCE_CLINICS = (
    ("jemur-andayani", "JoDerma Jemur Andayani"),
    ("citraland", "JoDerma Citraland"),
)

REFERENCE_PEOPLE = (
    ("hansen", "dr Hansen Sudarma", "Direktur Operasional", Role.AOM, None),
    ("heni", "Heni", "PIC Koordinator Shift", Role.PIC, "jemur-andayani"),
    ("desy", "Desy", "PIC Kasir dan Online", Role.PIC, "jemur-andayani"),
    ("elvira", "Elvira, Apt.", "PIC Kebersihan", Role.PIC, "jemur-andayani"),
)


class Command(BaseCommand):
    help = "Menampilkan preview cabang, role, dan PIC AOM tanpa menulis database."

    def handle(self, *args, **options):
        self.stdout.write("Preview seed AOM (dry-run, tidak membuat akun):")
        self.stdout.write("")
        self.stdout.write("Cabang:")
        for code, name in REFERENCE_CLINICS:
            exists = Clinic.objects.filter(code=code).exists()
            marker = "sudah ada" if exists else "akan dibuat saat seed disetujui"
            self.stdout.write(f"- {code}: {name} ({marker})")

        self.stdout.write("")
        self.stdout.write("Personel/role:")
        for username, display, title, role, clinic_code in REFERENCE_PEOPLE:
            exists = User.objects.filter(username=username).exists()
            scope = clinic_code or "lintas-cabang"
            marker = "akun sudah ada" if exists else "akun belum ada, perlu persetujuan"
            self.stdout.write(f"- {username}: {display} · {title} · {role} · {scope} ({marker})")

        self.stdout.write("")
        self.stdout.write("Tidak ada perubahan database. Gunakan hasil ini untuk review product owner.")
