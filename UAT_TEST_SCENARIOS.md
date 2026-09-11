# UAT Test Scenarios — JoDerma Staff Ops

**Versi:** 1.0
**Tanggal:** 11 September 2026
**Cara pakai:** Selama pilot, isi kolom **Actual Result**, **Pass/Fail**, **Notes**, dan
**Severity** (hanya bila gagal) langsung di file ini. Setiap kegagalan wajib dicatat juga
di `UAT_ISSUE_REGISTER.md` dengan ID yang sama.

**Severity bila gagal:** Critical / High / Medium / Low — definisi ada di
`UAT_ISSUE_REGISTER.md` bagian 2.

**Konvensi ID:**
`OPN` pembukaan · `CSH` kas · `QUE` antrean · `NUR` giliran perawat · `BRK` jadwal
istirahat · `CMP` komplain · `SUG` masukan · `DMG` kerusakan · `SUP` review supervisor ·
`OWN` review owner/manajemen · `ADM` admin & konfigurasi · `RPT` laporan ·
`EXC` pengecualian/override · `SEC` keamanan & privasi.

**Prasyarat umum semua skenario:** peserta memakai akun pribadi masing-masing (bukan akun
bersama), perangkat terhubung Tailscale, dan aplikasi dibuka lewat hostname MagicDNS.

---

## 1. Pembukaan klinik (OPN)

### OPN-01 — Membuat sesi hari operasional

| Field | Isi |
|---|---|
| **Actor** | Staf operasional / front desk (siapa pun yang datang pertama) |
| **Precondition** | Belum ada sesi hari untuk tanggal hari ini |
| **Steps** | 1. Buka **Hari Ini**. 2. Tekan **Buat sesi hari ini**. |
| **Expected** | Sesi dibuat dengan status *Pembukaan berjalan*; checklist keempat area muncul otomatis dari template aktif; jumlah item sesuai template klinik |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | Catat jam berapa sesi dibuat |
| **Severity** | |

### OPN-02 — Mengisi checklist sampai selesai (uji waktu ≤10 menit)

| Field | Isi |
|---|---|
| **Actor** | Staf operasional + perawat (ruang klinis) |
| **Precondition** | OPN-01 selesai |
| **Steps** | 1. Buka **Pembukaan**. 2. Catat jam mulai. 3. Isi seluruh item di keempat area. 4. Catat jam selesai. |
| **Expected** | Semua item tersimpan dengan petugas dan waktu otomatis; progres mencapai 100%; **total waktu ≤10 menit** |
| **Actual** | Waktu aktual: ____ menit |
| **Pass/Fail** | |
| **Notes** | Bila >10 menit, catat item mana yang paling lama diisi dan mengapa |
| **Severity** | |

### OPN-03 — Item bermasalah wajib catatan

| Field | Isi |
|---|---|
| **Actor** | Staf operasional |
| **Precondition** | Checklist terbuka |
| **Steps** | 1. Pilih satu item, set hasil **Rusak**, kosongkan catatan, Simpan. 2. Isi catatan, Simpan lagi. |
| **Expected** | Langkah 1 ditolak dengan pesan Indonesia yang jelas ("Catatan wajib diisi bila hasil bukan OK"); langkah 2 berhasil |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | Apakah pesan errornya dipahami staf tanpa dijelaskan? |
| **Severity** | |

### OPN-04 — Item kuantitas dan deteksi di bawah minimum

| Field | Isi |
|---|---|
| **Actor** | Perawat |
| **Precondition** | Template punya item BHP bertipe jumlah dengan nilai minimum |
| **Steps** | 1. Isi jumlah aktual di bawah minimum, hasil **Tidak lengkap**, beri catatan. 2. Simpan. 3. Coba isi jumlah negatif. |
| **Expected** | Item ditandai di bawah minimum; jumlah negatif ditolak |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | Apakah nilai minimum di template sudah sesuai kenyataan stok klinik? |
| **Severity** | |

### OPN-05 — Turunan dari item bermasalah

| Field | Isi |
|---|---|
| **Actor** | Staf operasional |
| **Precondition** | Ada item berstatus Rusak dan item berstatus Tidak lengkap |
| **Steps** | 1. Pada item Rusak, tekan **Buat laporan kerusakan**. 2. Pada item Tidak lengkap, tekan **Buat tindak lanjut kekurangan**. |
| **Expected** | Tiket kerusakan bernomor `DMG-YYYYMMDD-NNN` terbuat dan tertaut ke item; action item terbuat dan muncul di daftar action item |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | |
| **Severity** | |

---

## 2. Kas, uang modal, dan kembalian (CSH)

### CSH-01 — Menghitung kas awal dengan rincian pecahan

| Field | Isi |
|---|---|
| **Actor** | Front desk/kasir (penghitung pertama) |
| **Precondition** | Sesi hari aktif; kasir punya izin kas |
| **Steps** | 1. **Kas ▸ Hitung kas awal**. 2. Isi jumlah lembar/koin per pecahan. 3. Isi uang modal diharapkan dan uang kembalian tersedia. 4. Simpan. |
| **Expected** | Total aktual terhitung otomatis dan benar; selisih = aktual − diharapkan; nama penghitung dan waktu tercatat |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | **OPEN DECISION terkait:** apakah "uang modal", "kas", dan "uang kembalian" memang tiga pos terpisah seperti di form ini? (lihat OWNER_DECISION_REVIEW D1) |
| **Severity** | |

