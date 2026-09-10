#!/usr/bin/env bash
# Verifikasi acceptance criteria deployment (PRD 20.8). Jalankan di host produksi.
set -uo pipefail

PASS=0; FAIL=0
check() {
  local label="$1"; shift
  if "$@" >/dev/null 2>&1; then echo "  LULUS  $label"; PASS=$((PASS+1));
  else echo "  GAGAL  $label"; FAIL=$((FAIL+1)); fi
}

echo "== Verifikasi deployment JoDerma Staff Ops =="

echo "[1] Backend hanya bind ke localhost"
if ss -tln 2>/dev/null | grep -q "127.0.0.1:8000"; then
  echo "  LULUS  aplikasi listen di 127.0.0.1:8000"; PASS=$((PASS+1))
else
  echo "  GAGAL  tidak menemukan listener 127.0.0.1:8000"; FAIL=$((FAIL+1))
fi
if ss -tln 2>/dev/null | grep -qE "0\.0\.0\.0:8000|\[::\]:8000"; then
  echo "  GAGAL  aplikasi terekspos ke semua interface (0.0.0.0:8000)"; FAIL=$((FAIL+1))
else
  echo "  LULUS  tidak ada listener wildcard pada port 8000"; PASS=$((PASS+1))
fi

echo "[2] Health endpoint"
check "health endpoint merespons" curl -fsS http://127.0.0.1:8000/health/

echo "[3] Tailscale Serve aktif, Funnel mati"
if tailscale serve status 2>/dev/null | grep -q "127.0.0.1:8000"; then
  echo "  LULUS  Serve mengarah ke 127.0.0.1:8000"; PASS=$((PASS+1))
else
  echo "  GAGAL  Serve belum dikonfigurasi"; FAIL=$((FAIL+1))
fi
if tailscale funnel status 2>/dev/null | grep -qi "https://"; then
  echo "  GAGAL  Funnel aktif — layanan berpotensi terekspos ke internet publik"; FAIL=$((FAIL+1))
else
  echo "  LULUS  Funnel tidak aktif"; PASS=$((PASS+1))
fi

echo "[4] Auto-start setelah restart"
if systemctl is-enabled joderma-ops.service >/dev/null 2>&1 \
   || docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' joderma-ops 2>/dev/null | grep -q "unless-stopped\|always"; then
  echo "  LULUS  auto-start dikonfigurasi"; PASS=$((PASS+1))
else
  echo "  GAGAL  auto-start belum dikonfigurasi"; FAIL=$((FAIL+1))
fi

echo "[5] Backup"
LATEST=$(ls -1t backups/daily/ 2>/dev/null | head -1 || true)
if [ -n "$LATEST" ]; then
  echo "  LULUS  backup terbaru: $LATEST"; PASS=$((PASS+1))
  case "$LATEST" in
    *.enc) echo "  LULUS  backup terenkripsi"; PASS=$((PASS+1)) ;;
    *) echo "  GAGAL  backup TIDAK terenkripsi (isi BACKUP_PASSPHRASE)"; FAIL=$((FAIL+1)) ;;
  esac
else
  echo "  GAGAL  belum ada backup harian"; FAIL=$((FAIL+1))
fi

echo "[6] Secret tidak berada di source control"
if git ls-files --error-unmatch .env >/dev/null 2>&1; then
  echo "  GAGAL  file .env ter-commit ke git"; FAIL=$((FAIL+1))
else
  echo "  LULUS  .env tidak ada di git"; PASS=$((PASS+1))
fi

echo
echo "Ringkasan: $PASS lulus, $FAIL gagal"
echo "Uji manual yang tidak dapat diotomatiskan:"
echo "  - Buka aplikasi dari jaringan publik tanpa Tailscale: HARUS gagal."
echo "  - Buka dari perangkat tailnet TIDAK berizin: HARUS ditolak kebijakan."
echo "  - Reboot host, lalu pastikan aplikasi kembali otomatis."
[ "$FAIL" -eq 0 ]
