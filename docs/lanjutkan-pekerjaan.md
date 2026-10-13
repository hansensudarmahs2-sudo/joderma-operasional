# Melanjutkan Pekerjaan

Dokumen ini untuk memulai kembali setelah jeda, baik oleh Anda sendiri maupun
oleh asisten AI di sesi baru yang tidak mengetahui riwayat percakapan sebelumnya.

## Tiga kalimat konteks

JoDerma Staff Ops adalah aplikasi internal klinik (ops.joderma.id) untuk operasional
harian dua cabang, Jemur Andayani dan Citraland. Aplikasi berjalan di mini PC klinik
lewat Docker. Tahap sekarang (3 Oktober 2026): perbaikan dua cabang dan foto lampiran
(tahap 1) selesai, berikutnya task management GTD dan List View task (tahap 2) lalu catatan
KPI (tahap 3); fase 6–9 redefinisi peran menyusul.

**Posisi terakhir, sisa pekerjaan, dan roadmap ada di bagian atas
[`../current-progress.md`](../current-progress.md).** Baca itu lebih dulu.

## Di mana segalanya berada

| | |
|---|---|
| Kode di desktop (komputer kerja sejak 30 Sep 2026) | WSL: `~/joderma-operasional` (sejak 6 Okt 2026; sebelumnya `/mnt/e/Claude/Projects/joderma-operasional`, jangan dipakai lagi) |
| Kode di laptop | `~/Desktop/joderma-operasional` |
| Cadangan kode | https://github.com/hansensudarmahs2-sudo/joderma-operasional (private) |
| Server klinik | `ssh joderma-jemur@joderma-jemur`, aplikasi di `~/joderma-ops` |
| URL staf | `https://ops.joderma.id/` |
| Rencana aktif | [`KEBUTUHAN_REDEFINISI_PERAN.md`](KEBUTUHAN_REDEFINISI_PERAN.md) |
| Aplikasi lain di server | Photodex pada port 8080, jangan diganggu |

## Memulai sesi baru

Clone baru belum punya `.venv`. **Sebut versinya eksplisit**: pada laptop (6 Okt 2026)
`python3` menunjuk ke Python 3.14, sedangkan proyek ini memakai 3.11 dan produksi 3.12.
Django 5.1 hanya mendukung sampai 3.13, jadi venv yang dibuat dengan `python3` saja
menghasilkan puluhan test gagal di dalam Django sendiri — kegagalan yang tidak ada
hubungannya dengan kode.

```bash
cd ~/Desktop/joderma-operasional && python3.11 -m venv .venv && .venv/bin/pip install -q -r requirements-dev.txt
```

Jalankan `pytest` sebagai **perintah terpisah**, jangan dirangkai dengan `&&` sesudah
`pip install`: paket belum selesai ditulis ke disk saat pytest mulai membaca, dan
hasilnya error palsu seperti `No module named pytest`. Ambil ringkasannya dengan
`grep`, bukan `tail` — blok peringatan di akhir membuat `tail -2` justru memotong baris
yang dicari.

```bash
cd ~/Desktop/joderma-operasional && .venv/bin/python -m pytest 2>&1 | grep -E "passed|failed" | tail -1
```

```bash
cd ~/Desktop/joderma-operasional    # desktop: ~/joderma-operasional
git pull                                  # samakan dengan GitHub
git log --oneline -5                      # apa yang terakhir dikerjakan
.venv/bin/python -m pytest                # pastikan semuanya masih hijau
```

**Perintah untuk desktop tidak bisa dijalankan dari laptop.** Path `~/joderma-operasional`
hanya ada di WSL mesin desktop; dari laptop ia gagal di `cd`. Desktop bekerja di dalam
filesystem WSL, bukan di drive Windows `/mnt/e/...`: akses lintas sistem itu lambat dan
merusak izin berkas serta akhir baris. Saat berpindah ke desktop:

