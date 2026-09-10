#!/usr/bin/env python3
"""Snapshot SQLite yang konsisten walau WAL aktif dan aplikasi sedang menulis.

Memakai sqlite3.Connection.backup() dari stdlib, sehingga tidak memerlukan
sqlite3 CLI di host maupun container.

Pemakaian:
  db_snapshot.py backup <sumber.sqlite3> <tujuan.sqlite3>
  db_snapshot.py verify <db.sqlite3>
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


def backup(source: str, dest: str) -> int:
    src_path = Path(source)
    if not src_path.exists():
        print(f"ERROR: database tidak ditemukan: {source}", file=sys.stderr)
        return 1
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as src, sqlite3.connect(dest) as dst:
        src.backup(dst)
    print(f"snapshot ok: {dest} ({Path(dest).stat().st_size} bytes)")
    return 0


def verify(path: str) -> int:
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
        integrity = conn.execute("PRAGMA integrity_check;").fetchone()[0]
        tables = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table';"
        ).fetchone()[0]
        try:
            audit = conn.execute("SELECT count(*) FROM audit_auditevent;").fetchone()[0]
        except sqlite3.Error:
            audit = "n/a"
        try:
            users = conn.execute("SELECT count(*) FROM accounts_user;").fetchone()[0]
        except sqlite3.Error:
            users = "n/a"
    print(f"integrity={integrity} tables={tables} users={users} audit_events={audit}")
    return 0 if integrity == "ok" else 1


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    command = sys.argv[1]
    if command == "backup" and len(sys.argv) == 4:
        return backup(sys.argv[2], sys.argv[3])
    if command == "verify":
        return verify(sys.argv[2])
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
