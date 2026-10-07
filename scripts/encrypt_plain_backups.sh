#!/usr/bin/env bash
# Sekali jalan: enkripsi arsip backup lama yang tertinggal tanpa enkripsi.
#
# Setiap *.tar.gz (bukan .enc) di folder sasaran dienkripsi dengan parameter
# yang sama persis seperti backup.sh, diverifikasi dengan mendekripsinya
# kembali, lalu hasilnya dipindah ke backups/predeploy/ dan arsip polosnya
# dihapus. Arsip polos tidak dihapus bila verifikasi gagal.
#
# Pemakaian: bash scripts/encrypt_plain_backups.sh [--dry-run] [folder]
#   folder bawaan: $BACKUP_DIR/daily
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${APP_DIR:-$(dirname "$SCRIPT_DIR")}"
BACKUP_DIR="${BACKUP_DIR:-$APP_DIR/backups}"

DRY_RUN=no
SRC_DIR=""
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=yes ;;
    -*) echo "[enkripsi] GAGAL: opsi tidak dikenal: $arg" >&2; exit 2 ;;
    *) SRC_DIR="$arg" ;;
  esac
done
SRC_DIR="${SRC_DIR:-$BACKUP_DIR/daily}"
DEST_DIR="$BACKUP_DIR/predeploy"

# Passphrase: lingkungan dulu, lalu baris BACKUP_PASSPHRASE= di .env (tanpa source).
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
      echo "[enkripsi] GAGAL: nilai BACKUP_PASSPHRASE di .env ambigu (berisi $, komentar, atau spasi tepi); ekspor BACKUP_PASSPHRASE secara manual." >&2
      exit 1 ;;
  esac
  BACKUP_PASSPHRASE="$PASS_FROM_ENV"
  unset PASS_FROM_ENV
fi
export BACKUP_PASSPHRASE="${BACKUP_PASSPHRASE:-}"
if [ -z "$BACKUP_PASSPHRASE" ]; then
  echo "[enkripsi] GAGAL: BACKUP_PASSPHRASE tidak tersedia; tidak ada yang dienkripsi." >&2
  exit 1
fi

if [ ! -d "$SRC_DIR" ]; then
  echo "[enkripsi] GAGAL: folder tidak ditemukan: $SRC_DIR" >&2
  exit 1
fi

shopt -s nullglob
FILES=("$SRC_DIR"/*.tar.gz)
if [ "${#FILES[@]}" -eq 0 ]; then
  echo "[enkripsi] tidak ada arsip polos di $SRC_DIR"
  exit 0
fi

[ "$DRY_RUN" = "yes" ] || mkdir -p "$DEST_DIR"
TMPD="$(mktemp -d)"
trap 'rm -rf "$TMPD"' EXIT
COUNT=0
for plain in "${FILES[@]}"; do
  name="$(basename "$plain")"
  if [ -e "$DEST_DIR/$name.enc" ]; then
    echo "[enkripsi] LEWATI $name: $DEST_DIR/$name.enc sudah ada (tidak ditimpa)."
    continue
  fi
  if [ "$DRY_RUN" = "yes" ]; then
    echo "[enkripsi] (dry-run) $name -> $DEST_DIR/$name.enc"
    continue
  fi
  tmp_enc="$TMPD/$name.enc"
  if ! openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt \
      -in "$plain" -out "$tmp_enc" -pass env:BACKUP_PASSPHRASE; then
    echo "[enkripsi] GAGAL mengenkripsi $name; arsip polos dibiarkan." >&2
    exit 1
  fi
  # Verifikasi byte demi byte terhadap arsip asli sebelum menghapusnya.
  if ! openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
      -in "$tmp_enc" -out "$TMPD/verify.tar.gz" -pass env:BACKUP_PASSPHRASE \
      || ! cmp -s "$TMPD/verify.tar.gz" "$plain"; then
    echo "[enkripsi] GAGAL verifikasi $name; arsip polos dibiarkan." >&2
    exit 1
  fi
  rm -f "$TMPD/verify.tar.gz"
  # Salin ke tujuan dengan nama sementara lalu rename (atomik di filesystem yang sama).
  cp "$tmp_enc" "$DEST_DIR/.$name.enc.tmp"
  mv "$DEST_DIR/.$name.enc.tmp" "$DEST_DIR/$name.enc"
  rm -f "$tmp_enc" "$plain"
  COUNT=$((COUNT + 1))
  echo "[enkripsi] $name -> predeploy/$name.enc (terverifikasi, arsip polos dihapus)"
done

if [ "$DRY_RUN" = "yes" ]; then
  echo "[enkripsi] dry-run: tidak ada yang diubah."
else
  echo "[enkripsi] selesai: $COUNT arsip dienkripsi ke $DEST_DIR"
fi
