# Temuan Owner: task besar, sub task, dan hasil yang terlihat Owner

Status: desain disetujui product owner di percakapan 6 Oktober 2026; menunggu tinjauan spec.

## Tujuan

1. Owner mencatat temuan; Direktur Operasional memprosesnya.
2. Direktur menjadikan temuan itu satu **task besar** (mis. "Membuat alur untuk temuan X") dan
   memecahnya menjadi **sub task**, mis. koordinator shift menyosialisasikan ke rekan, Direktur
   menulis alur, Direktur mengevaluasi kesiapan staf dengan menanyakan alurnya.
3. Di dashboard Owner, tiap temuan menunjukkan progres, target dan kapan selesai, serta hasilnya:
   sub task apa yang dikerjakan oleh siapa dan apakah sudah diverifikasi Direktur.
4. Tanda **mendesak** pada temuan menentukan batas target.

## Yang sudah ada (tidak dibangun ulang)

- `owner.OwnerRequest` berjenis `TEMUAN`, dengan `urgent`, `target_date` (opsional untuk temuan),
  catatan, dan foto.
- Direktur menambah task dari halaman detail temuan (`owner/views.py:_request_task`), disimpan
  sebagai `core.ActionItem` dengan `source_type="permintaan_owner"`, `source_id=<temuan>`.
- Alur penerima task: ajukan selesai, lalu konfirmasi atau minta revisi oleh pemeriksa
  (`core/task_services.py`).
- `services.progress()` dan `request_rows()` untuk dashboard dan detail.

## Keputusan

| # | Keputusan |
|---|---|
| K1 | Satu temuan = satu task besar. Tidak ada tingkat baru di `core.ActionItem`; task yang sudah ada di bawah temuan berperan sebagai sub task. |
| K2 | Hasil yang dilihat Owner: per sub task siapa yang mengerjakan dan status verifikasinya. Tanpa foto, tanpa kesimpulan tertulis tambahan. |
| K3 | Sub task yang dikerjakan staf/PIC diverifikasi Direktur Operasional. Sub task yang dikerjakan Direktur sendiri tidak diverifikasi: selesai saat Direktur menandainya. Tanggung jawabnya ada pada pernyataan "temuan selesai" (bila keliru, menjadi penilaian Owner terhadap Direktur). |
| K4 | Temuan selesai hanya bila Direktur menyatakannya ("Nyatakan selesai & terverifikasi"), tidak otomatis. |
| K5 | Mendesak tetap centang tidak wajib. Dicentang: target paling lambat tanggal catat + 3 hari. Tidak dicentang: Direktur menentukan target, paling lambat tanggal catat + 30 hari; selama belum diisi, batas +30 hari yang berlaku. |
| K6 | Hanya berlaku untuk temuan. Permintaan Owner (target diisi Owner) dan task dari modul lain tidak berubah. |

## Bagian 1: Aturan target dan status

### Data

Tambahan pada `owner.OwnerRequest` (migrasi additive, semua nullable/blank):

- `plan_title` (CharField 200, blank): nama task besar. Bila kosong, tampilan memakai `title`.
- `completed_at` (DateTimeField, null) dan `completed_by` (FK User, null, PROTECT).

Tanggal pencatatan = `created_at` dalam zona waktu klinik (`local_today` dari `created_at`).

### Target

- Batas: `deadline_cap = tanggal_catat + 3 hari` bila `urgent`, selain itu `tanggal_catat + 30 hari`.
- Mendesak: saat dibuat, `target_date = tanggal_catat + 3`. Direktur boleh memajukan, tidak boleh
  melewati batas.
- Tidak mendesak: `target_date` kosong saat dibuat; Direktur mengisinya, maksimal `deadline_cap`.
- Target efektif = `target_date` bila ada, selain itu `deadline_cap`. Keterlambatan dihitung dari
  target efektif. Tampilan membedakan "target <tgl>" dan "paling lambat <tgl>" (belum ditetapkan).
- Form temuan untuk Owner tidak lagi menampilkan kolom target; Owner hanya mencentang mendesak.
- Validasi di service (server-side): target tidak boleh sebelum hari ini dan tidak boleh melewati
  `deadline_cap`; hanya Direktur Operasional yang mengubah rencana.

### Status temuan

| Status | Kondisi |
|---|---|
| Menunggu Direktur | belum ada sub task aktif |
| Berjalan | ada sub task, belum semua selesai |
| Siap ditutup | ada ≥1 sub task dan semua `SELESAI`, `completed_at` kosong |
| Selesai & terverifikasi | `completed_at` terisi |

