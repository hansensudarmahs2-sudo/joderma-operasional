# UAT 5-Day Pilot Plan — JoDerma Staff Ops

**Versi:** 1.0
**Tanggal:** 11 September 2026
**Status:** Menunggu persetujuan owner
**Pemilik pilot:** Manajemen Klinik JoDerma
**Penanggung jawab teknis:** Admin teknis JoDerma

---

## 1. Tujuan pilot

Membuktikan bahwa JoDerma Staff Ops dapat menjalankan **satu hari operasional penuh
secara berulang** di kondisi klinik nyata, tanpa menambah beban kerja staf dan tanpa
kehilangan data.

Pilot ini menjawab lima pertanyaan:

1. Apakah staf dapat menyelesaikan pekerjaan hariannya di sistem tanpa kembali ke buku/chat?
2. Apakah checklist pembukaan dapat diselesaikan dalam ≤10 menit (target PRD 3.2)?
3. Apakah alur kas dual-control berjalan wajar dengan jumlah staf yang benar-benar ada?
4. Apakah aturan rotasi perawat dapat diterima sebagai adil dan transparan oleh perawat?
5. Apakah ada kebutuhan operasional nyata yang belum tertangkap PRD?

Pilot **bukan** untuk menambah fitur. Temuan fitur baru dicatat sebagai backlog fase 2,
bukan dikerjakan selama pilot.

---

## 2. Scope

### Termasuk

- 5 hari operasional berturut-turut di **satu cabang** (Jemur Andayani).
- Kedelapan modul PRD dipakai dalam pekerjaan nyata:
  pembukaan, kas, antrean, giliran perawat, jadwal istirahat, komplain, masukan, kerusakan.
- Review supervisor harian dan review owner di akhir pilot.
- Akses melalui Tailscale dari perangkat staf yang biasa dipakai.
- Pengumpulan issue register dan feedback staf.

### Tidak termasuk

- Cabang G-Walk Citraland (menyusul setelah go-live cabang pertama).
- Migrasi data historis dari buku lama.
- Fitur fase 2: integrasi POS, import appointment, notifikasi WhatsApp/email,
  perhitungan komisi rupiah, PWA/aplikasi native.
- Halaman admin template checklist yang lebih lengkap (pengelolaan item sementara
  lewat Django admin oleh admin teknis).
- Penggantian proses kertas/WA yang tidak tercakup 8 modul PRD.

### Mode operasi: paralel

Selama 5 hari, klinik **tetap menjalankan pencatatan lama** (buku/chat) sebagai
jaring pengaman. Sistem adalah sumber kebenaran yang diuji; buku lama adalah cadangan.
Ini mencegah gangguan operasional bila terjadi kegagalan, dan memungkinkan
perbandingan data di akhir pilot.

---

## 3. Peserta

| Peran pilot | Siapa | Tanggung jawab selama pilot |
|---|---|---|
| Sponsor pilot | Owner/Manajemen | Menyetujui go/no-go, memutuskan OPEN DECISION, review akhir |
| Pilot lead | Supervisor operasional | Menjalankan review harian, mengisi daily checklist, memutuskan eskalasi |
| Peserta front desk | 2 staf front desk/kasir | Antrean, pembayaran, kas awal/akhir |
| Peserta perawat | Seluruh perawat yang bertugas | Checklist ruang, tindakan berkomisi, jadwal istirahat |
| Admin teknis | Admin IT | Backup, akses Tailscale, akun, konfigurasi, perbaikan issue |
| Pencatat issue | Supervisor (dibantu admin) | Mengisi `UAT_ISSUE_REGISTER.md` |

**Prasyarat peserta:** setiap orang punya akun pribadi sendiri, sudah mengganti
password awal, dan sudah membaca `docs/panduan-staf.md` (± 10 menit).

---

## 4. Aktivitas per hari

### H-1 — Persiapan (sebelum Hari 1)

- [ ] `manage.py pilot_check` menghasilkan **0 blocker**.
- [ ] Akun dibuat untuk semua peserta; password demo sudah diganti.
- [ ] Template checklist disesuaikan dengan alat/BHP nyata klinik.
- [ ] Kategori tindakan dan eligibility perawat diisi sesuai kompetensi nyata.
- [ ] Konfigurasi kebijakan disetel sesuai keputusan owner (lihat `OWNER_DECISION_REVIEW.md`).
- [ ] Backup malam berjalan dan **satu uji restore lulus**.
- [ ] Briefing staf 20 menit + bagikan `docs/panduan-staf.md`.
- [ ] Sepakati kanal pelaporan masalah (grup WA khusus pilot / catat di form).

### Hari 1 — Alur inti, pendampingan penuh

