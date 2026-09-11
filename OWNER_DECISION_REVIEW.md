# Owner Decision Review — 12 Keputusan PROVISIONAL

**Versi:** 1.0
**Tanggal:** 11 September 2026
**Untuk:** Owner/Manajemen Klinik JoDerma
**Disiapkan oleh:** Tim implementasi
**Sumber:** `DECISIONS.md` (jawaban PRD Bagian 27) — seluruhnya masih berstatus PROVISIONAL

---

## Cara membaca dokumen ini

Setiap keputusan dikelompokkan menjadi tiga:

| Kelompok | Arti | Konsekuensi bila tidak diputuskan |
|---|---|---|
| **A. Must decide before pilot** | Harus diputuskan **sebelum Hari 1** | Pilot menghasilkan data yang salah atau staf bekerja dengan aturan yang keliru |
| **B. May remain provisional during pilot** | Boleh memakai default; pilot justru dipakai untuk **menguji** apakah default itu tepat | Tidak ada — memang sengaja diuji |
| **C. Must decide before production** | Boleh provisional selama pilot, tetapi **wajib diputuskan sebelum go-live** | Risiko kepatuhan/hukum atau operasional jangka panjang |

Setiap keputusan menyertakan **kolom keputusan owner** untuk diisi. Bila owner memilih
nilai berbeda dari default, tim teknis mengubahnya lewat **Admin ▸ Konfigurasi** — tanpa
perubahan kode dan tercatat di audit log.

**Tim teknis tidak akan mengubah aturan bisnis apa pun tanpa keputusan tertulis di sini.**

---

## Ringkasan pengelompokan

| Kelompok | Keputusan |
|---|---|
| **A. Sebelum pilot** (5) | D1 pos kas · D2 dual-control · D3 keep nomor · D6 skip/batal perawat · D8 akses data sensitif |
| **B. Boleh provisional** (4) | D4 prioritas/no-show · D5 dasar hitung giliran · D7 minimum staf · D11 host produksi |
| **C. Sebelum produksi** (3) | D9 SLA · D10 retensi data · D12 kontingensi offline |

---

# A. Must decide before pilot

Lima keputusan berikut menentukan cara staf bekerja sejak Hari 1. Bila salah, data pilot
tidak dapat dipercaya.

---

## D1 — Definisi pos kas *(perhatian khusus)*

**Pertanyaan PRD 27.1:** Apakah "kas", "modal", dan "uang kembalian" tiga pos terpisah
atau hanya label untuk satu cash drawer?

**Default saat ini:** Satu laci uang, tiga nilai dicatat terpisah dalam satu sesi kas:

| Field di aplikasi | Arti yang diasumsikan |
|---|---|
| Uang modal diharapkan | Jumlah yang seharusnya ada di laci saat buka |
| Uang kembalian tersedia | Uang pecahan kecil untuk kembalian |
| Dana kas lain | Pos tambahan bila klinik membedakannya |
| Total aktual | Dihitung otomatis dari rincian pecahan |
| Selisih | Total aktual − uang modal diharapkan |

**Mengapa harus diputuskan sebelum pilot:** ini menentukan **angka mana yang dibandingkan
untuk menghitung selisih**. Bila kenyataannya uang kembalian adalah bagian dari uang modal
(bukan pos terpisah), maka selisih yang dihitung sistem akan salah setiap hari, dan seluruh
data kas pilot tidak dapat dipakai.

**Yang perlu owner jawab:**

1. Apakah uang kembalian **termasuk** dalam uang modal, atau **terpisah**?
   ☐ Termasuk (satu pos)  ☐ Terpisah (dua pos)
2. Apakah "dana kas lain" dipakai di JoDerma? ☐ Ya, yaitu: __________  ☐ Tidak, sembunyikan
3. Selisih dihitung terhadap apa?
   ☐ Uang modal saja  ☐ Uang modal + kembalian  ☐ Lainnya: __________
4. Apakah istilah di layar sudah sesuai bahasa sehari-hari kasir JoDerma?
   ☐ Sudah  ☐ Ganti menjadi: __________

