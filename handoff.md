# Handoff JoDerma Operasional

Dokumen ini adalah titik masuk untuk melanjutkan integrasi AOM sesuai
[`docs/AOM_MODULE_INTEGRATION_PLAN.md`](docs/AOM_MODULE_INTEGRATION_PLAN.md).

## Status saat handoff

- Repository: `/home/hansen-sudarma/Desktop/joderma-operasional`.
- Target kerja: desktop development Ubuntu/Linux.
- Target produksi: mini PC Ubuntu; belum boleh disentuh atau dideploy.
- Baseline sebelum perubahan AOM: `6fc10f98079de85c52c8004ff634a5b68fd4ad60`.
- Fase 0, 1, dan 2 sudah diimplementasikan dan gate pengujiannya lulus.
- Fase 3 (checklist harian) sudah diimplementasikan dan bukti pengujiannya lulus.
- Fase 4 (laporan dan masukan) sudah diimplementasikan dan bukti pengujiannya lulus.
- Fase 5 (UI dan usability) sudah diimplementasikan dan bukti pengujiannya lulus.
  Gate Fase 5 BELUM disetujui — menunggu review manusia sebelum Fase 6.
- Perubahan masih uncommitted. Jangan commit/push sebelum diff dan bukti pengujian
  ditinjau serta ada persetujuan yang diperlukan.

## Cara melanjutkan

1. Baca seluruh `AGENTS.md` dan `docs/AOM_MODULE_INTEGRATION_PLAN.md`.
2. Periksa `git status --short` dan jangan menghapus perubahan yang sudah ada.
3. Jalankan baseline cepat sebelum mengubah kode:

   ```bash
   .venv/bin/python manage.py check
   .venv/bin/python -m pytest -q --tb=short
   ```

4. Kerjakan satu fase saja. Fase 3 (checklist opening/closing, template berversi,
   assignment fungsi/tier, task tindak lanjut idempoten, koreksi dengan audit trail),
   Fase 4 (laporan cabang/rahasia AOM, publikasi masukan, arsip beralasan), dan Fase 5
   (dashboard per role, bahasa tindakan jelas, filter data selesai, halaman HTML
   laporan/masukan) sudah diimplementasikan — lihat `current-progress.md` untuk detail
   berkas dan bukti. Fase berikutnya yang boleh dikerjakan setelah approval adalah Fase 6:
   migration rehearsal data AOM standalone.
5. Gunakan database dummy atau salinan database untuk semua migration rehearsal dan UAT.
6. Setelah implementasi, jalankan test terkait, test penuh, `makemigrations --check`,
   `git diff --check`, dan migration rehearsal di database sementara.
7. Berhenti pada gate Fase 6 dan minta approval sebelum mengerjakan Fase 7, sama seperti
   Fase 5 saat ini berhenti menunggu approval sebelum Fase 6.

## Bukti pengujian terakhir

Pada akhir Fase 5, bukti berikut berhasil (diverifikasi ulang secara independen):

- `manage.py check` lulus (0 issues).
- Test penuh: 333 test lulus (`.venv/bin/python -m pytest -q --tb=short`), termasuk test
  remediation security, seed checklist PDF, dan role-scoped UI.
- `manage.py makemigrations --check --dry-run`: `No changes detected` (sebelum DAN sesudah
  Fase 5 — tidak ada perubahan model, murni UI-layer di atas model Fase 1–4).
- `git diff --check` lulus (tidak ada whitespace error).
- Tidak ada migration rehearsal baru untuk Fase 5 (tidak relevan, tidak ada migration baru).
  Migration rehearsal Fase 4 (SQLite sementara `/tmp`) tetap menjadi bukti terakhir untuk
  skema saat ini.

Diverifikasi ulang pada 20 September 2026 (bukan hanya klaim implementasi): `manage.py check`
bersih, `pytest` penuh → 333 passed, `makemigrations
--check --dry-run` → `No changes detected`, `git diff --check` → bersih (exit 0). Working
tree: 58 baris `git status --short` (file berubah/baru Fase 0–5), tidak ada commit.

