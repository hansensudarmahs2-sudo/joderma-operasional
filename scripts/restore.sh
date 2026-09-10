#!/usr/bin/env bash
# Restore backup ke direktori target. Uji restore wajib minimal per kuartal (PRD 15.4).
# Pemakaian: ./scripts/restore.sh <arsip.tar.gz[.enc]> <direktori-tujuan>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYBIN="${PYBIN:-python3}"
ARCHIVE="${1:?Arsip backup wajib diisi}"
TARGET="${2:?Direktori tujuan wajib diisi}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$TARGET"

if [[ "$ARCHIVE" == *.enc ]]; then
  : "${BACKUP_PASSPHRASE:?BACKUP_PASSPHRASE wajib diisi untuk arsip terenkripsi}"
  openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
    -in "$ARCHIVE" -out "$WORK/backup.tar.gz" -pass env:BACKUP_PASSPHRASE
  ARCHIVE="$WORK/backup.tar.gz"
fi

tar -xzf "$ARCHIVE" -C "$WORK"
echo "--- MANIFEST ---"; cat "$WORK/MANIFEST.txt"

"$PYBIN" "$SCRIPT_DIR/db_snapshot.py" verify "$WORK/db.sqlite3"

mkdir -p "$TARGET/data"
cp "$WORK/db.sqlite3" "$TARGET/data/db.sqlite3"
tar -xzf "$WORK/private_media.tar.gz" -C "$TARGET"

echo "[restore] selesai ke $TARGET"
echo "[restore] verifikasi manual: jalankan aplikasi dengan DJANGO_DB_PATH=$TARGET/data/db.sqlite3"
