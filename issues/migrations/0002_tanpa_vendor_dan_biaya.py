# Keputusan product owner 6 Okt 2026: harga dan supplier tidak disimpan di ops.joderma.id.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("issues", "0001_initial"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="issue",
            name="repair_cost",
        ),
        migrations.RemoveField(
            model_name="issue",
            name="repair_vendor",
        ),
    ]