### CSH-02 — Selisih kas wajib catatan

| Field | Isi |
|---|---|
| **Actor** | Front desk/kasir |
| **Precondition** | Form kas terbuka |
| **Steps** | 1. Buat total aktual berbeda dari diharapkan. 2. Simpan tanpa catatan. 3. Isi catatan, simpan lagi. |
| **Expected** | Langkah 2 ditolak; langkah 3 berhasil dan selisih tersimpan dengan penjelasan |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | |
| **Severity** | |

### CSH-03 — Dual-control: tidak boleh verifikasi hitungan sendiri

| Field | Isi |
|---|---|
| **Actor** | Front desk/kasir yang menghitung |
| **Precondition** | Kas sudah diajukan verifikasi oleh orang tersebut |
| **Steps** | 1. Buka **Review kas**. 2. Coba simpan verifikasi. |
| **Expected** | Ditolak: "Dual-control aktif: penghitung pertama tidak dapat memverifikasi hitungannya sendiri" |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | |
| **Severity** | |

### CSH-04 — Verifikasi oleh orang kedua

| Field | Isi |
|---|---|
| **Actor** | Front desk kedua **atau** supervisor (yang tidak menghitung) |
| **Precondition** | CSH-03 dilakukan |
| **Steps** | 1. Login sebagai orang kedua. 2. Buka **Review kas**. 3. Isi total hitung ulang. 4. Simpan verifikasi. |
| **Expected** | Verifikasi tersimpan; status menjadi *Sesuai* atau *Selisih*; riwayat menampilkan nama verifikator dan waktu; hitung ulang yang tidak cocok ditolak |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | Catat berapa lama proses ini memakan waktu di kondisi klinik ramai |
| **Severity** | |

### CSH-05 — Kas akhir dan koreksi pasca-verifikasi

| Field | Isi |
|---|---|
| **Actor** | Front desk + supervisor |
| **Precondition** | Hari operasional berjalan |
| **Steps** | 1. Sore hari, catat **kas akhir** dengan cara sama. 2. Verifikasi oleh orang kedua. 3. Supervisor melakukan koreksi dengan alasan. 4. Kasir mencoba melakukan koreksi. |
| **Expected** | Koreksi supervisor berhasil, status kembali menunggu verifikasi, nilai lama tetap terlihat di audit log; percobaan koreksi oleh kasir ditolak (403) |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | |
| **Severity** | |

---

## 3. Antrean pasien dan status pembayaran konsultasi (QUE)

### QUE-01 — Mendaftarkan pasien ke antrean

| Field | Isi |
|---|---|
| **Actor** | Front desk/kasir |
| **Precondition** | Sesi hari aktif |
| **Steps** | 1. **Antrean ▸ Tambah pasien**. 2. Isi nama tampilan, alias/inisial, jenis kunjungan. 3. Simpan. Ulangi untuk beberapa pasien nyata. |
| **Expected** | Nomor antrean urut dan unik per hari; status pembayaran default **Belum bayar**; entri muncul di papan |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | Apakah field yang diminta cukup, atau ada data yang biasa dicatat front desk tapi tidak ada tempatnya? |
| **Severity** | |

### QUE-02 — Status pembayaran dan aturan keep nomor

| Field | Isi |
|---|---|
| **Actor** | Front desk/kasir |
| **Precondition** | Ada pasien berstatus Belum bayar |
| **Steps** | 1. Ubah status ke **Sudah bayar** setelah pasien membayar. 2. Perhatikan badge di papan. |
| **Expected** | Badge menampilkan "Sudah bayar · keep nomor"; riwayat pembayaran mencatat pelaku dan waktu |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | **OPEN DECISION D3:** apakah hanya *Sudah bayar* dan *Dibebaskan* yang menahan nomor? |
| **Severity** | |

### QUE-03 — Alur status antrean sampai selesai

| Field | Isi |
|---|---|
| **Actor** | Front desk/kasir |
| **Precondition** | Pasien terdaftar |
| **Steps** | Jalankan: Check-in → Menunggu → Dipanggil → Dilayani → Selesai. Lalu coba lompat status (mis. Dipesan langsung ke Selesai). |
| **Expected** | Urutan normal berjalan; lompatan status ditolak dengan pesan jelas |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | Apakah urutan status ini sesuai alur kerja nyata front desk? |
| **Severity** | |

### QUE-04 — Pembatalan, no-show, dan refund wajib alasan

| Field | Isi |
|---|---|
| **Actor** | Front desk/kasir |
| **Precondition** | Ada pasien menunggu |
| **Steps** | 1. Tandai satu pasien **No-show** tanpa alasan. 2. Isi alasan, ulangi. 3. Ubah pembayaran ke **Refund** tanpa alasan lalu dengan alasan. |
| **Expected** | Tanpa alasan ditolak; dengan alasan berhasil dan tercatat sebagai event historis |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | **OPEN DECISION D4:** berapa lama toleransi keterlambatan sebelum no-show? Saat ini 15 menit |
| **Severity** | |

