# Kebutuhan Redefinisi Seluruh Peran

Disusun 29 September 2026 dari arahan product owner (Direktur Operasional), sesudah memeriksa
tampilan Owner di ops.joderma.id. Menggantikan `KEBUTUHAN_ROLE_OWNER.md` (draf pertama
di hari yang sama, hanya tentang Owner).

**Status 30 September 2026:** fase 2 (definisi peran dan tombol Reset peran ke default), fase 3
(menu per peran, halaman pertama sesudah login, penolakan server-side), fase 4 (halaman Owner), dan
fase 5 (kirim summary dan lonceng notifikasi) sudah dibangun dan di-commit, belum dideploy.
Pekerjaan dijeda sebelum fase 6; sisa pekerjaan dan roadmap ada di `current-progress.md`. Fase berikutnya menunggu persetujuan. Mengikuti `AGENTS.md`, pekerjaan
di bawah dikerjakan per fase, dimulai dari pemeriksaan read-only dan baseline test, dan berhenti
pada approval gate.

## Prinsip

1. **Setiap peran adalah entitas sendiri.** Tampilan satu peran tidak boleh berupa tambal
   sulam dari peran lain (misalnya halaman Direktur dengan tombol disembunyikan untuk Owner).
   Navigasi dan halaman utama dirancang per peran.
2. **Tampilkan hanya yang dikerjakan atau diputuskan peran itu.** Owner melihat keadaan dan
   keputusan. Staf melihat tugasnya sendiri. PIC melihat dan mengatur timnya. Direktur
   Operasional melihat semuanya.
3. **Staf dibuat sesederhana mungkin.** Yang tampil adalah yang harus ia kerjakan hari itu dan
   jadwalnya sendiri, bukan seluruh tim.
4. **Menyembunyikan menu bukan kontrol akses** (`AGENTS.md`). Setiap halaman yang tidak
   milik suatu peran juga ditolak di server (403), dengan test negatif.
5. **Tampilan dipisah, perhitungan tidak digandakan.** Angka yang sama (lewat target,
   keputusan menggantung, status cabang) dihitung oleh fungsi yang sama untuk semua peran,
   supaya Owner dan Direktur tidak melihat angka berbeda untuk hal yang sama.

## Masalah sekarang

Semua peran memakai satu navigasi (`templates/base.html`) yang dikurangi item demi item, dan
semua peran mendarat di "Hari Ini" sesudah login. Akibatnya Owner melihat sekitar 15 menu
(Hari Ini, Ringkasan, Kanban, Prioritas, Jadwal Task, Keputusan, Tim, Checklist Saya, Jadwal
Jaga, Pembagian Tugas, Laporan Operasional, Laporan Saya, Masukan Saya, Audit, Pengaturan
Klinik), dan staf biasa melihat checklist dan jadwal seluruh tim.

## Peran yang dituju

### Owner dan Direktur Utama

Satu peran, satu tampilan (`OWNER`). Akun: `yohanes` (Owner) dan `jean` (Direktur Utama).

| Menu utama | Isi |
|---|---|
| **Dashboard** | Halaman pertama sesudah login. Isinya Ringkasan yang sekarang (disetujui "sudah cukup bagus"): kuadran prioritas gabungan dua cabang, keputusan menggantung, kebijakan baru, menunggu konfirmasi, kartu per cabang. **Ditambah Permintaan Owner** (lihat di bawah) |
| **Keputusan** | Register keputusan dan kebijakan, hanya baca |
| **Summary Harian** | Summary of the day dari Direktur Operasional, bisa dipilih per tanggal |
| **Jadwal** | Pilih cabang Jemur atau Citraland; tampil siapa saja yang bertugas hari ini; tombol **Lihat jadwal penuh** membuka grid bulanan (hanya baca) |

- Tim, Prioritas, Kanban, dan Jadwal Task dibuka dari dalam dashboard, **bukan** menu utama.
- **Tidak** untuk Owner: Hari Ini, Checklist Saya, Pembagian Tugas, Audit, Laporan
  Operasional, Laporan Saya, Masukan Saya, Pengaturan Klinik, Kas.
