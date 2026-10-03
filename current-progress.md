# Current Progress

Status per **3 Oktober 2026** (Asia/Jakarta). Keputusan product owner 3 Okt: **perbaiki masalah
Citraland dulu** (tahap 1, selesai di kode, menunggu commit dan deploy), lalu task management
GTD dan daftar task (tahap 2), lalu catatan KPI (tahap 3). Fase 6–9 redefinisi peran menyusul.
Bagian atas dokumen ini adalah posisi terakhir, sisa pekerjaan, dan roadmap. Bagian **Riwayat**
di bawahnya adalah catatan per pekerjaan seperti ditulis saat dikerjakan.

## Posisi terakhir

| | |
|---|---|
| Produksi (mini PC, ops.joderma.id) | Commit `6273c6d` (dideploy 3 Oktober): tahap 2 paket B (Inbox pilah, temuan Owner; migrasi `owner 0002`, `reports 0003`), di atas `3830f6f` (paket A: Daftar Task, agenda keputusan bersama; `direktur 0005`), `4e3864e` (tally masuk audit), `bdec50a` (ekspor audit CSV), `43f49eb` (Laporan Masuk) dan `523ca4d` (dua cabang, koreksi tally, tutup hari, foto, penugasan staf; migrasi `nurses 0005`, `accounts 0009`). Peran dirapikan lewat `rapikan_peran.sh` 3 Okt |
| Desktop (WSL, `/mnt/e/Claude/Projects/joderma-operasional`) dan GitHub | Komputer kerja sejak 30 Sep. Sejajar dengan `origin/master` di `e966da7` |
| Langkah sesudah deploy (di UI produksi) | Reset peran ke default; Susun ulang otomatis Oktober kedua cabang; unggah ekspor Omnicare terbaru di Stok Apotek; ganti password `hansen1` dan `superadmin` |
| Belum dideploy | **Paket C tahap 2**: pemeriksa task (Dirut/Owner memverifikasi pekerjaan Direktur Operasional), lapor progres, catatan bukti wajib; migrasi `core 0006` (3 Okt, lihat Riwayat) |
| Test | 696 (695 lulus, 1 dilewati) per 3 Okt: 675 di luar Stok Apotek ditambah 21 test Stok Apotek (`.venv/bin/python -m pytest`) |
| Rencana aktif | [`docs/KEBUTUHAN_REDEFINISI_PERAN.md`](docs/KEBUTUHAN_REDEFINISI_PERAN.md), dikerjakan fase demi fase dengan persetujuan product owner di setiap akhir fase |
| Cara melanjutkan | [`docs/lanjutkan-pekerjaan.md`](docs/lanjutkan-pekerjaan.md) |

## Stok Apotek: status

Spesifikasi: [`docs/stok-apotek.md`](docs/stok-apotek.md). App baru `stok`, halaman `/stok-apotek/`.

| Fase | Isi | Status |
|---|---|---|
| 1 | Impor Daftar Produk, Tingkat Persediaan, Pergerakan (.xls Omnicare); penggabungan unduhan terpotong; 4 uji kelengkapan; tab Prioritas Order, Transfer, Impor Data; parameter | Selesai 1 Okt, angka identik dengan workbook 30 Sep. Commit `e966da7`, dideploy 1 Okt |
| 2 | Moving, Kandidat Nonaktif, tanda tindak lanjut, unduh daftar order per pabrikan | Belum |
| 3 | Lead time distributor, bulan berjalan, kemasan | Belum |

Hak akses (keputusan 1 Okt): apoteker, asisten apoteker, dan Direktur Operasional membuka,
mengunggah, dan mengubah parameter; Owner hanya baca; peran lain 403. Deploy butuh
`docker compose build app` karena dependensi baru `xlrd`. Migrasi baru: `stok 0001`.

## Redefinisi peran: status per fase

| Fase | Isi | Status |
|---|---|---|
| 1 | Baseline: pemeriksaan read-only, seluruh test lulus | Selesai |
| 2 | Definisi peran standar dan tombol **Reset peran ke default** (akun `jean`) | Selesai, di-commit 30 Sep |
| 3 | Menu per peran, halaman pertama sesudah login, penolakan server-side (403) dan test negatif | Selesai, di-commit 30 Sep |
| 4 | Owner: Dashboard + Permintaan Owner, Keputusan, Summary Harian, Jadwal ringkas | Selesai, di-commit 30 Sep |
| 5 | Direktur: tombol "Simpan dan kirim summary ke Owner", riwayat summary; lonceng notifikasi | Selesai, di-commit 30 Sep |
| 6 | Permintaan Owner sisi Direktur dan baris Gantt | **Belum** — berikutnya |
| 7 | Staf sederhana | Belum |
| 8 | PIC mengatur sesuai porsi fungsinya | Belum |
| 9 | Uji tampilan per peran (desktop dan HP) bersama product owner | Belum |

Fase 2–5 sudah lulus test dan tangkapan layarnya sudah ditinjau product owner per fase, tetapi
**belum diuji di mini PC** dan belum dipakai staf.

## Tahap 2 dan 3 (permintaan dr. Yohanes dan product owner, 3 Okt)

**Tahap 2 — task management GTD.** Alur: siapa pun (termasuk Owner) memasukkan ide/temuan ke
*Inbox* → Direktur Operasional memutuskan, menetapkan PIC dan prioritas → PIC mengerjakan,
melaporkan progres, mengirim bukti → Direktur Operasional memverifikasi → capaian dilaporkan ke
Direktur Utama. Bila Hansen sendiri PIC, verifikatornya dr. Yohanes. Juga: temuan Owner langsung
di aplikasi; nama/ID pelapor tercantum di setiap laporan; **List View** semua task dengan sort,
filter, dan pencarian; butir yang perlu diputuskan bersama tampil di halaman utama untuk rapat
mingguan (K-015). Foto bukti dan foto temuan sudah tersedia (tahap 1) dan dipakai alur ini.

Rencana disetujui product owner 3 Okt, dikerjakan per paket dengan persetujuan di akhir tiap paket:

| Paket | Isi | Status |
|---|---|---|
| A | Pelapor di task (butir 4), Daftar Task (5), agenda keputusan bersama + task menunggu keputusan (6, K-015) | `3830f6f`, dideploy 3 Okt |
| B | Inbox satu pintu dengan pilah sesuai matriks wewenang (putuskan/tugaskan, teruskan, bawa ke rapat, tidak ditindaklanjuti) + temuan Owner (digabung ke form Permintaan Owner, target opsional) | `6273c6d`, dideploy 3 Okt |
| C | Kolom Pemeriksa (task PIC Direktur Operasional diperiksa Owner/Dirut), Owner dapat konfirmasi/minta revisi task yang ia periksa, linimasa progres PIC; bukti: catatan wajib, foto opsional. Dirut = akun `jean` (peran Owner, sama dengan `yohanes`) | dibuat 3 Okt, belum di-commit |
| D | Halaman Bahan Rapat mingguan (Kamis lalu–Rabu) | berikutnya |

Keputusan bawaan yang dipakai: halaman utama K-015 = Ringkasan Direktur dan Dashboard Owner;
tenggat task yang menunggu keputusan dibekukan. Pertanyaan Owner yang masih terbuka: lama dan ukuran
berhasil uji coba task management.

**Tahap 3 — KPI (K-016).** Setiap checklist mencatat ID staf, geolokasi, dan IP Wi-Fi klinik;
metrik kedisiplinan (tepat waktu, kelengkapan) per staf.

## Task yang belum selesai

### Pengembangan (fase 6–9)

1. **Fase 6 — Permintaan Owner sisi Direktur.**
   - Kotak masuk permintaan untuk Direktur (menu Direktur), urut lewat target lalu target terdekat.
   - Tombol "Pecah jadi task" dari halaman permintaan: judul, cabang, penerima, target, prioritas;
     task dibuat lewat `core.task_services.create_task` dengan `source_type="permintaan_owner"`,
     `source_id` = permintaan (progres di sisi Owner sudah membaca dari sini).
   - Gantt (Jadwal Task): satu baris per permintaan beserta task turunannya; target permintaan
     ditandai.
   - Test: hanya AOM yang memecah, progres ikut berubah, baris Gantt muncul untuk Owner dan Direktur.
2. **Fase 7 — Staf sederhana.**
   - **Tugas hari ini**: daftar pendek butir checklist porsinya hari itu + task yang ditugaskan
     kepadanya (menggantikan Hari Ini dan Checklist Saya di menu staf).
   - **Jadwal saya**, **Istirahat saya**, **Tindakan saya** (giliran dan tally dirinya, hari ini dan
     bulan ini) — hanya dirinya, bukan grid tim; lalu tutup grid tim untuk staf di server.
   - **Kas hanya pada hari ia ditugaskan sebagai kasir** (porsi "Kasir hari ini"), ditegakkan di
     server, bukan hanya menu.
   - Komplain, Masukan, Kerusakan, Laporan Saya, Masukan Saya tetap.
3. **Fase 8 — PIC sesuai porsi fungsinya.** Pembagian tugas yang ada dipakai apa adanya (uji coba);
   PIC mengganti pelaksana, giliran perawat, istirahat, dan roster hanya untuk porsi fungsinya di
   cabangnya. Saat ini hanya Koordinator Shift (SUPERVISOR) yang boleh mengganti pelaksana.
