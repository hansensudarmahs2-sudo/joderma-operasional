# Kontrak Ekspor Legacy AOM Standalone (Fase 6)

> **STATUS: KONTRAK DOKUMENTASI, BELUM DIVALIDASI TERHADAP SISTEM ASLI.**
> Sumber kode AOM standalone yang sesungguhnya TIDAK tersedia di lingkungan
> pengembangan ini. Dokumen ini mendefinisikan format JSON yang diharapkan dari
> ekspor AOM standalone berdasarkan deskripsi entitas pada
> `docs/AOM_MODULE_INTEGRATION_PLAN.md` bagian 12.1–12.3. Seluruh rehearsal
> Fase 6 pada sesi ini memakai **data sintetis/dummy** yang dibangkitkan oleh
> `aom_migration generate_legacy_export_fixture`, sesuai izin eksplisit
> `AGENTS.md` untuk memakai data dummy/salinan pada migration rehearsal.
> **Data produksi AOM standalone yang sesungguhnya TIDAK BOLEH dipakai** sampai
> kontrak ini ditinjau ulang dan dikonfirmasi cocok dengan struktur ekspor
> nyata (field, tipe, dan makna status) oleh pemilik sistem AOM standalone.

## 1. Tujuan

Mendefinisikan format pertukaran data read-only, satu arah (AOM standalone →
JoDerma Operasional), untuk 7 tabel sumber pada plan 12.1:

- `ChecklistTemplate`
- `DailyChecklist`
- `Task`
- `Note`
- `Activity`
- `DailyClose`
- `AuditEvent`

Ekspor bersifat **read-only** dari sisi AOM standalone (plan 12.2.1): tidak ada
tulisan balik ke AOM standalone dari proses ini.

## 2. Bentuk berkas

Satu berkas JSON per ekspor, dengan struktur:

```json
{
  "manifest": {
    "exported_at": "2026-09-26T10:00:00+07:00",
    "source_label": "AOM-STANDALONE-DUMMY",
    "tables": {
      "ChecklistTemplate": {"row_count": 2, "checksum": "sha256:..."},
      "DailyChecklist": {"row_count": 3, "checksum": "sha256:..."},
      "Task": {"row_count": 5, "checksum": "sha256:..."},
      "Note": {"row_count": 2, "checksum": "sha256:..."},
      "Activity": {"row_count": 4, "checksum": "sha256:..."},
      "DailyClose": {"row_count": 2, "checksum": "sha256:..."},
      "AuditEvent": {"row_count": 5, "checksum": "sha256:..."}
    },
    "overall_checksum": "sha256:..."
  },
  "ChecklistTemplate": [ {...record...}, ... ],
  "DailyChecklist": [ {...record...}, ... ],
  "Task": [ {...record...}, ... ],
  "Note": [ {...record...}, ... ],
  "Activity": [ {...record...}, ... ],
  "DailyClose": [ {...record...}, ... ],
  "AuditEvent": [ {...record...}, ... ]
}
```

### 2.1 Checksum per record

Setiap record memiliki field `checksum` berisi `sha256:<hex>` dari JSON kanonik
record itu sendiri **tanpa field `checksum`**, dengan kunci diurutkan
(`json.dumps(record_without_checksum, sort_keys=True, separators=(",", ":"))`)
lalu di-hash SHA-256. Ini memungkinkan verifikasi integritas per baris saat
rekonsiliasi (plan 12.3) tanpa bergantung pada urutan field.

### 2.2 Checksum per tabel dan keseluruhan

- `manifest.tables.<Nama>.checksum`: `sha256:<hex>` dari gabungan checksum
  seluruh record tabel tsb., diurutkan berdasarkan `legacy_id` lalu digabung
  dengan pemisah `\n`, lalu di-hash SHA-256.
- `manifest.overall_checksum`: `sha256:<hex>` dari gabungan
  `manifest.tables.<Nama>.checksum` untuk seluruh 7 tabel (urutan tabel sesuai
  daftar tetap di atas), pemisah `\n`, lalu di-hash SHA-256.

Kedua checksum agregat ini adalah "checksum artefak ekspor" yang wajib dicatat
sebagai bukti (plan bagian 18).

## 3. Skema per tabel

Semua record wajib memiliki `legacy_id` (string, unik per tabel di sumber) dan
`checksum` (lihat 2.1). Label aktor (`created_by`, `assigned_to`, `author`,
`actor`, `closed_by`) adalah **string bebas dari sistem lama**, BUKAN foreign
key ke user JoDerma Operasional — sesuai plan 12.2.4, label ini tidak boleh
ditebak menjadi user nyata.

### 3.1 `ChecklistTemplate`

| Field | Tipe | Keterangan |
|---|---|---|
| `legacy_id` | string | ID template di AOM standalone |
| `name` | string | Nama template |
| `area` | string | Area/lokasi checklist |
| `active` | bool | Status aktif template |
| `order` | int | Urutan tampil |
| `checksum` | string | lihat 2.1 |

### 3.2 `DailyChecklist`

| Field | Tipe | Keterangan |
|---|---|---|
| `legacy_id` | string | ID entri checklist harian |
| `template_legacy_id` | string | Referensi ke `ChecklistTemplate.legacy_id` |
| `date` | string (YYYY-MM-DD) | Tanggal checklist |
| `area` | string | Area checklist |
| `status` | string | mis. `COMPLETE`/`INCOMPLETE`/`PROBLEM` (nilai apa adanya dari sumber, tidak dipetakan ulang) |
| `responses` | object | Payload jawaban item, struktur bebas apa adanya dari sumber |
| `checksum` | string | lihat 2.1 |

### 3.3 `Task`

