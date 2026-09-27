"""Test gaya migration-rehearsal: jalankan seluruh pipeline generate -> import
-> import lagi -> reconcile sebagai subprocess Django manage.py terhadap
database SQLite sementara di /tmp, mirip pola rehearsal Fase 4/5 sebelumnya
(lihat handoff.md/current-progress.md: "migration rehearsal SQLite sementara
`/tmp`"). Ini BUKAN test yang jalan di database test pytest biasa — tujuannya
membuktikan pipeline bekerja end-to-end lewat command line sungguhan,
termasuk migrate dari nol.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"


def _run(args, env, timeout=120):
    result = subprocess.run(
        [str(VENV_PYTHON), "manage.py", *args],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result


@pytest.mark.skipif(not VENV_PYTHON.exists(), reason=".venv tidak tersedia di lingkungan ini")
def test_full_migration_rehearsal_pipeline_on_temp_sqlite(tmp_path):
    db_path = tmp_path / "aom_fase6_pytest_rehearsal.sqlite3"
    export_path = tmp_path / "export.json"

    env = os.environ.copy()
    env["DJANGO_DB_PATH"] = str(db_path)
    env["DJANGO_SETTINGS_MODULE"] = "config.settings"

    migrate = _run(["migrate", "--noinput"], env)
    assert migrate.returncode == 0, migrate.stdout + migrate.stderr

    generate = _run(
        ["generate_legacy_export_fixture", str(export_path), "--seed=20260926", "--count=3"],
        env,
    )
    assert generate.returncode == 0, generate.stdout + generate.stderr
    assert export_path.exists()
    export_data = json.loads(export_path.read_text())
    assert export_data["manifest"]["tables"]["Task"]["row_count"] == 5  # 2 fixed (OPEN/DONE) + count=3

    import1 = _run(
        ["import_legacy_export", str(export_path), "--batch-name=rehearsal-1"], env
    )
    assert import1.returncode == 0, import1.stdout + import1.stderr
    assert "Jumlah exception:" in import1.stdout

    count_script = (
        "from aom_migration.models import LegacyIdMap, LegacyArchive; "
        "from core.models import ActionItem; "
        "from audit.models import AuditEvent; "
        "print(LegacyIdMap.objects.count(), LegacyArchive.objects.count(), "
        "ActionItem.objects.count(), AuditEvent.objects.count())"
    )
    counts1 = _run(["shell", "-c", count_script], env)
    assert counts1.returncode == 0, counts1.stdout + counts1.stderr

    import2 = _run(
        ["import_legacy_export", str(export_path), "--batch-name=rehearsal-2"], env
    )
    assert import2.returncode == 0, import2.stdout + import2.stderr

    counts2 = _run(["shell", "-c", count_script], env)
    assert counts2.returncode == 0, counts2.stdout + counts2.stderr

    # Idempotensi end-to-end: jumlah baris target tidak berubah setelah import kedua.
    assert counts1.stdout.strip() == counts2.stdout.strip(), (
        f"idempotency violated: run1={counts1.stdout!r} run2={counts2.stdout!r}"
    )

    reconcile = _run(["reconcile_legacy_import", str(export_path)], env)
    assert reconcile.returncode == 0, reconcile.stdout + reconcile.stderr
    assert "REKONSILIASI: PASS" in reconcile.stdout