**Catatan koreksi dokumentasi:** `DECISIONS.md` menyebut nama field `expected_opening_float`,
sedangkan implementasinya bernama `expected_total`. Ini hanya penamaan internal, tidak
mengubah perilaku — akan diselaraskan setelah D1 diputuskan.

| Keputusan owner | |
|---|---|
| Tanggal | |
| Keputusan | |
| Config yang diubah | `cash.track_change_fund_separately` |
| Tanda tangan | |

---

## D2 — Dual-control kas: apakah selalu dua orang?

**Pertanyaan PRD 27.2**

**Default saat ini:** Ya, aktif. Penghitung pertama tidak boleh memverifikasi hitungannya
sendiri.

**Siapa yang boleh menjadi verifikator kedua (kondisi kode saat ini):**
front desk/kasir lain, supervisor, atau pemegang kapabilitas `cash.approve`.
**Koreksi setelah verifikasi tetap hanya supervisor.**

> Catatan implementasi: awalnya hanya supervisor yang boleh memverifikasi. Itu membuat kas
> tidak pernah bisa diverifikasi bila supervisor sendiri yang menghitung. Perilaku
> diperbaiki agar sesuai PRD 8.3 ("penghitung kedua **atau** supervisor").
> **Owner perlu mengonfirmasi bahwa sesama kasir boleh saling memverifikasi.**

**Mengapa harus diputuskan sebelum pilot:** kalau shift sore hanya ada satu petugas, kas
tidak akan pernah selesai diverifikasi dan success criteria S2 gagal karena aturan, bukan
karena sistem.

**Yang perlu owner jawab:**

1. Dual-control aktif? ☐ Ya, selalu  ☐ Ya, kecuali shift tertentu: ______  ☐ Tidak
2. Sesama kasir boleh saling memverifikasi? ☐ Boleh  ☐ Harus supervisor
3. Bila hanya ada satu petugas di shift, apa yang dilakukan?
   ☐ Supervisor datang/verifikasi jarak jauh  ☐ Matikan dual-control untuk shift itu
   ☐ Tunda verifikasi ke shift berikutnya

| Keputusan owner | |
|---|---|
| Tanggal | |
| Keputusan | |
| Config yang diubah | `cash.dual_control_enabled` |
| Tanda tangan | |

---

## D3 — Status pembayaran yang mempertahankan nomor antrean

**Pertanyaan PRD 27.3**

**Default saat ini:** nomor dipertahankan bila **Sudah bayar** atau **Dibebaskan**
(dibebaskan hanya oleh supervisor/owner, wajib alasan).
Tidak menahan nomor: Belum perlu, Belum bayar, Refund.

**Mengapa harus diputuskan sebelum pilot:** ini aturan yang **langsung dirasakan pasien**.
Salah aturan berarti pasien kehilangan nomor antrean secara tidak adil di hari pertama.

**Yang perlu owner jawab:**

1. Status apa saja yang menahan nomor?
   ☐ Sudah bayar  ☐ Dibebaskan  ☐ Belum perlu  ☐ Lainnya: __________
2. Siapa yang boleh menetapkan "Dibebaskan"? ☐ Supervisor saja  ☐ Front desk juga
3. Kapan status "Belum perlu" dipakai? __________________

| Keputusan owner | |
|---|---|
| Tanggal | |
| Keputusan | |
| Config yang diubah | `queue.keep_number_statuses` |
| Tanda tangan | |

---

## D6 — Aturan skip dan pembatalan giliran perawat *(perhatian khusus)*

**Pertanyaan PRD 27.6**

**Default saat ini:**

| Kejadian | Perilaku sistem | Config |
|---|---|---|
| **Skip sementara** (perawat sedang tidak bisa) | Perawat **tetap di posisinya**, giliran jatuh ke berikutnya | `nurse.skip_keeps_position = true` |
| **Batal sebelum tindakan dimulai** | Posisi perawat **dikembalikan ke depan** (rotasi di-undo) | `nurse.cancel_before_start_restores_position = true` |
| **Batal setelah tindakan dimulai** | **Dihitung sebagai giliran terpakai**, perawat ke belakang | — |
| **Pulang lebih awal** | Ditandai off-duty, dilewati tanpa mengubah urutan orang lain | — |

