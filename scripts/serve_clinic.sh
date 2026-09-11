#!/usr/bin/env bash
# Mengekspos JoDerma Staff Ops lewat Tailscale Serve pada port terpisah,
# TANPA mengganggu aplikasi lain yang sudah memakai path "/" (mis. Photodex).
#
# Perlu sudo. Jalankan di mini-PC klinik:
#   sudo ./scripts/serve_clinic.sh
set -euo pipefail

APP_PORT="${APP_PORT:-8731}"
SERVE_PORT="${SERVE_PORT:-8443}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Perlu hak root. Jalankan: sudo $0" >&2
  exit 1
fi

echo "== Layanan yang sudah terdaftar di Serve (tidak akan diubah) =="
tailscale serve status || true

echo
echo "== Memastikan aplikasi hidup di 127.0.0.1:$APP_PORT =="
if ! curl -fsS "http://127.0.0.1:$APP_PORT/health/" >/dev/null; then
  echo "GAGAL: aplikasi tidak merespons di port $APP_PORT." >&2
  echo "Jalankan dulu: cd ~/joderma-ops && docker compose up -d" >&2
  exit 1
fi
echo "OK."

echo
echo "== Mendaftarkan Serve HTTPS port $SERVE_PORT -> 127.0.0.1:$APP_PORT =="
tailscale serve --bg --https="$SERVE_PORT" "http://127.0.0.1:$APP_PORT"

echo
echo "== Memastikan Funnel TIDAK aktif (aplikasi tidak boleh ke internet publik) =="
if tailscale funnel status 2>/dev/null | grep -qi "funnel on"; then
  echo "PERINGATAN: Funnel terdeteksi. Mematikan untuk port $SERVE_PORT..."
  tailscale funnel --https="$SERVE_PORT" off || true
fi

HOSTNAME_TS=$(tailscale status --json | python3 -c "import sys,json;print(json.load(sys.stdin)['Self']['DNSName'].rstrip('.'))")

echo
echo "== Konfigurasi Serve sekarang =="
tailscale serve status

cat <<EOF

============================================================
JoDerma Staff Ops siap diakses staf:

    https://${HOSTNAME_TS}:${SERVE_PORT}/

Photodex tetap di alamat lamanya:

    https://${HOSTNAME_TS}/

Verifikasi:
    APP_PORT=${APP_PORT} ~/joderma-ops/scripts/verify_deployment.sh
============================================================
EOF
