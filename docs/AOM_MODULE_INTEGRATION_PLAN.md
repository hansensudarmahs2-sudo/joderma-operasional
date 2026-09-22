# Rencana Integrasi Modul AOM ke JoDerma Operasional

Status: **DRAFT UNTUK PERSETUJUAN — BELUM MENJADI OTORISASI IMPLEMENTASI**

Tanggal: 20 September 2026

Target pengembangan: desktop development workspace Linux/Ubuntu

Target produksi: mini PC Ubuntu, hanya setelah seluruh gate desktop lulus

## 1. Tujuan

Menjadikan JoDerma Operasional sebagai rumah utama untuk fungsi AOM, penugasan staf,
checklist harian, laporan, dan masukan. AOM Daily Card standalone tetap berjalan selama
pengembangan, pengujian, migrasi percobaan, dan masa observasi. Penghentian AOM standalone
memerlukan persetujuan terpisah setelah rekonsiliasi data berhasil.

## 2. Batas pekerjaan

### Termasuk

- Struktur organisasi, cabang, tier akses, dan penugasan PIC.
- Task individual dan task bersama untuk user, PIC, tier, atau cabang.
- Pengajuan penyelesaian dan konfirmasi oleh pemberi tugas.
- Checklist harian individual dan bersama, termasuk opening dan closing.
- Laporan umum dalam satu cabang dan laporan rahasia ke AOM.
- Masukan privat yang dapat dipublikasikan oleh AOM ke cabang.
- Notifikasi dalam aplikasi.
- Audit trail, arsip, pencarian, dan penghapusan manual yang terkendali.
- Migrasi data AOM standalone ke JoDerma Operasional.
- Pengembangan, pengujian, UAT, rilis, dan rollback.

### Tidak termasuk pada rilis pertama

- Integrasi WhatsApp otomatis. AOM menyeleksi dan membagikan informasi lintas cabang
  secara manual melalui grup WhatsApp.
- Agen atau layanan AI sebagai ketergantungan runtime aplikasi.
- Penghentian AOM standalone sebelum migration rehearsal, rekonsiliasi, dan masa observasi.
- Perubahan modul klinik lain yang tidak diperlukan untuk integrasi AOM.
- Hard-delete otomatis untuk task, checklist, laporan, masukan, dan audit event.

## 3. Keputusan produk yang telah disetujui

1. JoDerma Operasional menjadi rumah modul AOM.
2. AOM standalone di mini PC tetap aktif sampai migrasi dinyatakan selesai.
3. AOM merupakan role yang dapat diberikan atau dicabut, bukan nama yang ditanam di kode.
4. Pengguna AOM awal adalah dr Hansen Sudarma.
5. PIC boleh mendelegasikan kepada staf mana pun di cabang yang sama.
6. Task dari AOM dikonfirmasi final oleh AOM.
7. Task dari PIC dikonfirmasi final oleh PIC pemberi tugas.
8. Penerima task hanya mengajukan selesai; penerima tidak dapat menetapkan selesai final.
9. Penugasan tier memiliki mode `INDIVIDUAL` dan `BERSAMA`; default `INDIVIDUAL`.
10. Checklist rutin langsung tercatat tanpa konfirmasi satu per satu.
11. Hasil checklist bermasalah membuat task tindak lanjut.
12. Laporan umum hanya terlihat dalam cabang yang sama.
13. Laporan rahasia hanya terlihat oleh pelapor dan AOM.
14. Masukan dapat dibuat semua pengguna, tetapi awalnya hanya terlihat oleh pengirim dan AOM.
15. AOM dapat memublikasikan masukan ke cabang terkait.
16. Data selesai tetap terlihat dan tidak hilang otomatis; penghapusan dilakukan manual.
17. Semua pengembangan dan pengujian dilakukan di desktop.
18. Commit, push, dan tag rilis dilakukan sebelum deployment mini PC.
19. Mini PC adalah runtime produksi, bukan tempat eksperimen atau pengembangan.

## 4. Struktur organisasi awal

