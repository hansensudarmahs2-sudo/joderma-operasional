"""Import idempoten berkas ekspor legacy AOM standalone (Fase 6).

Lihat `docs/AOM_LEGACY_EXPORT_SCHEMA.md` untuk kontrak lengkap dan aturan
pemetaan. Command ini TIDAK PERNAH menebak user dari label aktor, TIDAK
PERNAH membuat baris target tanpa `LegacyIdMap` yang sesuai, dan aman
dijalankan berulang kali pada berkas ekspor yang sama (idempoten).
"""
from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.dateparse import parse_datetime

from accounts.models import User
from audit.models import AuditAction, AuditEvent as CoreAuditEvent
from core.models import ActionItem, Clinic, Priority, TaskAssignment, TaskAssignmentStatus
from aom_migration.models import LegacyActor, LegacyArchive, LegacyIdMap, LegacyImportBatch
from aom_migration.schema import ARCHIVE_TABLES, record_checksum

DEFAULT_CLINIC_CODE = "jemur-andayani"
DEFAULT_CLINIC_NAME = "JoDerma Jemur Andayani"


def _get_or_create_legacy_actor(label: str | None) -> LegacyActor | None:
    """Simpan/ambil label aktor legacy apa adanya. `mapped_user` TIDAK PERNAH
    ditebak di sini — hanya dibaca bila baris LegacyActor dengan label yang
    sama persis sudah ada dari mapping tervalidasi sebelumnya.
    """
    if not label:
        return None
    actor, _ = LegacyActor.objects.get_or_create(label=label)
    return actor


