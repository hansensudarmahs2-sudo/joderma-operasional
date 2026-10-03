"""Isi koordinat awal kedua cabang dari Google Maps (product owner, 3 Okt 2026).

Hanya mengisi cabang yang koordinatnya masih kosong; nilai yang sudah diatur di Pengaturan
Klinik tidak ditimpa. Cabang dikenali dengan cara yang sama seperti core.services.clinic_key
(kode di mini PC: Citraland = JC).
"""
from decimal import Decimal

from django.db import migrations

COORDINATES = {
    "jemur-andayani": (Decimal("-7.328501"), Decimal("112.739425")),
    "citraland": (Decimal("-7.286665"), Decimal("112.655565")),
}


def _key(clinic) -> str:
    code = (clinic.code or "").strip()
    text = f"{code} {clinic.name or ''}".lower()
    if "citraland" in text or code.upper() == "JC":
        return "citraland"
    if "jemur" in text or code.upper() == "JJ":
        return "jemur-andayani"
    return code.lower()


def fill(apps, schema_editor):
    Clinic = apps.get_model("core", "Clinic")
    for clinic in Clinic.objects.filter(latitude__isnull=True, longitude__isnull=True):
        coords = COORDINATES.get(_key(clinic))
        if coords:
            clinic.latitude, clinic.longitude = coords
            clinic.save(update_fields=["latitude", "longitude"])


class Migration(migrations.Migration):
    dependencies = [("core", "0007_koordinat_klinik")]
    operations = [migrations.RunPython(fill, migrations.RunPython.noop)]