### Organisasi lintas cabang

| Jabatan | Personel |
|---|---|
| Owner | dr. Yohanes Widjaja, Sp. DVE |
| Direktur Utama | Jean Yaputra |
| Direktur Operasional | dr Hansen Sudarma |
| Purchasing | Luki |

### Jemur Andayani

| Jabatan/fungsi | Personel |
|---|---|
| Penanggung Jawab Medis | dr. Yohanes Widjaja, Sp. DVE |
| Apoteker | Elvira, Apt. |
| Asisten Apoteker | Arsi, Luki |
| Perawat | Desy, Heni, Yani, Alya, Lia |
| PIC Koordinator Shift | Heni |
| PIC Kasir | Desy |
| PIC Online | Desy |
| PIC Kebersihan | Elvira |

### Citraland

| Jabatan/fungsi | Personel |
|---|---|
| Penanggung Jawab Medis | dr. Wisnu Triadi Nugroho, Sp. DVE |
| Apoteker | Rahayu, Apt. |
| Asisten Apoteker | Nanda |
| Perawat | Silvi, Regitta, Naya |
| PIC | Belum ditetapkan |

Nama, gelar, ejaan, username, nomor telepon, dan status akun harus diverifikasi pada saat
seed/import pengguna. Data di atas tidak boleh otomatis membuat akun produksi sebelum
product owner menyetujui hasil preview.

## 5. Pemisahan konsep akses

Jabatan organisasi tidak boleh otomatis memberikan seluruh hak aplikasi. Sistem memisahkan:

1. **Jabatan organisasi** — informasi struktur formal, dapat lintas cabang atau bercabang.
2. **Role/tier akses** — AOM, PIC, Staff, Admin, Owner/Viewer, dan role lama yang masih dipakai.
3. **Fungsi PIC** — Koordinator Shift, Kasir, Online, Kebersihan; selalu memiliki cabang dan
   periode aktif.
4. **Capability sensitif** — akses audit, pengelolaan user, laporan rahasia, publikasi masukan,
   ekspor, serta persetujuan tertentu.

Satu orang dapat memiliki beberapa jabatan, role, capability, dan fungsi PIC. Desy, misalnya,
memegang PIC Kasir dan PIC Online. Penugasan Citraland ke grup PIC harus gagal dengan pesan
jelas selama PIC belum ditetapkan; sistem tidak boleh membuat assignment tanpa penerima.

## 6. Matriks akses target

| Kemampuan | Staff | PIC | AOM | Admin teknis | Owner/viewer |
|---|---:|---:|---:|---:|---:|
| Melihat checklist yang ditugaskan | Ya | Ya | Ya | Tidak otomatis | Baca sesuai izin |
| Mengisi checklist | Ya | Ya | Ya | Tidak otomatis | Tidak |
| Melihat task sendiri | Ya | Ya | Ya | Tidak otomatis | Baca sesuai izin |
| Mengajukan task selesai | Ya | Ya | Ya | Tidak otomatis | Tidak |
| Delegasi dalam cabang | Tidak | Ya | Ya | Tidak otomatis | Tidak |
| Konfirmasi task dari dirinya | Tidak | Ya | Ya | Tidak otomatis | Tidak |
| Mengirim laporan/masukan | Ya | Ya | Ya | Tidak otomatis | Ya |
| Melihat laporan umum satu cabang | Ya | Ya | Ya | Tidak otomatis | Sesuai scope |
| Melihat laporan rahasia | Milik sendiri | Milik sendiri | Semua sesuai scope | Tidak otomatis | Capability khusus |
| Publikasi masukan ke cabang | Tidak | Tidak | Ya | Tidak otomatis | Capability khusus |
| Kelola user/role | Tidak | Tidak | Sesuai capability | Ya | Tidak otomatis |
| Melihat audit | Tidak | Terbatas | Ya | Tidak otomatis | Capability khusus |

Semua otorisasi wajib diterapkan server-side. Penyembunyian tombol UI bukan kontrol akses.

