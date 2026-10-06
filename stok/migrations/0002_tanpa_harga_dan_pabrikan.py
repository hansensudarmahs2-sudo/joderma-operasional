"""Buang harga dan nama pabrikan dari Stok Apotek (keputusan product owner 6 Okt 2026).

Sebelum kolom `pabrikan` dibuang, tanda `produksi_sendiri` diisi dari kolom itu
(DRYN atau Joderma), supaya kolom Tindakan tetap benar tanpa menunggu Daftar Produk
diunggah ulang.
"""
from django.db import migrations, models

PABRIKAN_SENDIRI = {"dryn", "joderma"}


def isi_produksi_sendiri(apps, schema_editor):
    Produk = apps.get_model("stok", "Produk")
    ids = [
        pk
        for pk, pabrikan in Produk.objects.values_list("pk", "pabrikan")
        if (pabrikan or "").strip().lower() in PABRIKAN_SENDIRI
    ]
    Produk.objects.filter(pk__in=ids).update(produksi_sendiri=True)


class Migration(migrations.Migration):

    dependencies = [
        ("stok", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="produk",
            name="produksi_sendiri",
            field=models.BooleanField(
                default=False,
                help_text="Dari kolom pabrikan Omnicare saat impor (DRYN atau Joderma). Nama pabrikan tidak disimpan.",
                verbose_name="produksi sendiri",
            ),
        ),
        migrations.RunPython(isi_produksi_sendiri, migrations.RunPython.noop),
        migrations.RemoveField(model_name="posisistok", name="nilai_modal"),
        migrations.RemoveField(model_name="produk", name="harga_jual"),
        migrations.RemoveField(model_name="produk", name="harga_modal"),
        migrations.RemoveField(model_name="produk", name="pabrikan"),
    ]
