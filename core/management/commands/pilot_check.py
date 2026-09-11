"""Verifikasi kesiapan data awal sebelum pilot/UAT (PRD 22).

Read-only: perintah ini tidak pernah mengubah data. Menjawab pertanyaan
"apakah klinik sudah siap menjalankan hari operasional di sistem ini?"

Pemakaian:
  manage.py pilot_check            # ringkasan
  manage.py pilot_check --strict   # exit code 1 bila ada blocker
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from accounts.models import Role, User
from checklists.models import ChecklistArea, ChecklistTemplate
from core.models import Clinic, ClinicConfig, DEFAULT_CONFIG
from nurses.models import NurseEligibility, ProcedureCategory


class Command(BaseCommand):
    help = "Cek kesiapan data awal untuk pilot/UAT (read-only)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Keluar dengan kode 1 bila ada blocker.",
        )

    def handle(self, *args, **options):
        blockers: list[str] = []
        warnings: list[str] = []
        notes: list[str] = []

        # 1. Klinik
        clinic = Clinic.objects.filter(active=True).order_by("id").first()
        if clinic is None:
            blockers.append("Belum ada klinik aktif.")
            self._render(blockers, warnings, notes)
            return self._exit(blockers, options)
        notes.append(f"Klinik aktif: {clinic.name} ({clinic.open_time}-{clinic.close_time})")

        # 2. Pengguna dan peran
        active_users = User.objects.filter(is_active=True)
        notes.append(f"Pengguna aktif: {active_users.count()}")
        for role, label in Role.choices:
            count = active_users.filter(user_roles__role=role, user_roles__clinic=clinic).distinct().count()
            if role in {Role.SUPERVISOR, Role.FRONT_DESK, Role.PERAWAT} and count == 0:
                blockers.append(f"Tidak ada pengguna aktif dengan peran {label}.")
            elif role == Role.FRONT_DESK and count < 2:
                warnings.append(
                    "Hanya 1 front desk aktif: dual-control kas hanya dapat "
                    "diselesaikan bila supervisor bertindak sebagai penghitung kedua."
                )
            notes.append(f"  {label}: {count}")

        shared = active_users.filter(display_name="").count()
        if shared:
            warnings.append(f"{shared} pengguna belum punya nama tampilan (audit sulit dibaca).")

        weak = [u.username for u in active_users if u.check_password("JoDermaDemo2026!")]
        if weak:
            blockers.append(
                "Akun masih memakai password demo: " + ", ".join(sorted(weak))
                + ". Ganti sebelum pilot dengan data nyata."
            )

        # 3. Template checklist
        for area, label in ChecklistArea.choices:
            template = (
                ChecklistTemplate.objects.filter(clinic=clinic, area=area, active=True)
                .order_by("-version")
                .first()
            )
            if template is None:
                blockers.append(f"Template checklist area '{label}' belum ada/aktif.")
                continue
            item_count = template.items.count()
            if item_count == 0:
                blockers.append(f"Template '{label}' v{template.version} tidak punya item.")
            else:
                notes.append(f"  Template {label}: v{template.version}, {item_count} item")

        # 4. Kategori tindakan dan eligibility perawat
        categories = ProcedureCategory.objects.filter(clinic=clinic, active=True)
        if not categories.exists():
            blockers.append("Belum ada kategori tindakan berkomisi.")
        else:
            notes.append(f"Kategori tindakan aktif: {categories.count()}")
            nurses = active_users.filter(user_roles__role=Role.PERAWAT).distinct()
            for cat in categories:
                eligible = NurseEligibility.objects.filter(
                    category=cat, active=True, nurse__in=nurses
                ).count()
                if eligible == 0:
                    blockers.append(
                        f"Tidak ada perawat eligible untuk kategori '{cat.name}'. "
                        "Setiap penugasan akan memerlukan override supervisor."
                    )
                else:
                    notes.append(f"  {cat.name}: {eligible} perawat eligible")

        # 5. Konfigurasi kebijakan
        overridden = {c.key for c in ClinicConfig.objects.filter(clinic=clinic)}
        notes.append(
            f"Konfigurasi: {len(overridden)} diubah dari default, "
            f"{len(DEFAULT_CONFIG) - len(overridden & set(DEFAULT_CONFIG))} memakai default"
        )
        denominations = ClinicConfig.get(clinic, "cash.denominations")
        if not denominations:
            blockers.append("Daftar pecahan uang kosong.")
        else:
            notes.append(f"  Pecahan uang: {len(denominations)} nilai")

        self._render(blockers, warnings, notes)
        return self._exit(blockers, options)

    def _render(self, blockers, warnings, notes):
        self.stdout.write(self.style.MIGRATE_HEADING("== Kesiapan data awal pilot =="))
        for n in notes:
            self.stdout.write(n)

        self.stdout.write("")
        if blockers:
            self.stdout.write(self.style.ERROR(f"BLOCKER ({len(blockers)}):"))
            for b in blockers:
                self.stdout.write(self.style.ERROR(f"  - {b}"))
        else:
            self.stdout.write(self.style.SUCCESS("Tidak ada blocker."))

        if warnings:
            self.stdout.write(self.style.WARNING(f"PERINGATAN ({len(warnings)}):"))
            for w in warnings:
                self.stdout.write(self.style.WARNING(f"  - {w}"))

    def _exit(self, blockers, options):
        if blockers and options.get("strict"):
            raise SystemExit(1)
        return None