### QUE-05 — Layar bersama menyamarkan identitas

| Field | Isi |
|---|---|
| **Actor** | Staf operasional (bukan front desk) |
| **Precondition** | Ada pasien di antrean |
| **Steps** | 1. Buka **Antrean ▸ Layar bersama**. 2. Bandingkan dengan papan kerja front desk. |
| **Expected** | Layar bersama hanya menampilkan nomor, inisial (mis. "B*** S."), dan status; tidak ada nama lengkap maupun info pembayaran |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | Apakah pasien masih dapat mengenali nomornya sendiri dengan tampilan ini? |
| **Severity** | |

---

## 4. Giliran perawat untuk tindakan berkomisi (NUR)

### NUR-01 — Menyusun roster harian

| Field | Isi |
|---|---|
| **Actor** | Supervisor |
| **Precondition** | Perawat yang bertugas hari ini sudah diketahui |
| **Steps** | 1. **Giliran Perawat ▸ Atur roster**. 2. Centang perawat yang bertugas. 3. Simpan. |
| **Expected** | Urutan awal terbentuk sesuai urutan pilihan; "Giliran berikutnya" menampilkan perawat posisi 1; kebijakan rotasi tertulis di halaman |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | Apakah urutan awal seharusnya ditentukan cara lain (mis. jam datang, giliran kemarin)? |
| **Severity** | |

### NUR-02 — Penugasan mengikuti giliran

| Field | Isi |
|---|---|
| **Actor** | Supervisor / perawat |
| **Precondition** | Roster tersusun |
| **Steps** | 1. Tugaskan tindakan berkomisi tanpa memilih perawat (biarkan "Ikuti giliran"). 2. Tandai **Selesai**. |
| **Expected** | Perawat posisi 1 yang ditugaskan; setelah selesai ia pindah ke posisi terakhir; hitungan giliran bertambah 1; ledger mencatat posisi sebelum→sesudah |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | |
| **Severity** | |

### NUR-03 — Eligibility tindakan

| Field | Isi |
|---|---|
| **Actor** | Supervisor |
| **Precondition** | Ada perawat yang tidak eligible untuk kategori tertentu (mis. laser) |
| **Steps** | 1. Coba tugaskan kategori itu ke perawat yang tidak eligible tanpa alasan. 2. Ulangi dengan alasan override. |
| **Expected** | Tanpa alasan ditolak; dengan alasan berhasil dan ledger mencatat "Dilewati: tidak eligible" + override |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | Verifikasi daftar eligibility benar-benar sesuai kompetensi nyata perawat |
| **Severity** | |

### NUR-04 — Skip sementara

| Field | Isi |
|---|---|
| **Actor** | Supervisor |
| **Precondition** | Perawat giliran berikutnya sedang tidak bisa (mis. menyiapkan ruang) |
| **Steps** | 1. Tekan **Skip** tanpa alasan. 2. Ulangi dengan alasan. 3. Periksa posisi perawat setelahnya. |
| **Expected** | Tanpa alasan ditolak; dengan alasan berhasil; **default: perawat tetap di posisinya** (tidak dihukum), giliran jatuh ke berikutnya |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | **OPEN DECISION D6:** apakah perilaku ini yang diinginkan klinik? Tanyakan langsung ke perawat |
| **Severity** | |

### NUR-05 — Pembatalan tindakan

| Field | Isi |
|---|---|
| **Actor** | Supervisor / perawat |
| **Precondition** | Ada tindakan ditugaskan |
| **Steps** | 1. Batalkan tindakan **sebelum** dimulai, dengan alasan. 2. Pada tindakan lain, tekan Mulai lalu batalkan **setelah** dimulai. |
| **Expected** | Batal sebelum mulai: posisi perawat dikembalikan ke depan. Batal setelah mulai: dihitung sebagai giliran terpakai, perawat pindah ke belakang. Keduanya masuk ledger |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | **OPEN DECISION D6:** konfirmasi aturan ini adil menurut perawat |
| **Severity** | |

### NUR-06 — Ledger menjelaskan urutan saat ini

| Field | Isi |
|---|---|
| **Actor** | Perawat (bukan supervisor) |
| **Precondition** | Sudah ada beberapa tindakan, skip, dan override hari itu |
| **Steps** | 1. Buka **Giliran Perawat ▸ Ledger lengkap**. 2. Minta perawat menjelaskan mengapa urutan sekarang seperti itu, hanya berbekal ledger. |
| **Expected** | Perawat dapat menjelaskan urutan tanpa bertanya ke supervisor |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | **Ini uji keadilan yang paling penting di modul ini.** Catat keberatan apa pun |
| **Severity** | |

---

## 5. Jadwal istirahat, makan, dan ibadah (BRK)

### BRK-01 — Membuat jadwal istirahat

| Field | Isi |
|---|---|
| **Actor** | Supervisor |
| **Precondition** | Staf hari itu diketahui |
| **Steps** | 1. **Jadwal Istirahat ▸ Tambah jadwal**. 2. Pilih staf, jenis (istirahat/makan/ibadah), jam mulai–selesai. 3. Simpan. |
| **Expected** | Jadwal tersimpan; staf terkait menerima notifikasi in-app; jadwal muncul di daftar tim |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | Apakah jenis jadwal sudah cukup (istirahat/makan/ibadah/lainnya)? |
| **Severity** | |

