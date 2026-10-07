#!/usr/bin/env bash
# Backup database + lampiran, terenkripsi, dengan rotasi (PRD 15.4).
# Retensi: 7 harian, 4 mingguan, 12 bulanan, 10 sebelum-deploy.
#
# Pemakaian:
#   scripts/backup.sh               backup harian (dijalankan container backup pukul 02.00)
#   scripts/backup.sh --predeploy   backup sebelum deploy (atau BACKUP_KIND=predeploy)
#
# Backup sebelum deploy disimpan terpisah di backups/predeploy/ dan tidak ikut
# rotasi harian/mingguan/bulanan. Tanpa pemisahan ini, tujuh deploy dalam sehari
# menggusur semua backup malam, dan healthcheck container backup (yang membaca
# backups/daily/) tertutup oleh backup manual. Backup sebelum deploy wajib
# terenkripsi; passphrase dibaca dari BACKUP_PASSPHRASE atau dari baris
# BACKUP_PASSPHRASE= di $APP_DIR/.env (tanpa meng-source berkas itu).
set -euo pipefail
umask 077

KIND="${BACKUP_KIND:-daily}"
if [ "${1:-}" = "--predeploy" ]; then
  KIND="predeploy"
elif [ -n "${1:-}" ]; then
  echo "[backup] GAGAL: argumen tidak dikenal: $1 (gunakan --predeploy atau tanpa argumen)." >&2
  exit 2
fi
case "$KIND" in
  daily|predeploy) ;;
  *) echo "[backup] GAGAL: BACKUP_KIND tidak dikenal: $KIND (daily|predeploy)." >&2; exit 2 ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYBIN="${PYBIN:-python3}"
APP_DIR="${APP_DIR:-$(dirname "$SCRIPT_DIR")}"
DB_PATH="${DJANGO_DB_PATH:-$APP_DIR/data/db.sqlite3}"
MEDIA_DIR="${DJANGO_MEDIA_ROOT:-$APP_DIR/private_media}"
BACKUP_DIR="${BACKUP_DIR:-$APP_DIR/backups}"
KEEP_PREDEPLOY="${BACKUP_KEEP_PREDEPLOY:-10}"
case "$KEEP_PREDEPLOY" in
  ''|*[!0-9]*|0*)
    echo "[backup] GAGAL: BACKUP_KEEP_PREDEPLOY harus bilangan bulat >= 1 (nilai: $KEEP_PREDEPLOY)." >&2
    exit 2 ;;
esac
STAMP="$(date +%Y%m%d-%H%M%S)"
DOW="$(date +%u)"     # 7 = Minggu
DOM="$(date +%d)"