## 7. Alur task

### 7.1 Target penerima

Pemberi tugas dapat memilih satu dari:

- satu user;
- beberapa user;
- fungsi PIC dalam satu cabang;
- tier dalam satu cabang;
- seluruh staf dalam satu cabang.

Daftar penerima disimpan sebagai snapshot pada saat pengiriman. Perubahan anggota tier di
kemudian hari tidak mengubah histori task yang sudah dikirim.

### 7.2 Mode assignment

- `INDIVIDUAL`: satu assignment per penerima; setiap orang wajib menyelesaikan miliknya.
- `BERSAMA`: satu pekerjaan terlihat semua penerima; satu orang mengambil/menjadi pelaksana,
  sementara semua penerima dapat melihat status dan pelaksananya.

### 7.3 Status

```text
DRAFT -> OPEN -> IN_PROGRESS -> SUBMITTED -> CONFIRMED
                                     |
                                     +-> REVISION_REQUIRED -> IN_PROGRESS

DRAFT/OPEN/IN_PROGRESS -> CANCELLED (hanya pihak berwenang, wajib alasan)
```

- `SUBMITTED` berarti penerima mengajukan selesai.
- Task AOM hanya dapat menjadi `CONFIRMED` oleh AOM pemberi tugas atau AOM pengganti yang
  berwenang dan memberikan alasan.
- Task PIC hanya dapat menjadi `CONFIRMED` oleh PIC pemberi tugas; pengalihan reviewer wajib
  tercatat.
- Pengembalian ke revisi wajib mempunyai catatan.
- Task selesai tetap muncul di riwayat dan dapat difilter.

### 7.4 Model data yang diusulkan

Manfaatkan `core.ActionItem` sebagai inti task, lalu tambahkan entitas assignment dan event.

- `ActionItem`: definisi pekerjaan, pemberi tugas, cabang, mode assignment, due date, sumber.
- `TaskAudienceSnapshot`: jenis target dan snapshot penerima saat dikirim.
- `TaskAssignment`: penerima individual atau pelaksana task bersama, status, submitted_at,
  confirmed_at, reviewer, revision note.
- `TaskEvent`: event domain append-only untuk perubahan status, delegasi, komentar, dan koreksi.

Field `ActionItem.owner` lama dipertahankan selama masa kompatibilitas dan dimigrasikan ke
`TaskAssignment`; jangan dihapus pada migrasi pertama.

## 8. Checklist harian

### 8.1 Prinsip

- Template berversi dan setiap run menyimpan snapshot.
- Template memiliki cabang, sesi (`OPENING`, `CLOSING`, atau `ANYTIME`), fungsi PIC/tier,
  mode assignment, urutan, dan status aktif.
- Pengisian valid langsung tercatat; tidak membutuhkan persetujuan rutin.
- Jawaban bermasalah, kuantitas di bawah minimum, atau pilihan perlu tindak lanjut membuat
  task secara idempoten agar klik ulang tidak menggandakan task.
- Koreksi setelah submit tidak menimpa jejak lama; perubahan memiliki alasan dan audit event.

### 8.2 Template awal PIC

#### Koordinator Shift — opening

- Cek komputer.
- Cek EDC.
- Cek ruang konsultasi dan ketersediaan alat/bahan.
- Cek ruang facial dan ketersediaan alat/bahan.
- Cek papan giliran tindakan berkomisi.
- Cek papan giliran beristirahat.
- Cek modal awal bersama kasir/buka kasir.

#### Koordinator Shift — closing

- Cek komputer.
- Cek ruang konsultasi.
- Cek ruang facial; AC dan lampu sudah dimatikan.
- Cek uang setoran bersama kasir/tutup kasir.

#### Online

- Cek WhatsApp.
- Cek order online.
- Cek booking online.
- Cek komplain.
- Dokumentasikan dan koordinasikan komplain online/offline sampai solusi dan penutupan.
- Kelola dokumen order online dan booking online.

#### Kasir