### BRK-02 — Konflik jadwal orang yang sama ditolak

| Field | Isi |
|---|---|
| **Actor** | Supervisor |
| **Precondition** | Satu staf sudah punya jadwal 13.00–14.00 |
| **Steps** | Buat jadwal 13.30–14.30 untuk orang yang sama. |
| **Expected** | Ditolak dengan pesan bertabrakan |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | |
| **Severity** | |

### BRK-03 — Peringatan minimum staf aktif

| Field | Isi |
|---|---|
| **Actor** | Supervisor |
| **Precondition** | Jumlah front desk/perawat aktif mendekati batas minimum |
| **Steps** | 1. Jadwalkan istirahat yang membuat staf aktif di bawah minimum, tanpa alasan override. 2. Ulangi dengan alasan override. |
| **Expected** | Tanpa alasan ditolak dengan peringatan yang menyebut jumlah dan minimum; dengan alasan berhasil dan tercatat sebagai override |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | **OPEN DECISION D7:** apakah minimum 1 front desk + 1 perawat sudah tepat? Perlukah berbeda per jam sibuk? |
| **Severity** | |

### BRK-04 — Staf melihat jadwalnya di ponsel

| Field | Isi |
|---|---|
| **Actor** | Perawat / staf |
| **Precondition** | Jadwal sudah dibuat |
| **Steps** | Buka **Jadwal Istirahat** dari ponsel masing-masing. |
| **Expected** | Bagian "Jadwal saya" menampilkan jadwal sendiri; tampilan terbaca tanpa zoom dan tanpa geser horizontal |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | Catat merek/ukuran ponsel yang diuji |
| **Severity** | |

---

## 6. Buku komplain (CMP)

### CMP-01 — Mencatat komplain

| Field | Isi |
|---|---|
| **Actor** | Front desk / staf yang menerima komplain |
| **Precondition** | Ada komplain nyata (atau latihan bila tidak ada) |
| **Steps** | 1. **Komplain ▸ Buat catatan baru**. 2. Pilih tipe Komplain, isi sumber pelapor, kanal, ringkasan, uraian, tingkat dampak. 3. Simpan. |
| **Expected** | Nomor `CMP-YYYYMMDD-NNN` terbentuk; target penugasan dan target selesai terisi otomatis sesuai SLA; supervisor menerima notifikasi |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | Tandai jelas: komplain NYATA atau LATIHAN. **OPEN DECISION D9:** apakah SLA-nya realistis? |
| **Severity** | |

### CMP-02 — Komplain terbatas hanya terlihat pihak berkepentingan

| Field | Isi |
|---|---|
| **Actor** | Pembuat komplain + staf lain di luar cakupan |
| **Precondition** | Komplain dibuat dengan centang **Terbatas** |
| **Steps** | 1. Pembuat membuka catatan. 2. Staf lain mencari catatan itu di daftar. 3. Staf lain mencoba membuka URL detailnya langsung. |
| **Expected** | Pembuat bisa membuka; staf lain tidak melihatnya di daftar dan menerima "Akses ditolak" saat membuka URL langsung |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | **Kegagalan di sini = Critical dan stop criteria T3** |
| **Severity** | |

### CMP-03 — Penugasan dan tindak lanjut

| Field | Isi |
|---|---|
| **Actor** | Supervisor |
| **Precondition** | Ada komplain berstatus Baru |
| **Steps** | 1. Ubah status ke Ditinjau. 2. Tugaskan ke seorang staf dengan target selesai. 3. Staf yang ditugaskan menambah catatan progres. |
| **Expected** | Penanggung jawab menerima notifikasi; status menjadi Ditugaskan; timeline mencatat setiap perubahan beserta pelakunya |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | |
| **Severity** | |

### CMP-04 — Penutupan wajib ringkasan penyelesaian

| Field | Isi |
|---|---|
| **Actor** | Staf penanggung jawab + supervisor |
| **Precondition** | Komplain sedang dalam proses |
| **Steps** | 1. Coba tandai **Selesai** tanpa ringkasan penyelesaian. 2. Isi ringkasan, tandai Selesai. 3. Supervisor menutup dengan alasan. |
| **Expected** | Tanpa ringkasan ditolak; dengan ringkasan berhasil; penutupan tercatat di audit |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | |
| **Severity** | |

### CMP-05 — Lampiran bukti

| Field | Isi |
|---|---|
| **Actor** | Staf |
| **Precondition** | Ada komplain terbuka |
| **Steps** | 1. Unggah foto/PDF bukti (≤5 MB). 2. Coba unggah file selain JPG/PNG/PDF. 3. Coba unggah file >5 MB. |
| **Expected** | File valid terunggah dan dapat diunduh kembali; format lain dan file kebesaran ditolak dengan pesan jelas |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | |
| **Severity** | |

---

## 7. Buku masukan/saran (SUG)

### SUG-01 — Staf mengirim saran

