# DECISIONS.md — JoDerma Staff Ops

Status: **keputusan sementara (provisional)**. Semua nilai di bawah diambil dari PRD
Bagian 29 dan **harus dikonfirmasi product owner pada Milestone 0**. Setiap keputusan
dibuat dapat dikonfigurasi (lihat `core.models.ClinicConfig` dan halaman Admin ▸ Konfigurasi)
sehingga perubahan tidak memerlukan perubahan kode.

Legenda status: `PROVISIONAL` = default dipakai untuk membangun; `CONFIRMED` = disetujui PO.

> **Untuk owner:** pengelompokan 12 keputusan ini menjadi "harus diputuskan sebelum pilot",
> "boleh tetap provisional selama pilot", dan "harus diputuskan sebelum produksi" ada di
> [`OWNER_DECISION_REVIEW.md`](OWNER_DECISION_REVIEW.md), lengkap dengan kolom keputusan
> untuk ditandatangani. Dokumen ini tetap menjadi catatan nilai yang sedang berlaku.

---

## Jawaban Bagian 27

### 1. Apakah "kas", "modal", dan "uang kembalian" tiga pos terpisah atau satu cash drawer?
**PROVISIONAL.** Satu cash drawer dengan tiga pos nilai yang dicatat terpisah dalam satu
`CashSession`: `expected_total` (uang modal yang diharapkan), `change_fund_total`
(uang kembalian tersedia), dan `other_funds_total` (dana kas lain). Total aktual dihitung
dari rincian pecahan; selisih = `actual_total - expected_total`. Tidak ada buku besar
akuntansi pada MVP.
Config key: `cash.track_change_fund_separately = true`.
*Menunggu keputusan owner:* `OWNER_DECISION_REVIEW.md` D1 — apakah uang kembalian termasuk
dalam uang modal, dan terhadap angka mana selisih seharusnya dihitung.

### 2. Apakah verifikasi kas selalu membutuhkan dua orang?
**PROVISIONAL.** Ya — dual-control **aktif**. Verifikator tidak boleh sama dengan penghitung
pertama. Dapat dimatikan lewat config bila klinik hanya punya satu petugas pada shift tertentu.
Config key: `cash.dual_control_enabled = true`.

Sesuai PRD 8.3 ("penghitung kedua **atau** supervisor"), verifikator kedua boleh:
front desk/kasir lain, supervisor, atau pemegang kapabilitas `cash.approve`.
**Koreksi setelah verifikasi tetap hanya supervisor.** Bila hanya supervisor yang boleh
memverifikasi, kas tidak akan pernah dapat diverifikasi saat supervisor sendiri yang
menghitung.
*Menunggu konfirmasi owner:* `OWNER_DECISION_REVIEW.md` OD-A.

### 3. Status pembayaran apa yang menyebabkan nomor antrean dipertahankan?
**PROVISIONAL.** `SUDAH_BAYAR` dan `DIBEBASKAN` (dibebaskan hanya oleh pengguna berwenang —
supervisor/owner). Status `BELUM_PERLU`, `BELUM_BAYAR`, `REFUND` tidak menahan nomor.
Config key: `queue.keep_number_statuses = ["SUDAH_BAYAR", "DIBEBASKAN"]`.

### 4. Aturan pasien prioritas, keterlambatan, refund, dan no-show?
**PROVISIONAL.**
- Prioritas: hanya supervisor yang dapat menaikkan posisi; wajib alasan; tercatat sebagai event.
- Keterlambatan: pasien yang dipanggil dan tidak hadir ditandai `NO_SHOW` setelah
  `queue.no_show_grace_minutes = 15`; nomor tidak otomatis hangus, supervisor dapat
  mengaktifkan kembali dengan alasan.
- Refund: mengubah payment status ke `REFUND`, wajib alasan, nomor kehilangan status keep.
- No-show: tidak menghapus entri; entri tetap tampil di laporan harian.

### 5. Giliran perawat dihitung per tindakan, kategori, durasi, atau nilai komisi?
**PROVISIONAL.** Per **tindakan berkomisi yang selesai dikonfirmasi** (round-robin sederhana),
tanpa bobot durasi maupun nilai rupiah. Kategori tindakan hanya dipakai untuk cek *eligibility*.
Nilai komisi tidak dihitung pada MVP.
Config key: `nurse.rotation_policy = "ROUND_ROBIN_PER_CONFIRMED_PROCEDURE"`.

### 6. Apa yang terjadi pada posisi perawat saat skip, tindakan batal, atau pulang lebih awal?
**PROVISIONAL.**
- `SKIP` sementara: perawat **tetap di posisinya** (tidak dihukum), giliran jatuh ke berikutnya.
  Config key: `nurse.skip_keeps_position = true`.