- Buka kasir.
- Tutup kasir.
- Konfirmasi pembayaran.
- Cetak nota.
- Hitung total tagihan pasien.

#### Kebersihan

- Koordinasikan pembersihan zona 0, 1, dan 2.
- Cek sterilitas alat dan bahan; pelaksanaan sterilisasi tetap dilakukan perawat.

Kalimat, urutan, waktu, bukti foto, input kuantitas, dan kriteria masalah untuk setiap item
harus direview owner dalam preview template sebelum seed produksi.

### 8.3 Sumber checklist operasional yang disetujui

Enam PDF operasional yang diberikan owner menjadi sumber isi checklist role-specific:

- `Pembagian Tugas.pdf`: matriks `P` (pelaksana) dan `V` (verifikator), termasuk handoff
  Koordinator Shift, Kasir, Apoteker, Online, dan Perawat/Terapis.
- `Checklist Koordinator Shift.pdf`: buka shift, verifikasi bersama, tutup shift, dan rekap
  temuan ke Operation Manager.
- `Checklist Kasir.pdf`: modal awal, pecahan kembalian, EDC/QRIS/printer, kas akhir,
  rekonsiliasi, settlement, dan catatan nominal.
- `Checklist Apoteker.pdf`: stok farmasi, FEFO, cold chain, sterile pouch, emergency kit,
  hyaluronidase, verifikasi stok ruangan, dan lemari obat.
- `Checklist Online dan Reservasi.pdf`: kebersihan awal, jadwal dokter, booking, dan serah-terima
  daftar tindakan ke Perawat.
- `Checklist Perawat dan Terapis.pdf`: alat/bahan, emergensi, kesiapan tindakan, kebersihan,
  limbah, penutupan device, serta pengumpulan angka stok ruangan.

Implementasi menyimpan target role jamak pada template, pelaksana/verifikator pada item, dan
snapshot keduanya pada run/respons. Isi PDF tidak membuat akun produksi otomatis; `seed_demo`
hanya menghasilkan data sintetis untuk preview dan UAT.

## 9. Laporan

### 9.1 Jenis visibilitas

- `CABANG`: terlihat oleh pengguna aktif pada cabang yang sama.
- `RAHASIA_AOM`: terlihat oleh pelapor dan AOM yang berwenang.

Tidak ada publikasi otomatis lintas cabang. AOM memfilter lalu membagikan informasi yang layak
ke grup WhatsApp secara manual. Aplikasi tidak boleh menampilkan identitas atau isi laporan
rahasia melalui daftar, pencarian, counter, ekspor, atau notifikasi kepada user yang tidak
berwenang.

### 9.2 Status dan retensi

Status minimal: `OPEN`, `UNDER_REVIEW`, `RESOLVED`, `CLOSED`, `ARCHIVED`. Penutupan tidak
menghapus laporan. Penghapusan manual menggunakan soft-delete/arsip, memerlukan alasan,
capability khusus, dan audit event.

## 10. Masukan

- Semua user aktif dapat membuat masukan.
- Visibilitas awal: pengirim dan AOM.
- AOM dapat memublikasikan ke cabang terkait setelah review.
- Publikasi mencatat AOM, waktu, cabang, dan versi isi yang dipublikasikan.
- Pengirim tetap dapat melihat masukan miliknya dan status tindak lanjut.
- Arsip/penghapusan manual mengikuti aturan laporan.

## 11. Audit dan keamanan

- Gunakan `audit.AuditEvent` append-only yang sudah ada.
- Tambahkan action untuk submit, return-for-revision, confirm, delegate, publish, archive,
  dan migration-import.
- Perubahan role, PIC, capability, reviewer, visibilitas, serta akses laporan rahasia wajib
  tercatat.
- Admin teknis tidak otomatis dapat membaca data bisnis rahasia.
- Queryset wajib dibatasi cabang dan scope sebelum objek ditampilkan atau diubah.
- Semua POST memakai CSRF, transaksi database, validasi ulang server-side, dan perlindungan
  double-submit/idempotency.