| Field | Isi |
|---|---|
| **Actor** | Staf operasional / perawat |
| **Precondition** | — |
| **Steps** | 1. **Masukan ▸ Buat catatan baru**, tipe Masukan/saran. 2. Isi judul, uraian, manfaat/dampak. 3. Simpan. |
| **Expected** | Nomor `SUG-YYYYMMDD-NNN` terbentuk; input terasa lebih ringan daripada form komplain |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | Apakah istilah "Masukan/saran" sudah sesuai istilah internal klinik? |
| **Severity** | |

### SUG-02 — Alur keputusan saran

| Field | Isi |
|---|---|
| **Actor** | Supervisor |
| **Precondition** | Ada saran baru |
| **Steps** | 1. Ubah status ke Dipertimbangkan. 2. Ubah ke Direncanakan. 3. Pada saran lain, coba **Ditolak** tanpa alasan lalu dengan alasan. |
| **Expected** | Alur status berjalan; penolakan tanpa alasan ditolak sistem; alasan tersimpan dan terlihat |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | |
| **Severity** | |

### SUG-03 — Anonimitas terhadap staf biasa

| Field | Isi |
|---|---|
| **Actor** | Staf pengirim + staf lain |
| **Precondition** | Saran dibuat dengan centang anonim |
| **Steps** | 1. Kirim saran anonim. 2. Staf lain membuka daftar saran. |
| **Expected** | Isi saran terlihat, tetapi identitas pengirim tidak ditampilkan ke staf biasa |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | **OPEN DECISION D8:** siapa yang boleh melihat identitas pengirim saran anonim? |
| **Severity** | |

---

## 8. Laporan kerusakan fasilitas/alat (DMG)

### DMG-01 — Mencatat kerusakan

| Field | Isi |
|---|---|
| **Actor** | Siapa pun yang menemukan |
| **Precondition** | Ada kerusakan nyata (atau latihan) |
| **Steps** | 1. **Kerusakan ▸ Buat catatan baru**. 2. Isi lokasi/aset, kategori, urgensi, dampak penggunaan, uraian. 3. Lampirkan foto. 4. Simpan. |
| **Expected** | Nomor `DMG-YYYYMMDD-NNN`; target SLA terisi sesuai urgensi; supervisor mendapat notifikasi |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | Apakah daftar kategori sudah mencakup jenis kerusakan yang biasa terjadi? |
| **Severity** | |

### DMG-02 — Kerusakan kritis memberi alert

| Field | Isi |
|---|---|
| **Actor** | Staf + supervisor |
| **Precondition** | — |
| **Steps** | 1. Buat laporan dengan urgensi **Kritis**. 2. Supervisor membuka dashboard dan notifikasi. |
| **Expected** | Supervisor menerima notifikasi segera; dashboard menampilkan jumlah kritis terbuka |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | Berapa lama sampai supervisor benar-benar menyadarinya? |
| **Severity** | |

### DMG-03 — Alur perbaikan sampai verifikasi

| Field | Isi |
|---|---|
| **Actor** | Supervisor + pelaksana |
| **Precondition** | Ada laporan kerusakan baru |
| **Steps** | Jalankan: Ditriase → Ditugaskan → Dalam perbaikan → (Menunggu vendor bila ada) → Selesai → Diverifikasi → Ditutup. Isi data perbaikan (tindakan, vendor, biaya). |
| **Expected** | Setiap transisi tersimpan dengan pelaku dan waktu; verifikasi mencatat siapa yang memverifikasi; penutupan wajib ringkasan |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | Apakah alur ini cocok dengan cara klinik memanggil teknisi/vendor? |
| **Severity** | |

### DMG-04 — Menandai aset "Jangan digunakan"

| Field | Isi |
|---|---|
| **Actor** | Supervisor |
| **Precondition** | Aset terdaftar di daftar aset |
| **Steps** | 1. **Kerusakan ▸ Daftar aset**. 2. Tandai satu aset jangan digunakan tanpa alasan, lalu dengan alasan. |
| **Expected** | Tanpa alasan ditolak; dengan alasan berhasil; penanda terlihat jelas bagi staf lain |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | Apakah staf benar-benar melihat penanda ini sebelum memakai alat? |
| **Severity** | |

### DMG-05 — Penugasan dalam 1 hari operasional (target S4)

| Field | Isi |
|---|---|
| **Actor** | Supervisor |
| **Precondition** | Ada laporan kerusakan baru hari itu |
| **Steps** | Tugaskan setiap laporan baru ke penanggung jawab pada hari yang sama. |
| **Expected** | ≥90% laporan baru punya penanggung jawab dalam 1 hari operasional |
| **Actual** | ____ dari ____ laporan |
| **Pass/Fail** | |
| **Notes** | Diukur kumulatif selama 5 hari |
| **Severity** | |

### DMG-06 — Laporan dari checklist pembukaan

| Field | Isi |
|---|---|
| **Actor** | Staf |
| **Precondition** | OPN-05 dijalankan |
| **Steps** | Buka tiket kerusakan yang dibuat dari checklist. |
| **Expected** | Tiket berisi lokasi/area dari checklist dan catatan aslinya; keterkaitan ke item checklist terlihat |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | |
| **Severity** | |

---

## 9. Review supervisor (SUP)

### SUP-01 — Review pembukaan dan pengecualian

