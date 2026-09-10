#!/usr/bin/env bash
# Mengekspos aplikasi sebagai HTTPS privat di dalam tailnet menggunakan Tailscale Serve.
# Serve = hanya perangkat dalam tailnet. Funnel (internet publik) TIDAK digunakan.
set -euo pipefail

PORT="${APP_PORT:-8000}"

echo "== Status Tailscale =="
tailscale status --peers=false

echo
echo "== Memastikan Funnel tidak aktif =="
if tailscale funnel status 2>/dev/null | grep -qi "https"; then
  echo "PERINGATAN: Funnel terdeteksi aktif. Mematikan..."
  tailscale funnel --https=443 off || true
fi

echo
echo "== Mengaktifkan Serve pada 127.0.0.1:$PORT =="
tailscale serve --bg --https=443 "http://127.0.0.1:$PORT"

echo
echo "== Konfigurasi Serve aktif =="
tailscale serve status

echo
echo "Hostname aplikasi: https://$(tailscale status --json | grep -o '"DNSName":"[^"]*"' | head -1 | cut -d'"' -f4 | sed 's/\.$//')"
echo
echo "Verifikasi sebelum go-live:"
echo "  1. Buka hostname di atas dari perangkat tailnet berizin -> harus tampil halaman login."
echo "  2. Buka dari jaringan publik (data seluler tanpa Tailscale) -> harus GAGAL."
echo "  3. Jalankan: ss -tlnp | grep 8000  -> harus 127.0.0.1:8000, BUKAN 0.0.0.0:8000."