**Mengapa harus diputuskan sebelum pilot:** ini menyangkut **pendapatan perawat**. PRD
Bagian 23 secara eksplisit menyebut risiko "sengketa komisi" bila aturan rotasi belum jelas.
Menjalankan pilot dengan aturan yang belum disepakati berisiko menimbulkan keberatan yang
sulit diperbaiki setelahnya, karena ledger sudah terlanjur mencatat.

**Pertanyaan kunci — mohon dibahas bersama perawat, bukan diputuskan sendiri:**

1. Perawat yang di-*skip* karena sedang menyiapkan ruang — apakah adil bila ia **tetap**
   di posisi pertama?
   ☐ Adil, tetap di posisi  ☐ Tidak, dia harus mundur  ☐ Tergantung alasan skip
2. Tindakan batal **sebelum** dimulai (pasien membatalkan) — apakah perawat berhak
   mendapatkan giliran berikutnya?
   ☐ Ya, kembalikan posisinya  ☐ Tidak, tetap dihitung terpakai
3. Tindakan batal **setelah** dimulai (pasien tidak nyaman, dihentikan) — apakah
   dihitung sebagai giliran terpakai?
   ☐ Ya, sudah bekerja  ☐ Tidak  ☐ Tergantung sudah berapa lama
4. Perawat pulang lebih awal lalu kembali keesokan hari — mulai dari posisi mana?
   ☐ Urutan baru dari awal setiap hari  ☐ Meneruskan posisi kemarin

**Rekomendasi tim:** jalankan skenario NUR-04, NUR-05, dan NUR-06 pada Hari 2 pilot,
lalu **minta perawat sendiri yang menilai** apakah urutan terasa adil sebelum aturan
difinalkan. Sampai itu terjadi, catat sebagai OPEN DECISION.

| Keputusan owner | |
|---|---|
| Tanggal | |
| Dibahas bersama perawat? | ☐ Ya, tanggal: ______ |
| Keputusan | |
| Config yang diubah | `nurse.skip_keeps_position`, `nurse.cancel_before_start_restores_position` |
| Tanda tangan | |

---

## D8 — Siapa yang boleh melihat identitas pelapor dan detail finansial

**Pertanyaan PRD 27.8**

**Default saat ini:**

| Data sensitif | Yang dapat melihat |
|---|---|
| Komplain **Terbatas** dan identitas pelapor | Pembuat, penanggung jawab, supervisor, owner |
| Nominal kas | Front desk/kasir, supervisor, owner dengan kapabilitas `cash.view_amounts` |
| Detail pasien (nama lengkap, pembayaran) | Front desk, perawat terkait, supervisor, owner |
| Audit log | Supervisor, owner, admin yang diberi kapabilitas `audit.view` |
| **Admin teknis** | **Tidak** otomatis mendapat hak bisnis apa pun di atas |

**Mengapa harus diputuskan sebelum pilot:** kesalahan di sini adalah **kebocoran data**,
bukan sekadar ketidaknyamanan — dan memicu stop criteria T3. Lebih baik terlalu ketat di
awal lalu dilonggarkan, daripada sebaliknya.

**Yang perlu owner jawab:**

1. Apakah owner ingin melihat nominal kas? ☐ Ya (beri kapabilitas)  ☐ Tidak perlu
2. Apakah admin teknis (IT) boleh melihat nominal kas untuk keperluan dukungan?
   ☐ Tidak  ☐ Ya, sementara saat troubleshooting saja
3. Siapa yang boleh membuka komplain terbatas selain supervisor dan owner? __________
4. Apakah perawat boleh melihat nama lengkap pasien, atau cukup inisial?
   ☐ Nama lengkap  ☐ Cukup inisial

| Keputusan owner | |
|---|---|
| Tanggal | |
| Keputusan | |
| Yang diubah | Kapabilitas pengguna di Admin ▸ Pengguna |
| Tanda tangan | |

