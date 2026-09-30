# Current Progress

Status per **30 September 2026** (Asia/Jakarta). **Pekerjaan dijeda** atas permintaan product owner.
Bagian atas dokumen ini adalah posisi terakhir, sisa pekerjaan, dan roadmap. Bagian **Riwayat**
di bawahnya adalah catatan per pekerjaan seperti ditulis saat dikerjakan.

## Posisi terakhir

| | |
|---|---|
| Produksi (mini PC, ops.joderma.id) | Commit `1595435` (dideploy 29 September): jadwal jaga Oktober, pembagian tugas, giliran tally bulanan, pengaturan klinik, rapikan akun. Backup tersimpan satu: `joderma-ops-20260929-111438.tar.gz` (tidak terenkripsi; salinannya di Desktop laptop) |
| Laptop dan GitHub | Commit 30 September "Redefinisi peran fase 2–5". **Belum dideploy** ke mini PC |
| Test | 562 lulus, 1 dilewati (`.venv/bin/python -m pytest`) |
| Rencana aktif | [`docs/KEBUTUHAN_REDEFINISI_PERAN.md`](docs/KEBUTUHAN_REDEFINISI_PERAN.md), dikerjakan fase demi fase dengan persetujuan product owner di setiap akhir fase |
| Cara melanjutkan | [`docs/lanjutkan-pekerjaan.md`](docs/lanjutkan-pekerjaan.md) |

## Redefinisi peran: status per fase

| Fase | Isi | Status |
|---|---|---|
| 1 | Baseline: pemeriksaan read-only, seluruh test lulus | Selesai |
| 2 | Definisi peran standar dan tombol **Reset peran ke default** (akun `jean`) | Selesai, di-commit 30 Sep |
| 3 | Menu per peran, halaman pertama sesudah login, penolakan server-side (403) dan test negatif | Selesai, di-commit 30 Sep |
| 4 | Owner: Dashboard + Permintaan Owner, Keputusan, Summary Harian, Jadwal ringkas | Selesai, di-commit 30 Sep |
| 5 | Direktur: tombol "Simpan dan kirim summary ke Owner", riwayat summary; lonceng notifikasi | Selesai, di-commit 30 Sep |
| 6 | Permintaan Owner sisi Direktur dan baris Gantt | **Belum** — berikutnya |
| 7 | Staf sederhana | Belum |
| 8 | PIC mengatur sesuai porsi fungsinya | Belum |
| 9 | Uji tampilan per peran (desktop dan HP) bersama product owner | Belum |

Fase 2–5 sudah lulus test dan tangkapan layarnya sudah ditinjau product owner per fase, tetapi
**belum diuji di mini PC** dan belum dipakai staf.

## Task yang belum selesai

### Pengembangan (fase 6–9)

1. **Fase 6 — Permintaan Owner sisi Direktur.**
   - Kotak masuk permintaan untuk Direktur (menu Direktur), urut lewat target lalu target terdekat.
   - Tombol "Pecah jadi task" dari halaman permintaan: judul, cabang, penerima, target, prioritas;
     task dibuat lewat `core.task_services.create_task` dengan `source_type="permintaan_owner"`,
     `source_id` = permintaan (progres di sisi Owner sudah membaca dari sini).
   - Gantt (Jadwal Task): satu baris per permintaan beserta task turunannya; target permintaan
     ditandai.
   - Test: hanya AOM yang memecah, progres ikut berubah, baris Gantt muncul untuk Owner dan Direktur.
2. **Fase 7 — Staf sederhana.**
   - **Tugas hari ini**: daftar pendek butir checklist porsinya hari itu + task yang ditugaskan
     kepadanya (menggantikan Hari Ini dan Checklist Saya di menu staf).
   - **Jadwal saya**, **Istirahat saya**, **Tindakan saya** (giliran dan tally dirinya, hari ini dan
     bulan ini) — hanya dirinya, bukan grid tim; lalu tutup grid tim untuk staf di server.
   - **Kas hanya pada hari ia ditugaskan sebagai kasir** (porsi "Kasir hari ini"), ditegakkan di
     server, bukan hanya menu.
   - Komplain, Masukan, Kerusakan, Laporan Saya, Masukan Saya tetap.
3. **Fase 8 — PIC sesuai porsi fungsinya.** Pembagian tugas yang ada dipakai apa adanya (uji coba);
   PIC mengganti pelaksana, giliran perawat, istirahat, dan roster hanya untuk porsi fungsinya di
   cabangnya. Saat ini hanya Koordinator Shift (SUPERVISOR) yang boleh mengganti pelaksana.
4. **Fase 9 — Uji tampilan** per peran di desktop dan HP bersama product owner, lalu commit dan
   deploy fase 6–9 sebagai satu paket.

### Deploy dan operasional (dikerjakan product owner)

- **Deploy fase 2–5 ke mini PC** bila ingin dipakai sebelum fase 6–9 selesai: backup dulu,
  kirim kode yang sudah di-commit, `docker compose build app` dan `up -d --force-recreate app`
  (migrate otomatis). Migrasi baru: `accounts 0008`, `checklists 0006`, `direktur 0004`,
  `owner 0001`. Semua hanya menambah tabel atau mengubah label; data yang ada tidak diubah.
- **Sesudah deploy:** Admin ▸ Pengguna ▸ **Reset peran ke default**, periksa pratinjau, lalu
  terapkan. Efeknya: akun `jean` dibuat (password `klinik123`), `yohanes` dipastikan Owner, peran
  tambahan di `hansen1` dicabut sehingga ia murni Direktur Operasional (urusan admin lewat
  `superadmin`). `AOM_HS` tidak disentuh.