4. **Fase 9 — Uji tampilan** per peran di desktop dan HP bersama product owner, lalu commit dan
   deploy fase 6–9 sebagai satu paket.

### Catatan operasional (dikerjakan product owner, belakangan)

- **Password dan backup:** ditunda selama fase uji coba; rinciannya di
  [`docs/catatan-developer.md`](docs/catatan-developer.md) (password awal belum dikunci untuk
  diganti, backup belum terenkripsi dan belum ada salinan kedua).
- **Reset peran ke default** tidak perlu dijalankan: peran sudah dirapikan per orang (3 Okt, lihat
  Riwayat). Bila suatu saat dijalankan, periksa pratinjaunya, karena akan mencabut Front Desk
  heni/lia/yani yang dipasang manual.
- Isi DPJ, APJ, dan jam Citraland di Pengaturan Klinik (tidak terisi otomatis karena kode cabang
  Citraland di mini PC adalah `JC`).
- Putuskan akun `AOM_HS`: bila akun lama, nonaktifkan.
- **Jadwal jaga November:** siapkan JSON dari PDF jadwal libur sebelum akhir Oktober.
- **PDF jadwal Oktober** (sumber kebenaran) memuat angka ringkasan yang tidak cocok dengan selnya
  sendiri: kolom Jumlah Masuk Heni 25 dan Elvira 26 (sel: 26 dan 27); baris Total Perawat Jemur
  tanggal 6, 9, 10, 16, 17, 20 (PDF 3/4/5/5/3/4, sel 4/5/4/4/4/5); baris Total Farmasi Citraland
  tanggal 4 dan 24 (PDF 2/3, sel 3/2). Aplikasi mengikuti sel per tanggal; konfirmasi ke pembuat
  jadwal bila angka ringkasannya yang benar.
- Opsional: hapus `docs/KEBUTUHAN_ROLE_OWNER.md` (sudah digantikan, isinya hanya penunjuk).

### Celah yang dicatat (bukan blocker)

- Beberapa predikat di `core/permissions.py` (audit, ekspor, baca pengaturan klinik) masih
  menyebut owner. Untuk akun yang hanya Owner, halaman itu tetap ditolak oleh tampilan Owner
  (`core/peran.py`); predikatnya dirapikan bila disentuh lagi.
- Sampai fase 7, staf masih melihat grid Jadwal Jaga seluruh tim dan menu Kas setiap hari bila
  memegang peran front desk.
- Summary harian hanya terkirim bila Direktur menekan tombol; belum ada pengingat bila lupa.
- Pemilih tanggal memakai format bawaan browser (mis. bulan/tanggal di browser berbahasa Inggris).
- Tangkapan layar tiap fase dibuat di database uji (data contoh), bukan data klinik.
- Penangguhan lama dari integrasi AOM tetap berlaku (lampiran laporan/masukan, pencarian teks
  bebas, QA manual viewport dan keyboard) — lihat Riwayat ▸ Langkah berikutnya.

## Roadmap

| Kapan | Apa |
|---|---|
| Sekarang | Commit dan deploy tahap 1 (dua cabang + foto); Regitta mencoba koreksi tally, tutup hari, dan foto di Citraland |
| Berikutnya | Tahap 2: task management GTD, List View task, keputusan bersama di halaman utama, nama pelapor (permintaan dr. Yohanes) |
| Sesudah tahap 2 | Tahap 3: catatan KPI (ID staf, geolokasi, IP Wi-Fi) dan metrik kedisiplinan |
| Paralel | Stok Apotek fase 1 dipakai apoteker dengan data produksi; keputusan A5–A9; lalu fase 2 |
| Sesudah itu | Fase 6 (Permintaan Owner sisi Direktur), fase 7 (staf sederhana), fase 8 (PIC), fase 9 (uji tampilan bersama product owner) |
| Sesudah fase 9 | Commit, backup, deploy; perkenalan tampilan baru ke Owner, Direktur Utama, PIC, dan staf |
| Oktober 2026 | Uji coba jadwal jaga, pembagian tugas, dan giliran tally bulanan; catat masalah di `UAT_ISSUE_REGISTER.md`; aturan tally ditweak sesudah uji coba (ketetapan 30 Sep) |
| Akhir Oktober | Jadwal jaga November: siapkan JSON dari PDF, `import_jadwal_jaga`, `seed_tugas_harian --susun 2026-11` |
| Belum dijadwalkan | Pengingat summary harian; perapihan predikat owner di `core/permissions.py`; lampiran laporan/masukan; rehearsal migrasi data AOM legacy (fase 6–8 rencana integrasi AOM, perlu persetujuan terpisah) |

---

# Riwayat

## Paket C tahap 2: pemeriksa, verifikasi Dirut, lapor progres (3 Oktober 2026) — belum di-commit

- `ActionItem.review_by` (DIREKTUR/DIRUT, migrasi `core 0006`) dan `effective_review_by`: Dirut
  bila salah satu penerima aktif berperan AOM (dihitung, data lama tidak diubah). Dirut dan Owner
  sama-sama peran OWNER (akun `jean`, `yohanes`).
- `can_review_assignment`: task Dirut hanya diverifikasi peran OWNER; `close_task` ditolak untuk
  task Dirut; Owner boleh menulis catatan di task yang ia periksa (`add_task_comment`). Pemeriksa
  dapat diubah Direktur di **Ubah task**.
- Notifikasi: ajukan selesai → pemeriksa (`TASK_SUBMITTED`; Owner untuk task Dirut, Direktur dan
  pembuat untuk lainnya); konfirmasi → penerima (`TASK_CONFIRMED`); revisi → penerima (`TASK_REVISION`).
- Lapor progres: `report_progress` + rute `core:assignment_progress` (teks wajib, foto opsional,
  lampiran `taskevent`); event baru `PROGRESS`. Tampil di Hari Ini (progres terakhir), Semua task
  saya, dan riwayat detail task. Catatan bukti wajib saat ajukan selesai (view).
- Dashboard Owner: **Menunggu verifikasi Anda** dan **Capaian 7 hari terakhir**
  (`owner.services.verification_queue`, `recent_achievements`).
- Test: `direktur/tests/test_paket_c.py` (5); test lama disesuaikan untuk catatan bukti wajib.

## Paket B tahap 2: Inbox pilah dan temuan Owner (3 Oktober 2026) — `6273c6d`, dideploy 3 Okt

- Menu **Laporan Masuk** berganti nama **Inbox** (alamat tetap `/laporan/masuk/`). Isinya ditambah
  Permintaan/Temuan Owner dan Catatan Direktur milik penulisnya (`reports/inbox.py`). Tab: Belum
  dipilah (bawaan), Diteruskan/dipantau, Sudah dipilah, Semua. Item yang sudah ditangani cabang
  (status bukan Baru), permintaan yang sudah punya task, dan catatan yang sudah jadi task dihitung
  sudah dipilah. Kartu Inbox di Ringkasan/Dashboard menampilkan jumlah belum dipilah.
- Pilah (`reports/triage.py`, model `InboxTriage`, migrasi `reports 0003`; halaman
  `/laporan/masuk/pilah/<sumber>/<id>/`, hanya AOM): tugaskan (task bersumber `issue`/`laporan`/
  `masukan`/`permintaan_owner`; catatan lewat `convert_note`), teruskan (Dirut, Apoteker, Keuangan,
  Medis, Omnicare, Lainnya) lalu dipantau, bawa ke rapat (Keputusan Rapat bersama, rujukan = nomor
  item), tidak ditindaklanjuti (alasan wajib). Pada issue: status Baru maju ke tahap tinjau
  (Ditinjau/Dipertimbangkan/Ditriase) dan ke Ditugaskan bila ditugaskan dan alurnya mengizinkan;
  hasil pilah ditulis di riwayat. Pilah ulang menggantikan; semua tercatat di audit.
- **Temuan Owner**: `OwnerRequest.kind` (PERMINTAAN/TEMUAN), `target_date` opsional untuk temuan,
  `clinic`, `urgent` (migrasi `owner 0002`). Tombol **+ Catat temuan** di Dashboard Owner.
- Celah lama tertutup: sebelumnya tidak ada UI bagi Direktur untuk memecah Permintaan Owner menjadi
  task. Kini lewat pilah, dan task berikutnya dari halaman permintaan (**Tambah task**).
- Task detail: sumber task bisa diketuk (`dashboard.source_url`); pelapor untuk task dari issue,
  laporan, masukan.
- Test: `reports/tests/test_inbox_pilah.py` (10).

## Paket A tahap 2: pelapor, Daftar Task, keputusan bersama (3 Oktober 2026) — `3830f6f`, dideploy 3 Okt

- **Pelapor di task**: `direktur.dashboard.reporters()` mencari pelapor asal per sumber (checklist →
  pengisi butir, temuan Direktur → pemeriksa, permintaan Owner → Owner, catatan → penulis; selain itu
  pembuat). Tampil di kartu Kanban/Prioritas, detail task, Daftar Task, CSV.
- **Daftar Task** `/direktur/daftar/` (`direktur:tasks`, modul `direktur/task_list.py`): cari, saring
  status (termasuk lewat target, menunggu konfirmasi, menunggu keputusan, belum ada penerima),
  cabang, PIC, prioritas, sumber, tanggal dibuat; urut per kolom; 50 per halaman; unduh CSV (tercatat
  EXPORT di audit). Owner baca saja; menu Owner dan Direktur.