- Lampiran mengikuti pembatasan MIME, ukuran, nama acak, dan pemeriksaan izin saat download.
- Tidak ada hard-delete audit event melalui aplikasi.

## 12. Migrasi AOM standalone

### 12.1 Sumber yang dimigrasikan

- `ChecklistTemplate`
- `DailyChecklist`
- `Task`
- `Note`
- `Activity`
- `DailyClose`
- `AuditEvent`

### 12.2 Strategi

1. Buat eksportir read-only dari AOM dengan ID sumber, checksum, dan jumlah baris.
2. Buat importer idempoten di JoDerma Operasional dengan tabel pemetaan legacy ID.
3. Tetapkan seluruh data AOM lama ke cabang Jemur Andayani kecuali mapping eksplisit berkata
   lain; aturan ini harus disetujui saat rehearsal.
4. Mapping actor lama yang hanya berupa label tidak boleh ditebak menjadi user. Simpan label
   sebagai legacy actor sampai ada mapping yang diverifikasi.
5. Task AOM `OPEN` menjadi task terbuka yang belum memiliki penerima bila tidak ada mapping;
   daftar exception harus diselesaikan sebelum produksi.
6. Task AOM `DONE` menjadi histori terkonfirmasi dengan penanda `imported_legacy` dan waktu
   asli bila tersedia.
7. Note dan Activity tetap dipertahankan sebagai histori; tidak boleh hilang karena tampilan
   baru tidak memiliki padanan langsung.
8. Jalankan migrasi percobaan berulang pada salinan database, bukan database produksi.

### 12.3 Rekonsiliasi wajib

- Jumlah per tabel sebelum dan setelah migrasi.
- Jumlah per status dan per tanggal.
- Sampling konten, timestamp, legacy ID, serta hubungan checklist-task.
- Daftar record yang tidak dapat dipetakan.
- Checksum artefak ekspor dan backup.
- Import kedua menghasilkan nol duplikasi.

## 13. Tahapan implementasi

### Fase 0 — baseline dan perlindungan

- Pastikan repository desktop bersih dan catat commit baseline.
- Jalankan setup baseline di desktop Linux/Ubuntu:
  `python3.11 -m venv .venv`, install `requirements-dev.txt`, `collectstatic --noinput`,
  lalu `pytest`.
- Jalankan test suite lama dan simpan hasil.
- Buat database fixture anonim untuk test per role/cabang.
- Buat backup dan verifikasi restore sebelum migrasi skema.

**Gate:** tidak lanjut bila baseline test gagal atau repository mengandung perubahan yang
belum dipahami.

### Fase 1 — organisasi dan akses

- Cabang Jemur Andayani dan Citraland.
- Jabatan organisasi, role AOM/PIC/Staff, fungsi PIC, periode aktif, dan capability.
- Seed preview, bukan langsung membuat akun produksi.
- Matriks permission server-side beserta negative tests.

**Gate:** user cabang A tidak dapat membaca atau mengubah data cabang B; admin teknis tidak
otomatis membaca laporan rahasia.

### Fase 2 — task dan delegasi

- Assignment individual/bersama.
- Target user/tier/PIC/cabang dan snapshot penerima.
- Submit, revision, confirm, cancel, histori selesai, filter, dan notifikasi.
- Kompatibilitas `ActionItem.owner` lama.

**Gate:** tidak ada penerima yang dapat mengonfirmasi task sendiri; task ke PIC kosong gagal
dengan aman; pengiriman ulang tidak menggandakan assignment.

### Fase 3 — checklist harian

- Sesi opening/closing, target fungsi/tier, template berversi, dan assignment.
- Template PIC awal dalam mode preview.
- Tindak lanjut bermasalah membuat task idempoten.

**Gate:** perubahan template tidak mengubah histori; satu masalah tidak menghasilkan task
ganda; koreksi selalu memiliki audit trail.

### Fase 4 — laporan dan masukan

