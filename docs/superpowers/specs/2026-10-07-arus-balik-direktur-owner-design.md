# Arus balik Direktur Operasional ke Owner (tahap 2 audit arus balik)

Status: desain disetujui product owner di percakapan 7 Oktober 2026; menunggu tinjauan spec.
Latar: audit arus balik 7 Okt 2026 (`.claude-sync/audit-arus-balik.md`, tidak di Git). Tahap 1
(izin ubah status catatan) sudah dideploy di `7c636a9`.

## Masalah

- "Teruskan ke Direktur Utama / Owner" di Inbox buntu: Owner tidak diberi notifikasi, Inbox
  Owner baca saja, catatan Direktur tidak tampil.
- Register Keputusan (`direktur.Decision`) sudah mengenal pemutus Owner/Direktur Utama, tetapi
  Owner tidak diberi tahu, perkara tersembunyi di dashboard, dan hanya Direktur yang dapat
  menetapkan (`direktur/services.py:settle_decision` memanggil `assert_director`).
- Summary Harian satu arah: Direktur tidak tahu apakah sudah dibaca, Owner tidak dapat menanggapi.

## Keputusan

| # | Keputusan |
|---|---|
| K1 | Permintaan keputusan ke Owner memakai register `Decision` yang ada; tidak ada jenis data baru. Pemutus `OWNER` atau `DIRUT` = "permintaan keputusan Owner". |
| K2 | Siapa saja yang berperan `Role.OWNER` boleh memutuskan; keputusan pertama yang berlaku; nama pengambil tercatat. |
| K3 | Owner menjawab dengan tiga tombol + satu catatan: Setujui (catatan opsional), Tolak (alasan wajib), Bahas di rapat Kamis (catatan opsional). |
| K4 | Summary Harian mendapat tanda baca per Owner dan utas tanggapan Owner ↔ Direktur per tanggal. |
| K5 | Notifikasi: perkara baru → semua Owner aktif; keputusan Owner → semua Direktur aktif + pengaju; tanggapan → pihak lawan (Owner ↔ semua Direktur aktif), tidak ke penulis sendiri. |

## Bagian 1: Permintaan keputusan ke Owner

### Data (migrasi `direktur 0006`, additive)

Pada `Decision`:
- `verdict` CharField(10, blank, choices `SETUJU` "Disetujui" / `TOLAK` "Ditolak"): kosong bila
  belum diputuskan atau diputuskan lewat jalur lain (rapat, Direktur mencatat).
- `decided_by` FK User (null, `SET_NULL`, `related_name="+"`): Owner yang memutuskan lewat tombol.

Fungsi penentu di `direktur/services.py`:
- `OWNER_DECIDERS = {Decider.OWNER, Decider.DIRUT}`
- `is_owner_decision(decision) -> bool`: `decider in OWNER_DECIDERS`.

### Pintu masuk 1: Teruskan dari Inbox

`reports/triage.py:forward` dengan `to == ForwardTo.DIRUT`, dalam transaksi yang sama:
- membuat `Decision` lewat `direktur.services.create_decision(actor=..., decider=Decider.OWNER, ...)`:
  - `title` = judul item Inbox (dipotong 200);
  - `background` = uraian asli item, baris "Rujukan: <ref> (<jenis>, dari <pelapor>)", dan bila
    ada, baris "Catatan Direktur: <note>";
  - `clinic` = cabang item (kosong bila item lintas cabang);
- menyimpan `InboxTriage.decision` = perkara itu (kolom sudah ada);
- forward ke tujuan lain (Apoteker, Keuangan, Medis, Omnicare, Lainnya) tidak berubah.

### Pintu masuk 2: Halaman Keputusan Direktur

Tidak ada perubahan alur; `create_decision` sudah menerima pemutus Owner/Direktur Utama.

### Notifikasi perkara baru

