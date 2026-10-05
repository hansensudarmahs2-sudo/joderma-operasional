"""Memetakan ID mesin sidik jari ke user.

Nomor di mesin tidak sama dengan username, dan sebagian ejaannya berbeda: "Heny" di
mesin adalah user `heni`, "Agustin" adalah `nanda`, "Nadiya" adalah `naya`, "Rahayu"
adalah `ayu`. Pemetaan awal ini berasal dari ekspor September 2026; setelah dibuat,
perubahannya lewat admin, bukan dengan mengedit berkas ini.

Izul, Isya, dan Lina tidak ada di jadwal jaga dua cabang, jadi jam shift-nya tidak
diketahui dan skornya tidak berarti. Keputusan product owner (D1, Okt 2026): capnya
tetap direkam, tetapi tidak dinilai. User mereka dibuat **nonaktif dan tanpa peran**
— cukup untuk menautkan cap, tidak cukup untuk masuk aplikasi.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from absensi.models import AttendanceDevice
from accounts.models import User

# (ID di mesin, nama di mesin, username)
PEMETAAN = [
    ("4", "Heny", "heni"),
    ("5", "Desy", "desy"),
    ("7", "Yani", "yani"),
    ("8", "Luki", "luki"),
    ("10", "Arsi", "arsi"),
    ("11", "Rahayu", "ayu"),
    ("12", "Silvi", "silvi"),
    ("13", "Regita", "regitta"),
    ("14", "Agustin", "nanda"),
    ("15", "Alya", "alya"),
    ("16", "Lia", "lia"),
    ("17", "Elvira", "elvira"),
    ("18", "Nadiya", "naya"),
]

# D1: direkam saja. Tidak ada di jadwal jaga dua cabang, jadi tidak dinilai.
# (ID di mesin, nama di mesin, username, nama tampilan)
REKAM_SAJA = [
    ("2", "Izul", "izul", "Izul"),
    ("6", "Isya", "isya", "Isya"),
    ("9", "Lina", "lina", "Lina"),
]


class Command(BaseCommand):
    help = "Membuat pemetaan ID mesin sidik jari ke user (aman dijalankan berulang)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Tampilkan rencana tanpa menyimpan."
        )

    @transaction.atomic
    def handle(self, *args, **options):
        kering = options["dry_run"]
        dibuat = diperbarui = 0
        self.stdout.write("Staf yang dinilai:")
        for uid, label, username in PEMETAAN:
            user = User.objects.filter(username=username).first()
            if user is None:
                self.stderr.write(self.style.WARNING(f"  ID {uid} ({label}): user '{username}' tidak ada; dilewati."))
                continue
            alat = AttendanceDevice.objects.filter(device_uid=uid).first()
            if alat is None:
                self.stdout.write(f"  + ID {uid} {label} -> {username}")
                dibuat += 1
                if not kering:
                    AttendanceDevice.objects.create(device_uid=uid, device_label=label, user=user)
            elif alat.user_id != user.pk or alat.device_label != label:
                self.stdout.write(f"  ~ ID {uid} {label} -> {username} (sebelumnya {alat.device_label} -> {alat.user})")
                diperbarui += 1
                if not kering:
                    alat.device_label, alat.user = label, user
                    alat.save(update_fields=["device_label", "user"])

        self.stdout.write("Staf rekam-saja (capnya direkam, tidak dinilai):")
        for uid, label, username, nama in REKAM_SAJA:
            user = User.objects.filter(username=username).first()
            if user is None:
                self.stdout.write(f"  + user nonaktif '{username}' ({nama})")
                if not kering:
                    user = User.objects.create_user(
                        username=username, display_name=nama, is_active=False
                    )
                    user.set_unusable_password()
                    user.save(update_fields=["password"])
            if user is None:      # dry-run: belum ada user untuk ditautkan
                self.stdout.write(f"  + ID {uid} {label} -> {username} (rekam saja)")
                dibuat += 1
                continue
            alat = AttendanceDevice.objects.filter(device_uid=uid).first()
            if alat is None:
                self.stdout.write(f"  + ID {uid} {label} -> {username} (rekam saja)")
                dibuat += 1
                if not kering:
                    AttendanceDevice.objects.create(
                        device_uid=uid, device_label=label, user=user, recording_only=True,
                        note="Di luar jadwal jaga dua cabang; capnya direkam, tidak dinilai (D1).",
                    )
            elif not alat.recording_only:
                self.stdout.write(f"  ~ ID {uid} {label} ditandai rekam saja")
                diperbarui += 1
                if not kering:
                    alat.recording_only = True
                    alat.save(update_fields=["recording_only"])

        self.stdout.write(self.style.SUCCESS(f"{dibuat} dibuat, {diperbarui} diperbarui" + (" (dry-run)" if kering else "")))
        if kering:
            transaction.set_rollback(True)