---

# B. May remain provisional during pilot

Empat keputusan ini boleh memakai default. Pilot justru berfungsi menguji apakah defaultnya
tepat. Putuskan setelah melihat data 5 hari.

---

## D4 — Prioritas, keterlambatan, refund, dan no-show

**Pertanyaan PRD 27.4**

**Default:** Prioritas hanya oleh supervisor dengan alasan (kasus per kasus, bukan aturan
baku). No-show setelah 15 menit dipanggil, nomor tidak otomatis hangus. Refund wajib alasan.

**Mengapa boleh provisional:** aturan kasus-per-kasus + wajib alasan sudah aman secara
audit. Pilot akan menunjukkan **seberapa sering** prioritas dipakai dan untuk alasan apa —
dari situ baru dapat dirumuskan aturan baku yang berbasis kenyataan, bukan dugaan.

**Yang diamati selama pilot:** skenario QUE-04 dan EXC-02. Catat setiap pemakaian prioritas
beserta alasannya. Bila terlihat pola berulang (mis. lansia, ibu hamil, pasien tindakan),
usulkan aturan baku setelah pilot.

**Diputuskan setelah pilot:**

1. Perlu aturan prioritas baku? ☐ Ya, yaitu: __________  ☐ Tidak, tetap kasus per kasus
2. Toleransi keterlambatan: ☐ tetap 15 menit  ☐ ubah menjadi ____ menit
3. Pasien no-show yang datang kemudian: ☐ nomor lama  ☐ nomor baru

| Keputusan owner | Tanggal: ______ · Keputusan: ______________________________ |
|---|---|

---

## D5 — Dasar perhitungan giliran perawat

**Pertanyaan PRD 27.5**

**Default:** round-robin per **tindakan berkomisi yang selesai dikonfirmasi**. Tidak ada
bobot durasi maupun nilai rupiah. Kategori tindakan hanya untuk cek eligibility.

**Mengapa boleh provisional:** ini alat pemerataan giliran, **bukan sumber payroll**
(PRD Bagian 5). Laporan distribusi giliran (RPT-03) akan menunjukkan apakah pemerataan
sederhana ini sudah cukup adil, atau tindakan berdurasi panjang membuatnya timpang.

**Yang diamati selama pilot:** RPT-03 — apakah jumlah giliran antar perawat dengan
ketersediaan sama relatif merata? Bila timpang karena satu jenis tindakan jauh lebih lama,
pertimbangkan pembobotan di fase 2.

**Diputuskan setelah pilot:**

1. Round-robin sederhana sudah cukup? ☐ Cukup  ☐ Perlu bobot durasi  ☐ Perlu bobot nilai
2. Perlu rotasi terpisah per kategori tindakan? ☐ Tidak  ☐ Ya

| Keputusan owner | Tanggal: ______ · Keputusan: ______________________________ |
|---|---|

---

## D7 — Minimum staf aktif saat istirahat

**Pertanyaan PRD 27.7**

**Default:** minimal 1 front desk **dan** 1 perawat aktif setiap saat. Belum dibedakan per
jam atau per area. Pelanggaran memberi peringatan yang dapat di-override beralasan.

**Mengapa boleh provisional:** peringatan (bukan larangan) sudah aman — supervisor tetap
dapat memutuskan sesuai keadaan. Pilot akan menunjukkan seberapa sering override diperlukan.

**Yang diamati selama pilot:** BRK-03. Bila override terjadi hampir setiap hari, berarti
angka minimumnya tidak realistis dengan jumlah staf yang ada.

**Diputuskan setelah pilot:**

1. Minimum front desk: ____ orang · Minimum perawat: ____ orang
2. Perlu berbeda pada jam sibuk? ☐ Tidak  ☐ Ya, jam ______ minimum ____
3. Perlu minimum terpisah per area (konsultasi vs tindakan)? ☐ Tidak  ☐ Ya

| Keputusan owner | Tanggal: ______ · Keputusan: ______________________________ |
|---|---|

---

## D11 — Host produksi

