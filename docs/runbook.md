# Runbook Operator — JoDerma Staff Ops

Dokumen untuk admin teknis. Prosedur harian untuk staf ada di `docs/panduan-staf.md`.

---

## 1. Instalasi produksi

### Prasyarat
- Mini-PC/server Linux yang selalu menyala, terhubung UPS.
- Docker + Docker Compose, atau Python 3.12 bila memakai systemd native.
- Tailscale terpasang dan sudah login ke tailnet JoDerma.
- Zona waktu host: `Asia/Jakarta`.

### Catatan penting Docker

- **Bind address**: di dalam container Gunicorn memakai `APP_HOST=0.0.0.0` (disetel oleh
  `docker-compose.yml`). Yang membatasi akses ke localhost host adalah baris
  `ports: "127.0.0.1:${APP_PORT}:${APP_PORT}"`. Jangan menghapus prefiks `127.0.0.1:` itu —
  itulah satu-satunya yang mencegah aplikasi terbuka ke LAN.
- **UID/GID**: `APP_UID`/`APP_GID` di `.env` harus sama dengan pemilik direktori
  `data/`, `logs/`, `private_media/`, `backups/` di host (biasanya `1000`). Bila tidak
  cocok, container gagal menulis log dan restart terus-menerus.

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
- Port aplikasi (`APP_PORT`, default 8731) tidak pernah diberikan ke siapa pun; hanya loopback.

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
| Cek aplikasi hidup | `curl -fsS http://127.0.0.1:${APP_PORT:-8731}/health/` |
| Lihat log aplikasi | `docker compose logs -f app` atau `journalctl -u joderma-ops -f` |
| Lihat log backup | `logs/backup.log` |
| Cek kapasitas disk | `df -h /` — bertindak bila di atas 80% |
| Audit akses | Menu **Audit** di aplikasi (supervisor/owner/admin berizin) |

Log aplikasi terstruktur JSON dengan rotasi 10 MB × 10 berkas. Data pasien, password,
token, dan isi komplain **tidak** ditulis ke log teknis.

---

## 4. Backup dan restore

Backup otomatis setiap malam 02:00 WIB: snapshot SQLite konsisten (aman meski WAL
aktif) + arsip lampiran, dienkripsi AES-256, retensi 7 harian / 4 mingguan / 12 bulanan /
10 sebelum-deploy.

```bash
./scripts/backup.sh --predeploy        # backup sebelum deploy / manual (wajib terenkripsi)
ls -lt backups/predeploy/              # daftar backup sebelum deploy
ls -lt backups/daily/                  # daftar backup malam (dibuat container backup)
```

Tata letak folder `backups/`:

| Folder | Isi | Retensi |
|--------|-----|---------|
| `daily/` | backup malam 02:00 dari container `backup` | 7 terbaru |
| `weekly/`, `monthly/` | salinan backup malam hari Minggu / tanggal 1 | 4 / 12 |
| `predeploy/` | backup sebelum deploy (`--predeploy`) | 10 terbaru (`BACKUP_KEEP_PREDEPLOY`) |

Backup sebelum deploy tidak pernah menghapus atau menggusur backup malam. Karena itu
healthcheck container `backup` (yang memeriksa kesegaran `backups/daily/`, maksimal 48 jam)
benar-benar mencerminkan backup malam, bukan tertutup oleh backup manual.

`BACKUP_PASSPHRASE` hanya ada di container; di host, `backup.sh` membacanya dari baris
`BACKUP_PASSPHRASE=` di `.env` (tanpa meng-source berkas itu, nilainya tidak dicetak).
Bila passphrase tidak ditemukan, `--predeploy` berhenti dengan galat: backup sebelum deploy
tidak pernah tersimpan tanpa enkripsi.

Arsip `.tar.gz` polos yang terlanjur tertinggal di `backups/daily/` dienkripsi sekali jalan
dengan helper berikut (verifikasi dekripsi dulu, baru arsip polos dihapus; hasilnya masuk
`backups/predeploy/`):