- Visibilitas satu cabang dan rahasia AOM.
- Publikasi masukan oleh AOM.
- Arsip, pencarian, filter, notifikasi, dan attachment yang aman.

**Gate:** uji kebocoran lintas cabang dan laporan rahasia lulus pada halaman, URL langsung,
pencarian, counter, ekspor, dan download lampiran.

### Fase 5 — UI dan usability

- Dashboard berbeda untuk Staff, PIC, AOM, dan Admin.
- Bahasa tindakan jelas: `Ajukan selesai` berbeda dari `Konfirmasi selesai`.
- Data selesai tetap tersedia melalui filter, bukan disembunyikan permanen.
- Uji mobile, desktop, keyboard, pesan error, empty state, dan koneksi lambat.

**Gate:** seluruh skenario per role dapat diselesaikan pengguna tanpa memakai Django admin.

### Fase 6 — migration rehearsal

- Ekspor salinan AOM.
- Import ke database desktop terpisah.
- Rekonsiliasi dan ulangi sampai deterministik serta idempoten.
- UAT menggunakan hasil migrasi, bukan hanya data buatan.

**Gate:** seluruh jumlah cocok atau setiap selisih memiliki exception yang disetujui.

### Fase 7 — release

- Seluruh test code, test UI, security regression, dan UAT lulus di desktop.
- Product owner memberi persetujuan eksplisit.
- Commit, push GitHub, dan tag rilis sebelum deployment.
- Backup database mini PC dan verifikasi backup.
- Deploy tag yang sama; tidak mengedit source langsung di mini PC.
- Smoke test, rekonsiliasi, dan pantau log.

**Gate:** bila health check, migrasi, login, permission, atau rekonsiliasi gagal, hentikan rilis
dan rollback. AOM standalone tetap tersedia.

### Fase 8 — observasi dan cutover

- Jalankan JoDerma Operasional dan AOM standalone selama masa observasi yang disepakati.
- Tentukan source of truth untuk input baru agar tidak terjadi dual-write tanpa aturan.
- Tinjau error, feedback, audit, backup, dan hasil operasional.
- Matikan AOM standalone hanya dengan persetujuan terpisah dan backup final terverifikasi.

## 14. Strategi pengujian desktop

### Automated code tests

- Model constraints dan migration tests.
- Permission matrix: positive dan negative tests untuk setiap role/cabang.
- State-machine task dan tindakan ilegal.
- Snapshot audience dan perubahan keanggotaan setelah pengiriman.
- Mode individual dan bersama.
- Checklist follow-up idempotency.
- Kerahasiaan laporan/masukan dan attachment.
- Audit completeness.
- Export/import idempotency dan reconciliation.

### UI tests

- Dashboard Staff, PIC, AOM, dan Admin.
- Direct URL access yang tidak berwenang menghasilkan 403/404 yang aman.
- Mobile viewport dan desktop viewport.
- Status selesai tetap dapat ditemukan.
- Tombol submit/confirm tidak tertukar.
- Empty PIC Citraland menghasilkan pesan yang dapat dipahami.

### UAT berbasis pengguna

Gunakan akun dummy, bukan akun produksi:

1. Staff Jemur menerima checklist individual dan mengisinya.
2. Masalah checklist membuat task tindak lanjut tepat satu kali.
3. Staff mengajukan task selesai; status belum final.
4. PIC mengembalikan task delegasinya untuk revisi lalu mengonfirmasi.
5. AOM mengonfirmasi task AOM.
6. Desy melihat fungsi PIC Kasir dan Online tanpa duplikasi identitas.
7. Staff Citraland tidak melihat laporan umum Jemur.
8. Staff lain tidak melihat laporan rahasia.
9. AOM memublikasikan masukan ke cabang yang benar.
10. Histori selesai tetap terlihat setelah login ulang dan pergantian tanggal.

## 15. Acceptance criteria rilis pertama