**Batasan pengujian yang jujur dilaporkan (plan section 14):** repository ini TIDAK memiliki
infrastruktur browser/Selenium/Playwright. Django test Client menguji view dan rendering
HTML, bukan browser sungguhan. Karena itu viewport mobile, navigasi keyboard, dan simulasi
koneksi lambat TIDAK dibuktikan dengan test otomatis — tetap manual QA, belum dilakukan.
Yang dibuktikan otomatis: dashboard berbeda per role (Staff/PIC/AOM/Admin), tombol
"Ajukan selesai" vs "Konfirmasi selesai"/"Minta revisi" tidak tertukar (label dan endpoint
terpisah, teks tombol diverifikasi lewat assertion pada HTML respons), data selesai/arsip
tetap dapat ditemukan lewat filter status eksplisit, direct-URL access oleh pihak tak
berwenang menghasilkan 403 (bukan 200/500/kebocoran data), dan pesan error PIC kosong
tampil ramah di view checklist (bukan crash).

## Berkas utama hasil Fase 1–5

- `accounts/models.py`, `core/permissions.py`, dan `core/services.py`: role, capability,
  scope cabang, organisasi, serta fungsi PIC.
- `core/models.py` dan `core/task_services.py`: snapshot penerima, assignment individual/
  bersama, status, event, submit, revision, confirm, cancel, dan `can_review_assignment`
  (Fase 5: nama publik untuk predikat reviewer, dipakai view layer).
- `accounts/test_aom_phase1.py` dan `core/tests/test_task_delegation.py`: regression tests.
- Migration: `accounts/migrations/0004_*.py`, `core/migrations/0002_*.py`.
- `core/management/commands/preview_aom_seed.py`: preview seed tanpa menulis database.
- `checklists/models.py`: `ChecklistSession` (OPENING/CLOSING/ANYTIME), field sesi pada
  `ChecklistTemplate`/`ChecklistRun`, target fungsi PIC/role/assignment_mode pada template,
  model `ChecklistFollowup` untuk idempotensi tindak lanjut.
- `checklists/services.py`: `create_template_version()` (histori tidak berubah saat template
  diedit), `record_response()` dengan `reason` wajib untuk koreksi, `create_action_item_from_response()`
  idempoten via `core.task_services.create_task`.
- `audit/models.py`: `AuditAction.CORRECTION` untuk membedakan koreksi dari update biasa.
- Migration: `checklists/migrations/0002_*.py`, `audit/migrations/0002_*.py`.
- `checklists/tests/` (paket): `test_template_sessions.py`, `test_followup_idempotency.py`,
  `test_correction_audit.py`, `test_opening.py` (isi lama `checklists/tests.py`, dipindah
  tanpa perubahan), `test_empty_pic_ui.py` (Fase 5: pesan ramah PIC kosong di view).
- `reports/models.py`: `Laporan`, `LaporanUpdate` (visibilitas `CABANG`/`RAHASIA_AOM`, status
  `OPEN`/`UNDER_REVIEW`/`RESOLVED`/`CLOSED`/`ARCHIVED`), `Masukan`, `MasukanPublication`
  (snapshot isi immutable saat publikasi AOM, mirror pola `TaskAudienceSnapshot`).
- `reports/services.py` (baru): `create_laporan`, `visible_laporan_queryset`,
  `change_laporan_status`, `archive_laporan`, `log_confidential_access`, `create_masukan`,
  `visible_masukan_queryset`, `publish_masukan`, `archive_masukan`.
- `reports/views.py`, `reports/urls.py`, `reports/admin.py`: endpoint JSON laporan/masukan
  (Fase 4) plus halaman HTML `laporan_page`/`laporan_page_detail`/`masukan_page`/
  `masukan_page_detail` (Fase 5) yang dibangun di atas service layer yang sama.