```bash
cd ~/joderma-operasional && git pull && cp data/db.sqlite3 "data/db.sqlite3.bak-$(date +%F-%H%M)" && .venv/bin/python manage.py migrate
```

Database tidak ikut Git, jadi tiap mesin punya datanya sendiri dan migrasinya perlu
dijalankan di masing-masing. Beri nama cadangan berikut jamnya; tanpa jam, menjalankannya
dua kali di hari yang sama akan menimpa cadangan sebelumnya.

Bekerja paralel dengan agen lain: lihat bagian **Bekerja paralel** di `AGENTS.md`. Satu
pihak satu direktori kerja lewat `git worktree`, bukan `git switch` bergantian.

Lalu periksa keadaan server klinik:

```bash
ssh joderma-jemur@joderma-jemur
cd ~/joderma-ops
docker compose ps                         # kedua container harus Up
curl -sS http://127.0.0.1:8731/health/
docker compose exec app python manage.py pilot_check
```

## Menjalankan di komputer kerja untuk mencoba-coba

```bash
cd ~/Desktop/joderma-operasional
.venv/bin/python manage.py runserver 127.0.0.1:8731
```

Buka `http://127.0.0.1:8731/`. Basis data di komputer kerja berisi data sintetis
dan terpisah sama sekali dari data klinik, jadi aman untuk dicoba apa pun.

## Bila menemukan bug

Catat sebelum lupa, di `UAT_ISSUE_REGISTER.md`: apa yang dilakukan, apa yang
diharapkan, apa yang terjadi, siapa yang mengalaminya, dan seberapa mengganggu.
Bug yang dijelaskan dengan langkah ulang yang jelas jauh lebih cepat diperbaiki
daripada bug yang hanya digambarkan sebagai "kadang error".

Alur perbaikannya:

```bash
cd ~/Desktop/joderma-operasional
# 1. tulis test yang GAGAL karena bug tersebut
# 2. perbaiki kodenya sampai test lulus
.venv/bin/python -m pytest
git add -A && git commit && git push
```

Test yang gagal lebih dulu itu penting: tanpanya tidak ada bukti bug benar-benar
diperbaiki, dan tidak ada yang mencegahnya kembali.

## Menerapkan perubahan ke klinik

Hanya kode yang sudah di-commit yang dikirim, dan selalu backup lebih dulu.

Prosedur ini sama dari laptop maupun desktop; pakai persis begini supaya isi dan izin
berkas di server tidak bolak-balik tergantung siapa yang men-deploy.

```bash
# Dari laptop atau desktop, setelah test lulus, perubahan di-commit, dan di-push
cd ~/Desktop/joderma-operasional      # desktop: cd ~/joderma-operasional
git fetch origin && test "$(git rev-parse HEAD)" = "$(git rev-parse origin/master)" && echo "HEAD = GitHub"
rm -rf ~/.cache/joderma-deploy-stage && mkdir -p ~/.cache/joderma-deploy-stage
git -c tar.umask=022 archive --format=tar HEAD | tar -x -C ~/.cache/joderma-deploy-stage
rsync -az --delete \
  --exclude '/.venv/' --exclude '/data/' --exclude '/private_media/' --exclude '/logs/' \
  --exclude '/backups/' --exclude '/staticfiles/' --exclude '/.git' --exclude '/.env' \
  --exclude '__pycache__/' --exclude '/.pytest_cache/' --exclude '/apotek/' \
  --exclude '/.claude-sync/' --exclude '/Claude outputs/' \
  ~/.cache/joderma-deploy-stage/ joderma-jemur@joderma-jemur:~/joderma-ops/
rm -rf ~/.cache/joderma-deploy-stage
```

Tambahkan `--dry-run --itemize-changes` pada `rsync` untuk melihat dulu apa yang akan berubah.

Mengapa `git archive` (seragam sejak 13 Okt 2026):