- Tindakan `BATAL` sebelum dimulai: posisi dikembalikan ke depan (rotasi di-*undo*).
  Tindakan batal setelah dimulai: dihitung sebagai giliran terpakai. Config key:
  `nurse.cancel_before_start_restores_position = true`.
- Pulang lebih awal: `availability = OFF_DUTY`, dilewati dari rotasi tanpa mengubah urutan lain.

### 7. Minimum staf aktif saat istirahat, berbeda per area?
**PROVISIONAL.** Minimum 1 front desk **dan** 1 perawat aktif setiap saat. Belum dibedakan
per area pada MVP; pelanggaran memunculkan warning yang dapat di-override supervisor
dengan alasan. Config key: `break.min_active_front_desk = 1`, `break.min_active_nurse = 1`.

### 8. Siapa yang boleh melihat identitas pelapor komplain dan detail finansial?
**PROVISIONAL.**
- Identitas pelapor & komplain `TERBATAS`: pembuat, penanggung jawab (assignee),
  supervisor, owner. Akses ke detail terbatas dicatat di audit log.
- Nominal kas: kasir/front desk yang ditugaskan, supervisor, dan owner dengan capability
  `cash.view_amounts`. Admin teknis **tidak** otomatis mendapat hak ini.

### 9. SLA tiap tingkat komplain/kerusakan dan jalur eskalasi?
**PROVISIONAL** (jam kerja, dihitung dari waktu pencatatan):
| Severity | Target respons/penugasan | Target selesai |
|---|---|---|
| KRITIS | 1 jam | 8 jam |
| TINGGI | 4 jam | 24 jam |
| SEDANG | 1 hari | 3 hari |
| RENDAH | 2 hari | 7 hari |
Eskalasi: terlewat target → notifikasi ke supervisor; `KRITIS` memberi alert dashboard
segera saat dibuat. Config key: `sla.<severity>.assign_hours` / `sla.<severity>.resolve_hours`.

### 10. Berapa lama setiap tipe data disimpan?
**PROVISIONAL.** Audit event 24 bulan. Data operasional (hari, checklist, kas, antrean,
giliran, jadwal) 24 bulan. Issue dan lampiran 24 bulan setelah ditutup. Tidak ada hard-delete
untuk komplain dan kerusakan. **Kebijakan final wajib disetujui manajemen sesuai peraturan
Indonesia sebelum produksi.**

### 11. Host produksi Linux mini-PC atau Windows workstation?
**PROVISIONAL.** Linux mini-PC yang selalu menyala, Docker Compose (satu host), SQLite WAL,
backup malam ke perangkat kedua, Tailscale Serve. Tersedia juga unit systemd native bila
Docker tidak dipakai.

### 12. Perlu akses saat internet putus total?
**PROVISIONAL.** Tailscale dapat bekerja lewat jalur LAN langsung selama perangkat berada di
jaringan yang sama, sehingga akses lokal umumnya tetap berjalan. Kontingensi bila akses gagal:
formulir kertas darurat (checklist pembukaan, kas, antrean) lalu di-entry ulang saat sistem
kembali, ditandai sebagai entri susulan dengan alasan. Runbook: `docs/runbook.md`.

---

## Absensi jam kerja (D1–D6)

Keputusan khusus modul absensi, disalin dari
[`docs/absensi-jam-kerja.md`](docs/absensi-jam-kerja.md) bagian 6 pada 13 Okt 2026 agar
punya satu tempat bersama keputusan lain. Dokumen modulnya tetap memuat penjelasan
panjangnya; yang di bawah ini jawabannya saja beserta tempatnya di kode.

### D1. Izul (2), Isya (6), dan Lina (9) ikut skema penilaian ini?
**CONFIRMED.** Ikut, tetapi **rekam saja** — capnya disimpan dan bisa dilihat, tidak
dinilai. Ketiganya tidak ada di jadwal jaga kedua cabang, jadi jam shift-nya tidak
diketahui dan menilainya dengan jam Jemur/Citraland hanya menghasilkan angka yang tidak
berarti. Di kode: `AttendanceDevice.recording_only`; usernya nonaktif dan tanpa peran,
cukup untuk menautkan cap tetapi tidak cukup untuk masuk aplikasi. Mereka muncul di
bagian terpisah "Direkam tanpa penilaian" pada papan skor, dan tidak pernah menghasilkan
pengecualian — kalau dinilai, setiap harinya akan jadi `TANPA_ROSTER` dan menenggelamkan
temuan yang benar-benar perlu dilihat.