| Field | Tipe | Keterangan |
|---|---|---|
| `legacy_id` | string | ID task |
| `title` | string | Judul task |
| `description` | string | Uraian |
| `status` | string | `OPEN` atau `DONE` |
| `created_by_label` | string | Label aktor pembuat (bebas, bukan FK) |
| `assigned_to_label` | string \| null | Label aktor penerima; `null` bila tidak ada penerima |
| `created_at` | string ISO-8601 | Waktu dibuat |
| `done_at` | string ISO-8601 \| null | Waktu selesai; wajib ada bila `status == "DONE"` |
| `checksum` | string | lihat 2.1 |

### 3.4 `Note`

| Field | Tipe | Keterangan |
|---|---|---|
| `legacy_id` | string | ID catatan |
| `content` | string | Isi catatan |
| `author_label` | string | Label aktor penulis |
| `created_at` | string ISO-8601 | Waktu dibuat |
| `related_task_legacy_id` | string \| null | Referensi opsional ke `Task.legacy_id` |
| `checksum` | string | lihat 2.1 |

### 3.5 `Activity`

| Field | Tipe | Keterangan |
|---|---|---|
| `legacy_id` | string | ID aktivitas |
| `description` | string | Deskripsi aktivitas |
| `actor_label` | string | Label aktor |
| `timestamp` | string ISO-8601 | Waktu kejadian |
| `checksum` | string | lihat 2.1 |

### 3.6 `DailyClose`

| Field | Tipe | Keterangan |
|---|---|---|
| `legacy_id` | string | ID penutupan harian |
| `date` | string (YYYY-MM-DD) | Tanggal |
| `area` | string | Area yang ditutup |
| `closed_by_label` | string | Label aktor yang menutup |
| `summary` | string | Ringkasan penutupan |
| `timestamp` | string ISO-8601 | Waktu penutupan dicatat |
| `checksum` | string | lihat 2.1 |

### 3.7 `AuditEvent`

| Field | Tipe | Keterangan |
|---|---|---|
| `legacy_id` | string | ID audit event |
| `actor_label` | string | Label aktor |
| `action` | string | Aksi bebas dari sumber (mis. `CREATE_TASK`, `CLOSE_DAY`) |
| `target` | string | Deskripsi entitas target (bebas teks) |
| `timestamp` | string ISO-8601 | Waktu kejadian |
| `metadata` | object | Payload tambahan bebas |
| `checksum` | string | lihat 2.1 |

## 4. Aturan pemetaan saat import (ringkasan, detail di kode importer)

Mengikuti plan 12.2 secara eksplisit:

1. `Task` → `core.ActionItem` (+ `core.TaskAssignment` bila ada penerima yang
   *dapat dipetakan*). Cabang default adalah **Jemur Andayani** kecuali fixture
   menyediakan kode cabang eksplisit — aturan ini harus disetujui saat
   rehearsal (plan 12.2.3) dan **selalu dicatat eksplisit** di catatan batch
   import serta output command, tidak pernah didiamkan.
2. Label aktor (`assigned_to_label`, `created_by_label`, `author_label`,
   `actor_label`, `closed_by_label`) TIDAK PERNAH ditebak jadi user Django.
   Disimpan sebagai `aom_migration.LegacyActor` dengan `mapped_user=None`
   kecuali sudah ada mapping tervalidasi sebelumnya untuk label yang sama
   persis.
3. `Task` berstatus `OPEN` tanpa penerima yang bisa dipetakan menjadi
   `ActionItem` terbuka tanpa `TaskAssignment` — bukan error, tetapi masuk
   daftar exception yang harus diselesaikan sebelum produksi (plan 12.2.5).
4. `Task` berstatus `DONE` menjadi `ActionItem` + `TaskAssignment` berstatus
   `CONFIRMED`, dengan `imported_legacy=True`, `legacy_source_id` diisi
   `legacy_id`, dan `legacy_completed_at` diisi dari `done_at` (plan 12.2.6).
5. `ChecklistTemplate`, `DailyChecklist`, `Note`, `Activity`, `DailyClose`
   TIDAK dikonversi menjadi objek checklist/live baru — disimpan verbatim
   sebagai histori read-only di `aom_migration.LegacyArchive` (plan 12.2.7:
   "Note dan Activity tetap dipertahankan sebagai histori").
6. `AuditEvent` → `audit.AuditEvent` baru dengan `action=MIGRATION_IMPORT`
   (atau aksi asal yang dipetakan secara eksplisit dan aman bila ada padanan
   jelas), `actor` tetap `None` (label disimpan di `actor_label`), dan
   `before_json`/`after_json` menyimpan payload legacy apa adanya untuk audit
   trail.
7. Setiap record sumber yang berhasil dipetakan WAJIB memiliki baris
   `aom_migration.LegacyIdMap` (`source_model`, `legacy_id`, `target_model`,
   `target_id`) — ini adalah dasar deteksi idempotensi: menjalankan ulang
   import pada berkas ekspor yang sama TIDAK membuat baris target baru.

## 5. Rekonsiliasi (plan 12.3)

`aom_migration reconcile_legacy_import` memverifikasi:

- Jumlah baris per tabel pada `manifest.tables.*.row_count` cocok dengan
  jumlah `LegacyIdMap`/`LegacyArchive` untuk batch tsb.
- Checksum per record (2.1) pada sample/seluruh baris cocok dengan yang
  tercatat saat import.
- Menghasilkan laporan PASS/FAIL eksplisit beserta daftar exception (task
  tanpa penerima, label aktor belum ter-mapping ke user nyata).
- Import kedua pada berkas yang sama menghasilkan nol baris `LegacyIdMap` baru
  (plan 12.3: "Import kedua menghasilkan nol duplikasi").