class Command(BaseCommand):
    help = "Import idempoten berkas ekspor legacy AOM standalone (dummy/rehearsal)."

    def add_arguments(self, parser):
        parser.add_argument("export_path", help="Path berkas JSON hasil generate_legacy_export_fixture.")
        parser.add_argument(
            "--batch-name",
            default="rehearsal",
            help="Nama batch import (default: %(default)s).",
        )
        parser.add_argument(
            "--default-clinic-code",
            default=DEFAULT_CLINIC_CODE,
            help=(
                "Kode cabang default untuk seluruh data legacy tanpa kode cabang "
                "eksplisit (default: %(default)s, mengikuti plan 12.2.3). Keputusan "
                "ini SELALU dicatat eksplisit di catatan batch dan output."
            ),
        )

    def handle(self, *args, **options):
        export_path = options["export_path"]
        batch_name = options["batch_name"]
        clinic_code = options["default_clinic_code"]

        try:
            with open(export_path, "r", encoding="utf-8") as fh:
                export = json.load(fh)
        except OSError as exc:
            raise CommandError(f"Gagal membaca berkas ekspor: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise CommandError(f"Berkas ekspor bukan JSON valid: {exc}") from exc

        manifest = export.get("manifest", {})

        clinic, clinic_created = Clinic.objects.get_or_create(
            code=clinic_code, defaults={"name": DEFAULT_CLINIC_NAME}
        )
        clinic_notice = (
            f"KEPUTUSAN EKSPLISIT (plan 12.2.3): seluruh data Task/legacy tanpa kode "
            f"cabang eksplisit di-assign ke cabang default '{clinic_code}' "
            f"({'baru dibuat' if clinic_created else 'sudah ada'}). Aturan ini harus "
            f"disetujui product owner saat rehearsal sebelum lanjut ke produksi."
        )
        self.stdout.write(self.style.WARNING(clinic_notice))

        exceptions: list[str] = []
        counts = {
            "source": {},
            "imported": {},
            "skipped_duplicate": {},
        }

        with transaction.atomic():
            batch = LegacyImportBatch.objects.create(
                name=batch_name,
                source_label=manifest.get("source_label", ""),
                exported_at=parse_datetime(manifest["exported_at"]) if manifest.get("exported_at") else None,
                manifest_checksum=manifest.get("overall_checksum", ""),
                notes=clinic_notice,
            )

            # --- Task -> ActionItem (+TaskAssignment) ---
            counts["source"]["Task"] = len(export.get("Task", []))
            counts["imported"]["Task"] = 0
            counts["skipped_duplicate"]["Task"] = 0
            for rec in export.get("Task", []):
                legacy_id = rec["legacy_id"]
                existing = LegacyIdMap.objects.filter(
                    source_model="Task", legacy_id=legacy_id, target_model="core.ActionItem"
                ).first()
                if existing:
                    counts["skipped_duplicate"]["Task"] += 1
                    continue

                is_done = rec["status"] == "DONE"
                item = ActionItem.objects.create(
                    clinic=clinic,
                    title=rec["title"],
                    description=rec.get("description", ""),
                    source_type="aom_legacy_import",
                    source_label=f"AOM legacy Task#{legacy_id}",
                    priority=Priority.SEDANG,
                    imported_legacy=True,
                    legacy_source_id=legacy_id,
                )
                if is_done:
                    item.legacy_completed_at = parse_datetime(rec["done_at"]) if rec.get("done_at") else None
                    item.save(update_fields=["legacy_completed_at"])

                LegacyIdMap.objects.get_or_create(
                    source_model="Task",
                    legacy_id=legacy_id,
                    target_model="core.ActionItem",
                    defaults={"target_id": item.pk, "batch": batch},
                )

                assignee_label = rec.get("assigned_to_label")
                created_by_label = rec.get("created_by_label")
                _get_or_create_legacy_actor(created_by_label)
                assignee_actor = _get_or_create_legacy_actor(assignee_label)

                assignee_user = None
                if assignee_actor is not None and assignee_actor.mapped_user_id:
                    assignee_user = assignee_actor.mapped_user

                if assignee_user is not None:
                    assignment = TaskAssignment.objects.create(
                        action_item=item,
                        assignee=assignee_user,
                        status=(
                            TaskAssignmentStatus.CONFIRMED
                            if is_done
                            else TaskAssignmentStatus.OPEN
                        ),
                        confirmed_at=item.legacy_completed_at if is_done else None,
                    )
                    LegacyIdMap.objects.get_or_create(
                        source_model="Task",
                        legacy_id=legacy_id,
                        target_model="core.TaskAssignment",
                        defaults={"target_id": assignment.pk, "batch": batch},
                    )
                    item.owner = assignee_user
                    item.save(update_fields=["owner"])
                else:
                    # Tidak ada penerima yang bisa dipetakan ke user nyata.
                    # OPEN tanpa mapping -> exception eksplisit (plan 12.2.5).
                    # DONE tanpa mapping -> tetap histori, tapi tetap dicatat
                    # sebagai exception karena assignee asli tidak diketahui.
                    exceptions.append(
                        f"Task {legacy_id} ({rec['status']}): assignee_label="
                        f"{assignee_label!r} tidak dapat dipetakan ke user nyata; "
                        f"disimpan sebagai ActionItem tanpa TaskAssignment."
                    )
                counts["imported"]["Task"] += 1

            # --- ChecklistTemplate/DailyChecklist/Note/Activity/DailyClose -> LegacyArchive ---
            for table in ARCHIVE_TABLES:
                counts["source"][table] = len(export.get(table, []))
                counts["imported"][table] = 0
                counts["skipped_duplicate"][table] = 0
                for rec in export.get(table, []):
                    legacy_id = rec["legacy_id"]
                    if LegacyArchive.objects.filter(
                        source_model=table, legacy_id=legacy_id
                    ).exists():
                        counts["skipped_duplicate"][table] += 1
                        continue
                    archive = LegacyArchive.objects.create(
                        source_model=table,
                        legacy_id=legacy_id,
                        batch=batch,
                        payload=rec,
                        checksum=rec.get("checksum", record_checksum(rec)),
                    )
                    LegacyIdMap.objects.get_or_create(
                        source_model=table,
                        legacy_id=legacy_id,
                        target_model="aom_migration.LegacyArchive",
                        defaults={"target_id": archive.pk, "batch": batch},
                    )
                    counts["imported"][table] += 1

            # --- AuditEvent -> audit.AuditEvent ---
            counts["source"]["AuditEvent"] = len(export.get("AuditEvent", []))
            counts["imported"]["AuditEvent"] = 0
            counts["skipped_duplicate"]["AuditEvent"] = 0
            for rec in export.get("AuditEvent", []):
                legacy_id = rec["legacy_id"]
                existing = LegacyIdMap.objects.filter(
                    source_model="AuditEvent",
                    legacy_id=legacy_id,
                    target_model="audit.AuditEvent",
                ).first()
                if existing:
                    counts["skipped_duplicate"]["AuditEvent"] += 1
                    continue
                actor_label = rec.get("actor_label", "")
                actor = _get_or_create_legacy_actor(actor_label)
                mapped_user = actor.mapped_user if actor and actor.mapped_user_id else None
                event = CoreAuditEvent.objects.create(
                    actor=mapped_user,
                    actor_label=actor_label,
                    action=AuditAction.MIGRATION_IMPORT,
                    entity_type="aom_legacy",
                    entity_id=legacy_id,
                    entity_label=rec.get("target", ""),
                    before_json=None,
                    after_json=rec,
                    reason=f"Import legacy AOM standalone, aksi asal: {rec.get('action', '')}",
                )
                LegacyIdMap.objects.get_or_create(
                    source_model="AuditEvent",
                    legacy_id=legacy_id,
                    target_model="audit.AuditEvent",
                    defaults={"target_id": event.pk, "batch": batch},
                )
                counts["imported"]["AuditEvent"] += 1

            batch.notes = clinic_notice + (
                f"\n\nException count: {len(exceptions)}." if exceptions else "\n\nTidak ada exception."
            )
            batch.save(update_fields=["notes"])

        self.stdout.write(self.style.SUCCESS(f"Batch import: {batch.name} (id={batch.pk})"))
        self.stdout.write("Ringkasan per tabel sumber (source / imported / skipped_duplicate):")
        for table in counts["source"]:
            self.stdout.write(
                f"  - {table}: {counts['source'][table]} / "
                f"{counts['imported'][table]} / {counts['skipped_duplicate'][table]}"
            )
        self.stdout.write(f"Jumlah exception: {len(exceptions)}")
        for exc_msg in exceptions:
            self.stdout.write(f"  ! {exc_msg}")

        return json.dumps(
            {
                "batch_id": batch.pk,
                "counts": counts,
                "exceptions": exceptions,
            }
        )
