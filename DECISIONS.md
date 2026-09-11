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

## Default operasional lain (Bagian 29)

| Keputusan | Nilai | Status |
|---|---|---|
| Cakupan instalasi | Satu cabang, satu `OperationalDay` per tanggal | PROVISIONAL |
| Zona waktu | Asia/Jakarta | CONFIRMED (PRD 5) |
| Jam operasional | 12.00–21.00 | PROVISIONAL (dari website joderma.id) |
| Override | Hanya supervisor, selalu wajib alasan | PROVISIONAL |
| Hard-delete komplain/kerusakan | Tidak pernah | PROVISIONAL |
| Session idle / absolute timeout | 30 menit / 12 jam | PROVISIONAL |
| Panjang password minimum | 12 karakter | PROVISIONAL |
| Ukuran lampiran maksimum | 5 MB, JPG/PNG/PDF | PROVISIONAL |
| Database | SQLite WAL (migrasi ke PostgreSQL sesuai PRD 16.2) | PROVISIONAL |

## Catatan perubahan
- 2026-09-11 — Dokumen dibuat dari PRD v1.0 Bagian 29. Seluruh entri `PROVISIONAL`.
- 2026-09-11 — Persiapan UAT pilot: ditambahkan rujukan ke `OWNER_DECISION_REVIEW.md`;
  koreksi penamaan field kas pada D1 agar sesuai implementasi (`expected_total`);
  D2 diperjelas mengenai siapa yang boleh menjadi verifikator kedua.
  **Tidak ada keputusan bisnis yang diubah** — seluruh entri tetap `PROVISIONAL`
  dan menunggu keputusan owner.