| Field | Isi |
|---|---|
| **Actor** | Supervisor |
| **Precondition** | Checklist terisi, ada item bermasalah |
| **Steps** | 1. **Pembukaan ▸ Review pembukaan**. 2. Coba **Konfirmasi selesai** saat masih ada item wajib belum OK. 3. **Terima dengan pengecualian** tanpa alasan. 4. Ulangi dengan alasan. |
| **Expected** | Langkah 2 dan 3 ditolak; langkah 4 berhasil dan tercatat sebagai override di audit |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | |
| **Severity** | |

### SUP-02 — Menandai hari siap dan membuka klinik

| Field | Isi |
|---|---|
| **Actor** | Supervisor |
| **Precondition** | Checklist dan kas awal selesai |
| **Steps** | 1. **Hari Ini ▸ Tandai siap**. 2. Coba tandai siap saat kas awal belum dicatat (uji di hari lain). 3. **Buka klinik**. |
| **Expected** | Siap ditolak bila item wajib belum OK atau kas awal belum dicatat; setelah lengkap, status menjadi Siap lalu Buka |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | |
| **Severity** | |

### SUP-03 — Dashboard sebagai alat pantau harian

| Field | Isi |
|---|---|
| **Actor** | Supervisor |
| **Precondition** | Hari berjalan |
| **Steps** | Buka **Hari Ini** beberapa kali sepanjang hari. |
| **Expected** | Supervisor dapat menjawab tanpa bertanya ke siapa pun: berapa item pembukaan bermasalah, status kas, jumlah antrean, perawat berikutnya, siapa istirahat 60 menit ke depan, berapa catatan terbuka/lewat target |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | Informasi apa yang supervisor cari tapi tidak ada di dashboard? |
| **Severity** | |

### SUP-04 — Menutup hari operasional

| Field | Isi |
|---|---|
| **Actor** | Supervisor |
| **Precondition** | Sore hari, kas akhir sudah/belum selesai |
| **Steps** | 1. **Mulai penutupan**. 2. Coba **Tutup hari** saat kas akhir belum selesai atau ada catatan kritis belum ditriase. 3. Tutup dengan alasan override. |
| **Expected** | Penutupan tanpa syarat terpenuhi ditolak dengan daftar penghalang yang jelas; override wajib alasan dan tercatat |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | |
| **Severity** | |

---

## 10. Review manajemen/owner (OWN)

### OWN-01 — Owner meninjau data 5 hari

| Field | Isi |
|---|---|
| **Actor** | Owner/Manajemen |
| **Precondition** | Pilot berjalan minimal 4 hari |
| **Steps** | 1. Buka **Laporan**, set rentang tanggal seluruh pilot. 2. Baca kepatuhan checklist, kas & selisih, volume antrean, distribusi giliran perawat, catatan per status, item lewat target. |
| **Expected** | Owner memperoleh gambaran operasional 5 hari tanpa bertanya ke staf |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | Angka apa yang owner butuhkan tapi belum ada? |
| **Severity** | |

### OWN-02 — Ekspor CSV

| Field | Isi |
|---|---|
| **Actor** | Owner/Manajemen |
| **Precondition** | Owner punya izin ekspor |
| **Steps** | Ekspor antrean, kas, checklist, catatan, dan giliran; buka di Excel/Sheets. |
| **Expected** | Berkas terunduh, kolom terbaca, tanggal/waktu dalam WIB; setiap ekspor tercatat di audit log |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | |
| **Severity** | |

### OWN-03 — Menelusuri satu kejadian lewat audit

| Field | Isi |
|---|---|
| **Actor** | Owner + supervisor |
| **Precondition** | Sudah ada override/koreksi selama pilot |
| **Steps** | 1. Pilih satu kejadian (mis. koreksi kas atau override perawat). 2. Buka **Audit**, filter aktor/aksi/tanggal. 3. Telusuri: siapa, kapan, nilai lama → nilai baru, apa alasannya. |
| **Expected** | Seluruh pertanyaan terjawab dari audit log saja |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | **Ini uji akuntabilitas inti PRD.** Bila gagal, severity minimal High |
| **Severity** | |

---

## 11. Admin dan konfigurasi (ADM)

### ADM-01 — Mengelola pengguna dan peran

| Field | Isi |
|---|---|
| **Actor** | Admin |
| **Precondition** | — |
| **Steps** | 1. Buat akun staf baru. 2. Beri peran. 3. Nonaktifkan satu akun. 4. Reset password satu akun. |
| **Expected** | Akun baru wajib ganti password saat login pertama; akun nonaktif langsung tidak dapat masuk; riwayat milik akun nonaktif tetap utuh; semua perubahan peran tercatat di audit |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | |
| **Severity** | |

### ADM-02 — Admin teknis tidak otomatis punya hak bisnis

| Field | Isi |
|---|---|
| **Actor** | Admin teknis |
| **Precondition** | Admin hanya punya peran Admin |
| **Steps** | 1. Coba buka **Kas**. 2. Coba buka detail pasien. 3. Coba buka komplain terbatas. |
| **Expected** | Ketiganya ditolak; hak tersebut hanya diperoleh bila diberikan eksplisit sebagai kapabilitas tambahan |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | **Prinsip least privilege PRD 6.3. Kegagalan = Critical** |
| **Severity** | |

