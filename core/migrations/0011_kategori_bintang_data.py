"""Data awal kategori task dan bintang otomatis untuk task lama (keputusan PO 8 Okt 2026).

- Kategori bawaan diisi berurutan (`core.models.DEFAULT_TASK_CATEGORIES`); yang sudah ada dibiarkan.
- Task yang sudah selesai sebelum perubahan ini dibuat otomatis bintang 5: setiap assignment
  CONFIRMED yang belum bernilai mendapat rating=5, rating_auto=True, rated_at=confirmed_at (atau
  sekarang), tanpa penilai dan tanpa catatan. Penerima Direktur Operasional atau Owner (tanpa
  peran Direktur) tidak dinilai, sama dengan aturan baru, jadi dilewati.
"""
from django.db import migrations
from django.utils import timezone

CATEGORIES = (
    "Pelayanan pasien",
    "Kebersihan & kerapian",
    "Fasilitas & peralatan",
    "SDM & disiplin",
    "Keuangan & kas",
    "Stok & obat",
    "Pemasaran",
    "Administrasi & sistem",
    "Lainnya",
)


def seed_categories(apps, schema_editor):
    TaskCategory = apps.get_model("core", "TaskCategory")
    for order, name in enumerate(CATEGORIES, start=1):
        TaskCategory.objects.get_or_create(name=name, defaults={"sort_order": order * 10, "active": True})


def auto_rate_confirmed(apps, schema_editor):
    TaskAssignment = apps.get_model("core", "TaskAssignment")
    UserRole = apps.get_model("accounts", "UserRole")
    # Direktur Operasional, atau Owner (dengan atau tanpa peran Direktur): keduanya tidak dinilai.
    not_rated = set(UserRole.objects.filter(role__in=("AOM", "OWNER")).values_list("user_id", flat=True))
    now = timezone.now()
    qs = TaskAssignment.objects.filter(status="CONFIRMED", rating__isnull=True).exclude(assignee_id__in=not_rated)
    for a in qs.iterator():
        a.rating = 5
        a.rating_auto = True
        a.rating_note = ""
        a.rated_by = None
        a.rated_at = a.confirmed_at or now
        a.save(update_fields=["rating", "rating_auto", "rating_note", "rated_by", "rated_at"])


def forwards(apps, schema_editor):
    seed_categories(apps, schema_editor)
    auto_rate_confirmed(apps, schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0010_kategori_bintang_task"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
