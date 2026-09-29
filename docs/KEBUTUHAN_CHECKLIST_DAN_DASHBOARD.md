# Kekurangan Checklist Direktur dan Kebutuhan Dashboard Pandangan Menyeluruh

Disusun 28 September 2026, setelah hari pertama Checklist Direktur dipakai di ops.joderma.id
(harian 7/7, mingguan 8/13, bulanan 1/1).

**Status 29 September 2026:** dashboard untuk Owner dan Direktur sudah dibangun — Ringkasan
(C1), Kanban (C2; kolom dibaca dari status penerima task karena `ActionItem.status` tidak pernah
menjadi `DIKERJAKAN` pada alur task), Prioritas/Eisenhower tahap 1 (C3), label penghitung (A4),
dan register **Keputusan** (keputusan menggantung dan kebijakan yang ditetapkan, permintaan
Owner 29 Sep). Owner melihat seluruh task, baca saja. Revisi hari yang sama: halaman Ringkasan disederhanakan
menjadi kotak yang dapat diketuk (detail di halaman terpisah), infografik per cabang, dan halaman
**Jadwal** (gantt task). Butir lain di bawah masih kebutuhan.

Status awal (28 Sep): catatan kebutuhan, belum ada perubahan kode. Mengikuti `AGENTS.md`, setiap butir di
bawah dikerjakan per fase, dimulai dari pemeriksaan read-only dan baseline test, dan berhenti
pada approval gate.

Rujukan kode yang sudah ada dan dipakai ulang:

| Kebutuhan | Yang sudah ada |
|---|---|
| Butir, hasil, periode checklist Direktur | `direktur.AuditItem`, `AuditPoint`, `AuditCheck`, `period_start()` |
| Ringkasan belum dicek per cabang | `direktur.services.pending_summary()` |
| Task, penerima, status konfirmasi | `core.ActionItem`, `TaskAssignment`, `core.task_services` |
| Temuan terbuka | `direktur.services.open_findings()` |
| Ringkasan tim per cabang | `direktur.services.team_overview()` |
| Lampiran berkas | `core.Attachment` |
| Prioritas | `core.Priority` (RENDAH, SEDANG, TINGGI, KRITIS) |

---

## Bagian A — Kekurangan Checklist Direktur

Diurutkan dari yang paling berpengaruh pada keputusan.

### A1. "Sesuai" dapat menyimpan catatan yang sebenarnya temuan

**Kejadian 28/09.** Alur pengiriman sampel dicatat **Sesuai** dengan catatan *"Belum tahu tata
cara"*. Alur limbah dicatat **Sesuai** dengan catatan *"Wajib kontak vendor"*. Bila staf belum
tahu tata caranya, alur itu belum aman; tetapi di rekap ia terhitung hijau, dan tidak ada task
yang lahir.

**Kebutuhan.**
- Bila hasil Sesuai diberi catatan, tampilkan satu pertanyaan: *"Catatan ini perlu tindak
  lanjut?"* Ya → simpan sebagai **Ada temuan** (membuat task seperti biasa). Tidak → tetap
  Sesuai.
- Alternatif yang lebih ringan: hasil ke-4, **Sesuai dengan catatan**, yang dihitung terpisah
  di rekap dan dashboard (kuning, bukan hijau).
- Keputusan pilihan mana: Direktur Operasional.

### A2. Tindak lanjut bertanggal tidak punya pengingat

**Kejadian 28/09.** *"Vendor jemput tanggal 30 di Jemur"* hanya tersimpan sebagai teks catatan.
Tanggal 30 tidak ada yang mengingatkan untuk memastikan penjemputan benar terjadi.

**Kebutuhan.** Dari layar catat hasil, tombol **Ingatkan pada tanggal …** yang membuat task
(ActionItem) dengan `due_at`, penerima bawaan fungsi PIC butir itu, tanpa mengubah hasil cek.

### A3. Tanggal kedaluwarsa emergency kit tercatat sebagai teks bebas

**Kejadian 28/09.** *"Dexa 2/27, epi 3/27, diphen 01/27, idn 10/26"* ditulis di kolom catatan.
Sistem tidak tahu bahwa `idn 10/26` tinggal satu bulan.

**Kebutuhan.**
- Butir bulanan emergency kit mendapat isian terstruktur: nama obat/alat + bulan/tahun ED.
- Sistem menandai otomatis menurut empat tingkat yang sudah ditetapkan: ≤ 12, ≤ 6, ≤ 3, ≤ 1
  bulan. Tingkat ≤ 1 bulan membuat task ke PIC apotek.
- ED terdekat tampil di dashboard (Bagian C).
- Isian ini sebaiknya satu model dengan daftar hampir ED apotek (butir mingguan 5), bukan tabel
  kedua yang berjalan sendiri.

### A4. Label penghitung mudah terbaca terbalik

Tombol siklus menulis `belum 5/13`. Pembacaan cepat "5/13" terbaca sebagai *sudah 5 dari 13*,
padahal artinya *belum 5, sudah 8*.