# Passphrase: dari lingkungan; bila kosong (mis. dijalankan di host, bukan di
# container) baca dari $APP_DIR/.env tanpa meng-source berkas itu. Nilainya
# tidak pernah dicetak.
if [ -z "${BACKUP_PASSPHRASE:-}" ] && [ -r "$APP_DIR/.env" ]; then
  PASS_FROM_ENV="$(grep -m1 '^BACKUP_PASSPHRASE=' "$APP_DIR/.env" | cut -d= -f2- || true)"
  PASS_FROM_ENV="${PASS_FROM_ENV%$'\r'}"
  if [ "${#PASS_FROM_ENV}" -ge 2 ]; then
    case "$PASS_FROM_ENV" in
      \"*\") PASS_FROM_ENV="${PASS_FROM_ENV:1:${#PASS_FROM_ENV}-2}" ;;
      \'*\') PASS_FROM_ENV="${PASS_FROM_ENV:1:${#PASS_FROM_ENV}-2}" ;;
    esac
  fi
  # Compose menafsirkan $ dan komentar; shell host tidak. Nilai yang bisa
  # ditafsirkan berbeda ditolak, bukan ditebak.
  case "$PASS_FROM_ENV" in
    *'$'*|*' #'*|[[:space:]]*|*[[:space:]])
      echo "[backup] GAGAL: nilai BACKUP_PASSPHRASE di .env ambigu (berisi $, komentar, atau spasi tepi); ekspor BACKUP_PASSPHRASE secara manual." >&2
      exit 1 ;;
  esac
  BACKUP_PASSPHRASE="$PASS_FROM_ENV"
  unset PASS_FROM_ENV
fi
export BACKUP_PASSPHRASE="${BACKUP_PASSPHRASE:-}"

if [ "$KIND" = "predeploy" ] && [ -z "$BACKUP_PASSPHRASE" ]; then
  echo "[backup] GAGAL: BACKUP_PASSPHRASE tidak tersedia; backup sebelum deploy wajib terenkripsi." >&2
  exit 1
fi

OUT_DIR="$BACKUP_DIR/daily"
if [ "$KIND" = "predeploy" ]; then OUT_DIR="$BACKUP_DIR/predeploy"; fi
mkdir -p "$OUT_DIR" "$BACKUP_DIR/tmp"
if [ "$KIND" = "daily" ]; then
  mkdir -p "$BACKUP_DIR/weekly" "$BACKUP_DIR/monthly"
fi
WORK="$(mktemp -d "$BACKUP_DIR/tmp/$STAMP.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

echo "[backup] mulai $STAMP ($KIND)"

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
kind=$KIND
db_size_bytes=$(stat -c%s "$WORK/db.sqlite3")
media_size_bytes=$(stat -c%s "$WORK/private_media.tar.gz")
source_included=$CODE_INCLUDED
source_size_bytes=$(stat -c%s "$WORK/source.tar.gz" 2>/dev/null || echo 0)
git_commit=$(git -C "$APP_DIR" rev-parse --short HEAD 2>/dev/null || echo "-")
host=$(hostname)
EOF

# Arsip polos dibuat di folder kerja sementara, bukan di folder tujuan, supaya
# arsip tak terenkripsi tidak pernah tertinggal di backups/daily atau predeploy.
PLAIN="$WORK/joderma-ops.tar.gz"
tar -czf "$PLAIN" -C "$WORK" db.sqlite3 private_media.tar.gz source.tar.gz MANIFEST.txt

# Nama unik: dua backup dalam detik yang sama tidak boleh saling menimpa.
ARCHIVE="$OUT_DIR/joderma-ops-$STAMP.tar.gz"
N=1
while [ -e "$ARCHIVE" ] || [ -e "$ARCHIVE.enc" ]; do
  N=$((N + 1))
  ARCHIVE="$OUT_DIR/joderma-ops-$STAMP-$N.tar.gz"
done

# 5. Enkripsi bila passphrase tersedia (minimal satu salinan terenkripsi wajib;
#    pada mode predeploy passphrase sudah dipastikan ada di atas)
if [ -n "$BACKUP_PASSPHRASE" ]; then
  # Ditulis dulu di folder kerja, baru dipindah: proses yang terputus tidak
  # meninggalkan .enc terpotong di folder tujuan.
  if ! openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt \
      -in "$PLAIN" -out "$WORK/joderma-ops.tar.gz.enc" -pass env:BACKUP_PASSPHRASE; then
    echo "[backup] GAGAL: enkripsi arsip gagal." >&2
    exit 1
  fi
  mv "$WORK/joderma-ops.tar.gz.enc" "$ARCHIVE.enc"
  ARCHIVE="$ARCHIVE.enc"
  echo "[backup] terenkripsi: $(basename "$ARCHIVE")"
else
  mv "$PLAIN" "$ARCHIVE"
  echo "[backup] PERINGATAN: BACKUP_PASSPHRASE kosong, arsip TIDAK terenkripsi."
fi
rm -rf "$WORK"

# 6. Salin ke mingguan/bulanan (hanya backup harian)
if [ "$KIND" = "daily" ]; then
  if [ "$DOW" = "7" ]; then cp "$ARCHIVE" "$BACKUP_DIR/weekly/"; fi
  if [ "$DOM" = "01" ]; then cp "$ARCHIVE" "$BACKUP_DIR/monthly/"; fi
fi

# 7. Rotasi
prune() {
  local dir="$1" keep="$2"
  ls -1t "$dir" 2>/dev/null | tail -n "+$((keep + 1))" | while read -r old; do
    rm -f "$dir/$old"
    echo "[backup] hapus lama: $old"
  done
}
# Urut menurut nama berkas (joderma-ops-YYYYMMDD-HHMMSS...), bukan waktu berkas:
# arsip lama yang dienkripsi ulang atau disalin ulang mendapat waktu berkas baru
# dan, bila diurut waktu, justru bertahan menggantikan backup yang lebih baru.
prune_by_name() {
  local dir="$1" keep="$2"
  ls -1 "$dir" 2>/dev/null | grep '^joderma-ops-' | LC_ALL=C sort -r | tail -n "+$((keep + 1))" | while read -r old; do
    rm -f "$dir/$old"
    echo "[backup] hapus lama: $old"
  done
}
if [ "$KIND" = "predeploy" ]; then
  # Backup sebelum deploy tidak pernah menyentuh daily/weekly/monthly.
  prune_by_name "$BACKUP_DIR/predeploy" "$KEEP_PREDEPLOY"
else
  prune "$BACKUP_DIR/daily" 7
  prune "$BACKUP_DIR/weekly" 4
  prune "$BACKUP_DIR/monthly" 12
fi

# 8. Salinan ke perangkat kedua bila di-mount
if [ -n "${BACKUP_SECOND_COPY_DIR:-}" ] && [ -d "$BACKUP_SECOND_COPY_DIR" ]; then
  cp "$ARCHIVE" "$BACKUP_SECOND_COPY_DIR/" && echo "[backup] salinan kedua tersimpan."
else
  echo "[backup] CATATAN: salinan perangkat kedua belum dikonfigurasi (BACKUP_SECOND_COPY_DIR)."
fi

echo "[backup] selesai: $(basename "$ARCHIVE")"