```bash
bash scripts/encrypt_plain_backups.sh --dry-run     # lihat apa yang akan dikerjakan
bash scripts/encrypt_plain_backups.sh               # enkripsi sungguhan
```

Image Docker lama (dibuat sebelum ada `.dockerignore`) dan build cache-nya dapat memuat
`.env`, database, dan lampiran. Setelah deploy ini, hapus dengan `docker image prune` dan
`docker builder prune` (tinjau daftar image dulu; image yang masih dipakai tidak dihapus).

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
| Mesin mati total / tidak bisa dihubungi | Alarm RTC menyalakannya sendiri ≤ 30 menit (bagian 6). Lebih lama dari itu berarti listrik benar-benar putus atau RTC wake belum aktif |
| Tailscale bermasalah total | Kontingensi kertas (checklist, kas, antrean) lalu entry susulan dengan catatan alasan |
| Staf lupa password | Admin: menu **Admin ▸ Pengguna**, isi kata sandi baru; pengguna wajib menggantinya saat login |
| Staf keluar dari klinik | Nonaktifkan akun (jangan hapus) — riwayat dan audit tetap utuh |

---

## 6. Mesin tidak boleh dimatikan

Mini PC ini server dua cabang, tetapi ia juga punya desktop GNOME yang dipakai orang.
Pada 11 Oktober 2026 mesin mati tiga kali, dan yang pukul 22.00 membuat klinik
kehilangan sistemnya **15,5 jam** (mati 11 Okt 22.00, baru dinyalakan 12 Okt 13.34).

| Jam | Sebab | Bukti di log |
|---|---|---|
| 05.50 | Listrik padam | Log berhenti mendadak tanpa urutan shutdown; hidup sendiri 05.52 |
| 13.37 | Tombol power ditekan di layar login | `systemd-logind: Power key pressed short` |
| 22.00 | Diklik "Power Off" dari menu GNOME | `gnome-shell endSessionDialog ... logind: 3`, tanpa `Power key` |

Pengaman yang dipasang 4 Okt (`HandlePowerKey=ignore` dan `power-button-action='nothing'`)
tidak menahan dua yang terakhir: keduanya hanya berlaku di sesi pengguna, dan tidak
menyentuh menu GNOME maupun layar login GDM.

### Dua lapis yang terpasang sejak 12 Okt 2026

**Lapis 1 — polkit menolak mematikan dari desktop.** Menu GNOME, tombol power, dan layar
login semuanya bermuara ke logind lewat polkit, jadi ketiganya tertutup oleh satu berkas.
Root tidak melewati polkit, sehingga `sudo systemctl poweroff` lewat SSH tetap bisa — itu
jalan keluar yang sengaja disisakan.

**Lapis 2 — alarm RTC.** Tekan-tahan tombol power 4 detik ditangani firmware, di bawah
sistem operasi: Linux tidak pernah melihatnya dan tidak bisa menolaknya. Karena itu lapis
pertama saja tidak cukup. `wakealarm.timer` memajukan alarm RTC 30 menit ke depan setiap
10 menit, sehingga mesin yang mati karena sebab apa pun — listrik padam, tombol ditahan —
dinyalakan kembali oleh jam motherboard dalam **≤ 30 menit**. Mesin yang sudah mati tidak
bisa mengecek dirinya sendiri; yang bekerja di sini RTC yang hidup dari baterai CMOS.

### Memasang

```bash
sudo cp deploy/50-larang-matikan.rules /etc/polkit-1/rules.d/
sudo install -m 755 deploy/pasang-wakealarm /usr/local/sbin/pasang-wakealarm
sudo cp deploy/wakealarm.service deploy/wakealarm.timer /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now wakealarm.timer
sudo systemctl restart polkit
```

`sudo` di mini PC meminta password, dan `ssh host 'perintah'` tidak menyediakan terminal
untuk menanyakannya. Pakai `ssh -t`, atau masuk dulu baru jalankan.

