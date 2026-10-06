# Arus balik staf ↔ Direktur pada task (tahap 3a audit arus balik)

Status: desain disetujui product owner di percakapan 7 Oktober 2026; menunggu tinjauan spec.
Latar: audit arus balik 7 Okt 2026 (`.claude-sync/audit-arus-balik.md` di desktop, bagian A2–A3
dan baris 8–9 tabel asimetri). Tahap 1 (`7c636a9`) dan tahap 2 (`142d758`) sudah dideploy. Tahap 3b
(pelapor diberi tahu hasil laporan) dikerjakan terpisah sesudah ini.

## Masalah

- "Lapor progres" (`core/task_services.py:report_progress`) hanya membuat `TaskEvent` tanpa
  notifikasi; tidak ada yang tahu sampai membuka task.
- Komentar di riwayat task (`add_task_comment`) tidak memberi notifikasi, dan staf tidak dapat
  membaca riwayat karena `direktur:*` tertutup untuk staf; staf tidak punya form balas.
- Staf tidak punya cara menandai "terhambat" atau mengusulkan target baru.

## Keputusan

| # | Keputusan |
|---|---|
| K1 | Tiga bagian: notifikasi lapor progres; percakapan task dua arah di kartu staf; tombol "Ada kendala" dengan usulan target baru yang dapat disetujui satu tombol. |
| K2 | Notifikasi dari staf (progres, balasan, kendala) → pemberi tugas (`ActionItem.created_by`) + **semua** Direktur Operasional aktif (`Role.AOM`), tanpa duplikat, tidak ke penulis. Product owner ingin menjadi pemantau semua task. |
| K3 | Notifikasi dari pemberi tugas/Direktur (komentar, setujui target) → semua penerima task yang assignment-nya tidak `CANCELLED`, tidak ke penulis. |
| K4 | Tanda terhambat disimpan di task (kolom), bukan dihitung dari riwayat; hilang saat lapor progres, target baru disetujui, task selesai, atau dibatalkan. |
| K5 | Halaman detail task Direktur tetap tertutup untuk staf; percakapan staf ada di kartu "Tugas saya". |

## Bagian 1: Data dan aturan

### Data (migrasi `core 0009_task_kendala`, additive)

`TaskEventType` ditambah:
- `KENDALA = "KENDALA", "Kendala"`
- `TARGET_DIUBAH = "TARGET_DIUBAH", "Target diubah"`

`ActionItem` ditambah (semua nullable/blank):
- `blocked_at` DateTimeField null — kapan ditandai terhambat; `None` = tidak terhambat.
- `blocked_by` FK User null, `SET_NULL`, `related_name="+"`.
- `blocked_reason` TextField blank.
- `proposed_due_at` DateTimeField null — target baru yang diusulkan staf.
- Properti `is_blocked` = `blocked_at is not None and status in (BARU, DIKERJAKAN)`.

Helper `_clear_blocked(item)` mengosongkan keempat kolom (tanpa save terpisah bila dipanggil
bersama save lain).

### Penerima notifikasi (`core/task_services.py`)

- `_watchers(item)`: `created_by` (bila aktif) ∪ semua pengguna aktif ber-`Role.AOM`.
- `_active_recipients(item)`: assignee dari assignment yang statusnya bukan `CANCELLED`, aktif.
- Pengirim selalu dikecualikan; tiap orang paling banyak satu notifikasi per aksi.

### Aksi

| Aksi | Fungsi | Siapa (server-side) | Validasi | Efek | Notifikasi (`type_code`) |
|---|---|---|---|---|---|
| Lapor progres | `report_progress` (ada) | penerima/claimer (ada) | ada | + `_clear_blocked` | `_watchers` — `TASK_PROGRESS` |
| Balas/komentar | `add_task_comment` (ada) | pemberi tugas, Direktur, penerima (ada) | ada | — | penulis penerima → `_watchers`; penulis pemberi tugas/Direktur → `_active_recipients` — `TASK_COMMENT` |
| Ada kendala | `report_blocker(assignment, *, user, reason, proposed_due=None)` baru | penerima/claimer assignment itu | assignment `OPEN`/`IN_PROGRESS`/`REVISION_REQUIRED` dan task `BARU`/`DIKERJAKAN`; `reason` wajib; `proposed_due` (date) tidak boleh sebelum hari ini | isi kolom terhambat (`proposed_due_at` = akhir hari itu, pola `direktur.services.parse_due` jam 21.00 lokal); `TaskEvent` `KENDALA` dengan catatan alasan (+ " · usul target <dd/mm/YYYY>") | `_watchers` — `TASK_BLOCKED` |
| Setujui target baru | `approve_proposed_due(item, *, actor)` baru | `can_manage_task(item, actor)` (pemberi tugas atau Direktur) | task terhambat dan `proposed_due_at` terisi; task belum selesai/batal | `due_at = proposed_due_at`; `_clear_blocked`; `TaskEvent` `TARGET_DIUBAH` "Target diubah ke <dd/mm/YYYY HH.MM>" | `_active_recipients` — `TASK_DUE_CHANGED` |
| Task selesai | `_finish_item_if_all_confirmed`, `close_task` (ada) | — | — | + `_clear_blocked` | — |
| Task batal | `cancel_task` (ada) | — | — | + `_clear_blocked` | — |