- **Keputusan bersama (K-015)**: pemutus baru *Rapat bersama (Kamis)*; `Decision.waiting_tasks`
  (M2M, migrasi `direktur 0005`). Agenda rapat Kamis di atas Ringkasan Direktur dan Dashboard Owner.
  Detail task: tahan dengan perkara yang ada atau *Bawa ke rapat* (perkara baru), lepas. Selama
  ditahan `ActionItem.is_overdue` = False. Saat ditetapkan/dibatalkan: catatan di riwayat task +
  notifikasi `TASK_DECISION` ke penerima (sekali). Keputusan ditetapkan → *Buat task tindak lanjut*
  (sumber `keputusan`).
- Test: `direktur/tests/test_paket_a.py` (12).

## Audit kegiatan staf dan tally baru masuk audit (3 Oktober 2026) — `4e3864e`, dideploy 3 Okt

Product owner mengaudit kegiatan staf dari ekspor audit pertama (663 kejadian, 11 Sep–3 Okt).
Temuan utama: password awal `klinik123` masih dipakai sebagian besar akun dan pernah dipakai login
bergantian dari satu perangkat (sehingga pelaku di audit belum pasti); Jemur belum memakai checklist
dan kas di Oktober; Citraland mengisi sekitar 23–29 dari ~50 butir checklist per hari, semuanya OK
(laporan kerusakan lampu dibuat terpisah); kas Citraland yang tercatat bernilai Rp 0; Regitta
menandai Naya off 3 Okt padahal PDF menyebut masuk (kemungkinan tukar libur). Keputusan: password dan
backup ditunda sampai uji coba lancar ([`docs/catatan-developer.md`](docs/catatan-developer.md)).

Celah yang ditutup: tally baru kini tercatat di audit (`nurses.views.create_tally` →
`log_create`, label RM · tindakan · jumlah · perawat · cabang); sebelumnya hanya koreksinya.
Test di `core/tests/test_dua_cabang.py`.

## Ekspor audit CSV (3 Oktober 2026) — `bdec50a`, dideploy 3 Okt

Halaman Audit mendapat tombol **Unduh CSV** (`audit:export`, `/audit/ekspor/`) yang mengunduh persis
isi saringan di layar (pengguna, aksi, data, rentang tanggal): waktu WIB, pengguna dan username,
aksi, jenis/ID/nama data, alasan, nilai sebelum dan sesudah (JSON), alamat IP, perangkat, ID
permintaan. UTF-8 dengan BOM agar terbuka rapi di Excel; nilai yang diawali `= + - @` dinetralkan
(tidak dijalankan sebagai rumus); dialirkan per 500 baris sehingga ekspor besar tidak membebani.
Hanya Direktur Operasional dan admin berakses penuh (`audit.views.can_export_audit`); Koordinator
Shift tetap membaca di layar tanpa mengunduh. Setiap unduhan tercatat di audit (EXPORT, beserta
saringan dan jumlah baris). Juga: saringan "Data" ikut mencari nama data, saringan pengguna mencari
nama tampilan, navigasi halaman tidak lagi membuang saringan, dan menu Admin (superadmin) mendapat
Audit. Test `audit/test_ekspor.py` (4).

## Perapian peran dan hak akun (3 Oktober 2026) — data, lewat `rapikan_peran.sh`

Tinjauan daftar pengguna bersama product owner:
- `superadmin` memegang Owner, Perawat, Koordinator Shift, Front Desk, dan Staf di Jemur selain
  Admin. Karena peran Owner, akun ini masuk ke tampilan Owner (menu admin tidak terlihat) dan ikut
  muncul di daftar perawat. Keputusan: hanya Admin (sesuai `accounts/peran_standar.py`).
- `hansen1` masih memegang PIC cabang di Jemur. Keputusan: dicabut; tetap Direktur Operasional + Admin.
- Hak "Melihat komplain terbatas" (`issue.view_restricted`) terpasang manual di hampir semua staf
  (alya, arsi, ayu, desy, elvira, heni, lia, luki, yani), sehingga komplain Terbatas terbuka untuk
  mereka. Keputusan: dicabut dari staf biasa; komplain terbatas hanya untuk pembuat, penanggung
  jawab, Koordinator Shift, Direktur, dan Owner.

## Laporan Masuk lintas cabang untuk Direktur dan Owner (3 Oktober 2026) — `43f49eb`, dideploy 3 Okt

Temuan product owner sesudah deploy `523ca4d`: laporan kerusakan dan masukan Regitta (Citraland)
tidak terlihat dari akun Direktur. Sebabnya: (1) daftar Komplain/Masukan/Kerusakan dan Laporan/
Masukan staf hanya menampilkan cabang aktif, sedangkan Direktur terdaftar di Jemur; (2) menu Direktur
tidak memuat Komplain/Masukan/Kerusakan dan Owner ditolak sama sekali; (3) notifikasi catatan baru
hanya ke Koordinator Shift cabang itu, dan notifikasi masukan/laporan rahasia ke pemegang peran AOM
*di cabang pengirim* (tidak ada di Citraland). Ditemukan juga: nomor catatan dihitung per cabang
padahal unik di seluruh aplikasi, sehingga catatan kedua cabang pada hari yang sama bisa bentrok
nomor dan gagal tersimpan.

- Halaman **Laporan Masuk** (`reports:inbox`, `/laporan/masuk/`, `reports/inbox.py`): Komplain,
  Masukan, Kerusakan, Laporan staf, dan Masukan staf dari semua cabang; saring cabang, jenis,
  status (terbuka/semua), kata kunci termasuk nama pelapor; jumlah terbuka per cabang. Menu Direktur
  (di bawah Ringkasan) dan Owner (di bawah Dashboard); kotak ringkas di Ringkasan dan Dashboard Owner.
- Owner membuka detail catatan, laporan, dan masukan **baca saja** (`OWNER_READ_ONLY`: POST 403,
  tombol tindakan disembunyikan).
- `notifications.services.notify_leaders`: setiap catatan, laporan, dan masukan baru memberi tahu
  semua Direktur Operasional dari cabang mana pun (Owner untuk yang kritis). Notifikasi laporan
  rahasia tidak menyebut isi atau pelapor.
- Nama pelapor tampil di detail dan daftar catatan (kecuali catatan anonim bagi staf biasa);
  Direktur melihat catatan terbatas di daftar cabang.
- `issues.services.generate_number`: urutan lintas cabang + coba ulang bila bentrok.
- Test `reports/tests/test_laporan_masuk.py` (10).

## Penelusuran jadwal jaga Oktober dan penempatan staf (3 Oktober 2026)

Diperiksa pada salinan database mini PC (3 Okt 16.15) terhadap "JADWAL LIBUR OCTOBER 2026.pdf"
(warna sel dibaca per piksel): **403 dari 403 baris jadwal sama persis** dengan PDF, cabang asal
13 staf benar (8 Jemur termasuk Yani dan Luki, 5 Citraland), belum ada perubahan manual. Porsi
tugas Oktober seluruhnya jatuh ke orang yang bertugas di cabangnya, tally seluruhnya oleh perawat
yang bertugas di cabangnya. Kolom "Jumlah" di PDF menulis Heni 25 dan Elvira 26, sedangkan selnya
memberi 26 dan 27 (sel yang dipakai).

Yang keliru adalah **peran lama yang tertinggal**: regita masih ONLINE/PIC/SUPERVISOR di Jemur,
ayu masih APOTEKER/FRONT_DESK/STAF di Jemur, dan elvira SUPERVISOR di Jemur. Akibatnya Regita dan
Elvira berwenang sebagai Koordinator Shift Jemur (tutup hari, ubah jadwal, koreksi tally), dan
porsi opening/closing Koordinator Shift 8 Okt serta closing limbah 9 dan 29 Okt jatuh ke Elvira.
Keputusan product owner: Regitta hanya Citraland (Koordinator Shift dan Layanan Daring), Ayu hanya
Citraland sebagai apoteker, Elvira apoteker dan PIC Kebersihan Jemur. Perintah baru
`manage.py cabut_peran` (audit PERMISSION_CHANGED, `--dry-run`) dan `manage.py susun_ulang_tugas`
(porsi otomatis untuk rentang tanggal, porsi manual dipertahankan); `deploy_dua_cabang.sh`
menjalankan keduanya sesudah backup. Diuji pada salinan produksi: sesudahnya porsi Koordinator
Shift Jemur 8 Okt jatuh ke Desy, kas 4 Okt ke Elvira (cadangan kasir). Peran Regita di Citraland
(termasuk PERAWAT untuk giliran tally) dan FRONT_DESK Ayu di Citraland (kasir sementara) tetap.
Daftar "Siapa bertugas hari ini" tidak lagi menampilkan orang yang hanya punya peran tertinggal.

## Hak khusus koreksi tally untuk Regitta (3 Oktober 2026) — `523ca4d`, dideploy 3 Okt

