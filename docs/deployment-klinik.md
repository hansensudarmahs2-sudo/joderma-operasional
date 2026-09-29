# Deployment Klinik — JoDerma Jemur Andayani

Dokumen ini menjelaskan instalasi yang **sedang berjalan**, bukan contoh generik.
Untuk prosedur operasional harian (backup, restore, gangguan) lihat
[`runbook.md`](runbook.md).

## Ringkasan instalasi

| | |
|---|---|
| Host | mini-PC klinik, hostname Tailscale `joderma-jemur` |
| Akses SSH | `ssh joderma-jemur@joderma-jemur` (dari dalam tailnet) |
| Direktori aplikasi | `~/joderma-ops` |
| Port internal | `127.0.0.1:8731` (loopback saja, tidak pernah terbuka ke LAN) |
| URL untuk staf | `https://joderma-jemur.<tailnet>.ts.net:8443/` |
| Container | `joderma-ops` (aplikasi) dan `joderma-ops-backup` (backup terjadwal) |
| Restart policy | `unless-stopped` — otomatis hidup kembali setelah mini-PC reboot |

Mini-PC ini juga menjalankan **Photodex** (aplikasi foto klinik) pada port 8080,
yang sudah menempati path root Tailscale Serve. Dua aplikasi tidak dapat berbagi
path yang sama pada satu hostname, karena itu JoDerma Staff Ops memakai **port
8443**. Photodex tetap di `https://joderma-jemur.<tailnet>.ts.net/` dan tidak
boleh terganggu oleh pekerjaan apa pun di dokumen ini.

## Instalasi pertama kali

Dijalankan dari mesin pengembangan, dengan mini-PC dapat dijangkau lewat Tailscale.

```bash
# 1. Kirim kode (tanpa venv, database, lampiran, atau berkas rahasia)
cd ~/joderma-staff-ops
rsync -az --delete \
  --exclude '.venv/' --exclude 'data/' --exclude 'private_media/' \
  --exclude 'logs/' --exclude 'backups/' --exclude 'staticfiles/' \
  --exclude '.git/' --exclude '__pycache__/' --exclude '.env' \
  ./ joderma-jemur@joderma-jemur:~/joderma-ops/
```

```bash
# 2. Di mini-PC: siapkan berkas rahasia dan direktori data
ssh joderma-jemur@joderma-jemur
cd ~/joderma-ops
cp .env.example .env

# Secret dibuat DI mini-PC, tidak pernah dikirim lewat jaringan atau ditulis di chat
python3 -c "import secrets; print('DJANGO_SECRET_KEY=' + secrets.token_urlsafe(64))" >> .env
python3 -c "import secrets; print('BACKUP_PASSPHRASE=' + secrets.token_urlsafe(32))" >> .env

# UID/GID host agar container dapat menulis ke direktori bind-mount
printf 'APP_UID=%s\nAPP_GID=%s\n' "$(id -u)" "$(id -g)" >> .env

mkdir -p data private_media logs backups/daily
```

Sunting `.env` dan sesuaikan minimal:

```
APP_PORT=8731
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=joderma-jemur.<tailnet>.ts.net,127.0.0.1
CLINIC_TIMEZONE=Asia/Jakarta
```

```bash
# 3. Bangun dan jalankan
docker compose up -d --build
docker compose ps                      # kedua container harus "Up"
curl -sS http://127.0.0.1:8731/health/  # harus {"status": "ok", ...}
```

```bash
# 4. Ekspos lewat Tailscale Serve (perlu sudo)
sudo ~/joderma-ops/scripts/serve_clinic.sh
tailscale serve status                  # pastikan Photodex di / masih ada
```

```bash
# 5. Akun administrator pertama
docker compose exec app python manage.py createsuperuser
```

Login lewat URL klinik, lalu buat akun staf asli dari menu **Admin ▸ Pengguna**.
Beri akun pribadi Anda peran ADMIN, dan simpan akun superuser sebagai cadangan
darurat yang tidak dipakai sehari-hari.

```bash
# 6. Verifikasi kesiapan sebelum pilot
docker compose exec app python manage.py pilot_check
```

## Memperbarui aplikasi

```bash
# Dari mesin pengembangan — pastikan test lulus lebih dulu
cd ~/joderma-staff-ops && .venv/bin/python -m pytest

rsync -az --delete \
  --exclude '.venv/' --exclude 'data/' --exclude 'private_media/' \
  --exclude 'logs/' --exclude 'backups/' --exclude 'staticfiles/' \
  --exclude '.git/' --exclude '__pycache__/' --exclude '.env' \
  ./ joderma-jemur@joderma-jemur:~/joderma-ops/
```