- Ganti password `hansen1` dan `superadmin` (masih `klinik123`).
- Isi DPJ, APJ, dan jam Citraland di Pengaturan Klinik (tidak terisi otomatis karena kode cabang
  Citraland di mini PC adalah `JC`).
- Putuskan akun `AOM_HS`: bila akun lama, nonaktifkan.
- Backup terenkripsi: set `BACKUP_PASSPHRASE` untuk backup yang dijalankan dari host.
- Opsional: hapus `docs/KEBUTUHAN_ROLE_OWNER.md` (sudah digantikan, isinya hanya penunjuk).

### Celah yang dicatat (bukan blocker)

- Beberapa predikat di `core/permissions.py` (audit, ekspor, baca pengaturan klinik) masih
  menyebut owner. Untuk akun yang hanya Owner, halaman itu tetap ditolak oleh tampilan Owner
  (`core/peran.py`); predikatnya dirapikan bila disentuh lagi.
- Sampai fase 7, staf masih melihat grid Jadwal Jaga seluruh tim dan menu Kas setiap hari bila
  memegang peran front desk.
- Summary harian hanya terkirim bila Direktur menekan tombol; belum ada pengingat bila lupa.
- Pemilih tanggal memakai format bawaan browser (mis. bulan/tanggal di browser berbahasa Inggris).
- Tangkapan layar tiap fase dibuat di database uji (data contoh), bukan data klinik.
- Penangguhan lama dari integrasi AOM tetap berlaku (lampiran laporan/masukan, pencarian teks
  bebas, QA manual viewport dan keyboard) — lihat Riwayat ▸ Langkah berikutnya.

## Roadmap

| Kapan | Apa |
|---|---|
| Sesudah jeda | Fase 6 (Permintaan Owner sisi Direktur), fase 7 (staf sederhana), fase 8 (PIC), fase 9 (uji tampilan bersama product owner) |
| Sesudah fase 9 | Commit, backup, deploy satu paket; Reset peran ke default di mini PC; perkenalan tampilan baru ke Owner, Direktur Utama, PIC, dan staf |
| Oktober 2026 | Uji coba jadwal jaga, pembagian tugas, dan giliran tally bulanan; catat masalah di `UAT_ISSUE_REGISTER.md`; aturan tally ditweak sesudah uji coba (ketetapan 30 Sep) |
| Akhir Oktober | Jadwal jaga November: siapkan JSON dari PDF, `import_jadwal_jaga`, `seed_tugas_harian --susun 2026-11` |
| Belum dijadwalkan | Pengingat summary harian; perapihan predikat owner di `core/permissions.py`; lampiran laporan/masukan; rehearsal migrasi data AOM legacy (fase 6–8 rencana integrasi AOM, perlu persetujuan terpisah) |

---

# Riwayat

## Redefinisi peran — fase 5: summary harian dan lonceng notifikasi (30 September 2026) — di-commit 30 Sep, belum dideploy