Permintaan product owner: Regitta diberi hak khusus mengoreksi tally. Kapabilitas baru
`tally.correct` ("Mengoreksi tally perawat"), berlaku di cabang yang dapat diakses pemegangnya
dan tidak ikut hilang saat Reset peran. Bisa dicentang di Admin ▸ Pengguna ▸ ubah, atau lewat
perintah baru `manage.py beri_hak <username> tally.correct [--cabut]` (tercatat di audit).
`deploy_dua_cabang.sh` memberikannya ke akun `regita` di mini PC. Migrasi `accounts 0009`
(hanya pilihan kapabilitas). Test di `core/tests/test_dua_cabang.py`.

## Penugasan staf harian dan bulanan oleh Direktur dan Koordinator Shift (3 Oktober 2026) — `523ca4d`, dideploy 3 Okt

Keputusan product owner sesudah kasus Citraland: Direktur Operasional mengubah penugasan tiap
staf per hari atau per bulan; Koordinator Shift juga bisa. Sebelumnya jadwal jaga hanya diubah
Direktur/Admin lewat satu form di bawah tabel, dan perubahan tidak menyentuh porsi tugas.

- `jadwal.services.can_edit_duty(actor, cabang_asal)`: Direktur/Admin semua orang; Koordinator
  Shift (SUPERVISOR) untuk staf yang cabang asalnya cabangnya, termasuk mengirim perbantuan.
  `home_clinic_for` menjaga cabang asal saat diubah dari halaman cabang lain (sebelumnya form
  bulanan selalu menimpa cabang asal dengan cabang halaman).
- Tabel Jadwal Jaga: setiap kotak bisa diketuk untuk mengubah satu orang pada satu tanggal.
- Halaman tugas per tanggal: bagian **Siapa bertugas hari ini** dengan pilihan Masuk /
  Perbantuan ke cabang lain / Off / Cuti per orang.
- `set_duty` untuk hari ini ke depan: porsi orang yang tidak lagi bertugas di cabang itu dilepas,
  porsi kosong diisi (`_plan_day(..., fill_only=True)`, porsi orang lain tidak diacak), dan
  roster giliran perawat disinkronkan bila hari operasional sudah dibuat.
- Test `jadwal/tests/test_ubah_jadwal.py` (8); `test_only_director_edits_roster` diganti
  `test_who_edits_roster`. Panduan Direktur, Supervisor, `docs/jadwal-dan-giliran.md`,
  `docs/peran-dan-akses.md` diperbarui.

## Dua cabang (Jemur dan Citraland) dan foto lampiran (3 Oktober 2026) — `523ca4d`, dideploy 3 Okt

Laporan Regitta (Koordinator Shift Citraland) 2–3 Okt, didiagnosis pada salinan database mini PC
(`tarik_db.sh`, integrity ok):

- **Akun tampil sebagai Jemur.** Regita masih memegang peran lama di Jemur (Reset peran belum
  dijalankan) dan pada 2 Okt ia off, sehingga cabang aktif jatuh ke cabang pertama (Jemur).
  Perbaikan: `core.services.active_clinic` kini memakai pilihan cabang hari ini → cabang tugas di
  jadwal jaga → **cabang asal** (`home_clinic_id`: jadwal hari ini/terdekat, atau satu-satunya
  cabang fungsi PIC) → cabang pertama. Pengalih cabang di kanan atas (`accounts:switch_clinic`,
  berlaku hari ini saja lewat `core.middleware.ActiveClinicMiddleware`) untuk akun dengan lebih
  dari satu cabang; cabang aktif selalu terlihat. Di HP nama aplikasi disembunyikan agar cabang muat.
- **Kode Citraland di mini PC adalah `JC`**, bukan `citraland`, sehingga prefix RM jatuh ke `J_-`
  dan butir Direktur khusus Citraland tidak cocok. `core.services.clinic_key`/`rm_prefix` kini
  menjadi satu-satunya penentu; dipakai `orders.services.normalize_rm_number`, papan tally, dan
  `direktur.AuditItem.applies_to`.
- **Tally tidak bisa dikoreksi.** Koordinator Shift cabang itu dan Direktur Operasional kini bisa
  mengoreksi jumlah (0 = batal), perawat, dan nama tindakan dengan alasan wajib, tercatat di audit
  (CORRECTION) dan `turns_taken` ikut disesuaikan (`nurses.services.correct_tally`, halaman
  `nurses:tally_day` dan `nurses:tally_correct`, kolom Koreksi di papan). Migrasi `nurses 0005`
  (kolom `corrected_by`, `corrected_at`, `correction_reason`). Duplikat Sculptra JC-0108 1 Okt bisa
  dibatalkan dari sini.
- **Hari tidak bisa ditutup.** Semua hari operasional di produksi tertahan di "Pembukaan berjalan".
  Keputusan: Koordinator Shift boleh menutup sesudah kas akhir **diajukan**; verifikasi Direktur
  menyusul (juga setelah hari ditutup) dan sejak itu selisih menjadi tanggung jawab verifikator.
  Tutup hari kini boleh dari status mana pun yang belum tutup; pilihan di Hari Ini disederhanakan
  (hari tutup hanya "Buka kembali"). Direktur Operasional (AOM) melihat nominal, memverifikasi,
  dan mengoreksi kas; daftar **Menunggu verifikasi** di Kas dan Hari Ini Direktur. Sesi kas cabang
  lain kini ditolak (sebelumnya bisa dibuka lewat ID).

**Foto lampiran** (keputusan 3 Okt, empat tempat): butir checklist bermasalah (form "Ada masalah?"
dengan hasil Tidak lengkap/Rusak/Tidak berlaku, catatan wajib, foto), Komplain/Masukan/Kerusakan,
temuan Direktur (Checklist Direktur) dan Owner (permintaan dan catatannya), serta bukti task
selesai (Hari Ini, Semua task saya; tampil di detail task). `core/photos.py`: foto dikecilkan di
browser lalu dikompres ulang di server (sisi terpanjang 1600 px, JPEG q75, EXIF/GPS dibuang),
disimpan di `private_media` sebagai `core.Attachment`, dan hanya terbuka lewat `core:attachment`
(`?lihat=1` untuk tampil langsung) dengan izin mengikuti entitas induknya; foto sumber temuan ikut
terlihat oleh penerima task tindak lanjutnya. Laporan kerusakan dari butir checklist membawa foto
butirnya. Bila foto gagal dibaca, isian tidak tersimpan setengah (transaksi).

Uji coba: migrasi berjalan di salinan database produksi; tangkapan layar dari salinan itu (regita
melihat Citraland, koreksi tally 1 Okt, form masalah checklist, Tugas saya Desy dengan foto bukti,
Kas Direktur); unggah foto 11,7 MB dari browser HP menjadi 0,7 MB. Test baru:
`core/tests/test_dua_cabang.py` (24) dan `core/tests/test_foto.py` (12). Suite 620 lulus di luar
Stok Apotek.

## Tugas saya di Hari Ini (1 Oktober 2026) — belum dideploy

Temuan product owner: task pengolahan limbah untuk Desy ada di database mini PC tetapi tidak tampil
di Hari Ini, sehingga mudah terlupa. Sebabnya, daftar lama "Perlu tindakan saya": (1) hanya dirender
bila sesi hari operasional hari itu sudah dibuat; (2) hanya membaca `ActionItem.owner`, yang kosong
untuk task ke beberapa orang, ke satu peran, atau ke fungsi PIC; (3) hanya cabang aktif.

Perbaikan: `core.task_services.my_tasks(user)` membaca penerima task (`TaskAssignment`) di semua
cabang yang dapat diakses, tanpa bergantung pada sesi hari, menyembunyikan task bersama yang sudah
diambil orang lain, dan menaruh yang lewat target paling atas serta yang sudah diajukan paling bawah
("Menunggu konfirmasi"). Kartu **Tugas saya** kini paling atas di Hari Ini untuk semua peran, dengan
tombol **Ajukan selesai** / **Ambil task** yang kembali ke Hari Ini (`next` aman). Halaman Semua task
saya untuk staf kini lintas cabang yang dapat diakses. Test: `core/tests/test_tugas_saya.py` (9).

## Detail task untuk Direktur (1 Oktober 2026) — di-commit (`0e29474`), belum dideploy

Temuan: task "Limbah perlu koordinasi ..." untuk Desy tampil di Jadwal Task, tetapi Direktur
(hanya peran AOM sejak Reset peran) tidak bisa mengubahnya. `action_item_update` hanya menerima
Supervisor atau pemegang task, daftar Action item hanya memuat task milik sendiri, dan Jadwal
Task/Kanban/Prioritas/Tim tidak bertautan ke task.

Perbaikan: halaman `/direktur/task/<id>/` (`direktur.views.task_detail`, template
`direktur/task_detail.html`). Layanan baru di `core/task_services.py`: `can_manage_task`
(pembuat task atau AOM), `update_task`, `close_task` (penerima terbuka dikonfirmasi atas nama
penutup), `cancel_task`, `add_task_comment`. Judul task di Jadwal Task, Kanban, Prioritas, Tim,
dan Hari Ini (menunggu konfirmasi) menjadi tautan. Owner membuka detail tanpa tombol
(`direktur:task_detail` masuk `OWNER_ALLOWED`). `action_item_update` kini juga menerima
pembuat task dan AOM. Test `direktur/tests/test_task_detail.py` (10). Suite 596 lulus, 1 dilewati.

## Stok Apotek fase 1 (1 Oktober 2026) — di-commit dan dideploy 1 Okt (`e966da7`)

