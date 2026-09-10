#!/usr/bin/env bash
# Menjalankan backup setiap malam pukul 02:00 Asia/Jakarta (container sidecar).
set -euo pipefail

while true; do
  NOW="$(date +%s)"
  NEXT="$(date -d 'tomorrow 02:00' +%s 2>/dev/null || date -v+1d -j -f '%H:%M' '02:00' +%s)"
  TODAY_TWO="$(date -d 'today 02:00' +%s 2>/dev/null || echo 0)"
  if [ "$TODAY_TWO" -gt "$NOW" ]; then NEXT="$TODAY_TWO"; fi
  SLEEP=$((NEXT - NOW))
  echo "[backup-loop] backup berikutnya dalam ${SLEEP}s"
  sleep "$SLEEP"
  if /app/scripts/backup.sh >> /app/logs/backup.log 2>&1; then
    echo "[backup-loop] sukses $(date -Iseconds)"
  else
    echo "[backup-loop] GAGAL $(date -Iseconds)" | tee -a /app/logs/backup-failure.log
  fi
done
