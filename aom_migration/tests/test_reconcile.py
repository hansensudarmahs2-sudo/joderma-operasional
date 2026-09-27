"""Test rekonsiliasi (`reconcile_legacy_import`) — bukti bahwa command benar-
benar memeriksa sesuatu (PASS pada import bersih, FAIL non-zero saat manifest
sengaja dirusak), bukan no-op yang selalu sukses.
"""
from __future__ import annotations

import io
import json

import pytest
from django.core.management import CommandError, call_command

pytestmark = pytest.mark.django_db


@pytest.fixture
def export_path(tmp_path):
    path = tmp_path / "export.json"
    call_command("generate_legacy_export_fixture", str(path), "--seed=20260926", "--count=2")
    return path


def _import(path, batch_name="test-batch"):
    call_command("import_legacy_export", str(path), f"--batch-name={batch_name}")


def test_reconcile_passes_on_clean_import(export_path):
    _import(export_path)
    out = io.StringIO()
    call_command("reconcile_legacy_import", str(export_path), stdout=out)
    output = out.getvalue()
    assert "REKONSILIASI: PASS" in output


def test_reconcile_fails_on_corrupted_record_content(export_path, tmp_path):
    """Negative test: merusak isi record tanpa mengubah checksum-nya harus
    membuat reconcile melaporkan FAIL dan keluar dengan exit code non-zero.
    """
    _import(export_path)

    export = json.loads(export_path.read_text())
    export["Note"][0]["content"] = "DIRUSAK SENGAJA UNTUK TEST NEGATIF"
    corrupt_path = tmp_path / "corrupt.json"
    corrupt_path.write_text(json.dumps(export))

    out = io.StringIO()
    with pytest.raises(SystemExit) as exc_info:
        call_command("reconcile_legacy_import", str(corrupt_path), stdout=out)
    assert exc_info.value.code != 0
    output = out.getvalue()
    assert "REKONSILIASI: FAIL" in output
    assert "checksum" in output.lower()


def test_reconcile_fails_on_row_count_mismatch(export_path, tmp_path):
    """Negative test: menambah baris manifest tanpa mengimport data tersebut
    harus membuat pemeriksaan jumlah baris gagal.
    """
    _import(export_path)

    export = json.loads(export_path.read_text())
    export["manifest"]["tables"]["Task"]["row_count"] += 1
    corrupt_path = tmp_path / "corrupt_count.json"
    corrupt_path.write_text(json.dumps(export))

    out = io.StringIO()
    with pytest.raises(SystemExit) as exc_info:
        call_command("reconcile_legacy_import", str(corrupt_path), stdout=out)
    assert exc_info.value.code != 0
    output = out.getvalue()
    assert "REKONSILIASI: FAIL" in output
    assert "Task" in output


def test_reconcile_requires_existing_batch(tmp_path, export_path):
    with pytest.raises(CommandError):
        call_command(
            "reconcile_legacy_import", str(export_path), "--batch-id=999999"
        )