- "Nyatakan selesai" ditolak server bila tidak ada sub task atau masih ada yang belum `SELESAI`,
  atau bila pelaku bukan Direktur Operasional.
- Setelah selesai: tepat waktu bila `completed_at` (tanggal lokal) ≤ target efektif, selain itu
  "terlambat n hari".
- Tidak ada fitur buka kembali. Bila hasil keliru, Owner menulis catatan seperti sekarang.
- Owner diberi notifikasi saat temuan dinyatakan selesai. Peristiwa dicatat di audit.

### Urutan daftar

Temuan mendesak yang belum selesai di atas, lalu yang terlambat, lalu menurut target efektif.

## Bagian 2: Verifikasi sub task

Sub task temuan = `ActionItem` dengan `source_type="permintaan_owner"` yang `source_id`-nya
`OwnerRequest` berjenis `TEMUAN`. Satu fungsi penentu di `core` (mis. `is_temuan_subtask(item)`)
dipakai oleh:

- `ActionItem.effective_review_by`: untuk sub task temuan selalu `DIREKTUR`, walaupun salah satu
  penerimanya Direktur Operasional. Di luar temuan, aturan "pekerjaan Direktur diperiksa Dirut"
  tetap berlaku.
- `can_review_assignment`: untuk sub task temuan, hanya Direktur Operasional yang memverifikasi;
  Owner tidak. Penerima tetap tidak boleh memverifikasi dirinya sendiri.
- `submit_assignment`: bila sub task temuan diajukan oleh Direktur Operasional (pada assignment
  miliknya), assignment langsung `CONFIRMED` tanpa pemeriksa, dengan event yang mencatat
  "selesai tanpa verifikasi (task Direktur pada temuan)". Seperti di `confirm_assignment`,
  `ActionItem` menjadi `SELESAI` bila semua assignment-nya sudah `CONFIRMED`; logika itu dipakai
  bersama, bukan disalin.
- Antrean verifikasi Owner (`owner.services.verification_queue`) tidak memuat sub task temuan
  (otomatis, karena `reviewed_by_dirut` menjadi salah).

Status sub task untuk Owner: Berjalan, Menunggu verifikasi, Terverifikasi Direktur, Selesai oleh
Direktur. "Dikerjakan oleh" = penerima yang assignment-nya `CONFIRMED`.

## Bagian 3: Tampilan

### Dashboard Owner

Satu baris per temuan: label Mendesak, judul temuan dan nama task besar, target efektif dengan
"sisa n hari"/"terlambat n hari", progres "x dari y sub task selesai", status temuan, dan bila
selesai: "Selesai & terverifikasi oleh <Direktur>, <tanggal>, tepat waktu / terlambat n hari".
Baris membuka halaman detail.

### Detail temuan (Owner dan Direktur)

- Temuan dari Owner (judul, rincian, foto), mendesak, target, status.
- Daftar sub task: judul, dikerjakan oleh, status, tanggal selesai.
- Catatan Owner–Direktur tetap.

### Khusus Direktur di detail temuan

- Form Rencana penanganan: nama task besar dan target (batas 3 atau 30 hari).
- Form Tambah sub task yang sudah ada; Direktur boleh memilih dirinya sebagai penerima.
- Tombol "Nyatakan selesai & terverifikasi", tampil hanya saat Siap ditutup, dengan konfirmasi.

## Pengujian

Test otomatis:

- batas target mendesak 3 hari dan tidak mendesak 30 hari, termasuk target kosong dan target
  melewati batas;
- target efektif dan perhitungan terlambat/tepat waktu;
- status temuan untuk keempat keadaan;
- "Nyatakan selesai" ditolak saat tidak ada sub task, saat ada sub task terbuka, dan bila pelaku
  bukan Direktur Operasional;
- sub task Direktur pada temuan langsung `CONFIRMED` tanpa pemeriksa;
- sub task staf pada temuan diverifikasi Direktur dan tidak muncul di antrean Owner;
- task Direktur di luar temuan (Permintaan, modul lain) tetap diperiksa Dirut/Owner;
- form temuan tanpa kolom target; Permintaan tetap mewajibkan target;
- tampilan dashboard dan detail untuk Owner dan Direktur.

Uji UI di browser pada database pengembangan: Owner dan Direktur, desktop dan HP.

## Di luar cakupan

- Lebih dari satu task besar per temuan.
- Kesimpulan tertulis atau lampiran hasil di tingkat temuan.
- Persetujuan Owner atas penutupan, dan membuka kembali temuan.
- Perubahan pada Permintaan Owner dan task dari modul lain.
