# JoDerma Staff Ops

Web app internal klinik untuk mencatat, memantau, dan meninjau aktivitas operasional
harian. Local-first: berjalan di server klinik, diakses privat lewat Tailscale.

> **Repositori ini wajib berstatus private.** Isinya adalah seluruh logika
> operasional klinik termasuk aturan kas dan kewenangan akses. Tidak ada data
> pasien, kredensial, maupun rahasia di dalamnya — `.env`, basis data, lampiran,
> dan arsip backup dikecualikan dari kontrol versi — tetapi kodenya sendiri
> bukan untuk konsumsi publik. Lihat [`LICENSE`](LICENSE).

Implementasi dari PRD v1.0 (11 September 2026). Keputusan bisnis sementara ada di
[`DECISIONS.md`](DECISIONS.md) dan **harus dikonfirmasi product owner pada Milestone 0**.

## Delapan modul operasional

| Modul | Halaman | Aturan kunci |
|---|---|---|
| Pembukaan klinik | `/pembukaan/` | Template berversi disalin jadi snapshot harian; item bermasalah wajib catatan |
| Kas & kembalian | `/kas/` | Kalkulator pecahan, dual-control, koreksi pasca-verifikasi wajib alasan supervisor |
| Antrean & pembayaran | `/antrean/` | Nomor unik per hari, event pembayaran historis, reorder wajib alasan |
| Giliran perawat | `/giliran-perawat/` | Round-robin + ledger append-only, skip/override terdokumentasi |
| Jadwal istirahat | `/jadwal-istirahat/` | Tolak overlap, peringatan minimum staffing yang bisa di-override beralasan |
| Komplain | `/catatan/?tipe=KOMPLAIN` | Workflow, SLA, penandaan terbatas, ringkasan penyelesaian wajib |
| Masukan/saran | `/catatan/?tipe=MASUKAN` | Workflow ringan; penolakan wajib alasan |
| Kerusakan | `/catatan/?tipe=KERUSAKAN` | Triase → perbaikan → verifikasi; kritis memberi alert; aset bisa ditandai jangan digunakan |

Lintas modul: dashboard harian, action item, notifikasi in-app, laporan + ekspor CSV,
audit log append-only, admin pengguna/peran/konfigurasi.

Peran dan kewenangan dijelaskan di [`docs/peran-dan-akses.md`](docs/peran-dan-akses.md).
Cara melanjutkan pekerjaan setelah jeda ada di
[`docs/lanjutkan-pekerjaan.md`](docs/lanjutkan-pekerjaan.md).

## Stack

Django 5.1 monolit, template server-rendered, SQLite (WAL), Gunicorn di belakang
Tailscale Serve, WhiteNoise untuk static. Tanpa React, Redis, queue worker, atau
object storage — sesuai PRD 16.1.

## Menjalankan secara lokal

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env          # isi DJANGO_SECRET_KEY
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_demo      # data sintetis, bukan data pasien nyata
.venv/bin/python manage.py runserver 127.0.0.1:8731
```

Akun demo (password `JoDermaDemo2026!`): `admin`, `supervisor`, `kasir1`, `kasir2`,
`perawat1`, `perawat2`, `perawat3`, `owner`.

## Test

```bash
.venv/bin/python -m pytest          # 984 test dijalankan, tidak ada yang dilewati
```

Cakupan: state machine hari, validasi checklist, kas & dual-control, penomoran dan
event antrean, rotasi perawat, overlap jadwal, workflow issue, matriks izin,
konkurensi (optimistic locking), security smoke (CSRF, throttling, session, akses
lampiran, otorisasi ekspor), kesiapan pilot, bootstrap superuser dan pengaman
lockout, serta progressive disclosure form catatan.

## Produksi

Lihat [`docs/runbook.md`](docs/runbook.md) untuk instalasi, Tailscale Serve, backup,
restore, dan checklist go-live. Ringkas:

```bash
docker compose up -d --build
sudo ./scripts/serve_clinic.sh      # Tailscale Serve pada port 8443
./scripts/verify_deployment.sh
```

Instalasi klinik yang sedang berjalan dijelaskan di
[`docs/deployment-klinik.md`](docs/deployment-klinik.md).

**Aturan jaringan yang tidak boleh dilanggar:** aplikasi hanya listen di `127.0.0.1`.
Gunakan Tailscale **Serve** (privat dalam tailnet), **bukan Funnel** (internet publik).

## Cadangan dan pemulihan

Repositori Git adalah cadangan **kode dan dokumentasi**; arsip backup harian
adalah cadangan **data operasional**. Keduanya diperlukan: basis data tanpa
aplikasinya tidak dapat dipulihkan menjadi layanan yang berjalan.

Sejak versi ini, arsip backup harian turut menyertakan kode dan dokumentasi
(diambil dari daftar berkas Git sehingga rahasia tidak ikut), dan manifestnya
mencatat commit yang sedang berjalan.

## Privasi

Minimum necessary data: aplikasi menyimpan nama tampilan, jenis kunjungan, dan status
pembayaran — **tidak** menyimpan diagnosis, foto klinis, atau catatan medis. Layar
bersama menampilkan inisial. Lampiran berada di luar direktori static dan selalu
melewati pemeriksaan izin plus audit.