Semua aksi baru `@transaction.atomic` dan tercatat audit (`log_event`/`log_update`) seperti pola yang ada.

### Tautan notifikasi

- Untuk pemberi tugas/Direktur: `direktur:task_detail` (args `[item.pk]`).
- Untuk staf penerima: `reverse("core:today") + "#task-<pk>"` (diset ke `notif.url` sesudah
  `notify_user`, pola tahap 2 `add_summary_note`).

## Bagian 2: Tampilan

### Kartu "Tugas saya" staf (`templates/core/_my_tasks.html`)

- `<li id="task-<pk>">` supaya tautan notifikasi tepat ke task.
- Label kuning **"Terhambat"** bila `item.is_blocked`.
- Di samping "Lapor progres" dan "Ajukan selesai" (hanya bila `can_submit`):
  - **Percakapan (n)** — `<details>` berisi 10 kejadian terakhir task (urut lama → baru) dengan
    jenis PROGRESS, COMMENT, KENDALA, TARGET_DIUBAH, REVISION_REQUESTED: nama, jam, jenis,
    catatan; form **Balas** (POST ke `core:task_comment`, field `catatan`). `n` = jumlah kejadian
    jenis itu. Tombol ini tampil untuk setiap task penerima (juga saat menunggu konfirmasi).
  - **Ada kendala** — `<details>` berisi `alasan` (wajib) dan `target` (date, opsional, `min`
    hari ini); POST ke `core:assignment_blocker`.
- Data untuk kartu disiapkan di `my_task_row` (kunci baru `thread`, `thread_count`, `blocked`).

### URL baru (app `core`)

- `core:assignment_blocker` — `hari-ini/assignment/<pk>/kendala/` (POST; view memanggil
  `report_blocker`, PermissionDenied → 403, ValidationError → pesan).
- `core:task_comment` — `hari-ini/task/<pk>/komentar/` (POST; view memanggil `add_task_comment`).
  Keduanya diizinkan untuk persona staf (cek `core/peran.py` STAF_BLOCKED tidak memblokir `core:*`).

### Halaman detail task Direktur (`templates/direktur/task_detail.html`)

- Kotak **"Terhambat"** di atas bila `item.is_blocked`: oleh siapa, kapan, alasan, usulan target;
  tombol **"Setujui target <dd/mm/YYYY>"** (POST `aksi=setujui_target`) bila ada usulan dan
  penonton `can_manage_task`.
- Riwayat menampilkan label "Kendala" dan "Target diubah" (dari `get_event_type_display`).
- Form "Simpan catatan" yang ada tetap; kini memberi notifikasi (Bagian 1).

### Daftar dan ringkasan Direktur

- Daftar Task (`direktur/task_list.py` + `templates/direktur/task_list.html`) dan Tim
  (`templates/direktur/team.html` / `_task_card.html`): label **"Terhambat"** bila `is_blocked`.
- Ringkasan Direktur (`direktur/dashboard.py:headline_counts` + `templates/direktur/_overview_body.html`):
  angka **"task terhambat"** (task terbuka dengan `blocked_at` terisi, cakupan cabang pengguna),
  menaut ke Daftar Task. Tidak tampil bila 0.

## Pengujian

Test otomatis:
- Lapor progres: notifikasi `TASK_PROGRESS` ke pemberi tugas + semua Direktur aktif, tanpa
  duplikat bila pemberi tugas = Direktur, tidak ke penulis; tanda terhambat hilang.
- Balasan staf → `_watchers`; komentar Direktur/pemberi tugas → penerima aktif (bukan yang
  `CANCELLED`); tautan staf berakhiran `#task-<pk>`.
- Ada kendala: alasan wajib; target sebelum hari ini ditolak; kolom terisi; `TaskEvent` KENDALA;
  notifikasi `TASK_BLOCKED`; ditolak untuk assignment `SUBMITTED`/`CONFIRMED`/`CANCELLED`.
- Setujui target: `due_at` berganti, terhambat hilang, `TARGET_DIUBAH` tercatat, penerima diberi
  tahu; ditolak bila bukan pemberi tugas/Direktur, bila tidak ada usulan, atau oleh penerima sendiri.
- Task selesai (konfirmasi/close) dan batal menghapus tanda terhambat.
- Negatif: staf bukan penerima tidak bisa kendala/balas/setujui (403, data tetap); staf tetap
  ditolak di `direktur:task_detail`.
- Tampilan: kartu staf (Percakapan (n), urutan, Balas tersimpan; Ada kendala tersimpan, label
  Terhambat); detail task (kotak, tombol bekerja); Daftar Task label; Ringkasan angka muncul dan
  hilang.
- Migrasi: task lama tidak terhambat dan tampil normal.

Uji UI pada salinan database uji, desktop dan HP 375 px: progres → Direktur diberi tahu; kendala
dengan usulan target → label di Daftar Task dan Ringkasan → Direktur setujui → staf diberi tahu,
label hilang; Direktur menulis catatan → staf diberi tahu → Percakapan → balas → Direktur diberi tahu.

## Di luar cakupan

- Pelapor diberi tahu hasil Komplain/Masukan/Kerusakan/Laporan (tahap 3b).
- Usulan Direktur atas inisiatif sendiri (tahap 4).
- Tanya-jawab tentang kebijakan; lampiran foto pada balasan atau kendala; menolak usulan target
  sebagai aksi tersendiri (cukup dibalas di percakapan).