```bash
# Di mini-PC
ssh joderma-jemur@joderma-jemur
cd ~/joderma-ops

bash scripts/backup.sh                              # backup dulu, selalu
docker compose build app
docker compose up -d --force-recreate app
sleep 15 && curl -sS http://127.0.0.1:8731/health/  # container menjalankan migrate sendiri saat start
docker compose exec app python manage.py showmigrations | grep '\[ \]' || echo "semua migrasi sudah jalan"
```

Jangan menjalankan `migrate` manual tepat sesudah `up`: perintah `CMD` container
sudah menjalankannya, dan dua proses migrate bersamaan menghasilkan galat "table
already exists" yang menakutkan tetapi tidak merusak. Cukup periksa `showmigrations`.

Aplikasi juga diakses dari luar lewat `https://ops.joderma.id` (cloudflared →
Tailscale port 8446 → `127.0.0.1:8731`).

## Pembaruan 30 September 2026 — jadwal Oktober dan akun

Sekali jalan, sesudah kode baru terpasang dan `showmigrations` bersih:

```bash
cd ~/joderma-ops
# Hanya simpan backup terbaru (arahan product owner): hapus arsip lama
LATEST=$(ls -t backups/daily/joderma-ops-* | head -1); ls -l "$LATEST"
find backups/daily backups/weekly backups/monthly -type f ! -path "$LATEST" -print -delete

docker compose exec app python manage.py rapikan_akun --dry-run
docker compose exec app python manage.py rapikan_akun --password klinik123
docker compose exec app python manage.py seed_staf_cabang --password klinik123 --prune
docker compose exec app python manage.py import_jadwal_jaga jadwal/data/jadwal-2026-10.json
docker compose exec app python manage.py seed_tugas_harian --susun 2026-10
```

`rapikan_akun` membuang akhiran `_pic` dari username (akun yang sama, data lama
tetap melekat) dan menyetel password semua akun aktif ke password awal dengan
tanda wajib ganti saat login. Password baru yang dipilih staf minimal 12 karakter.

Bila gagal, kembalikan ke keadaan semula dengan memulihkan backup terakhir sesuai
prosedur di [`runbook.md`](runbook.md).

## Jam operasional aplikasi

Aplikasi berjalan **24 jam**. Ini disengaja:

- Checklist pembukaan dikerjakan sebelum klinik buka (Jemur 14.00, Citraland 12.00; lihat Pengaturan Klinik).
- Backup terjadwal berjalan pukul 02.00; container yang dimatikan malam hari
  membuat backup tidak pernah berjalan dan melanggar target pemulihan 24 jam.
- Mini-PC memiliki sumber daya berlimpah, sehingga tidak ada penghematan berarti.

Bila suatu saat akses perlu dibatasi per jam, gunakan
`scripts/schedule_hours.sh` yang menonaktifkan **akses Tailscale** saja dan
membiarkan container beserta backup tetap berjalan:

```bash
sudo crontab -e
0  11 * * * /home/joderma-jemur/joderma-ops/scripts/schedule_hours.sh on  >> /home/joderma-jemur/joderma-ops/logs/schedule.log 2>&1
59 23 * * * /home/joderma-jemur/joderma-ops/scripts/schedule_hours.sh off >> /home/joderma-jemur/joderma-ops/logs/schedule.log 2>&1
```

Jangan pernah membatasi jam dengan `docker compose stop`.

## Dua jebakan yang sudah diperbaiki

Keduanya ditemukan saat deployment nyata dan tidak terlihat pada pengujian di
mesin pengembangan. Bila suatu saat gejalanya muncul lagi, inilah sebabnya.

**Container restart terus-menerus, log berisi `Permission denied`.** Proses di
dalam container berjalan sebagai UID tertentu, sedangkan direktori bind-mount di
host dimiliki UID lain, sehingga log dan database tidak dapat ditulis. Pastikan
`APP_UID` dan `APP_GID` di `.env` sama dengan keluaran `id -u` dan `id -g` pada
host.

**Container sehat tetapi host tidak dapat menghubunginya.** Gunicorn yang bind ke
`127.0.0.1` di dalam container hanya mendengarkan loopback container itu sendiri,
sehingga docker-proxy tidak dapat meneruskan koneksi. Di dalam container aplikasi
harus bind `0.0.0.0`; pembatasan akses dilakukan oleh port publishing
`127.0.0.1:8731:8731` pada host, bukan oleh bind address container.

## Pemeriksaan rutin

```bash
cd ~/joderma-ops

docker compose ps                                 # kedua container Up
curl -sS http://127.0.0.1:8731/health/            # status ok
ss -tln | grep 8731                               # HANYA 127.0.0.1, tidak 0.0.0.0
tailscale serve status                            # Photodex di /, JoDerma di :8443
ls -lt backups/daily | head -3                    # backup terbaru < 24 jam
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/   # Photodex sehat
```

Bila `ss` menunjukkan `0.0.0.0:8731`, aplikasi terbuka ke seluruh jaringan lokal.
Hentikan container dan perbaiki port publishing sebelum melanjutkan.