- **Hanya berkas yang tercatat di Git pada commit itu yang dikirim.** Menyalin direktori kerja
  ikut membawa berkas lokal yang tidak di-commit: berkas kosong `s*1s*` sisa salah ketik
  sempat terkirim dan baru terhapus pada deploy 12 Okt. Arsip juga tidak memuat `.git` sama
  sekali, jadi tidak ada lagi berkas penunjuk worktree yang bisa ikut terkirim (pada 12 Okt
  berkas `.git` berisi `gitdir: …/.git/worktrees/joderma-deploy` sempat mendarat di
  `~/joderma-ops` dan harus dihapus tangan, karena worktree staging memakai pola
  `'/.git/'` yang hanya cocok untuk direktori).
- **Izin berkas mengikuti Git dan sama di setiap mesin.** `tar.umask=022` menghasilkan 644 untuk
  berkas biasa dan 755 untuk yang executable di Git. Tanpa itu, hasilnya tergantung umask mesin
  yang men-deploy (664/775 dari laptop, 644/755 dari desktop) dan setiap deploy dari mesin lain
  mengubah izin ratusan berkas.

Pola exclude diawali `/` supaya hanya folder di akar yang dilewati. Tanpa `/`, folder
bernama sama di dalam app (mis. `jadwal/.../data/`) ikut terlewat; itu pernah terjadi.
Dengan `--delete`, pola exclude juga melindungi folder yang hanya ada di server (data,
lampiran, backup, `.env`) dari penghapusan, jadi jangan dihapus dari daftar walaupun folder
itu tidak ada di Git. `'/.git'` tetap ditulis **tanpa** garis miring di belakang supaya cocok
baik dengan direktori maupun berkas.

```bash
# Di server klinik
ssh joderma-jemur@joderma-jemur
cd ~/joderma-ops
bash scripts/backup.sh --predeploy         # backup dulu, selalu (terenkripsi, folder backups/predeploy)
docker compose build app
docker compose up -d --force-recreate app  # container menjalankan migrate saat start
curl -sS http://127.0.0.1:8731/health/
```

Bila menjalankan `docker compose exec` dari dalam skrip yang dikirim lewat `ssh ... <<EOF`,
tambahkan `</dev/null` di akhir perintahnya, supaya perintah itu tidak menelan sisa skrip.
Jangan menempelkan `set -e` langsung ke terminal: satu perintah gagal akan menutup terminal.
Simpan langkahnya sebagai file lalu jalankan dengan `bash nama-file.sh`.

## Yang masih menunggu keputusan

Semuanya ada di `OWNER_DECISION_REVIEW.md`. Yang paling mendesak:

- **Definisi pos kas.** Menentukan angka pembanding selisih harian. Bila keliru,
  selisih akan salah setiap hari.
- **Aturan skip dan pembatalan giliran perawat.** Menyangkut pendapatan;
  bahas bersama perawat, jangan diputuskan sepihak.
- **OD-F: apakah semua perawat boleh semua kategori?** Saat ini ya; dapat diubah
  lewat `/django-admin/` tanpa menyentuh kode.

Sudah diputuskan: **OD-E** — ketiga kategori tindakan berkomisi, termasuk
asistensi dokter (11 September 2026).

## Sisa pekerjaan kecil

Daftar lengkap ada di [`../current-progress.md`](../current-progress.md) ▸ Task yang belum
selesai. Yang paling sering terlupa: ganti password `hansen1` dan `superadmin` (masih
`klinik123`), dan tekan **Reset peran ke default** sesudah setiap deploy yang mengubah definisi
peran.

## Bila bekerja dengan asisten AI di sesi baru

Tunjukkan dokumen ini. Yang perlu disampaikan di awal:

- lokasi repositori dan server klinik seperti di tabel atas;
- larangan mengganggu Photodex pada port 8080;
- aturan proyek: perubahan kode selalu disertai test, dokumentasi diperbarui
  bersamaan, keputusan bisnis tidak diambil sepihak melainkan dicatat sebagai
  OPEN DECISION, dan tidak ada commit sebelum ringkasannya Anda setujui.

Mulai dari `docs/README.md` untuk peta seluruh dokumentasi.