Di `create_decision`, bila `is_owner_decision`: `notify_user` ke setiap pengguna aktif ber-`Role.OWNER`
(kecuali pelaku), `type_code="DECISION_REQUESTED"`, judul "Direktur Operasional meminta
keputusan: <perkara>", isi "<cabang atau lintas cabang> · perlu diputuskan sebelum <tgl>" (tanpa
tenggat: "tanpa tenggat"), tautan `owner:decision` untuk perkara itu. Satu titik ini melayani
kedua pintu masuk.

## Bagian 2: Owner memutuskan

### Tampilan

- Dashboard Owner (`owner:dashboard`): kartu **"Menunggu keputusan Anda"** paling atas (di atas
  "Permintaan dan temuan"), berisi perkara `MENUNGGU` dengan pemutus Owner/Direktur Utama,
  urut: lewat tenggat dulu, lalu `needed_by`, lalu `created_at` (terlama dulu). Tiap baris: perkara,
  cabang, pengaju, umur (hari), tenggat; label merah "Lewat tenggat". Tidak tampil bila kosong.
- Halaman baru `owner:decision` di `/owner/keputusan/<pk>/` (masuk `owner:*`, sudah diizinkan
  untuk persona Owner): perkara, latar (pra-format), cabang, tenggat, pengaju, tanggal dibuat,
  task yang tertahan menunggu perkara ini (judul + penerima), status. Bila masih menunggu dan
  pemutusnya Owner/Direktur Utama: form satu kolom `catatan` + tiga tombol `aksi=setuju|tolak|rapat`.
  Bila sudah diputuskan: isi keputusan, pengambil, tanggal.
- GET halaman ini diizinkan untuk Owner dan Direktur Operasional (`can_view_requests` dari
  `owner/services.py`); POST hanya Owner (lihat aturan).

### Aturan (service `owner/services.py: decide(decision, *, actor, verdict, note)`)

- `actor` wajib `is_owner`; selain itu `PermissionDenied`.
- `is_owner_decision(decision)` dan `status == MENUNGGU`; selain itu `ValidationError`
  ("Perkara ini sudah diputuskan / dibatalkan / dipindah ke rapat"). Baris dikunci dengan
  `select_for_update` supaya dua Owner yang menekan hampir bersamaan tidak sama-sama lolos.
- `verdict == "setuju"`: `status=DITETAPKAN`, `verdict=SETUJU`, `decided_by=actor`,
  `decided_on=local_today()`, `decision_text` = "Disetujui <nama Owner>" + (": <catatan>" bila ada).
- `verdict == "tolak"`: catatan wajib (`ValidationError` "Tulis alasan penolakan."); sama seperti
  setuju dengan `verdict=TOLAK` dan teks "Ditolak <nama Owner>: <catatan>".
- Setuju/Tolak memanggil `_release_waiting(decision, actor=actor, verb="ditetapkan")` (sudah ada)
  dan `log_update(..., action=AuditAction.APPROVE)`; `is_policy` tidak diubah.
- `verdict == "rapat"`: `decider=RAPAT_BERSAMA`, status tetap `MENUNGGU`, `background` ditambah
  baris "Catatan Owner (<nama>, <tgl>): <catatan>" bila catatan diisi; task tetap tertahan;
  `log_update` biasa.
- Nilai `verdict` lain: `ValidationError`.
- Setelah setiap aksi: `notify_user` ke semua pengguna aktif `Role.AOM` ditambah `created_by`
  perkara (tanpa duplikat, kecuali pelaku), `type_code="DECISION_DECIDED"`, judul
  "Keputusan Owner: <perkara>", isi teks keputusan (atau "Dibawa ke rapat Kamis: <catatan>"),
  tautan `direktur:decision_detail`.
- Owner lain tidak diberi notifikasi.
- Direktur tetap dapat `settle_decision` dan `cancel_decision` seperti sekarang.

## Bagian 3: Summary Harian dua arah

### Data (migrasi `direktur 0007`, additive)

- `DailySummaryRead`: `summary` FK DailySummary (CASCADE, `related_name="reads"`), `user` FK User
  (CASCADE), `read_at` DateTimeField; unik (`summary`, `user`).
