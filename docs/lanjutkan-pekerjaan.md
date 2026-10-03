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
| Kode di desktop (komputer kerja sejak 30 Sep 2026) | WSL: `/mnt/e/Claude/Projects/joderma-operasional` (Windows: `E:\Claude\Projects\joderma-operasional`) |
| Kode di laptop | `~/Desktop/joderma-operasional` |
| Cadangan kode | https://github.com/hansensudarmahs2-sudo/joderma-operasional (private) |
| Server klinik | `ssh joderma-jemur@joderma-jemur`, aplikasi di `~/joderma-ops` |
| URL staf | `https://ops.joderma.id/` |
| Rencana aktif | [`KEBUTUHAN_REDEFINISI_PERAN.md`](KEBUTUHAN_REDEFINISI_PERAN.md) |
| Aplikasi lain di server | Photodex pada port 8080, jangan diganggu |

## Memulai sesi baru

Clone baru belum punya `.venv`: `python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`.

```bash
cd ~/Desktop/joderma-operasional    # desktop: /mnt/e/Claude/Projects/joderma-operasional
git pull                                  # samakan dengan GitHub
git log --oneline -5                      # apa yang terakhir dikerjakan
.venv/bin/python -m pytest                # pastikan semuanya masih hijau
```

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

```bash
# Dari laptop, setelah test lulus dan perubahan di-commit
cd ~/Desktop/joderma-operasional
rm -rf /tmp/joderma-deploy && git worktree prune
git worktree add /tmp/joderma-deploy HEAD
rsync -az --delete \
  --exclude '/.venv/' --exclude '/data/' --exclude '/private_media/' --exclude '/logs/' \
  --exclude '/backups/' --exclude '/staticfiles/' --exclude '/.git/' --exclude '__pycache__/' --exclude '/.env' \
  /tmp/joderma-deploy/ joderma-jemur@joderma-jemur:~/joderma-ops/
git worktree remove /tmp/joderma-deploy
```

Pola exclude diawali `/` supaya hanya folder di akar yang dilewati. Tanpa `/`, folder
bernama sama di dalam app (mis. `jadwal/.../data/`) ikut terlewat; itu pernah terjadi.

```bash
# Di server klinik
ssh joderma-jemur@joderma-jemur
cd ~/joderma-ops
bash scripts/backup.sh                     # backup dulu, selalu
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
