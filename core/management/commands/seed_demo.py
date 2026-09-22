"""Seed data sintetis untuk demo/UAT. JANGAN gunakan data pasien nyata."""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Capability, Role, User, UserCapability, UserRole
from checklists.models import (
    ChecklistArea,
    ChecklistSession,
    ChecklistTemplate,
    ChecklistTemplateItem,
    InputType,
)
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
    ("apoteker1", "Ayu Apoteker", [Role.APOTEKER, Role.STAF], []),
    ("asisten_apoteker1", "Ari Asisten Apoteker", [Role.ASISTEN_APOTEKER, Role.STAF], []),
    ("online1", "Oni Online", [Role.ONLINE, Role.STAF], []),
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


def _item(label, category="Operasional", *, input_type=InputType.CEKLIS, unit="", performer=(), verifier=(), help_text="", options=()):
    return {
        "label": label,
        "category": category,
        "input_type": input_type,
        "unit": unit,
        "options": list(options),
        "performer_roles": list(performer),
        "verifier_roles": list(verifier),
        "help_text": help_text,
    }


ROLE_TEMPLATES = [
    {
        "key": "KS_OPENING",
        "name": "Koordinator Shift — buka shift",
        "area": ChecklistArea.AKSES_UMUM,
        "session": ChecklistSession.OPENING,
        "roles": [Role.SUPERVISOR],
        "items": [
            _item("Komputer menyala & berfungsi", "Sistem", performer=(Role.SUPERVISOR,)),
            _item("Jaringan internet", "Sistem", performer=(Role.SUPERVISOR,)),
            _item("Koneksi ke Omnicare / Sehati", "Sistem", performer=(Role.SUPERVISOR,)),
            _item("AC & lampu seluruh ruangan", "Sarana", performer=(Role.SUPERVISOR,)),
            _item("Tidak ada sarana rusak", "Sarana", performer=(Role.SUPERVISOR,)),
            _item("Papan giliran asistensi & istirahat terpasang", "Alur", performer=(Role.SUPERVISOR,)),
            _item("APAR: ada, tekanan OK, tidak terhalang", "Keselamatan", performer=(Role.SUPERVISOR,)),
            _item("Nomor kontak darurat terpasang", "Keselamatan", performer=(Role.SUPERVISOR,)),
            _item("Hitung uang modal awal — nominal dicatat", "Keuangan", input_type=InputType.KUANTITAS, unit="Rp", performer=(Role.FRONT_DESK,), verifier=(Role.SUPERVISOR,)),
            _item("Kebersihan resepsionis & ruang tunggu", "Kebersihan", performer=(Role.ONLINE,), verifier=(Role.SUPERVISOR,)),
            _item("Kebersihan ruang konsultasi & facial", "Kebersihan", performer=(Role.ONLINE,), verifier=(Role.SUPERVISOR,)),
            _item("Toilet, wastafel, area staf", "Kebersihan", performer=(Role.ONLINE,), verifier=(Role.SUPERVISOR,)),
            _item("Oksigen: ada, isi cukup, regulator berfungsi", "Emergensi", performer=(Role.PERAWAT,), verifier=(Role.SUPERVISOR,)),
            _item("Safety box tidak lebih dari ¾ penuh", "Limbah", performer=(Role.PERAWAT,), verifier=(Role.SUPERVISOR,)),
            _item("Pemisahan sampah medis — non medis", "Limbah", performer=(Role.PERAWAT,), verifier=(Role.SUPERVISOR,)),
            _item("Serah-terima daftar tindakan ke perawat", "Alur pasien", performer=(Role.ONLINE,), verifier=(Role.SUPERVISOR,)),
            _item("Alat & bahan siap sesuai tindakan terjadwal", "Alur pasien", performer=(Role.PERAWAT,), verifier=(Role.SUPERVISOR,)),
        ],
    },
    {
        "key": "KS_CLOSING", "name": "Koordinator Shift — tutup shift", "area": ChecklistArea.AKSES_UMUM,
        "session": ChecklistSession.CLOSING, "roles": [Role.SUPERVISOR],
        "items": [
            _item("Hitung uang kas tutup — nominal dicatat", "Keuangan", input_type=InputType.KUANTITAS, unit="Rp", performer=(Role.FRONT_DESK,), verifier=(Role.SUPERVISOR,)),
            _item("Rekonsiliasi buku transaksi besar vs Omnicare", "Keuangan", performer=(Role.FRONT_DESK,), verifier=(Role.SUPERVISOR,)),
            _item("Settlement EDC akhir hari", "Keuangan", performer=(Role.FRONT_DESK,), verifier=(Role.SUPERVISOR,)),
            _item("Semua device & autoclave dimatikan", "Penutupan", performer=(Role.PERAWAT,), verifier=(Role.SUPERVISOR,)),
            _item("AC, lampu, komputer dimatikan", "Penutupan", performer=(Role.SUPERVISOR,)),
            _item("Pintu & akses terkunci", "Penutupan", performer=(Role.SUPERVISOR,)),
            _item("Rekap temuan semua peran → Operation Manager", "Pelaporan", performer=(Role.SUPERVISOR,)),
        ],
    },
    {
        "key": "KSR_OPENING", "name": "Kasir — buka kasir", "area": ChecklistArea.AKSES_UMUM,
        "session": ChecklistSession.OPENING, "roles": [Role.FRONT_DESK],
        "items": [
            _item("Hitung uang modal awal — tulis nominal", "Kasir", input_type=InputType.KUANTITAS, unit="Rp", performer=(Role.FRONT_DESK,), verifier=(Role.SUPERVISOR,)),
            _item("Komposisi pecahan kembalian minimum Rp200.000", "Kasir", input_type=InputType.KUANTITAS, unit="Rp", performer=(Role.FRONT_DESK,), verifier=(Role.SUPERVISOR,)),
            _item("EDC berfungsi & kertas EDC cukup", "Kasir", performer=(Role.FRONT_DESK,)),
            _item("QRIS berfungsi", "Kasir", performer=(Role.FRONT_DESK,)),
            _item("Kertas printer nota cukup", "Kasir", performer=(Role.FRONT_DESK,)),
        ],
    },
    {
        "key": "KSR_CLOSING", "name": "Kasir — tutup kasir", "area": ChecklistArea.AKSES_UMUM,
        "session": ChecklistSession.CLOSING, "roles": [Role.FRONT_DESK],
        "items": [
            _item("Hitung uang kas akhir — tulis nominal", "Kasir", input_type=InputType.KUANTITAS, unit="Rp", performer=(Role.FRONT_DESK,), verifier=(Role.SUPERVISOR,)),
            _item("Rekonsiliasi buku transaksi besar vs Omnicare", "Kasir", performer=(Role.FRONT_DESK,), verifier=(Role.SUPERVISOR,)),
            _item("Settlement EDC akhir hari", "Kasir", performer=(Role.FRONT_DESK,), verifier=(Role.SUPERVISOR,)),
            _item("Catat selisih lebih/kurang apa adanya", "Kasir", input_type=InputType.KUANTITAS, unit="Rp", performer=(Role.FRONT_DESK,), verifier=(Role.SUPERVISOR,), help_text="Jangan ditutup dengan uang pribadi."),
            _item("Serahkan setoran kepada", "Kasir", performer=(Role.FRONT_DESK,), verifier=(Role.SUPERVISOR,)),
        ],
    },
    {
        "key": "APT_OPENING", "name": "Apoteker — buka shift", "area": ChecklistArea.RUANG_KONSULTASI,
        "session": ChecklistSession.OPENING, "roles": [Role.APOTEKER],
        "items": [
            _item("Stok gudang farmasi & consumable", "Stok", performer=(Role.APOTEKER,)),
            _item("Kadaluwarsa obat & bahan — rotasi FEFO", "Stok", performer=(Role.APOTEKER,)),
            _item("Cold chain — suhu kulkas dicatat", "Cold chain", input_type=InputType.KUANTITAS, unit="°C", performer=(Role.APOTEKER,)),
            _item("Sterile pouch: tanggal ED & indikator steril", "Sterilisasi", performer=(Role.APOTEKER,)),
            _item("Lemari obat dibuka — kunci dipegang siapa", "Keamanan obat", performer=(Role.APOTEKER,)),
            _item("Isi laci ruang konsultasi — jumlah dicatat perawat", "Verifikasi stok", input_type=InputType.KUANTITAS, unit="item", performer=(Role.PERAWAT,), verifier=(Role.APOTEKER,)),
            _item("Isi ruang facial — jumlah dicatat perawat", "Verifikasi stok", input_type=InputType.KUANTITAS, unit="item", performer=(Role.PERAWAT,), verifier=(Role.APOTEKER,)),
        ],
    },
    {
        "key": "APT_CLOSING", "name": "Apoteker — tutup shift", "area": ChecklistArea.RUANG_KONSULTASI,
        "session": ChecklistSession.CLOSING, "roles": [Role.APOTEKER],
        "items": [_item("Lemari obat terkunci", "Penutupan", performer=(Role.APOTEKER,))],
    },
    {
        "key": "ONL_OPENING", "name": "Online & Reservasi — sebelum pasien pertama", "area": ChecklistArea.AKSES_UMUM,
        "session": ChecklistSession.OPENING, "roles": [Role.ONLINE],
        "items": [
            _item("Kebersihan resepsionis & ruang tunggu", "Kebersihan", performer=(Role.ONLINE,), verifier=(Role.SUPERVISOR,)),
            _item("Kebersihan ruang konsultasi & ruang facial", "Kebersihan", performer=(Role.ONLINE,), verifier=(Role.SUPERVISOR,)),
            _item("Toilet, wastafel, area staf", "Kebersihan", performer=(Role.ONLINE,), verifier=(Role.SUPERVISOR,)),
            _item("Handrub & sabun terisi", "Kebersihan", performer=(Role.ONLINE,), verifier=(Role.PERAWAT,)),
            _item("Linen bersih tersedia", "Kebersihan", performer=(Role.ONLINE,), verifier=(Role.PERAWAT,)),
            _item("Konfirmasi jadwal dokter hari ini", "Jadwal", performer=(Role.ONLINE,)),
            _item("Daftar booking & tindakan terjadwal disusun", "Jadwal", performer=(Role.ONLINE,)),
            _item("Serah-terima daftar tindakan ke perawat", "Handoff", performer=(Role.ONLINE,), verifier=(Role.PERAWAT,)),
        ],
    },
    {
        "key": "PRW_CONSULT", "name": "Perawat/Terapis — ruang konsultasi", "area": ChecklistArea.RUANG_KONSULTASI,
        "session": ChecklistSession.ANYTIME, "roles": [Role.PERAWAT],
        "items": [
            _item("Alat dan bahan siap di ruang konsultasi", "Alat"),
            _item("Isi laci ruang konsultasi", "Stok ruangan", input_type=InputType.KUANTITAS, unit="item"),
            _item("Gel ruang konsultasi", "Consumable", input_type=InputType.PILIHAN, options=("Full bottle", "Half", "Less than half")),
            _item("Kebersihan ruang konsultasi", "Kebersihan"),
            _item("Linen bersih tersedia", "Kebersihan"),
        ],
    },
    {
        "key": "PRW_TREATMENT", "name": "Perawat/Terapis — ruang tindakan", "area": ChecklistArea.RUANG_TINDAKAN,
        "session": ChecklistSession.ANYTIME, "roles": [Role.PERAWAT],
        "items": [
            _item("Alat steril siap pakai di ruangan", "Alat"),
            _item("Isi ruang tindakan", "Stok ruangan", input_type=InputType.KUANTITAS, unit="item"),
            _item("Device estetik berfungsi, sisa shot/kartrid", "Device"),
            _item("Kacamata pelindung laser tersedia", "Keselamatan"),
            _item("Alat dan bahan siap sesuai tindakan terjadwal", "Handoff"),
            _item("Kebersihan ruang tindakan", "Kebersihan"),
            _item("Safety box tidak lebih dari ¾ penuh", "Limbah"),
            _item("Pemisahan sampah medis dan nonmedis", "Limbah"),
        ],
    },
]


