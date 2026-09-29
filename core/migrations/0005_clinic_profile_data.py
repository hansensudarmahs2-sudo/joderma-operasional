"""Isi awal profil klinik dari Project-AOM (memory 04, 22; KP-178).

Hanya mengisi yang masih kosong atau masih bernilai bawaan, jadi aman dijalankan
di database yang sudah diubah lewat halaman Pengaturan klinik.
Jemur buka 14.00 (opening 13.30–14.00, closing mengikuti panggilan terakhir,
sasaran 21.40, tutup ±22.00). Citraland tetap 12.00–21.00.
"""
import datetime as dt

from django.db import migrations

PROFILES = {
    "jemur-andayani": {
        "hours": (dt.time(14, 0), dt.time(22, 0)),
        "dpj_name": "dr. Yohanes Widjaja, Sp.DVE",
        "apj_name": "apt. Veronika Elvira Manggo, S.Farm.",
    },
    "citraland": {
        "hours": None,
        "dpj_name": "dr. Wisnu Triadi Nugroho, Sp.DVE",
        "apj_name": "",
    },
}


def forward(apps, schema_editor):
    Clinic = apps.get_model("core", "Clinic")
    for code, p in PROFILES.items():
        clinic = Clinic.objects.filter(code=code).first()
        if clinic is None:
            continue
        if p["hours"] and clinic.open_time == dt.time(12, 0) and clinic.close_time == dt.time(21, 0):
            clinic.open_time, clinic.close_time = p["hours"]
        if not clinic.dpj_name:
            clinic.dpj_name = p["dpj_name"]
        if not clinic.apj_name:
            clinic.apj_name = p["apj_name"]
        clinic.save()


class Migration(migrations.Migration):
    dependencies = [("core", "0004_clinic_profile")]
    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
