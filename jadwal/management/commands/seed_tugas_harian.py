"""Pasang template checklist harian dan porsi tugas dari Project-AOM (jadwal/seed_data.py).

    manage.py seed_tugas_harian --dry-run
    manage.py seed_tugas_harian
    manage.py seed_tugas_harian --susun 2026-10     # sekalian susun pembagian tugas bulan itu

Template dipasang sebagai VERSI BARU (versi lama dinonaktifkan, riwayat run tetap
merujuk snapshot lama). Template dengan isi yang sama tidak dibuat ulang.
Porsi tugas dibuat atau diperbarui per cabang; porsi yang tidak ada lagi di
seed_data dinonaktifkan, tidak dihapus.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from checklists.models import ChecklistTemplate
from checklists.services import create_template_version, instantiate_runs_for_day
from core.models import Clinic, OperationalDay, local_today
from jadwal.models import DutyPortion
from jadwal.seed_data import PORTIONS, SUPERSEDED_KEYS, templates_for
from jadwal.services import plan_month

ITEM_FIELDS = ("label", "category", "required", "input_type", "unit", "min_quantity", "options",
               "performer_roles", "verifier_roles", "help_text", "portion")


def _same(template, spec) -> bool:
    if template.name != spec["name"] or list(template.target_roles or []) != list(spec["target_roles"]):
        return False
    current = [{f: getattr(i, f) for f in ITEM_FIELDS} for i in template.items.order_by("sort_order", "id")]
    wanted = [{f: item.get(f) for f in ITEM_FIELDS} for item in spec["items"]]
    for w in wanted:
        w["options"] = list(w["options"] or [])
        w["performer_roles"] = list(w["performer_roles"] or [])
        w["verifier_roles"] = list(w["verifier_roles"] or [])
    return current == wanted


def seed(*, dry_run=False, stdout=None, clinic_codes=None) -> dict:
    stats = {"templates": 0, "portions": 0, "retired": 0}

    def say(msg):
        if stdout is not None:
            stdout.write(msg)

    clinics = Clinic.objects.filter(active=True)
    if clinic_codes:
        clinics = clinics.filter(code__in=clinic_codes)
    with transaction.atomic():
        for clinic in clinics:
            say(f"== {clinic.name}")
            for p in PORTIONS:
                fields = {k: p[k] for k in ("name", "group", "description", "eligible_roles", "pic_function",
                                            "people", "weekdays", "sort_order")}
                obj, created = DutyPortion.objects.update_or_create(
                    clinic=clinic, code=p["code"], defaults={**fields, "active": True}
                )
                stats["portions"] += 1
                if created:
                    say(f"  + porsi {p['code']}")
            retired = DutyPortion.objects.filter(clinic=clinic, active=True).exclude(
                code__in=[p["code"] for p in PORTIONS]
            )
            stats["retired"] += retired.update(active=False)
            for spec in templates_for(clinic):
                current = (
                    ChecklistTemplate.objects.filter(clinic=clinic, audience_key=spec["key"], active=True)
                    .order_by("-version").first()
                )
                if current is not None and _same(current, spec):
                    say(f"  = template {spec['key']} v{current.version} sudah sama")
                    continue
                items = [{**item, "sort_order": n} for n, item in enumerate(spec["items"], start=1)]
                t = create_template_version(
                    clinic=clinic, area=spec["area"], session=spec["session"], name=spec["name"], items=items,
                    target_roles=spec["target_roles"], audience_key=spec["key"],
                )
                stats["templates"] += 1
                say(f"  + template {spec['key']} v{t.version} ({len(items)} butir)")
            old = ChecklistTemplate.objects.filter(clinic=clinic, active=True, audience_key__in=SUPERSEDED_KEYS)
            for t in old:
                say(f"  - nonaktifkan template lama {t}")
            stats["retired"] += old.update(active=False)
            # Hari operasional yang sudah dibuka hari ini ikut mendapat checklist baru;
            # run lama yang sudah terisi dibiarkan.
            today = OperationalDay.objects.filter(clinic=clinic, date=local_today()).first()
            if today is not None:
                added = instantiate_runs_for_day(today)
                if added:
                    say(f"  + {len(added)} checklist baru untuk hari ini")
        if dry_run:
            transaction.set_rollback(True)
    return stats


class Command(BaseCommand):
    help = "Template checklist harian dan porsi tugas sesuai Project-AOM."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--cabang", nargs="*", help="Kode cabang; kosong = semua.")
        parser.add_argument("--susun", help="Susun pembagian tugas untuk bulan YYYY-MM setelah seed.")

    def handle(self, *args, dry_run=False, cabang=None, susun=None, **opts):
        stats = seed(dry_run=dry_run, stdout=self.stdout, clinic_codes=cabang)
        self.stdout.write(self.style.SUCCESS(
            f"Template baru {stats['templates']}, porsi {stats['portions']}, dinonaktifkan {stats['retired']}."
            + (" (dry-run, tidak disimpan)" if dry_run else "")
        ))
        if susun and not dry_run:
            try:
                year, month = (int(x) for x in susun.split("-"))
            except ValueError:
                raise CommandError("--susun memakai format YYYY-MM.")
            clinics = Clinic.objects.filter(active=True)
            if cabang:
                clinics = clinics.filter(code__in=cabang)
            for clinic in clinics:
                n = plan_month(clinic, year, month)
                self.stdout.write(f"{clinic.name}: {n} porsi disusun untuk {susun}.")