**Kebutuhan.** Tulis keduanya: `Mingguan · sudah 8/13 · belum 5`. Perubahan teks templat saja.

### A5. Hanya satu cabang per tampilan

Checklist Direktur dipilih per cabang. Untuk mengetahui keadaan Jemur dan Citraland sekaligus,
Direktur harus berpindah cabang dan membandingkan di kepala.

**Kebutuhan.** Matriks butir × cabang (baris: butir; kolom: JMR, CTL; sel: status dan jam
cek). Ini juga menjadi satu panel di dashboard (Bagian C).

### A6. Tidak ada bukti foto pada hasil cek

Kesiapan buka Citraland dicek dari foto yang dikirim lewat WhatsApp; fotonya tidak menempel ke
hasil cek. Aturan "dicek dengan melihat bukti, bukan dengan bertanya" belum punya tempat
menyimpan buktinya.

**Kebutuhan.** Lampiran foto pada `AuditCheck` memakai `core.Attachment` yang sudah ada.
Opsional untuk semua butir, tidak wajib.

### A7. Saran cek langsung tidak terhubung dengan yang dikerjakan

Kotak "Saran cek langsung" memilih tiga rincian acak, tetapi tidak menandai apakah saran itu
kemudian benar dicek langsung.

**Kebutuhan.** Tampilkan `sudah dicek langsung hari ini: n dari 3`. Rekap mingguan
menunjukkan berapa hari aturan uji petik 2–3 butir terpenuhi.

### A8. Tidak ada riwayat dan temuan berulang

Setiap periode berdiri sendiri. Butir yang tiga minggu berturut-turut bertemuan tidak tampak
berbeda dari butir yang baru sekali.

**Kebutuhan.** Riwayat per butir (8 periode terakhir sebagai deret titik hijau/kuning/merah)
dan penanda **berulang** bila temuan muncul ≥ 2 periode berturut-turut.

### A9. Tidak ada keluaran untuk laporan harian

Hasil checklist hari ini disalin manual ke laporan kegiatan harian (JD-GOV-L01).

**Kebutuhan.** Tombol **Salin ringkasan** yang menghasilkan teks: jumlah per siklus, butir
belum dicek, catatan yang ada, dan temuan baru. Tidak perlu membuat docx dari aplikasi.

### A10. Temuan tanpa pemegang fungsi PIC tidak punya penerima

Sudah didokumentasikan di `panduan-direktur.md`: bila fungsi PIC butir belum ada pemegangnya di
cabang itu, temuan tercatat tanpa penerima. Di dashboard, temuan seperti ini perlu kolom
sendiri, **tanpa penerima**, agar tidak tenggelam.

---

## Bagian B — Hierarki Permintaan dan Jalur Informasi

Ini dasar untuk dashboard, bukan fitur terpisah.

### B1. Aturan yang ditetapkan 28 September

1. **Owner menyampaikan permintaan langsung kepada Direktur Operasional.**
2. **Direktur Operasional menjadi penghubung** antara staf dan Owner: meneruskan permintaan
   menjadi task ke PIC/staf, dan melaporkan balik statusnya.
3. **Owner dan Direktur tetap dapat menerima masukan dan temuan langsung dari staf.**
4. Tujuannya hierarki yang sehat antartingkatan dan prinsip **check and recheck of power**:
   jalur perintah melewati Direktur, tetapi jalur informasi tidak disaring oleh satu orang.

### B2. Akibatnya pada peran dan akses

| Peran | Keadaan sekarang | Yang dibutuhkan |
|---|---|---|
| `OWNER` | Hanya baca (`peran-dan-akses.md`) | Tetap hanya baca untuk data operasional, **ditambah** satu kemampuan: membuat **Permintaan Owner** yang penerimanya **hanya** Direktur Operasional |
| `AOM` | Membuat task ke PIC/staf | Menerima Permintaan Owner, memecahnya menjadi satu atau beberapa task, dan statusnya kembali terlihat oleh Owner |
| Staf | Masukan dan laporan lewat modul Reports | Tetap. Masukan/temuan staf terlihat oleh Owner **dan** Direktur tanpa perlu diteruskan |

- Owner **tidak** menugaskan staf langsung dari aplikasi. Ini yang menjaga Direktur sebagai
  penghubung.
- Permintaan Owner harus dapat dilacak ke task turunannya (satu permintaan → n task), dan
  status permintaan dihitung dari task-task itu. Ini sekaligus menjalankan aturan **laporan
  balik** (sudah/belum pada hari yang sama) di dalam sistem.
- Otorisasi ditegakkan di server, sesuai `AGENTS.md`.

### B3. Yang perlu diputuskan sebelum dibangun

| # | Perkara | Diputuskan oleh |
|---|---|---|
| 1 | Owner mendapat kemampuan membuat Permintaan Owner (satu-satunya pengecualian dari hanya-baca) | Owner dan Direktur Operasional |
| 2 | Direktur Utama: memakai peran `OWNER` yang sama, atau dibedakan | Owner dan/atau Direktur Utama |
| 3 | Apakah Owner melihat seluruh task staf, atau hanya task turunan Permintaan Owner ditambah ringkasan | Owner |

