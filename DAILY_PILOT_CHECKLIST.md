# Daily Pilot Checklist — JoDerma Staff Ops

**Cara pakai:** salin satu blok untuk setiap hari pilot. Diisi **supervisor** (pilot lead),
ditinjau **owner** di akhir hari. Perkiraan waktu pengisian: 10 menit pagi, 10 menit sore.

---

## Hari ke-___  ·  Tanggal: __________  ·  Supervisor: __________

### A. Sebelum buka (target selesai 15 menit sebelum jam buka)

- [ ] Aplikasi dapat diakses dari perangkat staf
      (buka hostname Tailscale; bila gagal, hubungi admin teknis segera)
- [ ] Sesi hari operasional dibuat
- [ ] Checklist pembukaan mulai diisi — **jam mulai: ______**
- [ ] Checklist pembukaan selesai — **jam selesai: ______**  → durasi: ____ menit *(target ≤10)*
- [ ] Kas awal dihitung oleh: __________
- [ ] Kas awal diverifikasi oleh orang berbeda: __________
- [ ] Item bermasalah pagi ini sudah ditindaklanjuti (laporan kerusakan / action item)
- [ ] Roster perawat hari ini disusun
- [ ] Jadwal istirahat/makan/ibadah hari ini dibuat
- [ ] Status hari: ☐ Siap  ☐ Siap dengan catatan (alasan: __________________)

### B. Sepanjang hari (cek dashboard 2–3 kali)

- [ ] Antrean dicatat di sistem, bukan hanya di buku
- [ ] Status pembayaran konsultasi diperbarui saat pasien membayar
- [ ] Tindakan berkomisi ditugaskan lewat sistem
- [ ] Komplain/saran/kerusakan yang muncul hari ini dicatat di sistem
- [ ] Catatan kritis (bila ada) langsung ditriase
- [ ] Tidak ada staf yang memakai akun orang lain

Isi angka dari dashboard sore hari:

| Ukuran | Jumlah |
|---|---|
| Total pasien di antrean | |
| Pasien selesai dilayani | |
| Batal / no-show | |
| Tindakan berkomisi selesai | |
| Override urutan perawat | |
| Komplain baru | |
| Saran baru | |
| Laporan kerusakan baru | |
| Catatan lewat target waktu | |

### C. Sebelum tutup

- [ ] Kas akhir dihitung oleh: __________
- [ ] Kas akhir diverifikasi oleh orang berbeda: __________
- [ ] Selisih kas hari ini: Rp __________ (bila ≠ 0, alasan: __________________)
- [ ] Semua laporan kerusakan baru sudah punya penanggung jawab
- [ ] Hari operasional ditutup
- [ ] Bila ditutup dengan override, alasan: __________________

### D. Perbandingan dengan pencatatan lama (mode paralel)

- [ ] Jumlah pasien di sistem **sama** dengan catatan buku: ☐ sama  ☐ berbeda (selisih: ____)
- [ ] Total kas sistem **sama** dengan hitungan manual: ☐ sama  ☐ berbeda (selisih: Rp ____)
- [ ] Giliran perawat di sistem **sesuai** kenyataan lapangan: ☐ sesuai  ☐ tidak (jelaskan di bawah)

Penjelasan perbedaan (bila ada):
_______________________________________________________________________________

### E. Kesehatan sistem (diisi admin teknis, boleh via telepon)

- [ ] Health check hijau: `curl -fsS http://127.0.0.1:${APP_PORT:-8731}/health/`
- [ ] Backup semalam berhasil (cek `logs/backup.log`)
- [ ] Ruang disk masih di bawah 80%
- [ ] Tidak ada error mencolok di log aplikasi
- [ ] Tidak ada percobaan akses dari luar tailnet

### F. Temuan hari ini

| ID | Judul singkat | Severity | Sudah dicatat di issue register? |
|---|---|---|---|
| | | | ☐ ya |
| | | | ☐ ya |
| | | | ☐ ya |

- Jumlah temuan **Critical** hari ini: ____
      → bila ≥1, evaluasi stop criteria bersama owner **hari ini juga**
- Jumlah temuan **High** hari ini: ____

### G. Suasana tim (satu kalimat, jujur)

Apa yang paling memperlambat staf hari ini?
_______________________________________________________________________________

Apa yang terasa membantu hari ini?
_______________________________________________________________________________

### H. Keputusan akhir hari

- [ ] **Lanjut** ke hari pilot berikutnya
- [ ] **Lanjut dengan perbaikan** — yang harus diperbaiki malam ini: ______________
- [ ] **Stop pilot** — pemicu stop criteria: ☐T1 ☐T2 ☐T3 ☐T4 ☐T5 ☐T6
      → jalankan prosedur rollback di `UAT_5_DAY_PILOT_PLAN.md` bagian 7

**Tanda tangan supervisor:** ____________   **Ditinjau owner:** ____________
