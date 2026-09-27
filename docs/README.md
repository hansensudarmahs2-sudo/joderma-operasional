# Dokumentasi JoDerma Staff Ops

**Melanjutkan setelah jeda?** Mulai dari
[`lanjutkan-pekerjaan.md`](lanjutkan-pekerjaan.md).

Selain itu, mulai dari peran Anda.

## Saya staf klinik

| Saya ingin | Baca |
|---|---|
| Tahu cara mengisi pekerjaan harian | [`panduan-staf.md`](panduan-staf.md) |
| Melakukan review, verifikasi, dan penutupan hari | [`panduan-supervisor.md`](panduan-supervisor.md) |
| Membuat akun dan mengatur izin | [`panduan-admin.md`](panduan-admin.md) |
| Memakai halaman Direktur Operasional (Tim, checklist Direktur, catatan) | [`panduan-direktur.md`](panduan-direktur.md) |

## Saya mengurus server

| Saya ingin | Baca |
|---|---|
| Tahu instalasi klinik yang sedang berjalan | [`deployment-klinik.md`](deployment-klinik.md) |
| Backup, restore, atau menangani gangguan | [`runbook.md`](runbook.md) |
| Memperbarui aplikasi ke versi baru | [`deployment-klinik.md`](deployment-klinik.md) |

## Saya akan melanjutkan kodenya

| Saya ingin | Baca |
|---|---|
| Memahami bentuk sistem dan alasan keputusannya | [`arsitektur.md`](arsitektur.md) |
| Tahu siapa boleh apa | [`peran-dan-akses.md`](peran-dan-akses.md) |
| Menjalankan dan menguji secara lokal | [`../README.md`](../README.md) |
| Melanjutkan rencana integrasi AOM | [`AOM_MODULE_INTEGRATION_PLAN.md`](AOM_MODULE_INTEGRATION_PLAN.md) |
| Melihat kontrak ekspor legacy AOM standalone (Fase 6) | [`AOM_LEGACY_EXPORT_SCHEMA.md`](AOM_LEGACY_EXPORT_SCHEMA.md) |

## Saya owner atau manajemen

| Saya ingin | Baca |
|---|---|
| Memutuskan hal yang menunggu keputusan saya | [`../OWNER_DECISION_REVIEW.md`](../OWNER_DECISION_REVIEW.md) |
| Menjalankan uji coba lima hari | [`../UAT_5_DAY_PILOT_PLAN.md`](../UAT_5_DAY_PILOT_PLAN.md) |
| Memutuskan aman tidaknya dipakai penuh | [`../GO_LIVE_READINESS_CHECKLIST.md`](../GO_LIVE_READINESS_CHECKLIST.md) |

## Dokumen uji coba

| Berkas | Isi |
|---|---|
| [`../UAT_5_DAY_PILOT_PLAN.md`](../UAT_5_DAY_PILOT_PLAN.md) | rencana lima hari, kriteria berhasil, berhenti, dan kembali ke cara lama |
| [`../UAT_TEST_SCENARIOS.md`](../UAT_TEST_SCENARIOS.md) | 64 skenario uji beserta kolom hasil |
| [`../UAT_ISSUE_REGISTER.md`](../UAT_ISSUE_REGISTER.md) | daftar temuan, tingkat keparahan, dan statusnya |
| [`../DAILY_PILOT_CHECKLIST.md`](../DAILY_PILOT_CHECKLIST.md) | pemeriksaan harian owner dan supervisor |
| [`../PILOT_FEEDBACK_FORM.md`](../PILOT_FEEDBACK_FORM.md) | formulir umpan balik staf |
| [`../DECISIONS.md`](../DECISIONS.md) | keputusan bisnis sementara |

## Aturan menjaga dokumen ini

Dokumen yang salah lebih berbahaya daripada dokumen yang tidak ada, karena orang
mengikutinya tanpa curiga. Bila mengubah kode, periksa dokumen yang
menjelaskannya dalam perubahan yang sama:

| Yang berubah | Perbarui juga |
|---|---|
| `core/permissions.py` atau peran | [`peran-dan-akses.md`](peran-dan-akses.md) |
| Label tombol atau alur layar | [`panduan-staf.md`](panduan-staf.md), [`panduan-supervisor.md`](panduan-supervisor.md), [`../UAT_TEST_SCENARIOS.md`](../UAT_TEST_SCENARIOS.md) |
| Cara deploy atau konfigurasi | [`deployment-klinik.md`](deployment-klinik.md), [`runbook.md`](runbook.md) |
| Jumlah test | [`../README.md`](../README.md), [`arsitektur.md`](arsitektur.md) |
| Keputusan bisnis | [`../DECISIONS.md`](../DECISIONS.md), [`../OWNER_DECISION_REVIEW.md`](../OWNER_DECISION_REVIEW.md) |
