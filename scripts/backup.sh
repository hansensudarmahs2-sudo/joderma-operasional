#!/usr/bin/env bash
# Backup database + lampiran, terenkripsi, dengan rotasi (PRD 15.4).
# Retensi: 7 harian, 4 mingguan, 12 bulanan.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYBIN="${PYBIN:-python3}"
APP_DIR="${APP_DIR:-$(dirname "$SCRIPT_DIR")}"
DB_PATH="${DJANGO_DB_PATH:-$APP_DIR/data/db.sqlite3}"
MEDIA_DIR="${DJANGO_MEDIA_ROOT:-$APP_DIR/private_media}"
BACKUP_DIR="${BACKUP_DIR:-$APP_DIR/backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"
DOW="$(date +%u)"     # 7 = Minggu
DOM="$(date +%d)"

mkdir -p "$BACKUP_DIR/daily" "$BACKUP_DIR/weekly" "$BACKUP_DIR/monthly" "$BACKUP_DIR/tmp"
WORK="$BACKUP_DIR/tmp/$STAMP"
mkdir -p "$WORK"

echo "[backup] mulai $STAMP"

# 1. Snapshot database konsisten (aman meski WAL aktif dan aplikasi berjalan)
"$PYBIN" "$SCRIPT_DIR/db_snapshot.py" backup "$DB_PATH" "$WORK/db.sqlite3"
"$PYBIN" "$SCRIPT_DIR/db_snapshot.py" verify "$WORK/db.sqlite3"

# 2. Lampiran
tar -czf "$WORK/private_media.tar.gz" -C "$(dirname "$MEDIA_DIR")" "$(basename "$MEDIA_DIR")"

# 3. Kode dan dokumentasi.
#
# Data operasional tanpa aplikasinya tidak cukup untuk memulihkan layanan:
# basis data SQLite tidak berguna bila kode yang membacanya ikut hilang.
# Yang disalin hanya berkas yang dilacak Git, sehingga .env, database,
# lampiran, dan log tidak pernah ikut -- rahasia tetap di luar arsip.
CODE_INCLUDED=no
if command -v git >/dev/null 2>&1 && git -C "$APP_DIR" rev-parse --git-dir >/dev/null 2>&1; then
  git -C "$APP_DIR" ls-files -z \
    | tar -czf "$WORK/source.tar.gz" -C "$APP_DIR" --null -T - 2>/dev/null \
    && CODE_INCLUDED=git
fi
if [ "$CODE_INCLUDED" = "no" ]; then
  # Salinan hasil rsync tidak membawa riwayat Git. Dokumentasi dan script
  # tetap diselamatkan agar prosedur pemulihan tidak ikut hilang.
  tar -czf "$WORK/source.tar.gz" -C "$APP_DIR" \
    --exclude='.git' --exclude='.venv' --exclude='data' --exclude='private_media' \
    --exclude='backups' --exclude='logs' --exclude='staticfiles' \
    --exclude='__pycache__' --exclude='.env' \
    . 2>/dev/null && CODE_INCLUDED=files
fi

# 4. Manifest (tanpa secret)
cat > "$WORK/MANIFEST.txt" <<EOF
backup_stamp=$STAMP
db_size_bytes=$(stat -c%s "$WORK/db.sqlite3")
media_size_bytes=$(stat -c%s "$WORK/private_media.tar.gz")
source_included=$CODE_INCLUDED
source_size_bytes=$(stat -c%s "$WORK/source.tar.gz" 2>/dev/null || echo 0)
git_commit=$(git -C "$APP_DIR" rev-parse --short HEAD 2>/dev/null || echo "-")
host=$(hostname)
EOF

ARCHIVE="$BACKUP_DIR/daily/joderma-ops-$STAMP.tar.gz"
tar -czf "$ARCHIVE" -C "$WORK" db.sqlite3 private_media.tar.gz source.tar.gz MANIFEST.txt
rm -rf "$WORK"

# 5. Enkripsi bila passphrase tersedia (minimal satu salinan terenkripsi wajib)
if [ -n "${BACKUP_PASSPHRASE:-}" ]; then
  openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt \
    -in "$ARCHIVE" -out "$ARCHIVE.enc" -pass env:BACKUP_PASSPHRASE
  rm -f "$ARCHIVE"
  ARCHIVE="$ARCHIVE.enc"
  echo "[backup] terenkripsi: $(basename "$ARCHIVE")"
else
  echo "[backup] PERINGATAN: BACKUP_PASSPHRASE kosong, arsip TIDAK terenkripsi."
fi

# 6. Salin ke mingguan/bulanan
[ "$DOW" = "7" ] && cp "$ARCHIVE" "$BACKUP_DIR/weekly/"
[ "$DOM" = "01" ] && cp "$ARCHIVE" "$BACKUP_DIR/monthly/"

# 7. Rotasi
prune() {
  local dir="$1" keep="$2"
  ls -1t "$dir" 2>/dev/null | tail -n "+$((keep + 1))" | while read -r old; do
    rm -f "$dir/$old"
    echo "[backup] hapus lama: $old"
  done
}
prune "$BACKUP_DIR/daily" 7
prune "$BACKUP_DIR/weekly" 4
prune "$BACKUP_DIR/monthly" 12

# 8. Salinan ke perangkat kedua bila di-mount
if [ -n "${BACKUP_SECOND_COPY_DIR:-}" ] && [ -d "$BACKUP_SECOND_COPY_DIR" ]; then
  cp "$ARCHIVE" "$BACKUP_SECOND_COPY_DIR/" && echo "[backup] salinan kedua tersimpan."
else
  echo "[backup] CATATAN: salinan perangkat kedua belum dikonfigurasi (BACKUP_SECOND_COPY_DIR)."
fi

echo "[backup] selesai: $(basename "$ARCHIVE")"
