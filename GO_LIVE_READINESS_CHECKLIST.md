# Go-Live Readiness Checklist — JoDerma Staff Ops

**Versi:** 1.0
**Diisi setelah:** pilot 5 hari selesai
**Diputuskan oleh:** Owner/Manajemen JoDerma
**Aturan:** setiap butir **wajib** dicentang atau diberi pengecualian tertulis yang
disetujui owner. Butir bertanda 🔒 **tidak boleh** dikecualikan — bila gagal, go-live ditunda.

---

## 1. Hasil pilot

- [ ] 🔒 Pilot 5 hari terlaksana penuh (tidak dihentikan oleh stop criteria)
- [ ] Success criteria S1 — sesi pembukaan selesai 5 dari 5 hari
- [ ] Success criteria S2 — kas terverifikasi 5 dari 5 hari (awal & akhir)
- [ ] 🔒 Success criteria S3 — 100% override urutan perawat punya alasan dan pelaku
- [ ] Success criteria S4 — ≥90% laporan kerusakan diberi PJ dalam 1 hari operasional
- [ ] Success criteria S5 — checklist ≤10 menit pada ≥3 dari 5 hari
- [ ] 🔒 Success criteria S6 — nol akses dari luar tailnet
- [ ] 🔒 Success criteria S7 — nol issue Critical yang belum ditutup
- [ ] 🔒 Success criteria S8 — nol kehilangan data; backup harian + 1 restore lulus
- [ ] Success criteria S9 — mayoritas staf menilai "sama" atau "lebih mudah"
- [ ] Success criteria S10 — data sistem cocok dengan buku lama (selisih terjelaskan)

Ringkasan: ____ dari 10 kriteria tercapai. Yang tidak tercapai: __________________

---

## 2. Test scenarios dan issue register

- [ ] 🔒 Seluruh 64 skenario di `UAT_TEST_SCENARIOS.md` sudah diisi hasilnya
- [ ] 🔒 Seluruh skenario **SEC-01..04** berstatus Pass
- [ ] 🔒 Skenario **ADM-02** (admin teknis tanpa hak bisnis) berstatus Pass
- [ ] 🔒 Tidak ada issue **Critical** berstatus selain Closed
- [ ] Setiap issue **High** berstatus Closed atau Deferred dengan persetujuan owner tertulis
- [ ] Issue **Medium** punya rencana perbaikan bertanggal
- [ ] Backlog fase 2 sudah dicatat dan tidak dikerjakan sebelum go-live

Jumlah issue: Critical ___ · High ___ · Medium ___ · Low ___
Yang di-*defer* beserta alasannya: __________________

---

## 3. Keputusan bisnis (`OWNER_DECISION_REVIEW.md`)

- [ ] 🔒 D1 — Definisi pos kas **CONFIRMED**
- [ ] 🔒 D2 — Aturan dual-control **CONFIRMED**
- [ ] 🔒 D3 — Status yang menahan nomor antrean **CONFIRMED**
- [ ] 🔒 D6 — Aturan skip/batal perawat **CONFIRMED** dan sudah dibahas bersama perawat
- [ ] 🔒 D8 — Hak akses data sensitif **CONFIRMED**
- [ ] D4 — Aturan prioritas/no-show difinalkan dari data pilot
- [ ] D5 — Dasar perhitungan giliran difinalkan
- [ ] D7 — Angka minimum staf difinalkan
- [ ] 🔒 D9 — SLA final ditetapkan, termasuk basis perhitungan (jam berjalan vs jam operasional)
- [ ] 🔒 D10 — **Kebijakan retensi data disetujui manajemen dan penasihat hukum**
- [ ] D11 — Perangkat host produksi ditetapkan
- [ ] 🔒 D12 — Prosedur kontingensi tertulis, tercetak, dan dilatih
- [ ] Seluruh OPEN DECISION (OD-A..OD-D) sudah dijawab
- [ ] 🔒 `DECISIONS.md` diperbarui: status PROVISIONAL → CONFIRMED beserta tanggal

