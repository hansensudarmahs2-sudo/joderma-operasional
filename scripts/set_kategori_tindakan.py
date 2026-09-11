"""Mengganti kategori tindakan menjadi tiga kategori operasional JoDerma.

Aman dijalankan berulang. Kategori lama dinonaktifkan, bukan dihapus, agar
riwayat penugasan dan event komisi yang mungkin sudah ada tidak terputus.
"""

from django.db import transaction

from accounts.models import Role, User
from nurses.models import (
    CommissionTurnEvent,
    NurseEligibility,
    ProcedureAssignment,
    ProcedureCategory,
)
from core.models import Clinic

# (kode, nama, berkomisi)
#
# Ketiganya berkomisi. Diputuskan pemilik 11 September 2026 (OD-E): penugasan
# dicatat manual, sehingga asistensi dokter yang memang berkomisi ikut tercatat
# sebagaimana adanya. Rotasi tetap adil karena setiap pekerjaan berkomisi
# menghabiskan giliran, tidak peduli jenisnya.
KATEGORI_BARU = [
    ("tindakan-estetik", "Tindakan estetik", True),
    ("asistensi-dokter", "Asistensi dokter", True),
    ("tindakan-infus", "Tindakan infus", True),
]

clinic = Clinic.objects.filter(active=True).first() or Clinic.objects.first()
if clinic is None:
    raise SystemExit("Tidak ada klinik. Jalankan setup awal lebih dulu.")

with transaction.atomic():
    # 1. Buat atau aktifkan kategori baru
    baru = []
    for kode, nama, berkomisi in KATEGORI_BARU:
        obj, dibuat = ProcedureCategory.objects.get_or_create(
            clinic=clinic,
            code=kode,
            defaults={"name": nama, "active": True, "commissioned": berkomisi},
        )
        ubah = []
        if obj.name != nama:
            obj.name, _ = nama, ubah.append("name")
        if not obj.active:
            obj.active, _ = True, ubah.append("active")
        if obj.commissioned != berkomisi:
            obj.commissioned, _ = berkomisi, ubah.append("commissioned")
        if ubah:
            obj.save(update_fields=ubah)
        baru.append(obj)
        status = "dibuat " if dibuat else ("diubah " if ubah else "ada    ")
        print(f"{status}: {nama} (komisi={berkomisi})")

    # 2. Nonaktifkan kategori lama. Dihapus hanya bila benar-benar tidak
    #    pernah dipakai, sehingga tidak ada riwayat yang terputus.
    kode_baru = {k for k, _, _ in KATEGORI_BARU}
    for lama in ProcedureCategory.objects.filter(clinic=clinic).exclude(code__in=kode_baru):
        terpakai = (
            ProcedureAssignment.objects.filter(category=lama).exists()
            or CommissionTurnEvent.objects.filter(procedure_category=lama).exists()
        )
        if terpakai:
            if lama.active:
                lama.active = False
                lama.save(update_fields=["active"])
            print(f"nonaktif: {lama.name} (punya riwayat, dipertahankan)")
        else:
            nama = lama.name
            NurseEligibility.objects.filter(category=lama).delete()
            lama.delete()
            print(f"dihapus : {nama} (tidak pernah dipakai)")

    # 3. Eligibility: semua perawat boleh semua kategori.
    #    Default sementara -- lihat OPEN DECISION OD-F. Supervisor dapat
    #    mengoreksinya lewat UI tanpa mengubah kode.
    perawat = [u for u in User.objects.filter(is_active=True) if Role.PERAWAT in u.role_codes()]
    dibuat = 0
    for p in perawat:
        for kat in baru:
            _, created = NurseEligibility.objects.get_or_create(nurse=p, category=kat)
            dibuat += int(created)
    print(f"\neligibility dibuat: {dibuat} ({len(perawat)} perawat x {len(baru)} kategori)")

print("\n=== hasil akhir ===")
for c in ProcedureCategory.objects.filter(active=True).order_by("name"):
    n = NurseEligibility.objects.filter(category=c).count()
    komisi = "berkomisi" if c.commissioned else "tanpa komisi"
    print(f"  {c.name} [{komisi}]: {n} perawat eligible")