App `stok`: model `Produk`, `ProdukAlias`, `Unggahan`, `PosisiStok`, `PergerakanBulanan`,
`StatusPeriode`, `Parameter` (migrasi `stok 0001`). `stok/parser.py` membaca tiga ekspor .xls
Omnicare (`xlrd` dengan `ignore_workbook_corruption=True`); `stok/services.py` mengimpor,
menggabungkan unduhan terpotong, dan menjalankan 4 uji kelengkapan; `stok/hitung.py`
menghitung status, moving, kebutuhan, kelebihan, dan saran transfer saat halaman dibuka.
Halaman `/stok-apotek/` (tab Prioritas Order, Transfer, Impor Data; parameter; unggah
beberapa file sekaligus). Izin `core.permissions.can_view_stok`/`can_edit_stok`; `stok:index`
masuk `OWNER_ALLOWED`; menu Stok Apotek untuk Direktur, Owner, dan staf apotek.
Test `stok/tests/test_stok.py` (21) memakai ekspor asli 30 Sep di `stok/tests/fixtures/`;
status 48/90/14/133/67 dan 43/49/19/149/50, transfer 40 + 19, nilai rupiah sama dengan workbook.

Juga: `conftest.py` memakai storage static biasa dan hash password MD5 khusus test, sehingga
test tidak butuh `collectstatic` di clone baru dan suite penuh selesai sekitar 40 detik;
`xlrd` masuk `requirements.txt`; `docs/stok-apotek.md` (revisi PRD), `docs/README.md`,
`docs/peran-dan-akses.md`, `README.md` (jumlah test).

## Redefinisi peran — fase 5: summary harian dan lonceng notifikasi (30 September 2026) — di-commit 30 Sep, dideploy 1 Okt (`e966da7`)