- `core/permissions.py`: `can_view_laporan`, `can_create_laporan`, `can_archive_laporan`,
  `can_view_masukan`, `can_publish_masukan`, `can_view_published_masukan`,
  `can_archive_masukan` — mengikuti pola `can_view_restricted_issue`.
- `audit/models.py`: `AuditAction.PUBLISH`, `AuditAction.ARCHIVE` (additive).
- Migration: `reports/migrations/0001_initial.py`, `audit/migrations/0003_*.py`.
- `reports/tests/` (paket): `test_laporan.py`, `test_masukan.py`,
  `test_confidentiality.py` — termasuk negative test kebocoran lintas cabang/rahasia lewat
  direct URL, list, dan queryset service-layer; `test_report_pages.py` (Fase 5: halaman HTML,
  filter status, direct-URL negatif).
- `core/views.py`, `core/urls.py`: view baru Fase 5 `assignment_claim`/`assignment_submit`/
  `assignment_confirm`/`assignment_revision`/`assignment_cancel`; `action_items` dan
  `dashboard` diperluas dengan context per role/assignment tanpa mengubah logika day-state
  yang sudah ada.
- `templates/core/action_items.html`, `templates/core/dashboard.html`,
  `templates/checklists/templates.html`, `templates/base.html`,
  `templates/reports/laporan_list.html`, `laporan_detail.html`, `masukan_list.html`,
  `masukan_detail.html` (baru): UI Fase 5.
- `core/tests/test_task_actions_ui.py`, `core/tests/test_dashboard_roles.py`: test Fase 5.

Detail lengkap ada di `current-progress.md`.

## Batasan dan risiko yang masih berlaku

- Belum ada seed akun produksi; nama dan penugasan PIC masih harus diverifikasi owner.
- AOM standalone tetap berjalan. Jangan mematikannya tanpa rekonsiliasi, masa observasi,
  dan persetujuan terpisah.
- Belum ada migration rehearsal data AOM standalone, UAT penuh berbasis hasil migrasi, atau
  deployment.
- Fase 4 sengaja TIDAK mengimplementasikan attachment/lampiran untuk laporan dan masukan
  (plan 9/11 menyebutnya, tetapi dideferral eksplisit agar tidak memperluas scope melebihi
  bukti test yang bisa diberikan). Belum ada pencarian teks bebas untuk laporan/masukan;
  Fase 5 menambah counter ringkas untuk AOM di dashboard, berbasis
  `visible_laporan_queryset`/`visible_masukan_queryset` (bukan query baru).
- Fase 5 sengaja TIDAK mengimplementasikan form create/edit template checklist lewat UI biasa
  (tetap lewat Django admin, konsisten dengan batas Fase 3); Fase 5 hanya menambah tampilan
  baca yang menjelaskan sesi/mode/target template.
- Tombol "Batal" untuk task assignment (`core:assignment_cancel`) sudah punya view+URL+test
  langsung tetapi BELUM punya tombol di `templates/core/action_items.html` — dapat ditambahkan
  bila product owner memintanya di iterasi berikutnya.
- Mobile viewport, navigasi keyboard, dan simulasi koneksi lambat (plan section 14) TIDAK
  dapat dibuktikan dengan Django test Client di repo ini — tetap manual QA, belum dilakukan.
- Pastikan setiap perubahan otorisasi tetap server-side dan memiliki negative test lintas
  cabang.
- Remediation audit terakhir menutup direct-URL checklist lintas cabang dan membatasi target
  publikasi masukan ke cabang aktif dalam scope publisher. Periksa test terkait sebelum
  menyatakan gate keamanan selesai.

## Format laporan saat berhenti di gate

Laporkan file berubah, perintah test dan hasilnya, migration rehearsal, risiko yang tersisa,
serta approval yang dibutuhkan. Jangan menyatakan fase selesai bila gate-nya belum terbukti.