- Owner tetap hanya baca untuk data operasional. Satu-satunya yang ia buat adalah
  **Permintaan Owner**.

#### Permintaan Owner

Menjawab bagian B2 `KEBUTUHAN_CHECKLIST_DAN_DASHBOARD.md` (sekarang diputuskan: masuk).

- Owner menulis permintaan. Penerimanya **hanya** Direktur Operasional; Owner tidak menugaskan
  staf langsung.
- Direktur memecah permintaan menjadi satu atau beberapa task. Progres permintaan dibaca dari
  task turunannya.
- Di dashboard Owner tampil: apa saja yang diminta, progresnya sampai mana, dan kapan targetnya.
  Rinciannya dibuka di Gantt (Jadwal Task), satu baris per permintaan dan task turunannya.
- Tujuannya supaya Owner ingat apa yang pernah ia minta tanpa bertanya.

### Direktur Operasional

Akun: `hansen1` (peran `AOM`). Semua halaman yang ada sekarang tetap, ditambah:

- **Satu tombol di Checklist Direktur: "Simpan dan kirim summary ke Owner".** Menyimpan hasil
  cek sekaligus menyusun **summary of the day**. Bisa ditekan lagi di hari yang sama untuk
  memperbarui summary; Owner melihat versi terakhir beserta jamnya.
- Isi summary, disusun otomatis kecuali catatan:
  1. hasil checklist Direktur hari itu per cabang: yang sesuai, temuan, dan yang belum dicek;
  2. **catatan Direktur**, satu kotak teks bebas yang ditulis sebelum menekan tombol;
  3. keputusan yang dicatat atau ditetapkan dan task yang dibuat atau selesai hari itu;
  4. status setiap Permintaan Owner yang masih berjalan.
- Menerima Permintaan Owner dan memecahnya menjadi task.

### PIC

Koordinator Shift, PIC Kasir, Koordinator Layanan Daring, PJ Kebersihan dan Sterilitas, PIC
Apotek. PIC **dapat melihat dan mengatur** tim dalam fungsinya, di cabangnya: pembagian tugas
(ganti pelaksana), giliran perawat, jadwal istirahat, roster, dan jadwal tim, **sesuai porsi
fungsinya** (keputusan no. 3).

### Staf

Perawat, bidan, apoteker, dan asisten apoteker yang tidak memegang fungsi PIC.

| Menu | Isi |
|---|---|
| **Tugas hari ini** | Checklist harian yang **ditugaskan kepadanya** sebagai tampilan bawaan: butir porsinya dari Pembagian Tugas, itu yang ia periksa dan kerjakan |
| **Jadwal saya** | Jadwal jaga dirinya sendiri, bukan grid tim |
| **Istirahat saya** | Jadwal istirahat dirinya sendiri |
| **Tindakan saya** | Untuk perawat: giliran dan tally dirinya (hari ini dan total bulan ini), bukan papan seluruh tim |

Ditambah **Komplain, Masukan, Kerusakan** (tetap ada), dan **Kas** hanya pada hari ia
ditugaskan sebagai kasir. Order Online tetap untuk peran layanan daring dan apotek.

### Admin

Akun: `superadmin`. Pengguna, konfigurasi, template, ditambah:

- **Tombol "Reset peran ke default"** di halaman Admin, supaya setelah sinkron ke mini PC
  cukup menekan satu tombol, tanpa perintah terminal.
  - Mengembalikan **peran, cabang, dan fungsi PIC** semua akun yang dikenal ke definisi
    standar di kode: staf dua cabang (`jadwal/staff.py`), `yohanes` dan `jean` sebagai Owner,
    `hansen1` sebagai Direktur Operasional, `superadmin` sebagai Admin.
  - Akun standar yang belum ada dibuat dengan password `klinik123` dan wajib ganti saat login.
  - **Tidak** mengubah password akun yang sudah ada, dan tidak menyentuh data (task, catatan,
    checklist, audit).
  - Akun di luar daftar standar (mis. `AOM_HS`) tidak disentuh.
  - Menampilkan pratinjau perubahan lebih dulu, lalu konfirmasi. Semua perubahan tercatat di
    audit.
