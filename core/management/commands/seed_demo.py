"""Seed data sintetis untuk demo/UAT. JANGAN gunakan data pasien nyata."""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Capability, Role, User, UserCapability, UserRole
from checklists.models import ChecklistArea, ChecklistTemplate, ChecklistTemplateItem, InputType
from core.models import Clinic
from issues.models import Asset, DamageCategory
from nurses.models import NurseEligibility, ProcedureCategory

DEMO_PASSWORD = "JoDermaDemo2026!"

USERS = [
    ("admin", "Admin Klinik", [Role.ADMIN], []),
    ("supervisor", "Sinta Supervisor", [Role.SUPERVISOR], [Capability.CASH_VIEW_AMOUNTS]),
    ("kasir1", "Kasih Front Desk", [Role.FRONT_DESK, Role.STAF], []),
    ("kasir2", "Kirana Front Desk", [Role.FRONT_DESK, Role.STAF], []),
    ("perawat1", "Nadia Perawat", [Role.PERAWAT, Role.STAF], []),
    ("perawat2", "Nur Perawat", [Role.PERAWAT, Role.STAF], []),
    ("perawat3", "Nina Perawat", [Role.PERAWAT, Role.STAF], []),
    ("owner", "Owner JoDerma", [Role.OWNER], [Capability.CASH_VIEW_AMOUNTS, Capability.AUDIT_VIEW]),
]

TEMPLATES = {
    ChecklistArea.AKSES_UMUM: [
        ("Pintu/akses klinik dibuka", "Akses", InputType.CEKLIS, None, ""),
        ("Area penerimaan siap dan bersih", "Kebersihan", InputType.CEKLIS, None, ""),
        ("Pencahayaan dan AC area umum berfungsi", "Fasilitas", InputType.CEKLIS, None, ""),
    ],
    ChecklistArea.KOMPUTER_SISTEM: [
        ("Komputer front desk menyala", "Perangkat", InputType.CEKLIS, None, ""),
        ("Printer dan jaringan siap", "Perangkat", InputType.CEKLIS, None, ""),
        ("Aplikasi kerja dapat diakses", "Sistem", InputType.CEKLIS, None, ""),
    ],
    ChecklistArea.RUANG_KONSULTASI: [
        ("Dermatoskop lengkap dan berfungsi", "Alat", InputType.CEKLIS, None, ""),
        ("Sarung tangan tersedia", "BHP", InputType.KUANTITAS, 20, "pasang"),
        ("Kasa steril tersedia", "BHP", InputType.KUANTITAS, 10, "pak"),
        ("Kebersihan ruang sesuai standar", "Kebersihan", InputType.CEKLIS, None, ""),
    ],
    ChecklistArea.RUANG_TINDAKAN: [
        ("Mesin laser berfungsi", "Alat", InputType.CEKLIS, None, ""),
        ("Alat bedah minor steril", "Alat", InputType.CEKLIS, None, ""),
        ("Alkohol swab tersedia", "BHP", InputType.KUANTITAS, 30, "pcs"),
        ("Wadah limbah medis tersedia", "Keselamatan", InputType.CEKLIS, None, ""),
    ],
}

PROCEDURES = [
    ("laser", "Laser"),
    ("peeling", "Chemical Peeling"),
    ("injeksi", "Filler & Botox"),
    ("acne", "Acne Care"),
]

ASSETS = [
    ("AST-001", "Mesin laser ruang tindakan", DamageCategory.ALAT_MEDIS, "Ruang tindakan"),
    ("AST-002", "Komputer front desk", DamageCategory.IT, "Front desk"),
    ("AST-003", "AC ruang tunggu", DamageCategory.FASILITAS, "Ruang tunggu"),
]


class Command(BaseCommand):
    help = "Membuat data demo sintetis (klinik, pengguna, template checklist, kategori tindakan, aset)."

    @transaction.atomic
    def handle(self, *args, **options):
        clinic, _ = Clinic.objects.get_or_create(
            code="jemur-andayani",
            defaults={
                "name": "JoDerma Jemur Andayani",
                "address": "Jl. Jemur Andayani XVIII No.34A, Surabaya",
                "open_time": "12:00",
                "close_time": "21:00",
            },
        )
        self.stdout.write(f"Klinik: {clinic}")

        for username, display, roles, caps in USERS:
            user, created = User.objects.get_or_create(
                username=username, defaults={"display_name": display}
            )
            if created:
                user.set_password(DEMO_PASSWORD)
                user.display_name = display
                user.is_staff = username == "admin"
                user.is_superuser = username == "admin"
                user.save()
            for role in roles:
                UserRole.objects.get_or_create(user=user, clinic=clinic, role=role)
            for cap in caps:
                UserCapability.objects.get_or_create(user=user, capability=cap)
            self.stdout.write(f"  pengguna {username} ({'baru' if created else 'ada'})")

        for area, items in TEMPLATES.items():
            template, created = ChecklistTemplate.objects.get_or_create(
                clinic=clinic,
                area=area,
                version=1,
                defaults={"name": dict(ChecklistArea.choices)[area], "active": True},
            )
            if created:
                for order, (label, category, input_type, minimum, unit) in enumerate(items, start=1):
                    ChecklistTemplateItem.objects.create(
                        template=template,
                        label=label,
                        category=category,
                        input_type=input_type,
                        min_quantity=minimum,
                        unit=unit,
                        required=True,
                        sort_order=order,
                    )
            self.stdout.write(f"  template {area} ({'baru' if created else 'ada'})")

        categories = []
        for code, name in PROCEDURES:
            cat, _ = ProcedureCategory.objects.get_or_create(
                clinic=clinic, code=code, defaults={"name": name}
            )
            categories.append(cat)

        nurses = User.objects.filter(user_roles__role=Role.PERAWAT).distinct()
        for nurse in nurses:
            for cat in categories:
                # perawat3 sengaja tidak eligible untuk laser (uji aturan eligibility)
                if nurse.username == "perawat3" and cat.code == "laser":
                    continue
                NurseEligibility.objects.get_or_create(nurse=nurse, category=cat)

        for code, name, category, location in ASSETS:
            Asset.objects.get_or_create(
                clinic=clinic, code=code, defaults={"name": name, "category": category, "location": location}
            )

        self.stdout.write(self.style.SUCCESS(f"Seed selesai. Password demo semua akun: {DEMO_PASSWORD}"))