`direktur/summary.py` menyusun summary (checklist Direktur per cabang, keputusan dan task hari itu,
status Permintaan Owner) dan `send_summary` menyimpannya sebagai snapshot `DailySummary` (kirim ulang
= perbarui, `send_count` naik), mencatat audit, dan memberi satu notifikasi belum-dibaca per tanggal
ke setiap Owner. Kartu **Summary hari ini untuk Owner** (pratinjau, catatan Direktur, tombol "Simpan
dan kirim summary ke Owner") di bawah Checklist Direktur; URL `direktur:summary_send` (hanya AOM).
Menu Direktur mendapat Summary Harian. Topbar: lonceng SVG dengan bulatan merah (99+), nama pengguna
disembunyikan di layar ≤600px. Test: `direktur/tests/test_summary.py`; 562 test lulus.

## Redefinisi peran — fase 4: halaman Owner (30 September 2026) — di-commit 30 Sep, dideploy 1 Okt (`e966da7`)

App baru `owner` (`/owner/`): Dashboard Owner (Permintaan Owner + isi Ringkasan yang sama lewat
`templates/direktur/_overview_body.html`), Permintaan baru/detail dengan catatan dua arah dan
notifikasi, Summary Harian per tanggal (membaca `direktur.DailySummary`; pengirimnya dibangun di
fase 5), Jadwal ringkas per cabang (bertugas, libur/cuti/di cabang lain, tombol jadwal penuh).
Owner mendarat di `/owner/`; `direktur:overview` tidak lagi terbuka untuk Owner. Migrasi:
`owner 0001`, `direktur 0004`, `checklists 0006` (label peran Owner yang tertinggal di fase 2). Test: `owner/tests/test_owner.py`; 552 test lulus. Panduan:
`docs/panduan-owner.md`.

## Redefinisi peran — fase 3: menu per peran dan penolakan server-side (30 September 2026) — di-commit 30 Sep, dideploy 1 Okt (`e966da7`)

`core/peran.py` menentukan satu tampilan per pengguna (Direktur, Owner, PIC, Staf, Admin): menu,
halaman pertama sesudah login (`/` dan login mengalihkan ke sana), dan halaman yang boleh dibuka.
`core.middleware.PersonaAccessMiddleware` menolak (403) halaman di luar tampilan: Owner hanya
Ringkasan/Tim/Kanban/Prioritas/Jadwal Task/Keputusan/Jadwal Jaga; staf tidak membuka Pembagian
Tugas tim, Laporan Operasional, Audit, halaman Direktur; Admin sistem hanya halaman akun,
konfigurasi, template, pengaturan klinik, jadwal. `next` pada login hanya diikuti bila URL internal.
Test: `core/tests/test_tampilan_peran.py`; 527 test lulus.

## Redefinisi peran — fase 2: peran standar dan Reset peran ke default (29 September 2026) — di-commit 30 Sep, dideploy 1 Okt (`e966da7`)

Rencana: `docs/KEBUTUHAN_REDEFINISI_PERAN.md`. `accounts/peran_standar.py` mendefinisikan akun
standar (Owner `yohanes`, Direktur Utama `jean` — peran OWNER yang sama —, Direktur Operasional
`hansen1`, Admin `superadmin`, dan staf dari `jadwal/staff.py`). Halaman Admin ▸ Pengguna ▸
**Reset peran ke default** (pratinjau → konfirmasi → terapkan; admin dan AOM). `seed_staf_cabang`
memakai logika yang sama. Label peran OWNER menjadi "Owner / Direktur Utama" (migrasi accounts 0008).
Test: `accounts/test_reset_peran.py`.

## Jadwal jaga, pembagian tugas, dan giliran tally bulanan (29 September 2026) — di-commit dan dideploy 29 Sep (`18dfcb6`, `1595435`)

Menjawab arahan product owner 29 Sep (10 butir) dan jadwal jaga Oktober 2026. Rincian:
`docs/jadwal-dan-giliran.md`.

- App baru `jadwal`: `DutyRoster` (masuk/perbantuan/off/cuti per orang per hari), `DutyPortion`,
  `DutyAssignment`. Halaman Jadwal Jaga, Pembagian Tugas (bulan + per hari, ganti pelaksana).
  Perintah `import_jadwal_jaga`, `seed_tugas_harian` (template checklist versi baru + porsi,
  `--susun YYYY-MM`), `seed_staf_cabang` (akun, peran, PIC dua cabang; `heny` → `heni`).
  Data Oktober: `jadwal/jadwal_bulanan/jadwal-2026-10.json` (dari warna sel PDF; kolom "Jumlah Masuk" PDF
  menulis Heni 25 dan Elvira 26, hitungan sel memberi 26 dan 27).
- Checklist harian baru per cabang: Opening (Lembar A), Piket kebersihan, Limbah, Closing
  (JD-FOB-F04 + permintaan 29 Sep), Apotek (hanya peran apotek). Butir membawa kode porsi;
  input baru `JAM`. Template lama role-specific dinonaktifkan (riwayat tetap).
- Giliran perawat: total tally bulanan gabung cabang, yang tertinggal ≥2 didahulukan sampai
  total −1, selebihnya urutan papan (▲▼ Koordinator Shift), serahkan pasien → sedang menangani,
  roster dari jadwal jaga, papan awal hari urut total terkecil; yang cuti bulan itu tanpa keistimewaan
  mengejar (ketetapan 30 Sep). Konfigurasi `nurse.catch_up_gap`.
- Pengaturan Klinik (nama, alamat, HP, jam, DPJ, APJ); migrasi data Jemur 14.00–22.00.
- Label: AOM → Direktur Operasional; fungsi PIC sesuai memo, tambah PIC Apotek. Menu gantt
  Direktur menjadi "Jadwal Task".
- Migrasi: accounts 0007, checklists 0005, core 0004–0005, direktur 0003, jadwal 0001,
  nurses 0003–0004, reports 0002.

## Dashboard Owner dan Direktur (29 September 2026) — di-commit dan dideploy (sampai `1595435`)

Menjawab `docs/KEBUTUHAN_CHECKLIST_DAN_DASHBOARD.md` dan arahan product owner 29 Sep: Owner melihat
gambaran luas (ada masalah atau tidak, keputusan menggantung, kebijakan yang ditetapkan), tidak
sedetail Direktur; dashboard = bird view + matriks Eisenhower + kanban, dengan halaman detail.

- `direktur/dashboard.py` (baru): `bird_view` (merah/kuning/hijau per cabang beserta alasan),
  `eisenhower` (tahap 1, tanpa migrasi; ambang `dashboard.urgent_hours` di `ClinicConfig`, bawaan
  48), `kanban` (kolom dari status `TaskAssignment`, baca saja).
- Model `direktur.Decision` (migration `direktur 0002`): register keputusan menggantung/ditetapkan/
  dibatalkan, pemutus, tenggat, penanda kebijakan berlaku. Ditulis AOM, dibaca Owner.
- Halaman baru (AOM + Owner): Ringkasan, Kanban, Prioritas, Keputusan (+detail). Halaman Tim kini
  juga dibaca Owner; tombol aksi hanya untuk AOM dan ditolak server untuk Owner.
- Label penghitung checklist Direktur: "sudah n/N · belum m" (A4).
- `core.DEFAULT_CONFIG` menambah `dashboard.urgent_hours` (tanpa migrasi).
- Test: `direktur/tests/test_dashboard.py`.
- Revisi Ringkasan (arahan product owner 29 Sep: "halaman utama jangan dipadatkan"): halaman
  utama kini hanya kotak ringkas — empat kuadran prioritas gabungan kedua cabang (angka + satu
  cuplikan task, diketuk membuka kuadran itu saja di `/direktur/prioritas/?kuadran=I..IV`), empat
  kotak (keputusan menggantung, kebijakan baru, menunggu konfirmasi, jadwal task), lalu
  infografik per cabang (meter checklist staf dan cek Direktur, chip lewat target/temuan/
  menunggu). Halaman baru **Jadwal** (`/direktur/jadwal/`): gantt task dari dibuat sampai target,
  jendela 7 hari ke belakang s.d. 21 hari ke depan; task lewat target memanjang sampai hari ini.
  `headline_counts()` dan `gantt()` di `direktur/dashboard.py`. Posisi bar ditulis tanpa format
  lokal (`{% localize off %}`) karena `LANGUAGE_CODE=id` memakai koma desimal.

## Peran Direktur Operasional (27 September 2026) — di-commit dan dideploy (sampai `1595435`)

Dikerjakan atas permintaan langsung product owner (Direktur Operasional), di luar urutan fase
integrasi AOM. Rencana dan keputusan: dokumen "Peran Direktur Operasional — Rencana Fitur"
(Opsi B dieksplorasi dulu; Opsi A dicatat sebagai alternatif).

- App baru `direktur` (migration `direktur 0001`): `AuditItem`/`AuditPoint` (butir checklist
  Direktur harian/mingguan/bulanan), `AuditCheck` (satu hasil per butir x cabang x periode,
  snapshot butir, task temuan), `DirectorNote` (catatan privat, arsip manual, dapat dijadikan task).
- Butir tidak memakai `checklists.ChecklistTemplate` karena template di sana diinstansiasi
  setiap hari operasional dan akan memunculkan butir mingguan/bulanan di checklist staf.
  Temuan memakai `core.ActionItem` lewat `create_task` (source `audit_direktur`).
- `core.task_services.create_task` menerima `source_type`/`source_id`/`source_label`
  opsional (bawaan tetap `manual`; pemanggil lama tidak berubah).
- Perintah `seed_audit_direktur` (idempoten, `--dry-run`, `--update`): 8 harian, 13 mingguan,
  1 bulanan dari dokumen checklist Direktur Rev 00 + keputusan 27 Sep (Kas, Kebersihan ruang,
  emergency kit bulanan). Teks butir Kas adalah usulan dari Pegangan PJ Area — perlu ditinjau.
- Halaman (semua `Role.AOM` server-side): Tim (`/direktur/`), Checklist Direktur, Catatan,
  Jadikan task, Task baru. Menu dan tombol di dashboard AOM ditambahkan.
- `AGENTS.md`: aturan "Codex satu-satunya agen" diganti aturan netral (keputusan product owner).
- Dokumentasi: `docs/panduan-direktur.md` (baru), `docs/README.md`, `docs/peran-dan-akses.md`.
- Test: `direktur/tests/test_direktur.py` (32 definisi, 35 kasus dengan parametrize).

Verifikasi (cloud workspace, Python 3.11.15, paket dari `.venv` desktop):

```text
python manage.py check                              # 0 issues
python -m pytest -q                                 # 387 passed, 1 skipped (baseline 352 passed, 1 skipped)
python manage.py makemigrations --check --dry-run   # No changes detected
migrate dari nol ke SQLite /tmp + seed_demo + seed_audit_direktur (dua kali) # berhasil, idempoten
```

Belum: QA manual mobile viewport; review manusia atas diff; commit/push; deployment.

## Integrasi AOM (status 26 September 2026)

Sumber rencana: `docs/AOM_MODULE_INTEGRATION_PLAN.md`.

### Ringkasan

Integrasi AOM telah melewati baseline/proteksi (Fase 0), organisasi dan akses (Fase 1),
task dan delegasi (Fase 2), checklist harian (Fase 3), laporan dan masukan (Fase 4), serta
UI dan usability (Fase 5, implementasi selesai). Fase 0–5 (termasuk desain checklist PDF dan
SDM multi-role) sudah DI-COMMIT dan DI-PUSH ke `origin/master` pada commit `0884b3f`
("feat: compact checklist and SDM role management"); working tree bersih. Semua pekerjaan
dilakukan di desktop Ubuntu/Linux dengan data dummy. Belum ada perubahan ke mini PC produksi
atau deployment. Approval eksplisit product owner untuk lanjut ke Fase 6 BELUM dikonfirmasi
di dokumen ini — verifikasi status approval sebelum memulai Fase 6.

### Matriks fase

| Fase | Status | Catatan |
|---|---|---|
| 0 — baseline dan perlindungan | Selesai | Baseline dicatat, fixture role/cabang ditambahkan, backup/restore dummy diverifikasi. |
| 1 — organisasi dan akses | Selesai | Role AOM/PIC, organisasi, fungsi PIC, capability, scope cabang, dan negative tests tersedia. |
| 2 — task dan delegasi | Selesai | Snapshot penerima, assignment individual/bersama, lifecycle submit/revision/confirm/cancel, histori, dan tests tersedia. |
| 3 — checklist harian | Implementasi selesai dan sudah di-commit (`0884b3f`) | Sesi opening/closing/anytime, template berversi (histori tidak berubah), target fungsi PIC/role, tindak lanjut idempoten, koreksi wajib beralasan dengan audit `CORRECTION`. |
| 4 — laporan dan masukan | Implementasi selesai dan sudah di-commit (`0884b3f`) | Model `Laporan`/`Masukan` ditambahkan di app `reports` yang sudah ada. Visibilitas `CABANG`/`RAHASIA_AOM`, status lifecycle, arsip beralasan+capability+audit, publikasi masukan AOM dengan snapshot immutable, dan negative tests kebocoran lintas cabang/rahasia. |
| 5 — UI dan usability | Implementasi selesai dan sudah di-commit (`0884b3f`) | Dashboard AOM/PIC/Admin ditambahkan (staf tetap seperti semula), aksi task 'Ajukan selesai'/'Konfirmasi selesai'/'Minta revisi'/'Ambil task bersama' sebagai view terpisah dengan proteksi server-side, halaman HTML laporan/masukan dengan filter status eksplisit di atas endpoint JSON Fase 4, PIC kosong menampilkan pesan ramah di view checklist (bukan crash). Approval eksplisit product owner untuk lanjut ke Fase 6 belum dikonfirmasi. |
| 6–8 | Belum dimulai | Rehearsal migrasi data AOM, release, observasi, dan cutover belum dikerjakan. |

## Implementasi yang sudah ada

- `Role.PIC` dan `Role.AOM`, `OrganizationAssignment`, `PicFunction`, `PicAssignment`.
- Capability sensitif untuk laporan rahasia, publikasi masukan, dan pengelolaan user.
- Pemeriksaan scope cabang pada layanan/views penting serta pembatasan assignee lintas cabang.
- `TaskAudienceSnapshot`, `TaskAssignment`, `TaskEvent`, mode `INDIVIDUAL`/`BERSAMA`,
  dan layanan task idempoten.
- Perintah `preview_aom_seed` yang hanya membaca dan menampilkan rencana seed.
- Migration `accounts 0004` dan `core 0002`.
- `checklists.ChecklistSession` (OPENING/CLOSING/ANYTIME), `ChecklistTemplate.session` +
  versi baru per sesi, `ChecklistTemplate.target_pic_function`/`target_role`/`assignment_mode`.
- Desain checklist PDF: role `APOTEKER` dan `ONLINE`, `audience_key` per template,
  `target_roles` jamak, run terpisah per template pada hari yang sama, serta item dengan
  `performer_roles` dan `verifier_roles` untuk penanda P/V dan handoff antarperan.
- `seed_demo` kini mengaktifkan 8 template role-specific dari PDF: Koordinator Shift (buka/tutup),
  Kasir (buka/tutup), Apoteker (buka/tutup), Online & Reservasi, dan Perawat/Terapis.
- `checklists.services.create_template_version()`: membuat versi baru tanpa memutasi versi
  lama; `ChecklistRun.template_snapshot` historis tidak berubah setelah edit template.
- `checklists.ChecklistFollowup`: penanda idempotensi tindak lanjut checklist bermasalah;
  `create_action_item_from_response()` sekarang memakai `core.task_services.create_task`
  (ActionItem + TaskAssignment + audience snapshot) dan aman dipanggil ulang (termasuk
  konkuren) tanpa menggandakan task.
- `audit.AuditAction.CORRECTION` ditambahkan; `checklists.services.record_response()`
  mewajibkan `reason` saat mengoreksi hasil yang sudah pernah dicek (result != BELUM) dan
  mencatat event `CORRECTION` terpisah dari `UPDATE` biasa.
- Migration `audit 0002` dan `checklists 0002`.
- `audit.AuditAction.PUBLISH` dan `audit.AuditAction.ARCHIVE` ditambahkan (Fase 4, mengikuti
  precedent `CORRECTION` — additive only). Migration `audit 0003`.
- `reports.Laporan`/`reports.LaporanUpdate`: laporan `CABANG` (satu cabang) dan `RAHASIA_AOM`
  (pelapor + AOM), status `OPEN`/`UNDER_REVIEW`/`RESOLVED`/`CLOSED`/`ARCHIVED`, arsip soft-delete
  wajib alasan + capability + audit `ARCHIVE`.
- `reports.Masukan`/`reports.MasukanPublication`: masukan privat (pengirim + AOM), publikasi AOM
  ke cabang dengan snapshot isi immutable (`title_snapshot`/`description_snapshot`/`source_version`)
  agar edit setelah publikasi tidak mengubah histori yang sudah terbit — pola sama dengan
  `checklists.services.create_template_version()`/`TaskAudienceSnapshot`.
- `core/permissions.py`: `can_view_laporan`, `can_create_laporan`, `can_archive_laporan`,
  `can_view_masukan`, `can_publish_masukan`, `can_view_published_masukan`, `can_archive_masukan`
  ditambahkan mengikuti pola `can_view_restricted_issue` yang sudah ada untuk app `issues`.
- `reports/services.py` (baru): `create_laporan`, `visible_laporan_queryset`,
  `change_laporan_status`, `archive_laporan`, `log_confidential_access`, `create_masukan`,
  `visible_masukan_queryset`, `publish_masukan`, `archive_masukan` — semua otorisasi
  server-side, tidak ada queryset tak terbatas yang dikirim ke view.
- `reports/views.py`, `reports/urls.py`, `reports/admin.py`: endpoint JSON (Fase 4) untuk
  create/list/detail/status/archive laporan dan create/list/detail/publish/archive masukan;
  direct-URL access diperiksa server-side. Fase 5 menambah halaman HTML di atas layanan yang
  sama (lihat bagian Fase 5 di bawah).
- Migration `reports/migrations/0001_initial.py` (app `reports` sudah ada sebelumnya untuk
  laporan operasional/ekspor CSV — Fase 4 menambah model baru di app yang sama).
- `reports/tests/` (paket): `test_laporan.py` (19 test: create/status/archive/queryset),
  `test_masukan.py` (13 test: create/publish/snapshot immutability/archive/negative HTTP),
  `test_confidentiality.py` (7 test: gate kebocoran RAHASIA_AOM lewat direct URL/list, lintas
  cabang, lintas visibility CABANG), `test_report_pages.py` (Fase 5, 9 test: halaman HTML
  laporan/masukan, filter status, direct-URL access negatif).
- Dokumentasi peran, arsitektur, README, dan rencana integrasi telah diperbarui.

### Fase 5 — UI dan usability (baru)

- `core/task_services.py`: `_can_review_task` diganti nama publik `can_review_assignment`
  (alias lama dipertahankan) agar dapat dipakai view layer untuk menentukan siapa yang boleh
  melihat tombol konfirmasi/revisi tanpa mengulang logika otorisasi.
- `core/views.py`: `action_items` sekarang menyusun `rows` per action item berisi
  `my_assignment`, `can_claim`, `can_submit`, `review_assignments` (assignment berstatus
  SUBMITTED yang boleh direview user ini). View baru `assignment_claim`, `assignment_submit`,
  `assignment_confirm`, `assignment_revision`, `assignment_cancel` — masing-masing memanggil
  fungsi `core.task_services` yang sudah ada (claim_shared_task/submit_assignment/
  confirm_assignment/request_revision/cancel_assignment); `PermissionDenied` dari service
  TIDAK ditangkap di view sehingga tetap menjadi 403 asli (bukan pesan flash yang
  menyembunyikan penolakan). `dashboard` view menambah context per role: `is_aom`/`is_pic`/
  `is_admin` plus data role-spesifik (lihat di bawah).
- `core/urls.py`: lima route baru `assignment/<pk>/ambil|ajukan|konfirmasi|revisi|batal/`.
- `templates/core/action_items.html`: tombol `Ajukan selesai` (penerima) dan
  `Konfirmasi selesai`/`Minta revisi` (reviewer) adalah form terpisah dengan label berbeda,
  tidak pernah tombol yang sama dipakai ulang untuk aksi berbeda.
- `templates/core/dashboard.html`: tiga section baru — "Ringkasan AOM" (assignment SUBMITTED
  lintas cabang menunggu konfirmasi AOM + shortcut ke laporan rahasia/masukan menunggu),
  "Ringkasan PIC" (assignment SUBMITTED dari task yang dibuat PIC ybs. + fungsi PIC aktif +
  jumlah template checklist yang menargetkan fungsi tsb.), "Ringkasan Admin" (shortcut kelola
  user/template). Section hanya tampil sesuai predikat role; staf biasa tidak melihat section
  tambahan apa pun (dashboard tetap seperti Fase 0-4).
- `reports/views.py`, `reports/urls.py`: empat view HTML baru — `laporan_page` (list + filter
  status via `<select>`, form buat laporan), `laporan_page_detail` (detail + ubah status/arsip,
  akses diperiksa lewat `can_view_laporan` yang sama dengan endpoint JSON), `masukan_page`
  (list + filter aktif/diarsipkan, form buat masukan), `masukan_page_detail` (detail +
  publikasi AOM + arsip). Semua dibangun di atas `visible_laporan_queryset`/
  `visible_masukan_queryset`/`create_laporan`/`archive_laporan`/dst. yang sudah ada dari
  Fase 4 — tidak ada query baru yang melewati service layer.
- `templates/reports/laporan_list.html`, `laporan_detail.html`, `masukan_list.html`,
  `masukan_detail.html` (baru): filter status eksplisit (`<select>` mengikuti pola
  `templates/issues/list.html`/`templates/core/action_items.html`), status ARCHIVED/CLOSED
  tetap terlihat lewat filter bukan disembunyikan permanen.
- `templates/checklists/templates.html`: menampilkan sesi, mode assignment, dan target
  (fungsi PIC/role) template secara eksplisit — sebelumnya field-field ini (Fase 3) tidak
  punya representasi UI sama sekali.
- `templates/base.html`: dua link nav baru "Laporan Saya" dan "Masukan Saya" menuju halaman
  HTML Fase 5 (endpoint JSON Fase 4 tetap ada, tidak dihapus/diubah).
- PIC/fungsi kosong: `checklists.services.resolve_followup_audience` dan
  `core.task_services.resolve_task_recipients` SUDAH melempar `ValidationError` pesan jelas
  sejak Fase 1–3; Fase 5 membuktikan lewat test bahwa VIEW (`checklists:make_action`) yang
  memicu jalur tersebut menampilkan pesan itu lewat Django messages (redirect + flash),
  bukan HTTP 500 — lihat `checklists/tests/test_empty_pic_ui.py`.
- Test baru: `core/tests/test_task_actions_ui.py` (7 test — submit/confirm/revision via view,
  direct URL negatif, label tombol tidak tertukar), `core/tests/test_dashboard_roles.py`
  (5 test — dashboard per role + negative unauthenticated), `reports/tests/test_report_pages.py`
  (9 test — halaman HTML laporan/masukan, filter, direct-URL negatif),
  `checklists/tests/test_empty_pic_ui.py` (1 test — pesan ramah PIC kosong di view).
- Tidak ada model/migration baru untuk Fase 5 (`makemigrations --check --dry-run` tetap
  "No changes detected" sebelum dan sesudah).

## Bukti verifikasi

Lingkungan test aktif menggunakan `.venv` dengan Python 3.11.16. Python 3.14 tersedia di
mesin, tetapi lingkungan proyek yang terbukti stabil untuk suite saat ini adalah `.venv`.

Perintah terakhir yang lulus (setelah Fase 5, sebelum commit):

```text
.venv/bin/python manage.py check                              # System check: 0 issues
.venv/bin/python -m pytest -q --tb=short                      # 333 passed
.venv/bin/python manage.py makemigrations --check --dry-run   # No changes detected
git diff --check                                              # tidak ada whitespace error
```

**Update 26 September 2026 — pasca-commit `0884b3f`:** diverifikasi ulang secara independen
pada HEAD saat ini (working tree bersih, sinkron `origin/master`):

```text
.venv/bin/python manage.py check                              # System check: 0 issues
.venv/bin/python -m pytest -q --tb=short                      # 336 passed (naik dari 333,
                                                                # test SDM multi-role baru)
.venv/bin/python manage.py makemigrations --check --dry-run   # No changes detected
git status --short                                            # kosong
```

Migration rehearsal khusus untuk migration baru di commit `0884b3f`
(`accounts/migrations/0005_*`, `checklists/migrations/0003_*`/`0004_*`) belum diulang
secara independen pasca-commit pada sesi ini.

Diverifikasi ulang pada 20 September 2026 setelah desain checklist PDF diterapkan. Rincian jumlah
test per file (`pytest --collect-only -q`,
hanya berkas AOM Fase 3–5 dan modul terdekat; sisanya adalah suite Fase 0–2 dan modul klinik lama):

| Berkas test | Jumlah |
|---|---:|
| `checklists/tests/test_correction_audit.py` | 5 |
| `checklists/tests/test_cross_clinic_access.py` | 4 |
| `checklists/tests/test_pdf_seed.py` | 3 |
| `checklists/tests/test_empty_pic_ui.py` | 1 |
| `checklists/tests/test_followup_idempotency.py` | 6 |
| `checklists/tests/test_opening.py` | 9 |
| `checklists/tests/test_template_sessions.py` | 7 |
| `core/tests/test_concurrency_and_privacy.py` | 11 |
| `core/tests/test_dashboard_roles.py` | 5 |
| `core/tests/test_day_state.py` | 9 |
| `core/tests/test_documentation.py` | 73 |
| `core/tests/test_pilot_readiness.py` | 15 |
| `core/tests/test_task_actions_ui.py` | 7 |
| `core/tests/test_task_delegation.py` | 10 |
| `issues/tests.py` | 16 |
| `nurses/tests.py` | 12 |
| `queueing/tests.py` | 13 |
| `reports/tests/test_confidentiality.py` | 7 |
| `reports/tests/test_laporan.py` | 19 |
| `reports/tests/test_masukan.py` | 15 |
| `reports/tests/test_report_pages.py` | 9 |

Fase 5 sebelumnya tidak menyertakan migration rehearsal karena hanya UI-layer. Desain checklist
PDF menambah migration accounts/checklists; migration rehearsal SQLite baru di `/tmp` sudah
berhasil sampai migration terbaru.

**Batasan pengujian Fase 5 yang jujur dilaporkan:** repository ini tidak memiliki
infrastruktur browser/Selenium/Playwright. "UI test" berarti Django test Client (`self.client`)
terhadap view dan rendering template — bukan browser sungguhan. Karena itu viewport mobile,
navigasi keyboard, dan kondisi koneksi lambat (disebut di plan section 14) TIDAK dapat
dibuktikan dengan test otomatis di suite ini dan tetap menjadi item QA manual. Yang otomatis
dibuktikan: dashboard per role, label tombol yang tidak tertukar, filter status data
selesai/arsip, dan direct-URL access 403 untuk pihak tak berwenang.

## Working tree (26 September 2026)

Posisi terbaru ada di bagian **Posisi terakhir** di atas. Perubahan Fase 0–5 SUDAH DI-COMMIT (`0884b3f`) dan DI-PUSH ke `origin/master`; working tree
per 26 September 2026 bersih (`git status --short` kosong). Bagian di bawah ini adalah
riwayat berkas baru/berubah per fase seperti tercatat saat implementasi (sekarang bagian dari
sejarah commit, bukan lagi perubahan pending). Berkas baru/berubah utama untuk Fase 3:

- `checklists/models.py`: `ChecklistSession`, field sesi pada `ChecklistTemplate`/`ChecklistRun`,
  field target fungsi PIC/role/assignment_mode pada template, model `ChecklistFollowup`.
- `checklists/services.py`: `create_template_version()`, `resolve_followup_audience()`,
  `record_response()` dengan parameter `reason` untuk koreksi, `create_action_item_from_response()`
  idempoten via `core.task_services.create_task`.
- `checklists/views.py`: `save_response` meneruskan `alasan` dari POST ke `record_response`.
- `checklists/admin.py`: menampilkan kolom sesi, registrasi `ChecklistFollowup`.
- `audit/models.py`: tambahan `AuditAction.CORRECTION`.
- `checklists/migrations/0002_aom_fase3_checklist.py`, `audit/migrations/0002_aom_fase3_checklist.py`.
- `accounts/migrations/0005_alter_userrole_role.py` dan
  `checklists/migrations/0003_remove_checklistrun_uniq_run_day_area_session_and_more.py`.
- `checklists/tests/` (paket baru, `checklists/tests.py` lama dipindah menjadi
  `checklists/tests/test_opening.py` tanpa perubahan isi):
  - `test_template_sessions.py`
  - `test_followup_idempotency.py`
  - `test_correction_audit.py`

Berkas sisa Fase 0–2 (lihat riwayat sebelumnya) tidak diubah lebih lanjut.

Berkas baru/berubah utama untuk Fase 4 (laporan dan masukan):

- `reports/models.py`: `Laporan`, `LaporanUpdate`, `Masukan`, `MasukanPublication` ditambahkan
  ke app `reports` yang sudah ada (sebelumnya hanya laporan operasional/ekspor CSV).
- `reports/services.py` (baru): logika visibilitas, status, publikasi, dan arsip — semua
  otorisasi server-side.
- `reports/views.py`, `reports/urls.py`, `reports/admin.py`: endpoint JSON untuk laporan dan
  masukan ditambahkan di akhir file (fungsi `index`/`export_csv` yang sudah ada sebelumnya
  tidak diubah oleh Fase 4; `active_clinic(request.user)` sudah menjadi perbaikan pra-existing
  di working tree sebelum Fase 4 dimulai).
- `core/permissions.py`: tujuh fungsi predikat baru untuk laporan/masukan (lihat di atas).
- `audit/models.py`: `AuditAction.PUBLISH`, `AuditAction.ARCHIVE` (additive, precedent `CORRECTION`).
- `reports/migrations/0001_initial.py`, `audit/migrations/0003_alter_auditevent_action.py`.
- `reports/tests/` (paket baru): `test_laporan.py`, `test_masukan.py`, `test_confidentiality.py`.

Berkas baru/berubah utama untuk Fase 5 (UI dan usability) — daftar lengkap dengan deskripsi
satu baris ada di bagian "Implementasi yang sudah ada → Fase 5" di atas; ringkasan file:

- Diubah: `core/task_services.py`, `core/views.py`, `core/urls.py`,
  `templates/core/action_items.html`, `templates/core/dashboard.html`,
  `templates/checklists/templates.html`, `templates/base.html`, `reports/views.py`,
  `reports/urls.py`, `README.md` (angka jumlah test).
- Baru: `core/tests/test_task_actions_ui.py`, `core/tests/test_dashboard_roles.py`,
  `reports/tests/test_report_pages.py`, `checklists/tests/test_empty_pic_ui.py`,
  `templates/reports/laporan_list.html`, `templates/reports/laporan_detail.html`,
  `templates/reports/masukan_list.html`, `templates/reports/masukan_detail.html`.
- Baru: `checklists/tests/test_pdf_seed.py` untuk memastikan template dan snapshot role dari
  sumber PDF dibuat idempoten.
- Tidak ada file model/migration yang ditambah atau diubah.

Berkas-berkas di atas SUDAH ter-commit di `0884b3f` (per 26 September 2026). Sebelum melakukan
commit baru berikutnya, tetap tinjau seluruh `git diff`, cek migration, ulangi test, dan
pastikan tidak ada secret, database, backup, media privat, atau data pasien yang ikut
ter-stage.

## Remediation audit keamanan

- `checklists/views.py` sekarang memvalidasi scope cabang untuk detail run, simpan respons,
  pembuatan kerusakan, pembuatan task, dan review checklist melalui direct URL.
- `checklists/services.py` mengulang pemeriksaan role dan scope cabang agar service tidak dapat
  dipanggil lintas cabang dari jalur non-HTTP.
- `reports/services.py` membatasi publisher berbasis capability ke cabang aktif dalam scope-nya
  dan menolak target cabang tidak aktif.
- Test baru: `checklists/tests/test_cross_clinic_access.py` dan dua test validasi target di
  `reports/tests/test_masukan.py`.

## Langkah berikutnya yang disetujui rencana

Fase 5 (UI dan usability) sudah diimplementasikan, lulus test desktop, DAN SUDAH DI-COMMIT/
DI-PUSH (`0884b3f`). Belum lanjut ke Fase 6. Yang masih perlu sebelum lanjut:

1. Review manusia atas diff dan bukti pengujian yang sudah di-commit (Fase 0–5).
2. Approval product owner untuk melanjutkan ke Fase 6 (migration rehearsal data AOM) — belum
   dikonfirmasi di dokumen ini.
3. Deferral eksplisit dari scope Fase 4 (masih berlaku, belum dikerjakan di Fase 5):
   - Attachment/lampiran untuk laporan dan masukan belum diimplementasikan (plan 9/11
     menyebut lampiran aman sebagai bagian Fase 4, tetapi deferred agar tidak memperluas
     scope melebihi apa yang bisa dibuktikan dengan test dalam waktu yang tersedia).
   - Pencarian teks bebas dan counter/dashboard laporan-masukan belum dibuat secara khusus
     (dashboard Fase 5 menampilkan counter sederhana untuk AOM saja, berbasis
     `visible_laporan_queryset`/`visible_masukan_queryset`; pencarian teks bebas belum ada).
   - Notifikasi publikasi masukan mengirim ke semua staf aktif cabang tujuan tanpa dedupe
     lintas-publikasi berulang di luar jendela 10 menit `notify_user`; cukup untuk MVP,
     belum diuji untuk volume besar.
4. Deferral eksplisit dari scope Fase 5:
   - Mobile viewport, navigasi keyboard, dan simulasi koneksi lambat (plan section 14)
     TIDAK dapat dibuktikan dengan Django test Client — tetap manual QA, belum dilakukan.
   - Checklist template session/target belum punya form buat/edit lewat UI (tetap lewat
     Django admin seperti sebelumnya) — Fase 5 hanya menambah tampilan baca yang menjelaskan
     field tsb., bukan form create/update; ini konsisten dengan batas eksplisit Fase 3.
   - Action item "Batal" (`assignment_cancel`) sudah punya view+URL tapi belum punya tombol
     di `templates/core/action_items.html` (cakupan test hanya di level view langsung);
     dapat ditambahkan di iterasi UI berikutnya bila product owner memintanya.

## Approval yang masih diperlukan

- Review bukti dan persetujuan untuk melanjutkan dari Fase 5 ke Fase 6.
- Persetujuan owner atas identitas/penugasan PIC sebelum seed atau import akun nyata.
- Persetujuan terpisah sebelum commit/push rilis, migration rehearsal data AOM, deployment,
  atau penghentian AOM standalone.