**Pertanyaan PRD 27.11**

**Default:** Linux mini-PC selalu menyala, Docker Compose, SQLite WAL, backup malam ke
perangkat kedua, Tailscale Serve. Unit systemd tersedia sebagai alternatif.

**Mengapa boleh provisional:** pilot dapat berjalan di perangkat apa pun yang memenuhi
syarat. Yang penting sudah terpenuhi: aplikasi hanya listen di localhost, auto-start aktif,
backup berjalan.

**Yang diamati selama pilot:** kestabilan perangkat, apakah pernah mati/restart, apakah
kapasitas disk cukup.

**Diputuskan sebelum go-live (bukan blocker pilot):**

1. Perangkat final: ☐ mini-PC Linux  ☐ workstation Windows  ☐ lainnya: ______
2. Sudah terpasang UPS? ☐ Ya  ☐ Belum — **wajib sebelum go-live**
3. Media backup kedua: ______________________

| Keputusan owner | Tanggal: ______ · Keputusan: ______________________________ |
|---|---|

---

# C. Must decide before production

Boleh provisional selama pilot, tetapi **tidak boleh** dibawa ke go-live.

---

## D9 — SLA per tingkat komplain dan kerusakan *(perhatian khusus)*

**Pertanyaan PRD 27.9**

**Default saat ini** (dihitung dari waktu pencatatan, **jam berjalan**, bukan jam kerja):

| Tingkat | Target penugasan | Target selesai |
|---|---|---|
| Kritis | 1 jam | 8 jam |
| Tinggi | 4 jam | 24 jam |
| Sedang | 1 hari (24 jam) | 3 hari (72 jam) |
| Rendah | 2 hari (48 jam) | 7 hari (168 jam) |

**Masalah yang harus disadari owner:** target ini dihitung dalam **jam berjalan**, bukan
jam operasional. Klinik buka 12.00–21.00 (9 jam/hari). Artinya:

- Kerusakan **Kritis** yang dilaporkan pukul 20.00 memiliki target selesai pukul 04.00 —
  di luar jam kerja, jadi otomatis terlewat.
- Kerusakan **Tinggi** dilaporkan Sabtu sore, targetnya jatuh saat klinik mungkin tutup.

**Akibatnya:** daftar "lewat target waktu" (RPT-04) akan penuh oleh item yang sebenarnya
ditangani wajar. Bila ini terjadi, staf akan berhenti mempercayai peringatan SLA —
persis risiko *alert fatigue* yang disebut PRD Bagian 23.

**Mengapa boleh provisional selama pilot:** justru pilot yang akan menunjukkan seberapa
besar masalah ini. Jangan mengubah angkanya sebelum ada data.

**Yang diamati selama pilot:** RPT-04. Hitung berapa item lewat target yang sebenarnya
**ditangani wajar** menurut penilaian supervisor.

**Diputuskan sebelum produksi:**

1. SLA dihitung dalam ☐ jam berjalan (sekarang)  ☐ jam operasional saja  ☐ hari kerja
2. Angka final:

   | Tingkat | Target penugasan | Target selesai |
   |---|---|---|
   | Kritis | | |
   | Tinggi | | |
   | Sedang | | |
   | Rendah | | |

3. Jalur eskalasi bila target terlewat: __________________
4. Siapa yang dieskalasi setelah supervisor? __________________

> Catatan teknis: perhitungan SLA berbasis **jam operasional** belum ada di MVP dan akan
> memerlukan perubahan kode kecil. Bila owner memilih opsi itu, jadwalkan sebelum go-live,
> bukan selama pilot.

| Keputusan owner | |
|---|---|
| Tanggal | |
| Keputusan | |
| Config yang diubah | `sla.<TINGKAT>.assign_hours`, `sla.<TINGKAT>.resolve_hours` |
| Tanda tangan | |

---

## D10 — Kebijakan retensi data *(perhatian khusus)*

**Pertanyaan PRD 27.10**

**Default saat ini:**