- `DailySummaryNote`: `summary` FK DailySummary (CASCADE, `related_name="notes"`), `author` FK
  User (PROTECT), `body` TextField, `created_at` auto_now_add; urut `created_at`. Tidak diubah atau
  dihapus lewat aplikasi.

### Tanda baca

- `owner:summary` GET oleh pengguna `is_owner` dan bukan `is_aom`, untuk tanggal yang punya
  summary: `update_or_create` `DailySummaryRead(summary, user)` dengan `read_at=now`.
- Tampil di bawah summary: setiap Owner aktif → "Dibaca <nama> <dd/mm HH.MM>"; bila
  `read_at < summary.sent_at` → "<nama> membaca versi sebelumnya (sebelum <dd/mm HH.MM>)";
  bila belum ada → "<nama> belum membaca".
- Daftar 14 hari terakhir: tanda "dibaca" bila ada Owner yang `read_at >= sent_at`, selain itu
  "belum dibaca"; ditambah "<n> tanggapan" bila ada tanggapan.

### Tanggapan

- Form "Tanggapan" di bawah summary (POST ke `owner:summary` dengan `aksi=tanggapan`,
  `tanggal`, `isi`), hanya bila summary tanggal itu ada.
- Service `owner/services.py: add_summary_note(summary, *, actor, body)`: hanya `is_owner` atau
  `is_aom` (`PermissionDenied`), isi kosong `ValidationError`. Audit `log_event(CREATE)`.
- Notifikasi `type_code="SUMMARY_NOTE"`: penulis Owner (bukan AOM) → semua AOM aktif; penulis
  AOM → semua Owner aktif; tidak ke penulis. Judul "Tanggapan Summary <dd/mm>: <60 karakter
  pertama>", tautan `owner:summary` dengan `?tanggal=<YYYY-MM-DD>`.

## Pengujian

Test otomatis:
- Teruskan ke Owner membuat perkara pemutus Owner dengan judul/latar/cabang benar, triage
  tersambung, semua Owner aktif diberi notifikasi; teruskan ke tujuan lain tidak membuat perkara.
- `create_decision` pemutus Owner/Direktur Utama memberi notifikasi ke Owner; pemutus lain tidak.
- Setujui (catatan kosong dan berisi), Tolak (tanpa alasan ditolak, dengan alasan berhasil), Bahas
  di rapat: status, verdict, decided_by, decision_text, background, task tertahan dilepas atau tidak,
  notifikasi ke Direktur dan pengaju, audit.
- Negatif: Direktur/staf/admin POST ke `owner:decision` ditolak; Owner memutuskan perkara pemutus
  lain, perkara yang sudah diputuskan, dibatalkan, atau sudah dipindah ke rapat ditolak; dua Owner
  berurutan, yang kedua ditolak; data tidak berubah.
- Kartu "Menunggu keputusan Anda": isi, urutan, label lewat tenggat, hilang setelah diputuskan.
- Tanda baca: Owner membuka mencatat, Direktur tidak; kirim ulang memunculkan "versi
  sebelumnya"; daftar 14 hari.
- Tanggapan: arah notifikasi, isi kosong ditolak, tanggal tanpa summary ditolak, staf/admin 403.
- Migrasi: perkara dan summary lama tampil normal.

Uji UI pada salinan database uji, desktop dan HP 375 px: laporan staf → teruskan → Owner
Setujui dengan catatan → Direktur diberi tahu dan membuat task tindak lanjut; ulangi Tolak dan
Bahas di rapat; summary → Owner buka dan menanggapi → Direktur lihat "Dibaca" dan membalas.

## Di luar cakupan

- Arus balik staf ↔ Direktur (tahap 3) dan usulan Direktur atas inisiatif sendiri di luar register
  Keputusan (tahap 4).
- Minta info tambahan sebagai tombol keempat; mengubah/menghapus tanggapan; foto pada tanggapan;
  tanggapan di PDF summary.
- Membedakan Owner dan Direktur Utama sebagai dua orang berbeda.