### D2. Hari off tetapi tetap mengecap dibayar?
**CONFIRMED.** Dibayar. Hari Minggu adalah hari biasa tanpa premi; penggantinya hari off
di jadwal jaga. Di kode: sudah sesuai perilaku sebelumnya, ditambah test penjaga agar
hari Minggu tidak pernah diberi perlakuan khusus. Hari off yang tetap mengecap dihitung
memakai jam cabang asal (`home_clinic`) dan ditandai `LIBUR_TAPI_NGECAP`.

### D3. Lembur sangat panjang perlu persetujuan?
**CONFIRMED.** Tidak, untuk saat ini. Lembur pulang dihitung penuh tanpa plafon. Di kode:
`AMBANG_LEMBUR_PANJANG_MENIT = 180` hanya menandai hari itu di daftar "Perlu dicek";
ia tidak pernah memotong bayaran.

### D4. Siapa boleh mengoreksi absen, skor, dan lembur?
**CONFIRMED.** Direktur Operasional, Direktur Utama, dan Owner. Lebih sempit daripada hak
mengimpor berkas, karena mengimpor hanya memasukkan apa yang dicatat mesin sedangkan
mengoreksi mengubah angka yang dipakai menilai orang. Hak jadwal jaga **tidak** berubah:
tetap Admin, Koordinator Shift, dan Direktur Operasional. Di kode:
`core.permissions.can_correct_absensi`, ditegakkan di halaman koreksi (Tahap 4), di
Django admin, dan di `core/peran.py`. Konsekuensi yang diterima: jadwal jaga tanggal
lampau tetap boleh diubah Koordinator Shift, dan itu menggeser skor bulan itu lewat jalur
yang berbeda.

### D5. Staf melihat jam kerjanya sendiri?
**CONFIRMED.** Ya. Di kode: `/absensi/saya/`, menu "Absensi saya". Rute itu tidak punya
parameter staf, jadi tidak ada cara meminta data orang lain dari sana. Sejak Tahap 5 staf
juga bisa menekan "Cap saya kurang" untuk melaporkan capnya hilang atau keliru; jam yang
ia tulis tidak mengikat, dan yang memutuskan tetap pemegang `can_correct_absensi`.

### D6. Ambang penandaan `CABANG_BEDA`
**TIDAK BERLAKU LAGI.** Pertanyaan aslinya menyangkut ambang 90 menit pada konstanta
`AMBANG_CURIGA_CABANG_MENIT`. Pemeriksaan 13 Okt 2026 menunjukkan **konstanta itu sudah
tidak ada di kode** — ia dihapus pada `c24b4b7` ketika penentuan cabang ditulis ulang
memakai jendela shift yang dicatat mesin, dan bagian 6 dokumen modulnya tidak ikut
diperbarui.

Perilaku sekarang **tanpa ambang sama sekali**: satu hari ditandai `CABANG_BEDA` bila
cabang menurut jendela shift mesin — atau, bila mesin tidak memberi keterangan, menurut
dugaan pola jam — berbeda dari cabang di jadwal jaga. Perbandingan langsung, bukan
selisih menit.

Angka yang masih ada di kode dan perlu dibedakan:

| Konstanta | Nilai | Mengubah bayaran? |
|---|---|---|
| `AMBANG_DATANG_AWAL_MENIT` | 60 | **Ya** — satu-satunya di modul ini. Keputusan product owner |
| `TOLERANSI_POLA_MENIT` | 60 | Tidak. Hanya dipakai menduga cabang saat jadwal jaga kosong |
| `TOLERANSI_PULANG_AWAL_MENIT` | 5 | Tidak. Idem; nilainya diuji terhadap 328 hari September 2026 |
| `AMBANG_LEMBUR_PANJANG_MENIT` | 180 | Tidak. Hanya menandai (D3) |

Yang tersisa untuk diputuskan, dan jauh lebih kecil daripada pertanyaan aslinya: apakah
perilaku tanpa ambang ini diterima, atau `CABANG_BEDA` perlu kelonggaran supaya tidak
menandai hari yang selisihnya sepele. Dijawab setelah ada satu bulan data nyata.

## Default operasional lain (Bagian 29)

| Keputusan | Nilai | Status |
|---|---|---|
| Cakupan instalasi | Satu cabang, satu `OperationalDay` per tanggal | PROVISIONAL |
| Zona waktu | Asia/Jakarta | CONFIRMED (PRD 5) |
| Jam operasional | Jemur Andayani 14.00–22.00, Citraland 12.00–21.00 (Pengaturan Klinik) | CONFIRMED (product owner, 4 Okt 2026) |
| Batas jam penutupan | Tidak ada: tutup boleh molor menunggu pasien terakhir, juga lewat tengah malam; hari kemarin yang belum ditutup tetap hari berjalan sampai 06.00 (`day.late_close_cutoff_hour`) | CONFIRMED (product owner, 4 Okt 2026) |
| Override | Hanya supervisor, selalu wajib alasan | PROVISIONAL |
| Hard-delete komplain/kerusakan | Tidak pernah | PROVISIONAL |
| Session idle / absolute timeout | 30 menit / 12 jam | PROVISIONAL |
| Panjang password minimum | 12 karakter | PROVISIONAL |
| Ukuran lampiran maksimum | 5 MB, JPG/PNG/PDF | PROVISIONAL |
| Database | SQLite WAL (migrasi ke PostgreSQL sesuai PRD 16.2) | PROVISIONAL |

