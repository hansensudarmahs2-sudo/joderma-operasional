# Melanjutkan Pekerjaan

Dokumen ini untuk memulai kembali setelah jeda, baik oleh Anda sendiri maupun
oleh asisten AI di sesi baru yang tidak mengetahui riwayat percakapan sebelumnya.

## Tiga kalimat konteks

JoDerma Staff Ops adalah aplikasi internal klinik untuk delapan area operasional
harian. Aplikasi sudah berjalan di mini-PC klinik lewat Docker dan diakses staf
melalui Tailscale. Tahap sekarang: siap menjalankan uji coba lima hari, menunggu
beberapa keputusan pemilik.

## Di mana segalanya berada

| | |
|---|---|
| Kode di komputer kerja | `~/joderma-staff-ops` |
| Cadangan kode | https://github.com/hansensudarmahs2-sudo/joderma-operasional (private) |
| Server klinik | `ssh joderma-jemur@joderma-jemur`, aplikasi di `~/joderma-ops` |
| URL staf | `https://joderma-jemur.<tailnet>.ts.net:8443/` |
| Aplikasi lain di server | Photodex pada port 8080, jangan diganggu |

## Memulai sesi baru

```bash
cd ~/joderma-staff-ops
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
cd ~/joderma-staff-ops
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
cd ~/joderma-staff-ops
# 1. tulis test yang GAGAL karena bug tersebut
# 2. perbaiki kodenya sampai test lulus
.venv/bin/python -m pytest
git add -A && git commit && git push
```

Test yang gagal lebih dulu itu penting: tanpanya tidak ada bukti bug benar-benar
diperbaiki, dan tidak ada yang mencegahnya kembali.

## Menerapkan perubahan ke klinik

```bash
# Dari komputer kerja, setelah test lulus
cd ~/joderma-staff-ops
rsync -az --delete \
  --exclude '.venv/' --exclude 'data/' --exclude 'private_media/' \
  --exclude 'logs/' --exclude 'backups/' --exclude 'staticfiles/' \
  --exclude '.git/' --exclude '__pycache__/' --exclude '.env' \
  ./ joderma-jemur@joderma-jemur:~/joderma-ops/
```

```bash
# Di server klinik
ssh joderma-jemur@joderma-jemur
cd ~/joderma-ops
docker compose exec -T backup /app/scripts/backup.sh    # backup dulu, selalu
docker compose build app
docker compose up -d --force-recreate app
docker compose exec app python manage.py migrate --noinput
curl -sS http://127.0.0.1:8731/health/
```

Backup dijalankan dari dalam container karena path basis data adalah path
container, bukan path host.

## Yang masih menunggu keputusan

Semuanya ada di `OWNER_DECISION_REVIEW.md`. Yang paling mendesak:

- **Definisi pos kas.** Menentukan angka pembanding selisih harian. Bila keliru,
  selisih akan salah setiap hari.
- **Aturan skip dan pembatalan giliran perawat.** Menyangkut pendapatan;
  bahas bersama perawat, jangan diputuskan sepihak.
- **OD-E: apakah asistensi dokter menghabiskan giliran komisi?** Saat ini ya.
- **OD-F: apakah semua perawat boleh semua kategori?** Saat ini ya.

Dua hal terakhir dapat diubah lewat `/django-admin/` tanpa menyentuh kode.

## Sisa pekerjaan kecil

- Tiga pengguna belum punya nama tampilan, sehingga audit log sulit dibaca.
- Akun `hansen1` dan `superadmin` adalah superuser tanpa peran; bila itu sisa
  percobaan, nonaktifkan agar tidak menjadi pintu masuk yang terlupakan.
- Beberapa akun demo masih memakai kata sandi bawaan; wajib diganti sebelum
  data nyata masuk.

## Bila bekerja dengan asisten AI di sesi baru

Tunjukkan dokumen ini. Yang perlu disampaikan di awal:

- lokasi repositori dan server klinik seperti di tabel atas;
- larangan mengganggu Photodex pada port 8080;
- aturan proyek: perubahan kode selalu disertai test, dokumentasi diperbarui
  bersamaan, keputusan bisnis tidak diambil sepihak melainkan dicatat sebagai
  OPEN DECISION, dan tidak ada commit sebelum ringkasannya Anda setujui.

Mulai dari `docs/README.md` untuk peta seluruh dokumentasi.
