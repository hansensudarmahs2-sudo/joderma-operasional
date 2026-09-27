"""Bangkitkan berkas ekspor sintetis untuk rehearsal migrasi legacy AOM.

READ-ONLY terhadap database Django — command ini murni menghasilkan berkas
JSON di disk sesuai kontrak `docs/AOM_LEGACY_EXPORT_SCHEMA.md`. Data yang
dibangkitkan adalah data dummy deterministik (seed tetap), BUKAN salinan
data produksi AOM standalone (yang sumber kodenya tidak tersedia di
lingkungan ini).
"""
from __future__ import annotations

import json
import random
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from aom_migration.schema import build_manifest, record_checksum

DEFAULT_SEED = 20260926


class Command(BaseCommand):
    help = (
        "Membangkitkan berkas ekspor JSON sintetis (dummy) untuk rehearsal "
        "migrasi legacy AOM standalone. Tidak menyentuh database."
    )

    def add_arguments(self, parser):
        parser.add_argument("output", help="Path berkas JSON output.")
        parser.add_argument(
            "--seed",
            type=int,
            default=DEFAULT_SEED,
            help="Seed random tetap agar hasil deterministik (default: %(default)s).",
        )
        parser.add_argument(
            "--count",
            type=int,
            default=3,
            help=(
                "Jumlah record dasar per tabel (default: %(default)s). Task selalu "
                "menyertakan minimal 1 OPEN tanpa mapping, 1 DONE, di luar --count."
            ),
        )

    def handle(self, *args, **options):
        seed = options["seed"]
        count = max(options["count"], 1)
        output_path = options["output"]
        rng = random.Random(seed)

        base_time = timezone.datetime(2026, 9, 1, 8, 0, 0, tzinfo=timezone.get_default_timezone())

        def iso(dt):
            return dt.isoformat()

        # --- ChecklistTemplate ---
        areas = ["Ruang Konsultasi", "Kasir", "Apotek", "Ruang Tunggu"]
        checklist_templates = []
        for i in range(count):
            rec = {
                "legacy_id": f"CT-{i + 1:03d}",
                "name": f"Template {areas[i % len(areas)]}",
                "area": areas[i % len(areas)],
                "active": True,
                "order": i + 1,
            }
            rec["checksum"] = record_checksum(rec)
            checklist_templates.append(rec)

        # --- DailyChecklist ---
        daily_checklists = []
        for i in range(count):
            tpl = checklist_templates[i % len(checklist_templates)]
            rec = {
                "legacy_id": f"DC-{i + 1:03d}",
                "template_legacy_id": tpl["legacy_id"],
                "date": (base_time + timedelta(days=i)).date().isoformat(),
                "area": tpl["area"],
                "status": "COMPLETE" if i % 2 == 0 else "PROBLEM",
                "responses": {"item_1": "OK", "item_2": "OK" if i % 2 == 0 else "MASALAH"},
            }
            rec["checksum"] = record_checksum(rec)
            daily_checklists.append(rec)

        # --- Task ---
        # Label aktor lama, sebagian sengaja TIDAK dapat dipetakan (unmapped
        # actor) untuk menguji jalur exception importer.
        actor_labels = ["Heni (Legacy)", "Desy (Legacy)", "Unknown Staff Lama"]
        tasks = []
        # 1) OPEN tanpa assignee (harus jadi exception di importer)
        rec = {
            "legacy_id": "TASK-OPEN-UNMAPPED",
            "title": "Cek stok kasa steril (legacy, belum ditugaskan)",
            "description": "Task lama AOM standalone yang belum punya penerima jelas.",
            "status": "OPEN",
            "created_by_label": actor_labels[2],
            "assigned_to_label": None,
            "created_at": iso(base_time),
            "done_at": None,
        }
        rec["checksum"] = record_checksum(rec)
        tasks.append(rec)
        # 2) DONE dengan assignee (mapped label, tapi tetap label-only)
        rec = {
            "legacy_id": "TASK-DONE-001",
            "title": "Tutup kas harian (legacy)",
            "description": "Task lama yang sudah selesai di AOM standalone.",
            "status": "DONE",
            "created_by_label": actor_labels[0],
            "assigned_to_label": actor_labels[1],
            "created_at": iso(base_time),
            "done_at": iso(base_time + timedelta(hours=6)),
        }
        rec["checksum"] = record_checksum(rec)
        tasks.append(rec)
        # Sisanya: campuran OPEN/DONE mengikuti --count
        for i in range(count):
            is_done = i % 2 == 0
            rec = {
                "legacy_id": f"TASK-{i + 1:03d}",
                "title": f"Task legacy {i + 1}",
                "description": f"Deskripsi task legacy nomor {i + 1}.",
                "status": "DONE" if is_done else "OPEN",
                "created_by_label": actor_labels[i % len(actor_labels)],
                "assigned_to_label": actor_labels[(i + 1) % len(actor_labels)] if is_done else None,
                "created_at": iso(base_time + timedelta(days=i)),
                "done_at": iso(base_time + timedelta(days=i, hours=4)) if is_done else None,
            }
            rec["checksum"] = record_checksum(rec)
            tasks.append(rec)

        # --- Note ---
        notes = []
        for i in range(count):
            rec = {
                "legacy_id": f"NOTE-{i + 1:03d}",
                "content": f"Catatan legacy nomor {i + 1} terkait operasional harian.",
                "author_label": actor_labels[i % len(actor_labels)],
                "created_at": iso(base_time + timedelta(days=i, hours=1)),
                "related_task_legacy_id": tasks[i % len(tasks)]["legacy_id"] if tasks else None,
            }
            rec["checksum"] = record_checksum(rec)
            notes.append(rec)

        # --- Activity ---
        activities = []
        for i in range(count + 1):
            rec = {
                "legacy_id": f"ACT-{i + 1:03d}",
                "description": f"Aktivitas legacy nomor {i + 1}.",
                "actor_label": actor_labels[i % len(actor_labels)],
                "timestamp": iso(base_time + timedelta(days=i, minutes=30)),
            }
            rec["checksum"] = record_checksum(rec)
            activities.append(rec)

        # --- DailyClose ---
        daily_closes = []
        for i in range(count):
            rec = {
                "legacy_id": f"DCL-{i + 1:03d}",
                "date": (base_time + timedelta(days=i)).date().isoformat(),
                "area": areas[i % len(areas)],
                "closed_by_label": actor_labels[i % len(actor_labels)],
                "summary": f"Penutupan area {areas[i % len(areas)]} hari ke-{i + 1}.",
                "timestamp": iso(base_time + timedelta(days=i, hours=9)),
            }
            rec["checksum"] = record_checksum(rec)
            daily_closes.append(rec)

        # --- AuditEvent ---
        audit_events = []
        actions = ["CREATE_TASK", "CLOSE_DAY", "EDIT_TEMPLATE", "COMPLETE_TASK"]
        for i in range(count + 2):
            rec = {
                "legacy_id": f"AUD-{i + 1:03d}",
                "actor_label": actor_labels[i % len(actor_labels)],
                "action": actions[i % len(actions)],
                "target": f"entity-legacy-{i + 1}",
                "timestamp": iso(base_time + timedelta(days=i, minutes=5)),
                "metadata": {"seq": i + 1, "seed": seed},
            }
            rec["checksum"] = record_checksum(rec)
            audit_events.append(rec)

        export = {
            "ChecklistTemplate": checklist_templates,
            "DailyChecklist": daily_checklists,
            "Task": tasks,
            "Note": notes,
            "Activity": activities,
            "DailyClose": daily_closes,
            "AuditEvent": audit_events,
        }
        manifest = build_manifest(
            export,
            source_label="AOM-STANDALONE-DUMMY",
            exported_at=iso(base_time),
        )
        payload = {"manifest": manifest, **export}

        try:
            with open(output_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, ensure_ascii=False)
        except OSError as exc:
            raise CommandError(f"Gagal menulis berkas output: {exc}") from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Fixture ekspor dummy ditulis ke {output_path} "
                f"(seed={seed}, count_dasar={count})."
            )
        )
        for name in export:
            self.stdout.write(f"  - {name}: {len(export[name])} baris")
        self.stdout.write(f"  overall_checksum: {manifest['overall_checksum']}")