### ADM-03 — Mengubah konfigurasi kebijakan

| Field | Isi |
|---|---|
| **Actor** | Admin (atas keputusan owner) |
| **Precondition** | Owner sudah memutuskan nilai kebijakan |
| **Steps** | 1. **Admin ▸ Konfigurasi**. 2. Ubah satu kunci (mis. `break.min_active_nurse`). 3. Amati perilaku sistem setelahnya. 4. Periksa audit log. |
| **Expected** | Nilai tersimpan, perilaku berubah tanpa deploy ulang, perubahan tercatat dengan nilai lama dan baru |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | Jangan mengubah kebijakan bisnis tanpa persetujuan owner |
| **Severity** | |

### ADM-04 — Perubahan template tidak mengubah riwayat

| Field | Isi |
|---|---|
| **Actor** | Admin teknis |
| **Precondition** | Sudah ada checklist harian tersimpan dari hari sebelumnya |
| **Steps** | 1. Ubah item template (tambah/hapus/ubah minimum) lewat Django admin. 2. Buka checklist hari-hari sebelumnya. 3. Buat sesi hari baru. |
| **Expected** | Checklist historis **tidak berubah**; hanya sesi hari baru yang memakai template terbaru |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | Catat kesulitan mengelola template lewat Django admin — bila menghambat, ini kandidat halaman admin khusus fase berikutnya |
| **Severity** | |

---

## 12. Pengecualian dan override (EXC)

### EXC-01 — Hari siap dengan catatan

| Field | Isi |
|---|---|
| **Actor** | Supervisor |
| **Precondition** | Ada item wajib yang tidak dapat dipenuhi pagi itu |
| **Steps** | Tandai hari **Siap dengan catatan** disertai alasan dan daftar pengecualian. |
| **Expected** | Status `READY_WITH_ISSUES`; alasan tersimpan dan terlihat di dashboard; tercatat sebagai override |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | |
| **Severity** | |

### EXC-02 — Reorder antrean beralasan

| Field | Isi |
|---|---|
| **Actor** | Supervisor |
| **Precondition** | Ada ≥3 pasien di antrean |
| **Steps** | Pindahkan seorang pasien ke posisi 1 dengan alasan (mis. lansia/ibu hamil). |
| **Expected** | Urutan berubah; alasan wajib; tercatat sebagai override di audit |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | **OPEN DECISION D4:** apakah perlu aturan prioritas baku, bukan kasus per kasus? |
| **Severity** | |

### EXC-03 — Membuka kembali hari yang sudah ditutup

| Field | Isi |
|---|---|
| **Actor** | Supervisor |
| **Precondition** | Ada hari berstatus Tutup |
| **Steps** | 1. Coba ubah data hari yang tertutup. 2. Buka kembali dengan alasan. 3. Lakukan koreksi. |
| **Expected** | Hari tertutup read-only; buka kembali wajib alasan; koreksi setelahnya tercatat lengkap |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | |
| **Severity** | |

### EXC-04 — Dua petugas mengubah data yang sama

| Field | Isi |
|---|---|
| **Actor** | Dua staf berbeda |
| **Precondition** | Dua perangkat membuka data yang sama (mis. item checklist atau entri antrean) |
| **Steps** | 1. Keduanya membuka halaman yang sama. 2. Orang A menyimpan. 3. Orang B menyimpan tanpa memuat ulang. |
| **Expected** | Simpanan B ditolak dengan pesan meminta muat ulang; **perubahan A tidak tertimpa diam-diam** |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | Kondisi ini biasa terjadi saat klinik ramai |
| **Severity** | |

### EXC-05 — Tombol simpan ganda

| Field | Isi |
|---|---|
| **Actor** | Staf mana pun |
| **Precondition** | — |
| **Steps** | Tekan tombol Simpan dua kali cepat pada form antrean atau kas. |
| **Expected** | Hanya satu data tersimpan; tidak ada entri/nomor antrean ganda |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | |
| **Severity** | |

### EXC-06 — Kontingensi saat sistem tidak dapat diakses

| Field | Isi |
|---|---|
| **Actor** | Supervisor + staf |
| **Precondition** | Latihan terencana, diberitahukan sebelumnya |
| **Steps** | 1. Admin menghentikan aplikasi ±15 menit. 2. Staf mencatat di kertas. 3. Aplikasi dinyalakan. 4. Staf memasukkan data susulan dengan catatan "entri susulan". |
| **Expected** | Klinik tetap beroperasi; data susulan dapat dimasukkan dan ditandai jelas |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | **OPEN DECISION D12:** apakah prosedur kontingensi ini memadai? |
| **Severity** | |

---

## 13. Keamanan dan privasi (SEC)

### SEC-01 — Akses hanya dari tailnet berizin

| Field | Isi |
|---|---|
| **Actor** | Admin teknis |
| **Precondition** | Tailscale Serve aktif |
| **Steps** | 1. Buka aplikasi dari perangkat tailnet berizin. 2. Buka dari data seluler tanpa Tailscale. 3. Jalankan `APP_PORT=8731 ./scripts/verify_deployment.sh`. |
| **Expected** | (1) halaman login muncul; (2) **gagal total**; (3) seluruh pemeriksaan lulus, aplikasi listen hanya di `127.0.0.1:8731` |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | **Kegagalan (2) = stop criteria T2, hentikan pilot segera** |
| **Severity** | |

