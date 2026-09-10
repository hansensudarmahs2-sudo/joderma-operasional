# Runbook Operator — JoDerma Staff Ops

Dokumen untuk admin teknis. Prosedur harian untuk staf ada di `docs/panduan-staf.md`.

---

## 1. Instalasi produksi

### Prasyarat
- Mini-PC/server Linux yang selalu menyala, terhubung UPS.
- Docker + Docker Compose, atau Python 3.12 bila memakai systemd native.
- Tailscale terpasang dan sudah login ke tailnet JoDerma.
- Zona waktu host: `Asia/Jakarta`.

### Langkah (Docker)

```bash
git clone <repo> /opt/joderma-staff-ops
cd /opt/joderma-staff-ops

cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(64))"   # -> DJANGO_SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # -> BACKUP_PASSPHRASE
chmod 600 .env
# Isi DJANGO_ALLOWED_HOSTS dan DJANGO_CSRF_TRUSTED_ORIGINS dengan hostname
# MagicDNS server, mis. joderma-ops.tailnet-xxxx.ts.net

docker compose up -d --build
docker compose exec app python manage.py createsuperuser
```

**Simpan `BACKUP_PASSPHRASE` di brankas/manajer kata sandi terpisah dari server.**
Tanpa passphrase itu, backup terenkripsi tidak dapat dipulihkan.

### Langkah (systemd native)

```bash
sudo useradd --system --home /opt/joderma-staff-ops joderma
sudo cp deploy/joderma-ops.service /etc/systemd/system/
sudo cp deploy/joderma-backup.service deploy/joderma-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now joderma-ops.service joderma-backup.timer
```

---

## 2. Tailscale: akses privat

Gunakan **Serve**, jangan Funnel. Serve mempublikasikan layanan hanya ke perangkat
dalam tailnet dan tetap tunduk pada access control; Funnel ditujukan untuk akses
internet publik dan **tidak boleh dipakai** untuk aplikasi ini.

```bash
sudo tailscale up --advertise-tags=tag:joderma-ops
sudo ./scripts/tailscale_serve.sh
```

Terapkan kebijakan akses dari `deploy/tailscale-policy-example.hujson` di admin
console Tailscale. Prinsipnya:
- Deny-by-default; hanya grup yang disebut yang memperoleh akses.
- `group:joderma-staff` -> hanya tcp:443 ke `tag:joderma-ops`.
- `group:joderma-tech` -> tcp:443 + tcp:22 (SSH admin), terpisah dari hak bisnis.
- Port aplikasi (8000) tidak pernah diberikan ke siapa pun; hanya loopback.

Simpan policy dengan blok `tests` agar Tailscale memverifikasi aturan saat disimpan.

### Verifikasi wajib sebelum go-live

```bash
./scripts/verify_deployment.sh
```

Ditambah tiga uji manual yang tidak dapat diotomatiskan:
1. Buka hostname dari perangkat tailnet berizin -> halaman login muncul.
2. Buka dari data seluler tanpa Tailscale -> **harus gagal total**.
3. Reboot host -> aplikasi kembali otomatis tanpa intervensi.

---

## 3. Operasional harian

| Kegiatan | Perintah/lokasi |
|---|---|
| Cek aplikasi hidup | `curl -fsS http://127.0.0.1:8000/health/` |
| Lihat log aplikasi | `docker compose logs -f app` atau `journalctl -u joderma-ops -f` |
| Lihat log backup | `logs/backup.log` |
| Cek kapasitas disk | `df -h /` — bertindak bila di atas 80% |
| Audit akses | Menu **Audit** di aplikasi (supervisor/owner/admin berizin) |

Log aplikasi terstruktur JSON dengan rotasi 10 MB × 10 berkas. Data pasien, password,
token, dan isi komplain **tidak** ditulis ke log teknis.

---

## 4. Backup dan restore

Backup otomatis setiap malam 02:00 WIB: snapshot SQLite konsisten (aman meski WAL
aktif) + arsip lampiran, dienkripsi AES-256, retensi 7 harian / 4 mingguan / 12 bulanan.