- Akun `jean` belum ada di laptop dan dibuat ulang di mini PC lewat tombol ini.

## Keputusan atas pertanyaan terbuka (29 September 2026)

| # | Perkara | Keputusan |
|---|---|---|
| 1 | Target Permintaan Owner | **Tanggal target ditulis Owner saat membuat permintaan.** Revisi tanggal atau target yang tidak terpenuhi dibicarakan Direktur langsung dengan Owner beserta penjelasannya, lewat WhatsApp atau ditulis di web app (catatan pada permintaan). Aplikasi tidak perlu alur tolak atau kembalikan |
| 2 | Pemberitahuan summary | **Notifikasi sederhana di kanan atas: ikon lonceng dengan bulatan merah berisi jumlah notifikasi yang belum dibaca.** Berlaku juga untuk pemberitahuan lain (mis. Permintaan Owner diperbarui) |
| 3 | Wewenang PIC | **PIC mengatur sesuai porsi fungsinya.** Pembagian tugas yang berjalan sekarang sudah memuaskan dan dipakai apa adanya sebagai fase uji coba |
| 4 | Menu lapor staf | **Komplain, Masukan, dan Kerusakan tetap ada** untuk staf |
| 5 | Kas untuk staf | **Menu Kas hanya muncul pada hari ia ditugaskan sebagai kasir** (porsi "Kasir hari ini" pada Pembagian Tugas) |
| 6 | Isi "Tugas hari ini" | **Tugas hari ini = checklist yang harus ia kerjakan.** Bukan seluruh checklist: cukup daftar pendek butir porsinya hari itu |

## Urutan kerja

1. **Baseline:** pemeriksaan read-only dan seluruh test lulus.
2. **Definisi peran dan tombol Reset peran ke default** (termasuk akun `jean`). Ini lebih dulu
   karena fase lain bergantung pada peran yang benar.
3. **Navigasi per peran dan pengalihan sesudah login**, beserta penolakan server-side dan
   test negatif per peran. *Selesai 30 September 2026:* `core/peran.py`,
   `core/middleware.py`, `core/tests/test_tampilan_peran.py`; rincian di
   `peran-dan-akses.md` ▸ Tampilan per peran. Summary Harian belum ada di menu Owner (fase 4–5);
   staf masih memakai halaman yang ada (Hari Ini, Checklist Saya, Jadwal Jaga) sampai fase 7.
4. **Owner:** Dashboard, Keputusan, Jadwal sederhana, Summary Harian. *Selesai 30 September 2026:*
   app `owner` (`/owner/`), model `OwnerRequest` dan `OwnerRequestNote`, model
   `direktur.DailySummary`; panduan di `panduan-owner.md`. Sisi Owner Permintaan Owner sudah
   lengkap (buat, target, progres dari task turunan, catatan dua arah dengan notifikasi). Sisi
   Direktur (memecah permintaan menjadi task, baris Gantt) di fase 6; tombol kirim summary di fase 5.
5. **Direktur:** tombol simpan dan kirim summary, dan riwayat summary per hari. *Selesai 30 September
   2026:* `direktur/summary.py`, kartu di bawah Checklist Direktur, menu Summary Harian untuk
   Direktur, lonceng notifikasi dengan bulatan merah (keputusan no. 2).
6. **Permintaan Owner** dari ujung ke ujung, termasuk baris Gantt. *Selesai 4 Oktober 2026:* memecah
   permintaan lewat Inbox (Paket B); baris Gantt per permintaan, lihat `current-progress.md` ▸ Fase 6.
7. **Staf:** Tugas hari ini, Jadwal saya, Istirahat saya, Tindakan saya. *Selesai di kode 4 Oktober
   2026:* lihat `current-progress.md` ▸ Riwayat ▸ Fase 7.
8. **PIC:** lihat dan atur tim sesuai jawaban pertanyaan no. 3. *Selesai di kode 4 Oktober 2026:*
   ganti pelaksana porsi per fungsi PIC, lihat `current-progress.md` ▸ Fase 8.
9. **Uji tampilan** per peran (desktop dan HP), dicek bersama product owner sebelum commit.