### SEC-02 — Staf biasa tidak dapat membuka data sensitif

| Field | Isi |
|---|---|
| **Actor** | Staf operasional (tanpa peran kas/supervisor) |
| **Precondition** | Ada data kas dan pasien |
| **Steps** | 1. Coba buka menu Kas. 2. Coba buka Audit. 3. Coba buka detail pasien. 4. Coba salin URL dari layar rekan dan buka langsung. |
| **Expected** | Semuanya ditolak dengan halaman "Akses ditolak", termasuk lewat URL langsung |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | **Kegagalan = Critical dan stop criteria T3** |
| **Severity** | |

### SEC-03 — Sesi berakhir otomatis

| Field | Isi |
|---|---|
| **Actor** | Staf mana pun |
| **Precondition** | Perangkat bersama (mis. komputer front desk) |
| **Steps** | Login, tinggalkan tanpa aktivitas 30 menit, lalu coba lanjut bekerja. |
| **Expected** | Sesi berakhir dan diminta login ulang |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | Apakah 30 menit terlalu pendek/panjang untuk kondisi klinik? |
| **Severity** | |

### SEC-04 — Lampiran tidak dapat diakses tanpa izin

| Field | Isi |
|---|---|
| **Actor** | Staf di luar cakupan komplain terbatas |
| **Precondition** | Ada lampiran pada komplain terbatas |
| **Steps** | 1. Minta tautan lampiran dari pihak berwenang. 2. Buka tautan itu dengan akun sendiri. 3. Buka tautan tanpa login (mode penyamaran). |
| **Expected** | (2) ditolak; (3) diarahkan ke login; setiap unduhan yang sah tercatat di audit |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | |
| **Severity** | |

---

## 14. Laporan (RPT)

### RPT-01 — Kepatuhan checklist pembukaan

| Field | Isi |
|---|---|
| **Actor** | Supervisor/Owner |
| **Steps** | Buka **Laporan**, periksa tabel kepatuhan checklist per area. |
| **Expected** | Jumlah item, OK, dan bermasalah sesuai kenyataan lapangan |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | |
| **Severity** | |

### RPT-02 — Kas dan selisih

| Field | Isi |
|---|---|
| **Actor** | Owner (berizin kas) |
| **Steps** | Periksa tabel kas: diharapkan, aktual, selisih, status verifikasi per hari. |
| **Expected** | Setiap hari punya kas awal dan akhir terverifikasi; selisih terlihat jelas |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | Bandingkan dengan catatan kas manual (target S10) |
| **Severity** | |

### RPT-03 — Distribusi giliran perawat

| Field | Isi |
|---|---|
| **Actor** | Owner + perawat |
| **Steps** | Periksa jumlah giliran per perawat dan jumlah override selama pilot. |
| **Expected** | Distribusi mendekati merata bagi perawat dengan ketersediaan sama; jumlah override wajar dan dapat dijelaskan |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | Bila distribusi timpang, catat penyebabnya sebagai OPEN DECISION |
| **Severity** | |

### RPT-04 — Item lewat target waktu

| Field | Isi |
|---|---|
| **Actor** | Supervisor/Owner |
| **Steps** | Periksa daftar catatan yang melewati target waktu. |
| **Expected** | Daftar akurat; setiap item punya penjelasan atau tindak lanjut |
| **Actual** | |
| **Pass/Fail** | |
| **Notes** | Bila banyak yang lewat target, kemungkinan SLA-nya yang tidak realistis (**OPEN DECISION D9**) |
| **Severity** | |

---

## Rekapitulasi hasil

Isi di akhir pilot.

| Kelompok | Jumlah skenario | Pass | Fail | Blocked/Tidak diuji |
|---|---:|---:|---:|---:|
| OPN Pembukaan | 5 | | | |
| CSH Kas | 5 | | | |
| QUE Antrean | 5 | | | |
| NUR Giliran perawat | 6 | | | |
| BRK Jadwal istirahat | 4 | | | |
| CMP Komplain | 5 | | | |
| SUG Masukan | 3 | | | |
| DMG Kerusakan | 6 | | | |
| SUP Review supervisor | 4 | | | |
| OWN Review owner | 3 | | | |
| ADM Admin & konfigurasi | 4 | | | |
| EXC Pengecualian | 6 | | | |
| SEC Keamanan & privasi | 4 | | | |
| RPT Laporan | 4 | | | |
| **Total** | **64** | | | |

**Kriteria kelulusan UAT:** seluruh skenario **SEC** dan **ADM-02** wajib Pass (tanpa
pengecualian). Tidak boleh ada kegagalan Critical yang belum ditutup. Kegagalan High
harus punya rencana perbaikan bertanggal sebelum go-live.

**Ditinjau oleh:**

| Peran | Nama | Tanda tangan | Tanggal |
|---|---|---|---|
| Pilot lead (supervisor) | | | |
| Admin teknis | | | |
| Owner/Manajemen | | | |