| Jenis data | Retensi |
|---|---|
| Audit event | 24 bulan |
| Data operasional (hari, checklist, kas, antrean, giliran, jadwal) | 24 bulan |
| Komplain/saran/kerusakan dan lampirannya | 24 bulan setelah ditutup |
| Komplain dan kerusakan | Tidak pernah dihapus permanen |

**Mengapa ini paling penting di kelompok C:** PRD Bagian 15.2 menyatakan kebijakan retensi
dan penghapusan **wajib disetujui manajemen sesuai peraturan Indonesia yang berlaku sebelum
produksi**. Ini kewajiban kepatuhan, bukan preferensi teknis.

Perlu diperhatikan:

- Aplikasi menyimpan **data pribadi terbatas**: nama tampilan pasien, waktu kunjungan,
  status pembayaran, dan identitas pelapor komplain. Meski bukan rekam medis, ini tetap
  data pribadi.
- Angka 24 bulan adalah **default teknis**, **bukan** hasil kajian hukum. Tim implementasi
  tidak berwenang menetapkan periode retensi yang sah.
- Saat ini **belum ada mekanisme penghapusan otomatis**. Data akan terus bertambah sampai
  kebijakan ditetapkan dan alat penghapusan dibuat.

**Yang perlu owner lakukan sebelum produksi:**

1. Konsultasikan dengan penasihat hukum/kepatuhan mengenai kewajiban retensi data pasien
   dan data kepegawaian di Indonesia (termasuk UU PDP).
2. Tetapkan periode retensi per jenis data:

   | Jenis data | Periode | Setelah itu |
   |---|---|---|
   | Audit event | ____ bulan | ☐ arsip ☐ hapus |
   | Data operasional | ____ bulan | ☐ arsip ☐ hapus |
   | Antrean (berisi nama pasien) | ____ bulan | ☐ anonimkan ☐ hapus |
   | Komplain/kerusakan | ____ bulan | ☐ arsip ☐ hapus |
   | Lampiran | ____ bulan | ☐ arsip ☐ hapus |

3. Tentukan siapa yang berwenang menyetujui penghapusan: __________________
4. Tentukan apakah data yang kedaluwarsa **dianonimkan** (nama dihapus, statistik
   dipertahankan) atau **dihapus seluruhnya**.

> Catatan teknis: alat penghapusan/anonimisasi terjadwal **belum ada** dan akan dibuat
> setelah kebijakan ditetapkan. Ini bukan blocker pilot 5 hari, tetapi **blocker go-live**.

| Keputusan owner | |
|---|---|
| Tanggal | |
| Sudah dikonsultasikan ke penasihat hukum? | ☐ Ya, tanggal: ______ |
| Keputusan | |
| Tanda tangan owner | |

---

## D12 — Kontingensi saat internet/Tailscale putus total

**Pertanyaan PRD 27.12**

**Default:** Tailscale umumnya tetap bekerja lewat jalur LAN langsung bila perangkat berada
di jaringan yang sama. Bila akses tetap gagal: formulir kertas darurat, lalu entry susulan
saat sistem kembali dengan penanda "entri susulan".

**Mengapa harus diputuskan sebelum produksi:** setelah pencatatan lama dihentikan
(pasca-pilot), klinik **tidak lagi punya jaring pengaman otomatis**. Prosedur darurat harus
sudah tertulis, tercetak, dan dilatih.

**Yang diuji selama pilot:** EXC-06 (latihan aplikasi mati 15 menit).

**Yang perlu owner putuskan sebelum produksi:**

1. Formulir kertas darurat sudah dicetak dan tersedia di klinik? ☐ Ya  ☐ Belum
2. Berapa lama gangguan yang dapat ditoleransi sebelum beralih ke kertas? ____ menit
3. Siapa yang memutuskan beralih ke prosedur darurat? __________________
4. Apakah perlu opsi akses LAN terkontrol sebagai cadangan bila Tailscale bermasalah
   berulang? ☐ Tidak  ☐ Ya — perlu kajian keamanan tersendiri
5. Siapa kontak darurat admin teknis di luar jam kerja? __________________

