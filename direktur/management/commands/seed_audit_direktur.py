"""Isi butir checklist Direktur Operasional (idempoten).

Butir yang sudah ada TIDAK ditimpa kecuali dengan `--update`, supaya teks yang
sudah disunting lewat Django admin tidak hilang. `--dry-run` hanya menampilkan
rencana tanpa menulis ke database.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from direktur.models import AuditItem, AuditPoint, Cadence
from direktur.seed_data import BULANAN, HARIAN, MINGGUAN

SETS = ((Cadence.HARIAN, HARIAN), (Cadence.MINGGUAN, MINGGUAN), (Cadence.BULANAN, BULANAN))


def seed(*, update: bool = False, dry_run: bool = False, stdout=None) -> dict:
    stats = {"created": 0, "updated": 0, "unchanged": 0}

    def say(msg):
        if stdout is not None:
            stdout.write(msg)

    with transaction.atomic():
        for cadence, rows in SETS:
            for order, (code, number, title, desc, source, pic, clinics, points) in enumerate(rows, 1):
                fields = {
                    "cadence": cadence,
                    "number": number,
                    "title": title,
                    "description": desc,
                    "source_label": source,
                    "pic_function": pic,
                    "clinic_codes": list(clinics),
                    "sort_order": order,
                }
                existing = AuditItem.objects.filter(code=code).first()
                if existing is None:
                    stats["created"] += 1
                    say(f"+ {cadence} {number}. {title} ({len(points)} rincian)")
                    if dry_run:
                        continue
                    item = AuditItem.objects.create(code=code, **fields)
                    _replace_points(item, points)
                elif update:
                    stats["updated"] += 1
                    say(f"~ {cadence} {number}. {title} (diperbarui)")
                    if dry_run:
                        continue
                    for key, value in fields.items():
                        setattr(existing, key, value)
                    existing.save()
                    _replace_points(existing, points)
                else:
                    stats["unchanged"] += 1
        if dry_run:
            transaction.set_rollback(True)
    return stats


def _replace_points(item, points):
    item.points.all().delete()
    AuditPoint.objects.bulk_create(
        [AuditPoint(item=item, text=t, evidence=e, sort_order=i) for i, (t, e) in enumerate(points, 1)]
    )


class Command(BaseCommand):
    help = "Isi butir checklist harian/mingguan/bulanan Direktur Operasional."

    def add_arguments(self, parser):
        parser.add_argument("--update", action="store_true", help="Timpa teks butir yang sudah ada.")
        parser.add_argument("--dry-run", action="store_true", help="Tampilkan rencana tanpa menulis.")

    def handle(self, *args, **options):
        stats = seed(update=options["update"], dry_run=options["dry_run"], stdout=self.stdout)
        prefix = "[dry-run] " if options["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}baru {stats['created']}, diperbarui {stats['updated']}, "
                f"tetap {stats['unchanged']}"
            )
        )
