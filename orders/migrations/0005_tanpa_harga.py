# Keputusan product owner 6 Okt 2026: harga dan supplier tidak disimpan di ops.joderma.id.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0004_alter_onlineorder_status_onlineorderitem"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="onlineorder",
            name="total_price",
        ),
        migrations.RemoveField(
            model_name="onlineorder",
            name="unit_price",
        ),
        migrations.RemoveField(
            model_name="onlineorderitem",
            name="total_price",
        ),
        migrations.RemoveField(
            model_name="onlineorderitem",
            name="unit_price",
        ),
        migrations.RemoveField(
            model_name="product",
            name="sale_price",
        ),
    ]
