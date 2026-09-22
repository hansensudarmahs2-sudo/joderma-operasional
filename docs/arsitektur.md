# Arsitektur — JoDerma Staff Ops

Untuk orang yang akan memelihara atau melanjutkan kode ini.

## Bentuk keseluruhan

Monolit Django 5.1 dengan template server-rendered. Tanpa React, tanpa API
terpisah, tanpa Redis, tanpa queue worker, tanpa object storage. Pilihan ini
diambil sadar sesuai PRD bagian 16.1: satu klinik, belasan pengguna, dan tidak
ada staf IT di tempat. Setiap dependency baru adalah beban pemeliharaan bagi
orang yang tidak ada di sini.

```
Browser (HP/tablet/komputer klinik)
        |
        v  HTTPS dalam tailnet
Tailscale Serve  :8443
        |
        v  HTTP loopback
Gunicorn  127.0.0.1:8731    <- di dalam container bind 0.0.0.0,
        |                      dibatasi oleh port publishing host
        v
Django (WhiteNoise untuk static)
        |
        v
SQLite (mode WAL)  +  private_media/ (lampiran, di luar direktori static)
```

## Modul

Sebelas app Django. Delapan yang pertama memetakan langsung ke delapan area
operasional dalam PRD.

| App | Isi |
|---|---|
| `core` | klinik, konfigurasi, hari operasional, action item, lampiran, izin, locking |
| `accounts` | pengguna, peran, kapabilitas, login, timeout sesi |
| `audit` | jejak audit append-only, middleware correlation ID |
| `checklists` | template berversi dan snapshot harian pembukaan klinik |
| `cash` | hitung pecahan, dual-control, koreksi beralasan |
| `queueing` | antrean pasien, status kunjungan, event pembayaran |
| `nurses` | rotasi round-robin dan ledger giliran |
| `breaks` | jadwal istirahat, makan, ibadah |
| `issues` | mesin terpadu komplain, masukan, dan kerusakan |
| `notifications` | notifikasi dalam aplikasi |
| `reports` | laporan harian dan ekspor CSV |

Sekitar 9.000 baris Python di luar migrasi dan dependency.

## Lapisan

**Model** menyimpan bentuk data dan aturan yang selalu benar.

**Service** memuat aturan bisnis dan merupakan satu-satunya pintu penulisan.
View tidak pernah menulis langsung ke model untuk operasi yang perlu diaudit.
Service-lah yang memanggil pencatatan audit, sehingga tidak ada jalur penulisan
yang lolos dari jejak.

**View** mengurus HTTP, form, dan pemeriksaan izin. Tipis dengan sengaja.

**Template** server-rendered, mobile-first. JavaScript hanya dipakai untuk
kenyamanan, tidak pernah untuk aturan bisnis maupun keamanan.

## Keputusan yang perlu diketahui

**Audit bersifat append-only.** `AuditEvent` menolak pembaruan setelah dibuat.
Setiap perubahan sensitif menyimpan aktor, waktu, nilai lama, nilai baru, dan
alasan bila diwajibkan. Tidak ada yang dapat menghapusnya, termasuk admin.

**Koreksi, bukan penghapusan.** Komplain dan kerusakan tidak pernah dihapus
permanen. Kesalahan diperbaiki dengan koreksi beralasan sehingga riwayatnya utuh.

**Optimistic locking dipusatkan di `core/locking.py`.** Versi dibandingkan
dengan nilai di basis data, bukan dengan objek di memori. Implementasi pertama
membandingkan dengan objek in-memory yang membawa versinya sendiri, sehingga
konflik dua petugas tidak pernah terdeteksi. Bila menambahkan operasi
berisiko konflik, gunakan helper ini.

**Izin terpusat di `core/permissions.py`.** Semua pemeriksaan dilakukan di sisi
server. Tombol yang disembunyikan di template bukan kontrol akses; mengetik URL
secara langsung tetap ditolak.

**Waktu klinik memakai zona Asia/Jakarta.** Penomoran harian pernah memakai UTC
dan menghasilkan tanggal yang meleset satu hari pada sore hari. Untuk apa pun
yang berkaitan dengan tanggal operasional, konversikan ke zona klinik lebih dulu.

**Template checklist berversi.** Mengubah template tidak mengubah hari-hari yang
sudah lewat, karena setiap hari menyimpan salinan miliknya sendiri.

**SQLite, bukan PostgreSQL.** Satu klinik dengan belasan pengguna berada jauh di
bawah batas kemampuan SQLite dalam mode WAL, dan SQLite membuat backup menjadi
sekadar penyalinan berkas. Bila suatu saat ada banyak cabang menulis ke satu
basis data, keputusan ini perlu ditinjau ulang.

## Berkas yang sering dicari

| Berkas | Isi |
|---|---|
| `core/permissions.py` | seluruh aturan siapa boleh apa |
| `core/locking.py` | optimistic locking |
| `core/services.py` | state machine hari operasional |
| `audit/services.py` | satu-satunya pintu pencatatan audit |
| `config/settings.py` | local-first, pengaturan keamanan saat `DEBUG=false` |
| `gunicorn.conf.py` | bind address, dibaca dari `APP_PORT` |
| `core/management/commands/pilot_check.py` | pemeriksaan kesiapan, read-only |
| `core/management/commands/seed_demo.py` | data sintetis untuk pengembangan |

## Test

333 test dijalankan dengan `pytest`. Yang paling penting bukan jumlahnya,
melainkan bahwa setiap bug yang pernah ditemukan meninggalkan satu test yang
akan gagal bila bug itu kembali. Bila memperbaiki bug, tambahkan test yang gagal
sebelum perbaikan.

Cakupan: state machine hari, validasi checklist, dual-control kas, penomoran dan
event antrean, rotasi perawat, overlap jadwal, workflow catatan, matriks izin,
konkurensi, keamanan (CSRF, throttling, sesi, akses lampiran), kesiapan pilot,
bootstrap superuser, pengaman lockout, perilaku form catatan, dan kesesuaian
dokumentasi dengan kode.

## Batas yang tidak boleh dilanggar

- Aplikasi tidak pernah terbuka ke internet publik. Gunakan Tailscale **Serve**,
  bukan **Funnel**.
- Diagnosis, hasil pemeriksaan, foto klinis, dan catatan medis tidak disimpan.
  Ini batas produk, bukan sekadar pengaturan izin.
- Lampiran berada di luar direktori static dan setiap pengambilannya melewati
  pemeriksaan izin serta dicatat.
- Data pasien nyata tidak boleh masuk ke lingkungan pengembangan. Gunakan
  `seed_demo`.