## Catatan perubahan
- 2026-10-13 — **Hak impor absensi dan lihat jadwal jaga bisa diberikan per orang** (keputusan
  product owner). Dibuat untuk staf fasilitas (Izul) yang menerima laporan kerusakan, melapor
  balik ke pelapor, mengurus pengambilan berkas dari mesin absensi, dan perlu tahu siapa jaga
  kapan — tanpa dijadikan PIC atau Koordinator Shift. Dua kapabilitas baru: `absensi.import` dan
  `roster.view`. Konsekuensi yang **diterima sadar**: `can_view_absensi` memakai
  `can_edit_absensi`, sehingga pemegang `absensi.import` juga melihat papan skor seluruh staf;
  memisahkannya menuntut halaman impor tersendiri dan ditunda. Yang **tidak** ikut diberikan:
  hak mengoreksi cap (tetap D4 — Direktur Operasional, Direktur Utama, Owner) dan hak mengubah
  jadwal jaga (`roster.view` baca saja; POST tetap ditolak `can_edit_duty`).
- 2026-10-13 — **Data absensi September 2026 diabaikan** (keputusan product owner). September
  tidak ditinjau dan tidak dipakai menilai siapa pun; bulan penilaian pertama adalah bulan yang
  rosternya memang terisi di sistem. Dasarnya: produksi punya 776 cap September tetapi **nol
  baris jadwal jaga September**, sehingga setiap harinya muncul sebagai `TANPA_ROSTER` dengan
  skor 0 — papan skornya memang tidak berarti. Ke-328 baris jadwal "dari absensi" yang sempat
  dicatat sebagai pekerjaan tertunda ternyata **tidak pernah ada di produksi**; ia artefak
  verifikasi di salinan database laptop. Cap September tetap disimpan sebagai rekaman apa yang
  dicatat mesin; yang dibatalkan hanya pemakaiannya untuk penilaian.
- 2026-10-13 — **Celah tekan-tahan 4 detik dibiarkan terbuka, sengaja** (keputusan product owner).
  Mematikan mini PC dengan menahan tombol power 4 detik tidak dapat dicegah maupun dipulihkan oleh
  software: *power button override* memaksa mesin ke S5 tanpa OS maupun firmware berjalan, sehingga
  alarm RTC tidak terpasang dan mesin tetap mati sampai dinyalakan tangan (terjadi 13 Okt, padam 24
  menit). Dasar keputusan: 4 detik cukup lama sehingga tidak mungkin tidak disengaja, dan penyebab
  yang paling mungkin berulang — listrik padam — sudah tertutup "Restore on AC Power Loss" di BIOS
  yang aktif dan terbukti. Memperpanjang ambang override ke 6 detik adalah setelan chipset PCH yang
  hanya dapat diubah lewat BIOS, dan ikut ditunda. Ditinjau ulang bila kejadiannya berulang.
- 2026-10-06 — Angka diharapkan kas disusun sistem: kas awal = kas akhir terakhir cabang itu; kas akhir
  = kas awal hari itu + tunai masuk − tunai keluar (keputusan product owner).
- 2026-10-05 — Item Inbox dapat dijadikan kebijakan tanpa penugasan, diumumkan ke semua orang di
  cabangnya tanpa nama pelapor; Direktur Operasional dapat menjadi penerima task di semua cabang
  (keputusan product owner).
- 2026-10-04 — Jam operasional per cabang dan penutupan tanpa batas jam dikonfirmasi product owner.
- 2026-09-11 — Dokumen dibuat dari PRD v1.0 Bagian 29. Seluruh entri `PROVISIONAL`.
- 2026-09-11 — Persiapan UAT pilot: ditambahkan rujukan ke `OWNER_DECISION_REVIEW.md`;
  koreksi penamaan field kas pada D1 agar sesuai implementasi (`expected_total`);
  D2 diperjelas mengenai siapa yang boleh menjadi verifikator kedua.
  **Tidak ada keputusan bisnis yang diubah** — seluruh entri tetap `PROVISIONAL`
  dan menunggu keputusan owner.
