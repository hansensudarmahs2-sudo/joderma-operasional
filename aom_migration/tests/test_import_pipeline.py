"""Fase 6: migration rehearsal legacy AOM standalone — test dasar (idempotensi,
exception path, arsip histori, aktor tidak ditebak).

Semua test memakai data dummy yang dibangkitkan
`generate_legacy_export_fixture` (seed tetap), BUKAN data produksi AOM
standalone (yang sumbernya tidak tersedia di lingkungan ini).
"""
from __future__ import annotations

import io
import json

import pytest
from django.core.management import call_command

from accounts.models import User
from aom_migration.models import LegacyActor, LegacyArchive, LegacyIdMap, LegacyImportBatch
from audit.models import AuditAction, AuditEvent
from core.models import ActionItem, TaskAssignment, TaskAssignmentStatus

pytestmark = pytest.mark.django_db


def _generate_fixture(path, seed=20260926, count=3):
    call_command("generate_legacy_export_fixture", str(path), f"--seed={seed}", f"--count={count}")


def _import(path, batch_name="test-batch"):
    out = io.StringIO()
    call_command("import_legacy_export", str(path), f"--batch-name={batch_name}", stdout=out)
    return out.getvalue()


@pytest.fixture
def export_path(tmp_path):
    path = tmp_path / "export.json"
    _generate_fixture(path)
    return path


def test_generate_fixture_is_read_only_and_deterministic(tmp_path):
    """Command generator tidak menyentuh DB dan hasilnya deterministik untuk
    seed yang sama.
    """
    assert LegacyIdMap.objects.count() == 0
    p1 = tmp_path / "a.json"
    p2 = tmp_path / "b.json"
    _generate_fixture(p1, seed=111, count=2)
    _generate_fixture(p2, seed=111, count=2)
    assert LegacyIdMap.objects.count() == 0  # masih tidak menyentuh DB
    d1 = json.loads(p1.read_text())
    d2 = json.loads(p2.read_text())
    assert d1 == d2
    assert d1["manifest"]["overall_checksum"] == d2["manifest"]["overall_checksum"]


def test_import_is_idempotent(export_path):
    """Import kedua pada berkas yang sama tidak membuat baris target baru
    (plan 12.3: import kedua menghasilkan nol duplikasi).
    """
    _import(export_path, batch_name="run-1")

    counts_after_first = {
        "LegacyIdMap": LegacyIdMap.objects.count(),
        "ActionItem": ActionItem.objects.count(),
        "LegacyArchive": LegacyArchive.objects.count(),
        "AuditEvent": AuditEvent.objects.filter(action=AuditAction.MIGRATION_IMPORT).count(),
    }
    assert counts_after_first["LegacyIdMap"] > 0

    _import(export_path, batch_name="run-2")

    counts_after_second = {
        "LegacyIdMap": LegacyIdMap.objects.count(),
        "ActionItem": ActionItem.objects.count(),
        "LegacyArchive": LegacyArchive.objects.count(),
        "AuditEvent": AuditEvent.objects.filter(action=AuditAction.MIGRATION_IMPORT).count(),
    }
    assert counts_after_second == counts_after_first
    # Dua batch tetap tercatat (audit trail proses import itu sendiri tetap ada)
    assert LegacyImportBatch.objects.count() == 2


def test_open_task_without_mapped_assignee_becomes_unassigned_exception(export_path):
    _import(export_path, batch_name="run-1")

    item_map = LegacyIdMap.objects.get(
        source_model="Task", legacy_id="TASK-OPEN-UNMAPPED", target_model="core.ActionItem"
    )
    item = ActionItem.objects.get(pk=item_map.target_id)
    assert item.imported_legacy is True
    assert item.legacy_source_id == "TASK-OPEN-UNMAPPED"
    assert not TaskAssignment.objects.filter(action_item=item).exists()

    out = io.StringIO()
    call_command(
        "import_legacy_export", str(export_path), "--batch-name=run-2-exceptions", stdout=out
    )
    output = out.getvalue()
    assert "TASK-OPEN-UNMAPPED" not in output  # sudah diimport di run-1, run-2 skip duplikat


def test_open_task_exception_reported_on_first_import(export_path):
    out = _import(export_path, batch_name="run-1")
    assert "TASK-OPEN-UNMAPPED" in out
    assert "tidak dapat dipetakan" in out


def test_done_task_creates_confirmed_assignment_when_actor_mapped(export_path):
    """Bila label aktor legacy SUDAH punya mapping user tervalidasi
    sebelumnya, task DONE menghasilkan TaskAssignment CONFIRMED dengan
    imported_legacy dan legacy_completed_at terisi benar.
    """
    desy = User.objects.create_user(username="desy_real", password="TestPassword123!")
    LegacyActor.objects.create(label="Desy (Legacy)", mapped_user=desy)

    _import(export_path, batch_name="run-1")

    item_map = LegacyIdMap.objects.get(
        source_model="Task", legacy_id="TASK-DONE-001", target_model="core.ActionItem"
    )
    item = ActionItem.objects.get(pk=item_map.target_id)
    assert item.imported_legacy is True
    assert item.legacy_source_id == "TASK-DONE-001"
    assert item.legacy_completed_at is not None

    assignment_map = LegacyIdMap.objects.get(
        source_model="Task", legacy_id="TASK-DONE-001", target_model="core.TaskAssignment"
    )
    assignment = TaskAssignment.objects.get(pk=assignment_map.target_id)
    assert assignment.assignee_id == desy.pk
    assert assignment.status == TaskAssignmentStatus.CONFIRMED
    assert assignment.confirmed_at == item.legacy_completed_at


def test_unmapped_legacy_actor_never_silently_linked_to_a_user(export_path):
    """Label aktor tanpa mapping tervalidasi TIDAK PERNAH ditebak ke user
    manapun, walau ada user lain dengan nama serupa di database.
    """
    User.objects.create_user(username="heni_lookalike", password="TestPassword123!")

    _import(export_path, batch_name="run-1")

    actor = LegacyActor.objects.get(label="Heni (Legacy)")
    assert actor.mapped_user is None


def test_archive_tables_preserve_source_model_and_payload(export_path):
    _import(export_path, batch_name="run-1")

    export = json.loads(export_path.read_text())
    for table in ("ChecklistTemplate", "DailyChecklist", "Note", "Activity", "DailyClose"):
        for rec in export[table]:
            archived = LegacyArchive.objects.get(source_model=table, legacy_id=rec["legacy_id"])
            assert archived.payload == rec
            assert archived.checksum == rec["checksum"]


def test_audit_events_created_with_migration_import_action(export_path):
    _import(export_path, batch_name="run-1")

    export = json.loads(export_path.read_text())
    assert AuditEvent.objects.filter(action=AuditAction.MIGRATION_IMPORT).count() == len(
        export["AuditEvent"]
    )
    for rec in export["AuditEvent"]:
        event_map = LegacyIdMap.objects.get(
            source_model="AuditEvent", legacy_id=rec["legacy_id"], target_model="audit.AuditEvent"
        )
        event = AuditEvent.objects.get(pk=event_map.target_id)
        assert event.actor_label == rec["actor_label"]
        assert event.actor is None  # tidak ditebak, label tetap dari legacy


def test_default_clinic_decision_is_recorded_loudly_in_batch_notes(export_path):
    _import(export_path, batch_name="run-1")
    batch = LegacyImportBatch.objects.get(name="run-1")
    assert "jemur-andayani" in batch.notes
    assert "KEPUTUSAN EKSPLISIT" in batch.notes
