"""Utilitas checksum kanonik untuk kontrak ekspor legacy AOM standalone.

Lihat `docs/AOM_LEGACY_EXPORT_SCHEMA.md` bagian 2 untuk definisi lengkap.
Modul ini dipakai oleh generator fixture, importer, dan reconciler agar
ketiganya selalu menghitung checksum dengan cara yang identik.
"""
from __future__ import annotations

import hashlib
import json

SOURCE_TABLES = (
    "ChecklistTemplate",
    "DailyChecklist",
    "Task",
    "Note",
    "Activity",
    "DailyClose",
    "AuditEvent",
)

# Tabel yang menjadi histori read-only di LegacyArchive (tidak dikonversi ke
# objek live) — plan 12.2.7.
ARCHIVE_TABLES = (
    "ChecklistTemplate",
    "DailyChecklist",
    "Note",
    "Activity",
    "DailyClose",
)


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_json(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def record_checksum(record: dict) -> str:
    """Checksum sha256 dari record tanpa field `checksum`, kunci diurutkan."""
    without = {k: v for k, v in record.items() if k != "checksum"}
    return f"sha256:{_sha256_hex(canonical_json(without))}"


def table_checksum(records: list[dict]) -> str:
    """Checksum agregat satu tabel: gabungan checksum per record, diurutkan
    berdasarkan legacy_id, digabung dengan newline, lalu di-hash.
    """
    ordered = sorted(records, key=lambda r: str(r.get("legacy_id", "")))
    joined = "\n".join(r.get("checksum", "") for r in ordered)
    return f"sha256:{_sha256_hex(joined)}"


def overall_checksum(table_checksums: dict[str, str]) -> str:
    """Checksum agregat seluruh ekspor: gabungan checksum per tabel, urutan
    tabel tetap sesuai SOURCE_TABLES, digabung newline, lalu di-hash.
    """
    joined = "\n".join(table_checksums.get(name, "") for name in SOURCE_TABLES)
    return f"sha256:{_sha256_hex(joined)}"


def build_manifest(export: dict, *, source_label: str, exported_at: str) -> dict:
    """Bangun blok manifest untuk berkas ekspor lengkap `export`
    (dict tabel -> list of records, checksum SUDAH terisi per record).
    """
    tables = {}
    table_sums = {}
    for name in SOURCE_TABLES:
        records = export.get(name, [])
        chk = table_checksum(records)
        table_sums[name] = chk
        tables[name] = {"row_count": len(records), "checksum": chk}
    return {
        "exported_at": exported_at,
        "source_label": source_label,
        "tables": tables,
        "overall_checksum": overall_checksum(table_sums),
    }