---

## 4. Kesiapan data dan konfigurasi

- [ ] 🔒 `manage.py pilot_check` menghasilkan **0 blocker**
- [ ] 🔒 Tidak ada akun yang masih memakai password demo
- [ ] Seluruh staf punya akun pribadi; tidak ada akun bersama
- [ ] Peran dan kapabilitas setiap akun sesuai keputusan D8
- [ ] Akun peserta pilot yang tidak lagi diperlukan sudah dinonaktifkan (bukan dihapus)
- [ ] Template checklist mencerminkan alat dan BHP nyata, termasuk nilai minimum
- [ ] Kategori tindakan dan eligibility perawat sesuai kompetensi nyata
- [ ] Daftar aset awal terisi (bila modul aset dipakai)
- [ ] Konfigurasi kebijakan sesuai keputusan owner (`Admin ▸ Konfigurasi`)
- [ ] Hari libur klinik dimasukkan
- [ ] 🔒 Data uji/latihan dari pilot sudah dibersihkan atau ditandai jelas

Cara membersihkan data latihan: __________________

---

## 5. Keamanan dan jaringan

- [ ] 🔒 `APP_PORT=<port> ./scripts/verify_deployment.sh` — seluruh pemeriksaan LULUS
- [ ] 🔒 Aplikasi hanya listen di `127.0.0.1:<APP_PORT>`, bukan `0.0.0.0`
- [ ] 🔒 Tailscale **Serve** aktif; **Funnel tidak aktif**
- [ ] 🔒 Diuji dari jaringan publik tanpa Tailscale → **gagal total**
- [ ] 🔒 Diuji dari perangkat tailnet tidak berizin → **ditolak kebijakan**
- [ ] Kebijakan Tailscale deny-by-default diterapkan; blok `tests` lulus saat disimpan
- [ ] Grup staf hanya diberi tcp:443; port aplikasi tidak diberikan ke siapa pun
- [ ] Akses SSH terbatas pada grup admin teknis
- [ ] `.env` permission 600 dan tidak ada di git
- [ ] `DJANGO_SECRET_KEY` produksi baru (bukan nilai contoh/uji)
- [ ] `DJANGO_DEBUG=false` di produksi
- [ ] `manage.py check --deploy` bersih
- [ ] Perangkat staf terkunci dengan PIN/biometrik (perangkat bersama di klinik)

Tanggal uji akses publik: ______ · Diuji oleh: ______

---

## 6. Backup dan pemulihan

- [ ] 🔒 Backup otomatis berjalan setiap malam selama pilot tanpa gagal
- [ ] 🔒 Backup terenkripsi (`.enc`) — `BACKUP_PASSPHRASE` terisi
- [ ] 🔒 **Uji restore lulus**: database terbaca dan lampiran terbuka
- [ ] 🔒 `BACKUP_PASSPHRASE` disimpan di brankas/manajer kata sandi **terpisah dari server**
- [ ] Salinan backup kedua ada di media/perangkat berbeda (`BACKUP_SECOND_COPY_DIR`)
- [ ] Retensi backup berjalan: 7 harian, 4 mingguan, 12 bulanan
- [ ] Jadwal uji restore kuartalan ditetapkan; penanggung jawab: ______
- [ ] Ruang disk mencukupi untuk 12 bulan ke depan (estimasi: ____ GB)

Tanggal uji restore terakhir: ______ · Hasil: ______

---

## 7. Keandalan operasional

- [ ] 🔒 Auto-start aktif: aplikasi kembali sendiri setelah host di-reboot
- [ ] 🔒 Reboot host benar-benar diuji, bukan diasumsikan
- [ ] UPS terpasang dan diuji
- [ ] Health check hijau dan dipantau
- [ ] Rotasi log aktif; disk tidak akan penuh oleh log
- [ ] Waktu host akurat dan zona waktu `Asia/Jakarta`
- [ ] Peringatan lokal untuk disk penuh dan backup gagal sudah disiapkan