| Keputusan owner | |
|---|---|
| Tanggal | |
| Keputusan | |
| Tanda tangan | |

---

# Ringkasan tindakan owner

## Sebelum Hari 1 pilot

- [ ] D1 — Definisi pos kas ditetapkan
- [ ] D2 — Aturan dual-control dan siapa verifikator kedua ditetapkan
- [ ] D3 — Status pembayaran yang menahan nomor antrean ditetapkan
- [ ] D6 — Aturan skip/batal perawat dibahas **bersama perawat** dan ditetapkan
- [ ] D8 — Hak akses data sensitif ditetapkan dan kapabilitas diberikan
- [ ] Tim teknis menerapkan keputusan di Admin ▸ Konfigurasi
- [ ] `manage.py pilot_check` menghasilkan 0 blocker

## Selama pilot (amati, jangan ubah)

- [ ] D4 — catat setiap pemakaian prioritas dan alasannya
- [ ] D5 — periksa distribusi giliran perawat di laporan
- [ ] D7 — catat frekuensi override minimum staf
- [ ] D9 — hitung berapa item "lewat target" yang sebenarnya wajar
- [ ] D11 — catat gangguan perangkat bila ada

## Sebelum go-live

- [ ] D4, D5, D7, D11 difinalkan berdasarkan data pilot
- [ ] D9 — SLA final ditetapkan (dan basis perhitungannya)
- [ ] D10 — **kebijakan retensi disetujui manajemen + penasihat hukum**
- [ ] D12 — prosedur kontingensi tertulis, tercetak, dan dilatih
- [ ] `DECISIONS.md` diperbarui: status PROVISIONAL → CONFIRMED beserta tanggal

---

## OPEN DECISION yang muncul dari implementasi

Hal yang ditemukan tim teknis dan memerlukan keputusan owner, di luar 12 pertanyaan PRD:

| No | Pertanyaan | Konteks | Keputusan owner |
|---|---|---|---|
| OD-A | Bolehkah sesama front desk/kasir saling memverifikasi kas? | Kode saat ini mengizinkan (sesuai PRD 8.3 "penghitung kedua atau supervisor"), tetapi `DECISIONS.md` D2 hanya menyebut supervisor | |
| OD-B | Apakah SLA dihitung jam berjalan atau jam operasional? | Klinik buka 9 jam/hari; SLA jam berjalan membuat item malam otomatis terlewat | |
| OD-C | Apakah data antrean yang kedaluwarsa dihapus atau dianonimkan? | Berisi nama pasien; anonimisasi mempertahankan statistik tanpa data pribadi | |
| OD-D | Apakah pengelolaan item template checklist lewat Django admin cukup? | Halaman admin khusus sengaja ditunda; dievaluasi lewat skenario ADM-04 | |
| OD-E | Apakah **asistensi dokter** dan **tindakan infus** ikut dihitung sebagai giliran berkomisi? | Kategori tindakan diubah menjadi tiga: tindakan estetik, asistensi dokter, tindakan infus. Ketiganya ditandai berkomisi, sehingga perawat yang mengasisteni dokter juga maju dalam antrean giliran. | **DIPUTUSKAN 11 Sep 2026 — ya, ketiganya berkomisi.** Penugasan dicatat manual, sehingga asistensi dokter yang memang berkomisi akan ikut tercatat sebagaimana adanya. Dengan begitu rotasi tetap adil: setiap pekerjaan berkomisi menghabiskan giliran, tidak peduli jenisnya. |
| OD-F | Apakah semua perawat boleh mengerjakan semua kategori? | Saat ini ketiga perawat diberi eligibility untuk ketiga kategori sebagai default awal. Bila ada kategori yang menuntut sertifikasi tertentu, supervisor dapat mencabut eligibility lewat UI tanpa perubahan kode. | |

---

**Disiapkan oleh:** Tim implementasi · **Menunggu keputusan:** Owner/Manajemen JoDerma

> Tim teknis **tidak akan** mengubah aturan bisnis apa pun berdasarkan asumsi. Setiap
> perubahan kebijakan menunggu keputusan tertulis di dokumen ini.