```bash
./scripts/backup.sh                    # backup manual
ls -lt backups/daily/                  # daftar backup
```

Salinan perangkat kedua: mount disk eksternal lalu set `BACKUP_SECOND_COPY_DIR`
di `.env`. PRD mensyaratkan minimal satu salinan terenkripsi di media berbeda.

### Uji restore (wajib minimal per kuartal, catat hasilnya)

```bash
export BACKUP_PASSPHRASE='<dari brankas>'
./scripts/restore.sh backups/daily/joderma-ops-YYYYMMDD-HHMMSS.tar.gz.enc /tmp/uji-restore

# Verifikasi data terbaca lewat aplikasi
DJANGO_DB_PATH=/tmp/uji-restore/data/db.sqlite3 .venv/bin/python manage.py shell -c \
  "from core.models import Clinic; from accounts.models import User; \
   print(Clinic.objects.first(), User.objects.count())"
```

Restore dianggap lulus bila: `integrity=ok`, jumlah pengguna wajar, lampiran terbuka,
dan aplikasi dapat login memakai database hasil restore.

**Target: RPO 24 jam, RTO 4 jam pada jam operasional.**

---

## 5. Pemulihan insiden

| Gejala | Tindakan |
|---|---|
| Aplikasi tidak dapat diakses staf | Cek `tailscale status`, lalu `/health/` lokal, lalu log aplikasi |
| Health gagal | `docker compose restart app`; bila gagal, periksa log migrasi |
| Disk penuh | Hapus backup bulanan lama setelah dipastikan ada salinan kedua; cek ukuran `private_media/` |
| Database corrupt | Hentikan aplikasi, restore backup terakhir, jalankan uji restore di atas |
| Tailscale bermasalah total | Kontingensi kertas (checklist, kas, antrean) lalu entry susulan dengan catatan alasan |
| Staf lupa password | Admin: menu **Admin ▸ Pengguna**, isi kata sandi baru; pengguna wajib menggantinya saat login |
| Staf keluar dari klinik | Nonaktifkan akun (jangan hapus) — riwayat dan audit tetap utuh |

---

## 6. Perubahan konfigurasi kebijakan

Semua kebijakan operasional dapat diubah tanpa deploy ulang, lewat
**Admin ▸ Konfigurasi** (`/hari-ini/konfigurasi/`). Contoh kunci:

| Kunci | Arti |
|---|---|
| `cash.dual_control_enabled` | Wajibkan dua orang untuk verifikasi kas |
| `queue.keep_number_statuses` | Status pembayaran yang mempertahankan nomor antrean |
| `nurse.skip_keeps_position` | Apakah skip mempertahankan posisi perawat |
| `nurse.cancel_before_start_restores_position` | Efek pembatalan sebelum tindakan dimulai |
| `break.min_active_front_desk` / `break.min_active_nurse` | Minimum staf aktif saat istirahat |
| `sla.<TINGKAT>.assign_hours` / `resolve_hours` | Target SLA per tingkat |

Setiap perubahan konfigurasi tercatat di audit log beserta nilai lama dan baru.

Template checklist dikelola di **Admin ▸ Template**. Perubahan template hanya berlaku
untuk sesi hari baru; checklist historis tidak pernah berubah.

---

## 7. Keamanan yang harus dijaga

- Aplikasi **hanya** listen di `127.0.0.1`. Jangan pernah mengubah bind ke `0.0.0.0`.
- Gunakan Serve, bukan Funnel. Jalankan `verify_deployment.sh` setelah setiap perubahan.
- `.env` permission 600, tidak pernah masuk git.
- Admin teknis tidak otomatis memperoleh hak bisnis (kas, detail pasien, komplain
  terbatas). Hak itu diberikan eksplisit sebagai kapabilitas tambahan dan tercatat.
- Perbarui dependensi dan OS secara berkala:
  `docker compose build --pull --no-cache && docker compose up -d`
- Retensi audit 24 bulan; kebijakan retensi final wajib disetujui manajemen sebelum
  produksi sesuai peraturan Indonesia.