def _seed_role_templates(clinic):
    """Seed isi PDF sebagai template role-specific yang idempoten."""
    ChecklistTemplate.objects.filter(clinic=clinic, audience_key="").update(active=False)
    for spec in ROLE_TEMPLATES:
        template, _ = ChecklistTemplate.objects.update_or_create(
            clinic=clinic,
            area=spec["area"],
            session=spec["session"],
            version=1,
            audience_key=spec["key"],
            defaults={
                "name": spec["name"],
                "active": True,
                "target_roles": spec["roles"],
                "target_role": spec["roles"][0] if len(spec["roles"]) == 1 else "",
            },
        )
        template.items.all().delete()
        ChecklistTemplateItem.objects.bulk_create(
            [ChecklistTemplateItem(template=template, sort_order=index, **item) for index, item in enumerate(spec["items"], start=1)]
        )

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
        citraland, citraland_created = Clinic.objects.get_or_create(
            code="citraland",
            defaults={
                "name": "JoDerma Citraland",
                "address": "Citraland, Surabaya",
                "open_time": "12:00",
                "close_time": "21:00",
            },
        )
        self.stdout.write(f"Klinik: {citraland} ({'baru' if citraland_created else 'ada'})")

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

        # Demo memakai kasir1 sebagai PIC Online/Kasir agar alur lintas fungsi
        # dapat dicoba tanpa membuat akun produksi.
        kasir_pic = User.objects.get(username="kasir1")
        UserRole.objects.get_or_create(user=kasir_pic, clinic=clinic, role=Role.PIC)

        for area, items in TEMPLATES.items():
            # Database lama dapat memiliki beberapa template generik dengan
            # area/sesi sama. Ambil satu secara deterministik; seed berikutnya
            # tidak boleh gagal hanya karena data legacy tersebut.
            template = ChecklistTemplate.objects.filter(
                clinic=clinic,
                area=area,
                session=ChecklistSession.OPENING,
                version=1,
                audience_key="",
            ).order_by("id").first()
            created = template is None
            if created:
                template = ChecklistTemplate.objects.create(
                    clinic=clinic,
                    area=area,
                    session=ChecklistSession.OPENING,
                    version=1,
                    audience_key="",
                    name=dict(ChecklistArea.choices)[area],
                    active=True,
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

        _seed_role_templates(clinic)
        self.stdout.write(self.style.SUCCESS(f"  {len(ROLE_TEMPLATES)} template role-specific dari PDF aktif"))

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