---

## Bagian C — Dashboard Pandangan Menyeluruh (Bird View)

Satu halaman, dua penonton: **Direktur Operasional** (memantau cepat, lalu bertindak) dan
**Owner** (melihat keadaan tanpa bertanya). Isi sama, tombol berbeda: Owner hanya melihat dan
membuat Permintaan Owner; Direktur dapat menindaklanjuti.

### C1. Baris atas — keadaan per cabang (satu kartu per cabang)

| Indikator | Sumber |
|---|---|
| Hari operasional: sudah buka / belum / tutup, dan jamnya | `core.OperationalDay` |
| Checklist staf hari ini: butir wajib belum diisi | `team_overview()` |
| Checklist Direktur: sudah/belum per siklus | `pending_summary()` |
| Temuan terbuka, termasuk **tanpa penerima** | `open_findings()` |
| Task lewat target waktu | `ActionItem.due_at` |
| ED terdekat (obat emergensi dan apotek) | Bagian A3 |
| Permintaan Owner yang belum dilapor balik | Bagian B2 |

Warna hanya tiga: hijau (beres), kuning (perlu dilihat), merah (lewat batas). Tidak ada skor
atau peringkat antarorang, sesuai prinsip `team_overview()`.

### C2. Kanban

Kolom mengikuti status yang sudah ada, tanpa status baru:

| Kolom | Dari data |
|---|---|
| Baru | `ActionItem.status = BARU` |
| Dikerjakan | `DIKERJAKAN` |
| Menunggu konfirmasi | ada `TaskAssignment.status = SUBMITTED` |
| Selesai (7 hari) | `SELESAI`, diperbarui ≤ 7 hari |

- Kartu: judul, cabang, penerima/fungsi PIC, target waktu, sumber (Permintaan Owner, temuan
  Direktur, catatan, modul lain), umur task.
- Penyaring: cabang, sumber, penerima, hanya Permintaan Owner.
- `BATAL` tidak ditampilkan di papan tetapi tetap ada di riwayat. Tidak ada penghapusan.
- Tahap pertama **tanpa drag-and-drop**: status tetap berubah lewat alur task yang sudah ada,
  agar konfirmasi dan jejak audit (`TaskEvent`) tidak terlewati.

### C3. Matriks Eisenhower

Dua sumbu: **penting** dan **mendesak**. Saat ini `ActionItem` hanya punya satu sumbu
(`priority`). Usulan bertahap:

**Tahap 1 — diturunkan dari data yang ada, tanpa migrasi.**
- Penting = `priority` TINGGI atau KRITIS, **atau** sumbernya Permintaan Owner.
- Mendesak = `due_at` ≤ 48 jam lagi atau sudah lewat, **atau** `priority` KRITIS.

| | Mendesak | Tidak mendesak |
|---|---|---|
| **Penting** | I. Kerjakan sekarang | II. Jadwalkan |
| **Tidak penting** | III. Delegasikan | IV. Tinjau ulang |

Kuadran IV bernama **Tinjau ulang**, bukan "hapus", karena task tidak dihapus.

**Tahap 2 — bila Owner ingin menempatkan sendiri.** Tambah field `important` (boolean)
pada `ActionItem`, dengan migrasi dan test. Hanya dikerjakan bila Tahap 1 terbukti kurang.

Angka 48 jam adalah usulan; disimpan di `ClinicConfig` agar dapat diubah tanpa kode.

### C4. Aliran masukan dan temuan staf

Panel kecil: masukan dan temuan staf 7 hari terakhir yang terlihat oleh Owner dan Direktur
bersamaan (Bagian B1 butir 3). Laporan rahasia tetap mengikuti kapabilitas
`report.view_confidential`.

---

## Bagian D — Urutan Pengerjaan yang Diusulkan

| Fase | Isi | Migrasi | Catatan |
|---|---|---|---|
| 1 | A4 label penghitung, A9 salin ringkasan | Tidak | Paling kecil, langsung terasa |
| 2 | C1 kartu per cabang + C2 kanban (baca saja) + A5 matriks cabang | Tidak | Bird view Direktur |
| 3 | C3 Eisenhower Tahap 1 | Tidak | Konfigurasi ambang di `ClinicConfig` |
| 4 | B2 Permintaan Owner | Ya | Menunggu keputusan B3 |
| 5 | A1, A2, A6, A7 | Ya (A1 opsi hasil ke-4, A6 relasi lampiran) | Penyempurnaan checklist |
| 6 | A3 ED terstruktur, A8 riwayat | Ya | Disatukan dengan daftar hampir ED apotek |

Di luar dokumen ini, dicatat supaya tidak tercampur: modul finance (mirip Accurate) dan
perluasan absensi geolokasi + phototag adalah pekerjaan terpisah.