### Verifikasi

```bash
# Shutdown harus DITOLAK: pkcheck keluar dengan kode 1.
pkcheck --action-id org.freedesktop.login1.power-off --process $$ ; echo "kode=$?"

# Aksi polkit lain TIDAK boleh ikut terblokir: kode 2 dengan pesan
# "polkit.result=auth_admin" itu kebijakan bawaan, bukan aturan ini.
pkcheck --action-id org.freedesktop.systemd1.manage-units --process $$ ; echo "kode=$?"

cat /sys/class/rtc/rtc0/wakealarm     # harus berisi epoch, bukan kosong
systemctl list-timers wakealarm.timer
journalctl -u polkit --since -5min -p warning   # harus kosong
```

### Uji RTC wake — wajib sekali, di luar jam klinik

Sebagian firmware hanya membangunkan dari S3/S4, bukan dari mati total (S5). Lapis 2 tidak
boleh dianggap aktif sebelum ini terbukti:

```bash
sudo systemctl stop wakealarm.timer
sudo bash -c 'echo 0 > /sys/class/rtc/rtc0/wakealarm; echo $(( $(date +%s) + 180 )) > /sys/class/rtc/rtc0/wakealarm'
sudo systemctl poweroff
# Tunggu 3 menit. Bila mesin tidak hidup sendiri, aktifkan "Wake system from S5"
# di BIOS (F2 saat boot) lalu ulangi.
sudo systemctl start wakealarm.timer   # jalankan lagi setelah mesin hidup
```

### Mematikan untuk pemeliharaan

Hentikan timer-nya dulu, kalau tidak mesin hidup lagi dalam 30 menit:

```bash
sudo systemctl stop wakealarm.timer
sudo bash -c 'echo 0 > /sys/class/rtc/rtc0/wakealarm'
sudo systemctl poweroff
```

### Mencabut seluruhnya

```bash
sudo rm -f /etc/polkit-1/rules.d/50-larang-matikan.rules && sudo systemctl restart polkit
sudo systemctl disable --now wakealarm.timer
sudo rm -f /etc/systemd/system/wakealarm.{service,timer} /usr/local/sbin/pasang-wakealarm
sudo systemctl daemon-reload
sudo bash -c 'echo 0 > /sys/class/rtc/rtc0/wakealarm'
```

### Yang masih terbuka

- **Tidak ada UPS.** Kejadian 05.50 adalah listrik padam, dan satu-satunya baterai yang
  terbaca di mesin ini milik mouse wireless. BIOS "Restore on AC Power Loss" sudah aktif
  (terbukti mesin hidup sendiri 2 menit kemudian), jadi UPS kecil sudah cukup untuk
  membuat padam singkat tidak mematikan mesin sama sekali.
- **Akar masalahnya belum hilang.** Selama mesin ini dipakai sebagai komputer kerja
  (desktop GNOME, Firefox), tombol Power Off akan terus terasa wajar diklik. Dua lapis di
  atas menambal akibatnya, bukan sebabnya.

---

## 7. Perubahan konfigurasi kebijakan

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

## 8. Keamanan yang harus dijaga

- Aplikasi **hanya** listen di `127.0.0.1`. Jangan pernah mengubah bind ke `0.0.0.0`.
- Gunakan Serve, bukan Funnel. Jalankan `verify_deployment.sh` setelah setiap perubahan.
- `.env` permission 600, tidak pernah masuk git.
- Admin teknis tidak otomatis memperoleh hak bisnis (kas, detail pasien, komplain
  terbatas). Hak itu diberikan eksplisit sebagai kapabilitas tambahan dan tercatat.
- Perbarui dependensi dan OS secara berkala:
  `docker compose build --pull --no-cache && docker compose up -d`
- Retensi audit 24 bulan; kebijakan retensi final wajib disetujui manajemen sebelum
  produksi sesuai peraturan Indonesia.