Fokus: pembukaan, kas, antrean. Supervisor dan admin teknis hadir mendampingi.

- Pagi: buat sesi hari, checklist pembukaan (**catat waktu mulai–selesai**), kas awal + verifikasi.
- Siang: antrean pasien nyata, status pembayaran, jadwal istirahat.
- Sore: kas akhir, tutup hari.
- Akhir hari: isi `DAILY_PILOT_CHECKLIST.md`, catat issue.

Skenario UAT yang dijalankan: **OPN-01..05, CSH-01..05, QUE-01..05, SUP-01, SUP-02**.

### Hari 2 — Giliran perawat dan jadwal

Fokus: rotasi komisi dan istirahat. Perawat memberi penilaian keadilan urutan.

- Pagi: roster perawat, ulangi alur Hari 1.
- Siang: tindakan berkomisi berjalan normal; uji minimal satu skip dan satu pembatalan.
- Sore: perawat memeriksa ledger — "apakah urutan hari ini masuk akal?"
- Skenario: **NUR-01..06, BRK-01..04**, ulangi OPN/CSH/QUE.

### Hari 3 — Buku komplain, masukan, kerusakan

Fokus: tiga buku catatan dan tindak lanjutnya.

- Catat komplain/saran/kerusakan **nyata** yang muncul hari itu.
- Bila tidak ada kejadian nyata, jalankan skenario latihan dan tandai jelas di catatan.
- Uji komplain terbatas: pastikan staf di luar cakupan benar-benar tidak bisa membuka.
- Skenario: **CMP-01..05, SUG-01..03, DMG-01..06**.

### Hari 4 — Pengecualian, override, dan kondisi tidak normal

Fokus: apa yang terjadi saat keadaan tidak ideal.

- Sengaja buat selisih kas kecil dan selesaikan lewat alur yang benar.
- Uji `READY_WITH_ISSUES` dengan alasan.
- Uji override urutan perawat dan reorder antrean beralasan.
- Uji buka kembali hari yang sudah ditutup.
- Uji akses ditolak: staf biasa mencoba membuka kas dan audit.
- Skenario: **EXC-01..06, SEC-01..04**.

### Hari 5 — Review, laporan, dan keputusan

Fokus: apakah data yang terkumpul berguna bagi manajemen.

- Jalankan alur harian normal seperti biasa.
- Owner membuka **Laporan**, memeriksa 5 hari data, mengekspor CSV.
- Bandingkan data sistem vs buku lama (spot check: jumlah antrean, total kas, giliran perawat).
- Supervisor dan owner membaca audit log untuk satu kejadian override.
- Staf mengisi `PILOT_FEEDBACK_FORM.md`.
- Rapat penutup 45 menit: bahas issue register, feedback, dan keputusan go-live.
- Skenario: **RPT-01..04, OWN-01..03, ADM-01..04**.

---

## 5. Success criteria

Pilot dinyatakan **berhasil** bila seluruh poin berikut tercapai:

| # | Kriteria | Ukuran | Sumber |
|---|---|---|---|
| S1 | Sesi pembukaan selesai setiap hari | 5 dari 5 hari | Dashboard |
| S2 | Rekonsiliasi kas terverifikasi setiap hari | 5 dari 5 hari, kas awal & akhir | Modul Kas |
| S3 | Perubahan manual urutan perawat selalu beralasan | 100% override punya alasan + pelaku | Ledger + audit |
| S4 | Laporan baru diberi penanggung jawab | ≥90% dalam 1 hari operasional | Modul Kerusakan |
| S5 | Checklist pembukaan selesai tepat waktu | ≤10 menit, diukur ≥3 dari 5 hari | Catatan harian |
| S6 | Tidak ada akses dari luar tailnet | 0 kejadian | `verify_deployment.sh` + audit |
| S7 | Tidak ada issue Critical yang belum ditutup | 0 terbuka di akhir pilot | Issue register |
| S8 | Tidak ada kehilangan data | 0 kejadian; backup harian + 1 restore lulus | Log backup |
| S9 | Staf menilai sistem tidak lebih berat dari cara lama | Mayoritas peserta menjawab "sama" atau "lebih mudah" | Feedback form |
| S10 | Data sistem cocok dengan buku lama | Selisih terjelaskan pada spot check 5 hari | Perbandingan manual |

**Berhasil bersyarat:** S1–S8 tercapai tetapi S9 atau S10 bermasalah → perbaiki temuan,
lanjutkan pilot 3 hari tambahan sebelum go-live.

---

## 6. Stop criteria

Hentikan pilot **segera** (kembali ke proses lama, jangan lanjut ke hari berikutnya)
bila salah satu terjadi:

| # | Pemicu | Tindakan |
|---|---|---|
| T1 | Kehilangan atau kerusakan data yang tidak dapat dipulihkan dari backup | Stop, restore, investigasi akar masalah |
| T2 | Aplikasi dapat diakses dari luar tailnet / dari internet publik | Stop segera, matikan Serve, audit akses |
| T3 | Data pasien atau nominal kas terlihat oleh pengguna tanpa izin | Stop, cabut akses, audit, perbaiki sebelum lanjut |
| T4 | Aplikasi tidak dapat dipakai >2 jam pada jam operasional | Stop hari itu, lanjut manual, evaluasi teknis |
| T5 | Sistem menyebabkan kesalahan pelayanan pasien nyata | Stop, tinjau alur kerja |
| T6 | Issue Critical baru muncul dua hari berturut-turut | Stop, evaluasi kelayakan pilot |

Keputusan stop diambil **supervisor (pilot lead)** dan dilaporkan ke owner pada hari
yang sama. Stop bukan kegagalan proyek — ini pengaman yang memang disediakan.

---

## 7. Rollback criteria dan prosedur

### Kapan rollback

- Stop criteria T1, T2, atau T3 terjadi.
- Atau owner memutuskan pilot dihentikan permanen.

### Prosedur rollback (target ≤30 menit)

1. **Beri tahu staf** — satu pesan: "Mulai sekarang kembali ke buku/checklist kertas."
   Klinik tidak pernah kehilangan kemampuan beroperasi karena pencatatan lama berjalan paralel.
2. **Matikan akses aplikasi**
   ```bash
   sudo tailscale serve --https=443 off      # staf tidak dapat lagi mengakses
   docker compose stop app                    # hentikan aplikasi
   ```
3. **Amankan data** — jangan hapus apa pun.
   ```bash
   APP_DIR=$PWD ./scripts/backup.sh           # snapshot kondisi saat insiden
   cp logs/app.log backups/insiden-$(date +%F).log
   ```
4. **Cetak/salin data hari berjalan** dari backup agar operasional manual tidak
   kehilangan konteks (daftar antrean, catatan kas, laporan terbuka).
5. **Catat insiden** di `UAT_ISSUE_REGISTER.md` dengan severity Critical.
6. **Laporkan ke owner** dalam 24 jam: apa yang terjadi, data apa yang terdampak,
   apa yang diperlukan sebelum mencoba lagi.

### Yang TIDAK dilakukan saat rollback

- Jangan menghapus database atau lampiran — bukti insiden diperlukan.
- Jangan menghapus audit log (memang tidak bisa dari aplikasi).
- Jangan "memperbaiki cepat" di server produksi tanpa pencatatan.

---

## 8. Risiko pilot dan mitigasi

| Risiko | Dampak | Mitigasi |
|---|---|---|
| Staf sibuk, sistem jadi beban tambahan | Data tidak lengkap | Mode paralel, pendampingan Hari 1–2, briefing singkat |
| Hanya 1 front desk pada shift tertentu | Dual-control kas macet | Supervisor menjadi penghitung kedua; bila sering terjadi, jadikan OPEN DECISION |
| Perawat merasa rotasi tidak adil | Penolakan modul komisi | Tampilkan kebijakan + ledger; kumpulkan keberatan sebagai OPEN DECISION, jangan ubah aturan sepihak |
| Tidak ada komplain/kerusakan nyata pada Hari 3 | Modul tidak teruji | Jalankan skenario latihan, tandai jelas sebagai latihan |
| Kebutuhan fitur baru bermunculan | Scope creep | Semua masuk backlog fase 2; hanya blocker yang dikerjakan saat pilot |
| Internet/Tailscale terganggu | Akses terhenti | Runbook kontingensi kertas + entry susulan |

---

## 9. Definisi selesai pilot

Pilot dianggap selesai bila:

- [ ] 5 hari operasional terlaksana (atau dihentikan sesuai stop criteria).
- [ ] `UAT_TEST_SCENARIOS.md` terisi kolom Actual Result dan Pass/Fail untuk semua skenario.
- [ ] `UAT_ISSUE_REGISTER.md` lengkap; setiap Critical/High berstatus Closed atau Deferred beralasan.
- [ ] Seluruh peserta mengisi `PILOT_FEEDBACK_FORM.md`.
- [ ] `OWNER_DECISION_REVIEW.md` terisi keputusan owner untuk kategori
      "must decide before production".
- [ ] `GO_LIVE_READINESS_CHECKLIST.md` dievaluasi dan ditandatangani owner.
- [ ] Rapat penutup terlaksana dengan keputusan tertulis: **go-live / perbaiki dulu / tidak dilanjutkan**.