- Seluruh test lama dan baru lulus di desktop.
- Tidak ada akses lintas cabang yang tidak diizinkan.
- Tidak ada penerima yang bisa mengonfirmasi tugasnya sendiri.
- Task individual dan bersama berfungsi sesuai snapshot penerima.
- Checklist bermasalah membuat satu task tindak lanjut.
- Laporan umum terbatas satu cabang; laporan rahasia hanya untuk pelapor dan AOM.
- Masukan privat dapat dipublikasikan AOM dengan audit trail.
- Data selesai tetap dapat dicari dan difilter.
- Migration rehearsal idempoten dan rekonsiliasi disetujui.
- Backup dan restore rehearsal berhasil.
- Commit/tag GitHub yang akan dideploy telah ditentukan.
- Product owner memberikan approval deployment.

## 16. Rollback dan stop rules

Hentikan deployment dan rollback bila terjadi salah satu kondisi berikut:

- migration error atau jumlah data tidak cocok;
- login/otorisasi gagal;
- kebocoran laporan rahasia atau data lintas cabang;
- health check gagal;
- audit event penting tidak tercatat;
- task/checklist ganda akibat retry;
- UI tidak memungkinkan pekerjaan utama diselesaikan;
- backup belum diverifikasi dapat dipulihkan.

Rollback berarti menjalankan kembali image/tag sebelumnya dan database backup yang telah
diverifikasi. Jangan menghapus container, volume, atau AOM standalone sebelum bukti pemulihan
tersedia.

## 17. Model pelaksanaan dengan Codex

Codex menjadi satu-satunya agen pengembangan untuk proyek ini. Repository desktop dan GitHub
menjadi sumber kebenaran; tidak ada agen lain yang menjalankan implementasi paralel pada
working tree yang sama.

- **Implementasi:** Codex membuat perubahan terukur di repository desktop sesuai fase yang
  telah disetujui.
- **Verifikasi:** Codex menjalankan test otomatis, test UI, pemeriksaan permission, migration
  rehearsal, dan review diff sebelum perubahan dianggap siap.
- **Approval bisnis:** product owner tetap menjadi satu-satunya pihak yang menyetujui keputusan
  bisnis, hasil UAT, deployment, serta penghentian AOM standalone.
- **Git:** perubahan yang lulus review di-commit, di-push ke GitHub, dan diberi tag sebelum
  deployment.
- **Produksi:** Codex hanya memandu atau menjalankan deployment setelah approval eksplisit;
  tidak ada eksperimen atau pengeditan langsung di mini PC.
- **Stop rule:** bila bukti pengujian, backup, permission, migrasi, atau rekonsiliasi belum
  memenuhi gate, Codex harus menghentikan proses dan tidak melanjutkan ke deployment.

Aplikasi tidak bergantung pada Codex saat runtime. Setelah dideploy, seluruh workflow task,
checklist, laporan, masukan, notifikasi, dan audit berjalan mandiri di JoDerma Operasional.

## 18. Bukti yang harus disimpan

- Commit baseline dan status repository.
- Hasil test otomatis sebelum/sesudah.
- Matriks permission dan hasil negative tests.
- Screenshot atau rekaman singkat UAT tiap role.
- Laporan migration rehearsal dan exception list.
- Checksum ekspor dan backup.
- Approval produk, approval deployment, tag rilis, dan waktu deployment.
- Health check, smoke test, rekonsiliasi, dan keputusan lanjut/rollback.
- Approval terpisah bila AOM standalone akan dihentikan.

## 19. Keputusan yang masih perlu dikonfirmasi saat desain rinci

Keputusan ini tidak menghalangi persetujuan rencana, tetapi harus selesai sebelum fase terkait:

- username dan identitas akun final setiap personel;
- waktu dan deadline checklist opening/closing;
- item wajib, kebutuhan foto, serta kriteria otomatis “bermasalah”;
- siapa pengganti reviewer ketika AOM/PIC pemberi tugas tidak aktif;
- lama masa observasi sebelum cutover;
- kebijakan retensi dan siapa yang mempunyai capability arsip/penghapusan manual;
- aturan source of truth untuk input selama masa observasi agar tidak terjadi dual-write.
