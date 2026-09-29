"""Impor jadwal jaga satu bulan dari berkas JSON (lihat jadwal/data/).

    manage.py import_jadwal_jaga jadwal/data/jadwal-2026-10.json --dry-run
    manage.py import_jadwal_jaga jadwal/data/jadwal-2026-10.json

Menimpa baris jadwal orang-orang di berkas untuk bulan itu (idempoten).
"""
from __future__ import annotations

import json

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from jadwal.services import import_month


class Command(BaseCommand):
    help = "Impor jadwal jaga bulanan (masuk/off/perbantuan) dari JSON."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, path, dry_run=False, **opts):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        try:
            with transaction.atomic():
                result = import_month(data)
                if dry_run:
                    transaction.set_rollback(True)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages))
        for w in result["warnings"]:
            self.stdout.write(self.style.WARNING(f"! {w}"))
        verb = "akan ditulis" if dry_run else "ditulis"
        self.stdout.write(self.style.SUCCESS(f"{result['people']} orang, {result['rows']} baris {verb}."))
