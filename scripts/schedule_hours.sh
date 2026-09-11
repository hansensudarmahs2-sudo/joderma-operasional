#!/usr/bin/env bash
# OPSIONAL — membatasi jam akses staf ke JoDerma Staff Ops.
#
# Yang dimatikan adalah AKSES (Tailscale Serve), bukan container.
# Alasannya:
#   - Container tetap hidup, sehingga backup malam (02.00) tetap berjalan.
#   - Data tidak pernah berisiko rusak karena container dihentikan paksa.
#   - Menghidupkan kembali instan, tanpa menunggu container start.
#
# Pemakaian:
#   sudo ./scripts/schedule_hours.sh on     # buka akses
#   sudo ./scripts/schedule_hours.sh off    # tutup akses
#   sudo ./scripts/schedule_hours.sh status
#
# Pasang jadwal otomatis (contoh buka 11.00, tutup 23.59):
#   sudo crontab -e
#   0  11 * * * /home/joderma-jemur/joderma-ops/scripts/schedule_hours.sh on  >> /home/joderma-jemur/joderma-ops/logs/schedule.log 2>&1
#   59 23 * * * /home/joderma-jemur/joderma-ops/scripts/schedule_hours.sh off >> /home/joderma-jemur/joderma-ops/logs/schedule.log 2>&1
#
# CATATAN PENTING: klinik buka 12.00-21.00 dan checklist pembukaan dikerjakan
# SEBELUM jam buka. Menyalakan akses pukul 14.00 membuat staf tidak dapat
# mencatat pembukaan sama sekali. Bila memakai jadwal, nyalakan minimal
# 1 jam sebelum klinik buka.
set -euo pipefail

APP_PORT="${APP_PORT:-8731}"
SERVE_PORT="${SERVE_PORT:-8443}"
ACTION="${1:-status}"

if [ "$(id -u)" -ne 0 ] && [ "$ACTION" != "status" ]; then
  echo "Perlu hak root. Jalankan: sudo $0 $ACTION" >&2
  exit 1
fi

case "$ACTION" in
  on)
    tailscale serve --bg --https="$SERVE_PORT" "http://127.0.0.1:$APP_PORT"
    echo "$(date -Iseconds) AKSES DIBUKA pada port $SERVE_PORT"
    ;;
  off)
    tailscale serve --https="$SERVE_PORT" off
    echo "$(date -Iseconds) AKSES DITUTUP pada port $SERVE_PORT (container tetap jalan, backup tetap berjalan)"
    ;;
  status)
    echo "=== Serve ==="
    tailscale serve status || true
    echo "=== Container ==="
    docker ps --filter name=joderma-ops --format '{{.Names}}\t{{.Status}}' || true
    ;;
  *)
    echo "Pemakaian: $0 {on|off|status}" >&2
    exit 2
    ;;
esac