`direktur/summary.py` menyusun summary (checklist Direktur per cabang, keputusan dan task hari itu,
status Permintaan Owner) dan `send_summary` menyimpannya sebagai snapshot `DailySummary` (kirim ulang
= perbarui, `send_count` naik), mencatat audit, dan memberi satu notifikasi belum-dibaca per tanggal
ke setiap Owner. Kartu **Summary hari ini untuk Owner** (pratinjau, catatan Direktur, tombol "Simpan
dan kirim summary ke Owner") di bawah Checklist Direktur; URL `direktur:summary_send` (hanya AOM).
Menu Direktur mendapat Summary Harian. Topbar: lonceng SVG dengan bulatan merah (99+), nama pengguna
disembunyikan di layar ≤600px. Test: `direktur/tests/test_summary.py`; 562 test lulus.

## Redefinisi peran — fase 4: halaman Owner (30 September 2026) — di-commit 30 Sep, belum dideploy

App baru `owner` (`/owner/`): Dashboard Owner (Permintaan Owner + isi Ringkasan yang sama lewat
`templates/direktur/_overview_body.html`), Permintaan baru/detail dengan catatan dua arah dan
notifikasi, Summary Harian per tanggal (membaca `direktur.DailySummary`; pengirimnya dibangun di
fase 5), Jadwal ringkas per cabang (bertugas, libur/cuti/di cabang lain, tombol jadwal penuh).
Owner mendarat di `/owner/`; `direktur:overview` tidak lagi terbuka untuk Owner. Migrasi:
`owner 0001`, `direktur 0004`, `checklists 0006` (label peran Owner yang tertinggal di fase 2). Test: `owner/tests/test_owner.py`; 552 test lulus. Panduan:
`docs/panduan-owner.md`.

## Redefinisi peran — fase 3: menu per peran dan penolakan server-side (30 September 2026) — di-commit 30 Sep, belum dideploy

`core/peran.py` menentukan satu tampilan per pengguna (Direktur, Owner, PIC, Staf, Admin): menu,
halaman pertama sesudah login (`/` dan login mengalihkan ke sana), dan halaman yang boleh dibuka.
`core.middleware.PersonaAccessMiddleware` menolak (403) halaman di luar tampilan: Owner hanya
Ringkasan/Tim/Kanban/Prioritas/Jadwal Task/Keputusan/Jadwal Jaga; staf tidak membuka Pembagian
Tugas tim, Laporan Operasional, Audit, halaman Direktur; Admin sistem hanya halaman akun,
konfigurasi, template, pengaturan klinik, jadwal. `next` pada login hanya diikuti bila URL internal.
Test: `core/tests/test_tampilan_peran.py`; 527 test lulus.

## Redefinisi peran — fase 2: peran standar dan Reset peran ke default (29 September 2026) — di-commit 30 Sep, belum dideploy

Rencana: `docs/KEBUTUHAN_REDEFINISI_PERAN.md`. `accounts/peran_standar.py` mendefinisikan akun
standar (Owner `yohanes`, Direktur Utama `jean` — peran OWNER yang sama —, Direktur Operasional
`hansen1`, Admin `superadmin`, dan staf dari `jadwal/staff.py`). Halaman Admin ▸ Pengguna ▸
**Reset peran ke default** (pratinjau → konfirmasi → terapkan; admin dan AOM). `seed_staf_cabang`
memakai logika yang sama. Label peran OWNER menjadi "Owner / Direktur Utama" (migrasi accounts 0008).
Test: `accounts/test_reset_peran.py`.

## Jadwal jaga, pembagian tugas, dan giliran tally bulanan (29 September 2026) — di-commit dan dideploy 29 Sep (`18dfcb6`, `1595435`)

Menjawab arahan product owner 29 Sep (10 butir) dan jadwal jaga Oktober 2026. Rincian:
`docs/jadwal-dan-giliran.md`.

- App baru `jadwal`: `DutyRoster` (masuk/perbantuan/off/cuti per orang per hari), `DutyPortion`,
  `DutyAssignment`. Halaman Jadwal Jaga, Pembagian Tugas (bulan + per hari, ganti pelaksana).
  Perintah `import_jadwal_jaga`, `seed_tugas_harian` (template checklist versi baru + porsi,
  `--susun YYYY-MM`), `seed_staf_cabang` (akun, peran, PIC dua cabang; `heny` → `heni`).
  Data Oktober: `jadwal/jadwal_bulanan/jadwal-2026-10.json` (dari warna sel PDF; kolom "Jumlah Masuk" PDF
  menulis Heni 25 dan Elvira 26, hitungan sel memberi 26 dan 27).
- Checklist harian baru per cabang: Opening (Lembar A), Piket kebersihan, Limbah, Closing
  (JD-FOB-F04 + permintaan 29 Sep), Apotek (hanya peran apotek). Butir membawa kode porsi;
  input baru `JAM`. Template lama role-specific dinonaktifkan (riwayat tetap).
- Giliran perawat: total tally bulanan gabung cabang, yang tertinggal ≥2 didahulukan sampai
  total −1, selebihnya urutan papan (▲▼ Koordinator Shift), serahkan pasien → sedang menangani,
  roster dari jadwal jaga, papan awal hari urut total terkecil; yang cuti bulan itu tanpa keistimewaan
  mengejar (ketetapan 30 Sep). Konfigurasi `nurse.catch_up_gap`.
- Pengaturan Klinik (nama, alamat, HP, jam, DPJ, APJ); migrasi data Jemur 14.00–22.00.
- Label: AOM → Direktur Operasional; fungsi PIC sesuai memo, tambah PIC Apotek. Menu gantt
  Direktur menjadi "Jadwal Task".
- Migrasi: accounts 0007, checklists 0005, core 0004–0005, direktur 0003, jadwal 0001,
  nurses 0003–0004, reports 0002.

## Dashboard Owner dan Direktur (29 September 2026) — di-commit dan dideploy (sampai `1595435`)

Menjawab `docs/KEBUTUHAN_CHECKLIST_DAN_DASHBOARD.md` dan arahan product owner 29 Sep: Owner melihat
gambaran luas (ada masalah atau tidak, keputusan menggantung, kebijakan yang ditetapkan), tidak
sedetail Direktur; dashboard = bird view + matriks Eisenhower + kanban, dengan halaman detail.

- `direktur/dashboard.py` (baru): `bird_view` (merah/kuning/hijau per cabang beserta alasan),
  `eisenhower` (tahap 1, tanpa migrasi; ambang `dashboard.urgent_hours` di `ClinicConfig`, bawaan
  48), `kanban` (kolom dari status `TaskAssignment`, baca saja).
- Model `direktur.Decision` (migration `direktur 0002`): register keputusan menggantung/ditetapkan/
  dibatalkan, pemutus, tenggat, penanda kebijakan berlaku. Ditulis AOM, dibaca Owner.
- Halaman baru (AOM + Owner): Ringkasan, Kanban, Prioritas, Keputusan (+detail). Halaman Tim kini
  juga dibaca Owner; tombol aksi hanya untuk AOM dan ditolak server untuk Owner.
- Label penghitung checklist Direktur: "sudah n/N · belum m" (A4).
- `core.DEFAULT_CONFIG` menambah `dashboard.urgent_hours` (tanpa migrasi).
- Test: `direktur/tests/test_dashboard.py`.
- Revisi Ringkasan (arahan product owner 29 Sep: "halaman utama jangan dipadatkan"): halaman
  utama kini hanya kotak ringkas — empat kuadran prioritas gabungan kedua cabang (angka + satu
  cuplikan task, diketuk membuka kuadran itu saja di `/direktur/prioritas/?kuadran=I..IV`), empat
  kotak (keputusan menggantung, kebijakan baru, menunggu konfirmasi, jadwal task), lalu
  infografik per cabang (meter checklist staf dan cek Direktur, chip lewat target/temuan/
  menunggu). Halaman baru **Jadwal** (`/direktur/jadwal/`): gantt task dari dibuat sampai target,
  jendela 7 hari ke belakang s.d. 21 hari ke depan; task lewat target memanjang sampai hari ini.
  `headline_counts()` dan `gantt()` di `direktur/dashboard.py`. Posisi bar ditulis tanpa format
  lokal (`{% localize off %}`) karena `LANGUAGE_CODE=id` memakai koma desimal.

## Peran Direktur Operasional (27 September 2026) — di-commit dan dideploy (sampai `1595435`)

Dikerjakan atas permintaan langsung product owner (Direktur Operasional), di luar urutan fase
integrasi AOM. Rencana dan keputusan: dokumen "Peran Direktur Operasional — Rencana Fitur"
(Opsi B dieksplorasi dulu; Opsi A dicatat sebagai alternatif).

- App baru `direktur` (migration `direktur 0001`): `AuditItem`/`AuditPoint` (butir checklist
  Direktur harian/mingguan/bulanan), `AuditCheck` (satu hasil per butir x cabang x periode,
  snapshot butir, task temuan), `DirectorNote` (catatan privat, arsip manual, dapat dijadikan task).
- Butir tidak memakai `checklists.ChecklistTemplate` karena template di sana diinstansiasi
  setiap hari operasional dan akan memunculkan butir mingguan/bulanan di checklist staf.
  Temuan memakai `core.ActionItem` lewat `create_task` (source `audit_direktur`).
- `core.task_services.create_task` menerima `source_type`/`source_id`/`source_label`
  opsional (bawaan tetap `manual`; pemanggil lama tidak berubah).
- Perintah `seed_audit_direktur` (idempoten, `--dry-run`, `--update`): 8 harian, 13 mingguan,
  1 bulanan dari dokumen checklist Direktur Rev 00 + keputusan 27 Sep (Kas, Kebersihan ruang,
  emergency kit bulanan). Teks butir Kas adalah usulan dari Pegangan PJ Area — perlu ditinjau.
- Halaman (semua `Role.AOM` server-side): Tim (`/direktur/`), Checklist Direktur, Catatan,
  Jadikan task, Task baru. Menu dan tombol di dashboard AOM ditambahkan.
- `AGENTS.md`: aturan "Codex satu-satunya agen" diganti aturan netral (keputusan product owner).
- Dokumentasi: `docs/panduan-direktur.md` (baru), `docs/README.md`, `docs/peran-dan-akses.md`.
- Test: `direktur/tests/test_direktur.py` (32 definisi, 35 kasus dengan parametrize).

Verifikasi (cloud workspace, Python 3.11.15, paket dari `.venv` desktop):

```text
python manage.py check                              # 0 issues
python -m pytest -q                                 # 387 passed, 1 skipped (baseline 352 passed, 1 skipped)
python manage.py makemigrations --check --dry-run   # No changes detected
migrate dari nol ke SQLite /tmp + seed_demo + seed_audit_direktur (dua kali) # berhasil, idempoten
```

Belum: QA manual mobile viewport; review manusia atas diff; commit/push; deployment.

## Integrasi AOM (status 26 September 2026)

Sumber rencana: `docs/AOM_MODULE_INTEGRATION_PLAN.md`.

### Ringkasan

Integrasi AOM telah melewati baseline/proteksi (Fase 0), organisasi dan akses (Fase 1),
task dan delegasi (Fase 2), checklist harian (Fase 3), laporan dan masukan (Fase 4), serta
UI dan usability (Fase 5, implementasi selesai). Fase 0–5 (termasuk desain checklist PDF dan
SDM multi-role) sudah DI-COMMIT dan DI-PUSH ke `origin/master` pada commit `0884b3f`
("feat: compact checklist and SDM role management"); working tree bersih. Semua pekerjaan
dilakukan di desktop Ubuntu/Linux dengan data dummy. Belum ada perubahan ke mini PC produksi
atau deployment. Approval eksplisit product owner untuk lanjut ke Fase 6 BELUM dikonfirmasi
di dokumen ini — verifikasi status approval sebelum memulai Fase 6.

### Matriks fase

| Fase | Status | Catatan |
|---|---|---|
| 0 — baseline dan perlindungan | Selesai | Baseline dicatat, fixture role/cabang ditambahkan, backup/restore dummy diverifikasi. |
| 1 — organisasi dan akses | Selesai | Role AOM/PIC, organisasi, fungsi PIC, capability, scope cabang, dan negative tests tersedia. |
| 2 — task dan delegasi | Selesai | Snapshot penerima, assignment individual/bersama, lifecycle submit/revision/confirm/cancel, histori, dan tests tersedia. |
| 3 — checklist harian | Implementasi selesai dan sudah di-commit (`0884b3f`) | Sesi opening/closing/anytime, template berversi (histori tidak berubah), target fungsi PIC/role, tindak lanjut idempoten, koreksi wajib beralasan dengan audit `CORRECTION`. |
| 4 — laporan dan masukan | Implementasi selesai dan sudah di-commit (`0884b3f`) | Model `Laporan`/`Masukan` ditambahkan di app `reports` yang sudah ada. Visibilitas `CABANG`/`RAHASIA_AOM`, status lifecycle, arsip beralasan+capability+audit, publikasi masukan AOM dengan snapshot immutable, dan negative tests kebocoran lintas cabang/rahasia. |
| 5 — UI dan usability | Implementasi selesai dan sudah di-commit (`0884b3f`) | Dashboard AOM/PIC/Admin ditambahkan (staf tetap seperti semula), aksi task 'Ajukan selesai'/'Konfirmasi selesai'/'Minta revisi'/'Ambil task bersama' sebagai view terpisah dengan proteksi server-side, halaman HTML laporan/masukan dengan filter status eksplisit di atas endpoint JSON Fase 4, PIC kosong menampilkan pesan ramah di view checklist (bukan crash). Approval eksplisit product owner untuk lanjut ke Fase 6 belum dikonfirmasi. |
| 6–8 | Belum dimulai | Rehearsal migrasi data AOM, release, observasi, dan cutover belum dikerjakan. |

## Implementasi yang sudah ada

- `Role.PIC` dan `Role.AOM`, `OrganizationAssignment`, `PicFunction`, `PicAssignment`.
- Capability sensitif untuk laporan rahasia, publikasi masukan, dan pengelolaan user.
- Pemeriksaan scope cabang pada layanan/views penting serta pembatasan assignee lintas cabang.
- `TaskAudienceSnapshot`, `TaskAssignment`, `TaskEvent`, mode `INDIVIDUAL`/`BERSAMA`,
  dan layanan task idempoten.
- Perintah `preview_aom_seed` yang hanya membaca dan menampilkan rencana seed.
- Migration `accounts 0004` dan `core 0002`.
- `checklists.ChecklistSession` (OPENING/CLOSING/ANYTIME), `ChecklistTemplate.session` +
  versi baru per sesi, `ChecklistTemplate.target_pic_function`/`target_role`/`assignment_mode`.
- Desain checklist PDF: role `APOTEKER` dan `ONLINE`, `audience_key` per template,
  `target_roles` jamak, run terpisah per template pada hari yang sama, serta item dengan
  `performer_roles` dan `verifier_roles` untuk penanda P/V dan handoff antarperan.
- `seed_demo` kini mengaktifkan 8 template role-specific dari PDF: Koordinator Shift (buka/tutup),
  Kasir (buka/tutup), Apoteker (buka/tutup), Online & Reservasi, dan Perawat/Terapis.
- `checklists.services.create_template_version()`: membuat versi baru tanpa memutasi versi
  lama; `ChecklistRun.template_snapshot` historis tidak berubah setelah edit template.
- `checklists.ChecklistFollowup`: penanda idempotensi tindak lanjut checklist bermasalah;
  `create_action_item_from_response()` sekarang memakai `core.task_services.create_task`
  (ActionItem + TaskAssignment + audience snapshot) dan aman dipanggil ulang (termasuk
  konkuren) tanpa menggandakan task.
- `audit.AuditAction.CORRECTION` ditambahkan; `checklists.services.record_response()`
  mewajibkan `reason` saat mengoreksi hasil yang sudah pernah dicek (result != BELUM) dan
  mencatat event `CORRECTION` terpisah dari `UPDATE` biasa.
- Migration `audit 0002` dan `checklists 0002`.
- `audit.AuditAction.PUBLISH` dan `audit.AuditAction.ARCHIVE` ditambahkan (Fase 4, mengikuti
  precedent `CORRECTION` — additive only). Migration `audit 0003`.
- `reports.Laporan`/`reports.LaporanUpdate`: laporan `CABANG` (satu cabang) dan `RAHASIA_AOM`
  (pelapor + AOM), status `OPEN`/`UNDER_REVIEW`/`RESOLVED`/`CLOSED`/`ARCHIVED`, arsip soft-delete
  wajib alasan + capability + audit `ARCHIVE`.
- `reports.Masukan`/`reports.MasukanPublication`: masukan privat (pengirim + AOM), publikasi AOM
  ke cabang dengan snapshot isi immutable (`title_snapshot`/`description_snapshot`/`source_version`)
  agar edit setelah publikasi tidak mengubah histori yang sudah terbit — pola sama dengan
  `checklists.services.create_template_version()`/`TaskAudienceSnapshot`.
- `core/permissions.py`: `can_view_laporan`, `can_create_laporan`, `can_archive_laporan`,
  `can_view_masukan`, `can_publish_masukan`, `can_view_published_masukan`, `can_archive_masukan`
  ditambahkan mengikuti pola `can_view_restricted_issue` yang sudah ada untuk app `issues`.
- `reports/services.py` (baru): `create_laporan`, `visible_laporan_queryset`,
  `change_laporan_status`, `archive_laporan`, `log_confidential_access`, `create_masukan`,
  `visible_masukan_queryset`, `publish_masukan`, `archive_masukan` — semua otorisasi
  server-side, tidak ada queryset tak terbatas yang dikirim ke view.
- `reports/views.py`, `reports/urls.py`, `reports/admin.py`: endpoint JSON (Fase 4) untuk
  create/list/detail/status/archive laporan dan create/list/detail/publish/archive masukan;
  direct-URL access diperiksa server-side. Fase 5 menambah halaman HTML di atas layanan yang
  sama (lihat bagian Fase 5 di bawah).
- Migration `reports/migrations/0001_initial.py` (app `reports` sudah ada sebelumnya untuk
  laporan operasional/ekspor CSV — Fase 4 menambah model baru di app yang sama).
- `reports/tests/` (paket): `test_laporan.py` (19 test: create/status/archive/queryset),
  `test_masukan.py` (13 test: create/publish/snapshot immutability/archive/negative HTTP),
  `test_confidentiality.py` (7 test: gate kebocoran RAHASIA_AOM lewat direct URL/list, lintas
  cabang, lintas visibility CABANG), `test_report_pages.py` (Fase 5, 9 test: halaman HTML
  laporan/masukan, filter status, direct-URL access negatif).
- Dokumentasi peran, arsitektur, README, dan rencana integrasi telah diperbarui.

### Fase 5 — UI dan usability (baru)

- `core/task_services.py`: `_can_review_task` diganti nama publik `can_review_assignment`
  (alias lama dipertahankan) agar dapat dipakai view layer untuk menentukan siapa yang boleh
  melihat tombol konfirmasi/revisi tanpa mengulang logika otorisasi.
- `core/views.py`: `action_items` sekarang menyusun `rows` per action item berisi
  `my_assignment`, `can_claim`, `can_submit`, `review_assignments` (assignment berstatus
  SUBMITTED yang boleh direview user ini). View baru `assignment_claim`, `assignment_submit`,
  `assignment_confirm`, `assignment_revision`, `assignment_cancel` — masing-masing memanggil
  fungsi `core.task_services` yang sudah ada (claim_shared_task/submit_assignment/
  confirm_assignment/request_revision/cancel_assignment); `PermissionDenied` dari service
  TIDAK ditangkap di view sehingga tetap menjadi 403 asli (bukan pesan flash yang
  menyembunyikan penolakan). `dashboard` view menambah context per role: `is_aom`/`is_pic`/
  `is_admin` plus data role-spesifik (lihat di bawah).
- `core/urls.py`: lima route baru `assignment/<pk>/ambil|ajukan|konfirmasi|revisi|batal/`.
- `templates/core/action_items.html`: tombol `Ajukan selesai` (penerima) dan
  `Konfirmasi selesai`/`Minta revisi` (reviewer) adalah form terpisah dengan label berbeda,
  tidak pernah tombol yang sama dipakai ulang untuk aksi berbeda.
- `templates/core/dashboard.html`: tiga section baru — "Ringkasan AOM" (assignment SUBMITTED
  lintas cabang menunggu konfirmasi AOM + shortcut ke laporan rahasia/masukan menunggu),
  "Ringkasan PIC" (assignment SUBMITTED dari task yang dibuat PIC ybs. + fungsi PIC aktif +
  jumlah template checklist yang menargetkan fungsi tsb.), "Ringkasan Admin" (shortcut kelola
  user/template). Section hanya tampil sesuai predikat role; staf biasa tidak melihat section
  tambahan apa pun (dashboard tetap seperti Fase 0-4).
- `reports/views.py`, `reports/urls.py`: empat view HTML baru — `laporan_page` (list + filter
  status via `<select>`, form buat laporan), `laporan_page_detail` (detail + ubah status/arsip,
  akses diperiksa lewat `can_view_laporan` yang sama dengan endpoint JSON), `masukan_page`
  (list + filter aktif/diarsipkan, form buat masukan), `masukan_page_detail` (detail +
  publikasi AOM + arsip). Semua dibangun di atas `visible_laporan_queryset`/
  `visible_masukan_queryset`/`create_laporan`/`archive_laporan`/dst. yang sudah ada dari
  Fase 4 — tidak ada query baru yang melewati service layer.
- `templates/reports/laporan_list.html`, `laporan_detail.html`, `masukan_list.html`,
  `masukan_detail.html` (baru): filter status eksplisit (`<select>` mengikuti pola
  `templates/issues/list.html`/`templates/core/action_items.html`), status ARCHIVED/CLOSED
  tetap terlihat lewat filter bukan disembunyikan permanen.
- `templates/checklists/templates.html`: menampilkan sesi, mode assignment, dan target
  (fungsi PIC/role) template secara eksplisit — sebelumnya field-field ini (Fase 3) tidak
  punya representasi UI sama sekali.
- `templates/base.html`: dua link nav baru "Laporan Saya" dan "Masukan Saya" menuju halaman
  HTML Fase 5 (endpoint JSON Fase 4 tetap ada, tidak dihapus/diubah).
- PIC/fungsi kosong: `checklists.services.resolve_followup_audience` dan
  `core.task_services.resolve_task_recipients` SUDAH melempar `ValidationError` pesan jelas
  sejak Fase 1–3; Fase 5 membuktikan lewat test bahwa VIEW (`checklists:make_action`) yang
  memicu jalur tersebut menampilkan pesan itu lewat Django messages (redirect + flash),
  bukan HTTP 500 — lihat `checklists/tests/test_empty_pic_ui.py`.
- Test baru: `core/tests/test_task_actions_ui.py` (7 test — submit/confirm/revision via view,
  direct URL negatif, label tombol tidak tertukar), `core/tests/test_dashboard_roles.py`
  (5 test — dashboard per role + negative unauthenticated), `reports/tests/test_report_pages.py`
  (9 test — halaman HTML laporan/masukan, filter, direct-URL negatif),
  `checklists/tests/test_empty_pic_ui.py` (1 test — pesan ramah PIC kosong di view).
- Tidak ada model/migration baru untuk Fase 5 (`makemigrations --check --dry-run` tetap
  "No changes detected" sebelum dan sesudah).

## Bukti verifikasi

Lingkungan test aktif menggunakan `.venv` dengan Python 3.11.16. Python 3.14 tersedia di
mesin, tetapi lingkungan proyek yang terbukti stabil untuk suite saat ini adalah `.venv`.

Perintah terakhir yang lulus (setelah Fase 5, sebelum commit):

```text
.venv/bin/python manage.py check                              # System check: 0 issues
.venv/bin/python -m pytest -q --tb=short                      # 333 passed
.venv/bin/python manage.py makemigrations --check --dry-run   # No changes detected
git diff --check                                              # tidak ada whitespace error
```

**Update 26 September 2026 — pasca-commit `0884b3f`:** diverifikasi ulang secara independen
pada HEAD saat ini (working tree bersih, sinkron `origin/master`):

```text
.venv/bin/python manage.py check                              # System check: 0 issues
.venv/bin/python -m pytest -q --tb=short                      # 336 passed (naik dari 333,
                                                                # test SDM multi-role baru)
.venv/bin/python manage.py makemigrations --check --dry-run   # No changes detected
git status --short                                            # kosong
```

Migration rehearsal khusus untuk migration baru di commit `0884b3f`
(`accounts/migrations/0005_*`, `checklists/migrations/0003_*`/`0004_*`) belum diulang
secara independen pasca-commit pada sesi ini.

Diverifikasi ulang pada 20 September 2026 setelah desain checklist PDF diterapkan. Rincian jumlah
test per file (`pytest --collect-only -q`,
hanya berkas AOM Fase 3–5 dan modul terdekat; sisanya adalah suite Fase 0–2 dan modul klinik lama):

| Berkas test | Jumlah |
|---|---:|
| `checklists/tests/test_correction_audit.py` | 5 |
| `checklists/tests/test_cross_clinic_access.py` | 4 |
| `checklists/tests/test_pdf_seed.py` | 3 |
| `checklists/tests/test_empty_pic_ui.py` | 1 |
| `checklists/tests/test_followup_idempotency.py` | 6 |
| `checklists/tests/test_opening.py` | 9 |
| `checklists/tests/test_template_sessions.py` | 7 |
| `core/tests/test_concurrency_and_privacy.py` | 11 |
| `core/tests/test_dashboard_roles.py` | 5 |
| `core/tests/test_day_state.py` | 9 |
| `core/tests/test_documentation.py` | 73 |
| `core/tests/test_pilot_readiness.py` | 15 |
| `core/tests/test_task_actions_ui.py` | 7 |
| `core/tests/test_task_delegation.py` | 10 |
| `issues/tests.py` | 16 |
| `nurses/tests.py` | 12 |
| `queueing/tests.py` | 13 |
| `reports/tests/test_confidentiality.py` | 7 |
| `reports/tests/test_laporan.py` | 19 |
| `reports/tests/test_masukan.py` | 15 |
| `reports/tests/test_report_pages.py` | 9 |

Fase 5 sebelumnya tidak menyertakan migration rehearsal karena hanya UI-layer. Desain checklist
PDF menambah migration accounts/checklists; migration rehearsal SQLite baru di `/tmp` sudah
berhasil sampai migration terbaru.

**Batasan pengujian Fase 5 yang jujur dilaporkan:** repository ini tidak memiliki
infrastruktur browser/Selenium/Playwright. "UI test" berarti Django test Client (`self.client`)
terhadap view dan rendering template — bukan browser sungguhan. Karena itu viewport mobile,
navigasi keyboard, dan kondisi koneksi lambat (disebut di plan section 14) TIDAK dapat
dibuktikan dengan test otomatis di suite ini dan tetap menjadi item QA manual. Yang otomatis
dibuktikan: dashboard per role, label tombol yang tidak tertukar, filter status data
selesai/arsip, dan direct-URL access 403 untuk pihak tak berwenang.

## Working tree (26 September 2026)

Posisi terbaru ada di bagian **Posisi terakhir** di atas. Perubahan Fase 0–5 SUDAH DI-COMMIT (`0884b3f`) dan DI-PUSH ke `origin/master`; working tree
per 26 September 2026 bersih (`git status --short` kosong). Bagian di bawah ini adalah
riwayat berkas baru/berubah per fase seperti tercatat saat implementasi (sekarang bagian dari
sejarah commit, bukan lagi perubahan pending). Berkas baru/berubah utama untuk Fase 3:

- `checklists/models.py`: `ChecklistSession`, field sesi pada `ChecklistTemplate`/`ChecklistRun`,
  field target fungsi PIC/role/assignment_mode pada template, model `ChecklistFollowup`.
- `checklists/services.py`: `create_template_version()`, `resolve_followup_audience()`,
  `record_response()` dengan parameter `reason` untuk koreksi, `create_action_item_from_response()`
  idempoten via `core.task_services.create_task`.
- `checklists/views.py`: `save_response` meneruskan `alasan` dari POST ke `record_response`.
- `checklists/admin.py`: menampilkan kolom sesi, registrasi `ChecklistFollowup`.
- `audit/models.py`: tambahan `AuditAction.CORRECTION`.
- `checklists/migrations/0002_aom_fase3_checklist.py`, `audit/migrations/0002_aom_fase3_checklist.py`.
- `accounts/migrations/0005_alter_userrole_role.py` dan
  `checklists/migrations/0003_remove_checklistrun_uniq_run_day_area_session_and_more.py`.
- `checklists/tests/` (paket baru, `checklists/tests.py` lama dipindah menjadi
  `checklists/tests/test_opening.py` tanpa perubahan isi):
  - `test_template_sessions.py`
  - `test_followup_idempotency.py`
  - `test_correction_audit.py`

Berkas sisa Fase 0–2 (lihat riwayat sebelumnya) tidak diubah lebih lanjut.

Berkas baru/berubah utama untuk Fase 4 (laporan dan masukan):

- `reports/models.py`: `Laporan`, `LaporanUpdate`, `Masukan`, `MasukanPublication` ditambahkan
  ke app `reports` yang sudah ada (sebelumnya hanya laporan operasional/ekspor CSV).
- `reports/services.py` (baru): logika visibilitas, status, publikasi, dan arsip — semua
  otorisasi server-side.
- `reports/views.py`, `reports/urls.py`, `reports/admin.py`: endpoint JSON untuk laporan dan
  masukan ditambahkan di akhir file (fungsi `index`/`export_csv` yang sudah ada sebelumnya
  tidak diubah oleh Fase 4; `active_clinic(request.user)` sudah menjadi perbaikan pra-existing
  di working tree sebelum Fase 4 dimulai).
- `core/permissions.py`: tujuh fungsi predikat baru untuk laporan/masukan (lihat di atas).
- `audit/models.py`: `AuditAction.PUBLISH`, `AuditAction.ARCHIVE` (additive, precedent `CORRECTION`).
- `reports/migrations/0001_initial.py`, `audit/migrations/0003_alter_auditevent_action.py`.
- `reports/tests/` (paket baru): `test_laporan.py`, `test_masukan.py`, `test_confidentiality.py`.

Berkas baru/berubah utama untuk Fase 5 (UI dan usability) — daftar lengkap dengan deskripsi
satu baris ada di bagian "Implementasi yang sudah ada → Fase 5" di atas; ringkasan file:

- Diubah: `core/task_services.py`, `core/views.py`, `core/urls.py`,
  `templates/core/action_items.html`, `templates/core/dashboard.html`,
  `templates/checklists/templates.html`, `templates/base.html`, `reports/views.py`,
  `reports/urls.py`, `README.md` (angka jumlah test).
- Baru: `core/tests/test_task_actions_ui.py`, `core/tests/test_dashboard_roles.py`,
  `reports/tests/test_report_pages.py`, `checklists/tests/test_empty_pic_ui.py`,
  `templates/reports/laporan_list.html`, `templates/reports/laporan_detail.html`,
  `templates/reports/masukan_list.html`, `templates/reports/masukan_detail.html`.
- Baru: `checklists/tests/test_pdf_seed.py` untuk memastikan template dan snapshot role dari
  sumber PDF dibuat idempoten.
- Tidak ada file model/migration yang ditambah atau diubah.

Berkas-berkas di atas SUDAH ter-commit di `0884b3f` (per 26 September 2026). Sebelum melakukan
commit baru berikutnya, tetap tinjau seluruh `git diff`, cek migration, ulangi test, dan
pastikan tidak ada secret, database, backup, media privat, atau data pasien yang ikut
ter-stage.

## Remediation audit keamanan

- `checklists/views.py` sekarang memvalidasi scope cabang untuk detail run, simpan respons,
  pembuatan kerusakan, pembuatan task, dan review checklist melalui direct URL.
- `checklists/services.py` mengulang pemeriksaan role dan scope cabang agar service tidak dapat
  dipanggil lintas cabang dari jalur non-HTTP.
- `reports/services.py` membatasi publisher berbasis capability ke cabang aktif dalam scope-nya
  dan menolak target cabang tidak aktif.
- Test baru: `checklists/tests/test_cross_clinic_access.py` dan dua test validasi target di
  `reports/tests/test_masukan.py`.

## Langkah berikutnya yang disetujui rencana

Fase 5 (UI dan usability) sudah diimplementasikan, lulus test desktop, DAN SUDAH DI-COMMIT/
DI-PUSH (`0884b3f`). Belum lanjut ke Fase 6. Yang masih perlu sebelum lanjut:

1. Review manusia atas diff dan bukti pengujian yang sudah di-commit (Fase 0–5).
2. Approval product owner untuk melanjutkan ke Fase 6 (migration rehearsal data AOM) — belum
   dikonfirmasi di dokumen ini.
3. Deferral eksplisit dari scope Fase 4 (masih berlaku, belum dikerjakan di Fase 5):
   - Attachment/lampiran untuk laporan dan masukan belum diimplementasikan (plan 9/11
     menyebut lampiran aman sebagai bagian Fase 4, tetapi deferred agar tidak memperluas
     scope melebihi apa yang bisa dibuktikan dengan test dalam waktu yang tersedia).
   - Pencarian teks bebas dan counter/dashboard laporan-masukan belum dibuat secara khusus
     (dashboard Fase 5 menampilkan counter sederhana untuk AOM saja, berbasis
     `visible_laporan_queryset`/`visible_masukan_queryset`; pencarian teks bebas belum ada).
   - Notifikasi publikasi masukan mengirim ke semua staf aktif cabang tujuan tanpa dedupe
     lintas-publikasi berulang di luar jendela 10 menit `notify_user`; cukup untuk MVP,
     belum diuji untuk volume besar.
4. Deferral eksplisit dari scope Fase 5:
   - Mobile viewport, navigasi keyboard, dan simulasi koneksi lambat (plan section 14)
     TIDAK dapat dibuktikan dengan Django test Client — tetap manual QA, belum dilakukan.
   - Checklist template session/target belum punya form buat/edit lewat UI (tetap lewat
     Django admin seperti sebelumnya) — Fase 5 hanya menambah tampilan baca yang menjelaskan
     field tsb., bukan form create/update; ini konsisten dengan batas eksplisit Fase 3.
   - Action item "Batal" (`assignment_cancel`) sudah punya view+URL tapi belum punya tombol
     di `templates/core/action_items.html` (cakupan test hanya di level view langsung);
     dapat ditambahkan di iterasi UI berikutnya bila product owner memintanya.

## Approval yang masih diperlukan

- Review bukti dan persetujuan untuk melanjutkan dari Fase 5 ke Fase 6.
- Persetujuan owner atas identitas/penugasan PIC sebelum seed atau import akun nyata.
- Persetujuan terpisah sebelum commit/push rilis, migration rehearsal data AOM, deployment,
  atau penghentian AOM standalone.
