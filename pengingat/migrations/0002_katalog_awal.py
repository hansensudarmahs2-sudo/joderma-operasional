"""Katalog awal 22 materi dari docs/KEBUTUHAN_PENGINGAT_HARIAN_DO.md bagian 5 (pengingat/katalog_awal.json).

Katalog awal tidak mendapat ulangan materi baru (kebutuhan 4.3), kecuali materi yang sudah punya
tanggal sosialisasi (saat ini hanya AR-12): ulangan hari ke-1, 3, 7, 14, 30 yang belum lewat dibuat
sebagai butir paksa. Hari kerja bawaan Senin–Sabtu.
"""
import datetime as dt
import json
from pathlib import Path

from django.db import migrations
from django.utils import timezone

HARI_KERJA = [0, 1, 2, 3, 4, 5]
ULANGAN_HARI = (1, 3, 7, 14, 30)


def _hari_kerja(day):
    while day.weekday() not in HARI_KERJA:
        day += dt.timedelta(days=1)
    return day


def isi(apps, schema_editor):
    Materi = apps.get_model("pengingat", "Materi")
    Paksa = apps.get_model("pengingat", "Paksa")
    Pengaturan = apps.get_model("pengingat", "Pengaturan")
    Pengaturan.objects.get_or_create(pk=1, defaults={"hari_kerja": HARI_KERJA})
    data = json.loads((Path(__file__).resolve().parent.parent / "katalog_awal.json").read_text(encoding="utf-8"))
    today = timezone.localdate()
    for row in data:
        tgl = dt.date.fromisoformat(row["tanggal_sosialisasi"]) if row["tanggal_sosialisasi"] else None
        m, created = Materi.objects.get_or_create(kode=row["kode"], defaults={
            "judul": row["judul"], "jenis": row["jenis"], "sasaran": row["sasaran"], "kelas": row["kelas"],
            "poin": row["poin"], "teks_wa": row["teks_wa"], "rujukan": row["rujukan"], "aktif": row["aktif"],
            "tanggal_sosialisasi": tgl, "catatan": row["catatan"], "urutan": row["urutan"],
        })
        if created and tgl:
            for k in ULANGAN_HARI:
                hari = _hari_kerja(tgl + dt.timedelta(days=k))
                if hari >= today:
                    Paksa.objects.get_or_create(materi=m, tanggal=hari, sebab="ULANGAN")


class Migration(migrations.Migration):
    dependencies = [("pengingat", "0001_initial")]

    operations = [migrations.RunPython(isi, migrations.RunPython.noop)]