Tanggal uji reboot: ______ · Hasil: ______

---

## 8. Manusia dan proses

- [ ] Seluruh staf sudah membaca `docs/panduan-staf.md`
- [ ] Seluruh staf sudah memakai sistem minimal 3 dari 5 hari pilot
- [ ] Staf yang tidak ikut pilot mendapat pelatihan susulan
- [ ] Supervisor memahami: review pembukaan, verifikasi kas, penutupan hari, audit log
- [ ] Admin teknis memahami: backup, restore, akun, konfigurasi, Tailscale
- [ ] Owner memahami: laporan, ekspor, penelusuran audit
- [ ] 🔒 Ditetapkan **tanggal penghentian pencatatan lama** (akhir mode paralel): ______
- [ ] Prosedur darurat kertas tercetak dan tersedia di klinik
- [ ] Kontak dukungan teknis diketahui seluruh staf, termasuk di luar jam kerja
- [ ] Proses onboarding staf baru dan offboarding staf keluar ditetapkan

---

## 9. Dokumentasi

- [ ] `docs/runbook.md` sesuai kondisi produksi yang sebenarnya
- [ ] `docs/panduan-staf.md` diperbarui bila alur berubah setelah pilot
- [ ] `DECISIONS.md` mencerminkan keputusan final
- [ ] Perubahan konfigurasi selama pilot tercatat
- [ ] Hasil pilot (`UAT_TEST_SCENARIOS.md`, `UAT_ISSUE_REGISTER.md`) diarsipkan
- [ ] Rangkuman umpan balik staf diarsipkan

---

## 10. Rencana pasca go-live

- [ ] Periode pemantauan ketat ditetapkan (disarankan 2 minggu pertama)
- [ ] Penanggung jawab pemantauan harian: ______
- [ ] Ambang batas untuk rollback pasca go-live ditetapkan
- [ ] Jadwal review 30 hari (mengukur indikator PRD 3.2) ditetapkan: ______
- [ ] Backlog fase 2 diprioritaskan bersama owner
- [ ] Rencana cabang kedua (G-Walk Citraland) — perkiraan waktu: ______

---

## 11. Keputusan go-live

Berdasarkan seluruh butir di atas:

☐ **GO-LIVE** — seluruh butir 🔒 terpenuhi; sistem menjadi sumber kebenaran mulai ______

☐ **GO-LIVE BERSYARAT** — go-live dengan mode paralel diperpanjang sampai ______
    Syarat yang harus selesai: __________________

☐ **TUNDA** — perbaiki dulu, evaluasi ulang pada ______
    Yang menghalangi: __________________

☐ **TIDAK DILANJUTKAN** — alasan: __________________

### Butir 🔒 yang tidak terpenuhi (bila ada)

| Butir | Mengapa belum terpenuhi | Rencana | Target tanggal |
|---|---|---|---|
| | | | |

> Pengecualian terhadap butir 🔒 hanya sah bila ditandatangani owner dan disertai
> mitigasi tertulis. Butir keamanan (bagian 5) dan retensi data (D10) **tidak dapat
> dikecualikan** karena menyangkut kepatuhan dan kerahasiaan data pasien.

---

## Tanda tangan

| Peran | Nama | Keputusan | Tanda tangan | Tanggal |
|---|---|---|---|---|
| Pilot lead (supervisor) | | ☐ setuju ☐ keberatan | | |
| Admin teknis | | ☐ setuju ☐ keberatan | | |
| Perwakilan front desk | | ☐ setuju ☐ keberatan | | |
| Perwakilan perawat | | ☐ setuju ☐ keberatan | | |
| **Owner/Manajemen** | | ☐ **GO-LIVE** ☐ tunda | | |

Keberatan yang dicatat (bila ada):
_______________________________________________________________________________
