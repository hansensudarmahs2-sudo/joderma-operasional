# Tinjauan PRD — Pendamping Tindakan Perawat

> **STATUS: tinjauan teknis, 13 Oktober 2026.** Belum ada kode yang ditulis.
> Sumbernya [`prd-pendamping-tindakan.md`](prd-pendamping-tindakan.md) (13 Okt 2026,
> Hansen Sudarma). Versi ringkas untuk Owner ada di
> [`usulan-pendamping-tindakan.pdf`](usulan-pendamping-tindakan.pdf).
> Dokumen ini memuat hasil pemeriksaan PRD itu terhadap kode yang sebenarnya,
> keputusan product owner yang diambil saat membahasnya, dan usul perubahan
> rencana fase. Dibuat untuk dibahas bersama dr. Yohanes dan Jean.

## Ringkasan

PRD-nya matang dan seluruh klaimnya tentang kode **terbukti benar**. Tiga temuan di
bawah mengubah rencananya, dan satu di antaranya cukup mendasar sehingga sebaiknya
diputuskan sebelum ada baris kode yang ditulis.

| # | Temuan | Akibat |
|---|---|---|
| 1 | Volume tindakan terlalu kecil untuk rata-rata per perawat | Ambang minimum tidak tercapai 4–24 bulan. Rating sebagai **angka per perawat** belum layak; sebagai **temuan** layak sejak hari pertama |
| 2 | Skema aplikasi survei terikat alur ekspor Omnicare di tiga titik | Rating tidak bisa menumpang `undangan`; perlu jalur dan pekerjaan skema sendiri |
| 3 | Catatan dasarnya sedang menurun dipakai, dan tidak seragam | Perbaiki input dulu. Katalog tindakan (Fase 1) terbukti sangat layak, bahkan bila rating ditunda |
| 4 | Citraland belum punya kategori tindakan sama sekali | Kebutuhan A tidak bisa jalan di Citraland; masuk Fase 0 |

## 1. Klaim PRD tentang kode: terverifikasi

Diperiksa pada `master` 13 Okt 2026, terhadap [`prd-pendamping-tindakan.md`](prd-pendamping-tindakan.md).

| Klaim PRD | Hasil |
|---|---|
| `NurseActionTally` menyimpan RM, nama pasien, tindakan sebagai teks bebas, dan jumlah | **Benar** |
| `ProcedureCategory` per cabang menandai tindakan berkomisi | **Benar** (`clinic` FK, `commissioned`) |
| `NurseEligibility` mencatat kompetensi perawat per kategori | **Benar** |
| Peran `PERAWAT` ditegakkan di sisi server | **Benar** |
| Tally masih menyimpan nama pasien selain RM | **Benar** |

Tidak ada yang keliru di bagian "kondisi sistem saat ini".

## 2. Volume: ambang minimum tidak akan tercapai

Diambil dari produksi sebagai **agregat saja** — tidak ada nomor RM maupun nama
pasien yang dibaca. Oktober 2026, data 1–12 Okt, 58 tally biasa, 8 perawat.

| Perawat | Tally | Perawat | Tally |
|---|---|---|---|
| Naya | 12 | Heni | 5 |
| Regita | 12 | Lia | 4 |
| Silvi | 12 | Desy | 3 |
| Alya | 8 | Yani | 2 |

Min 2 · median 6,5 · maks 12. Citraland 36, Jemur 22. **Hanya Oktober yang punya
data** — tally baru dipakai bulan ini. Angka ini dipakai untuk menakar volume,
bukan menilai kinerja: tally yang tidak ditulis tidak berarti tindakan tidak
dikerjakan (lihat bagian 4).

Diskalakan ke sebulan kerja lalu dikalikan tingkat penawaran × tingkat respons:

| | Tindakan/bulan (perkiraan) | Rating/bulan bila 40% | bila 21% | Bulan untuk N=20 |
|---|---|---|---|---|
| Perawat teratas | ~20–25 | ~9 | ~5 | **4 bulan** |
| Perawat median | ~12 | ~5 | ~2,5 | **7 bulan** |
| Perawat terbawah | ~4 | ~1,5 | ~0,8 | **24 bulan** |

Dengan N=20 dashboard rata-rata per perawat kosong 4–24 bulan; dengan N=10 pun
masih 2–12 bulan. Saat akhirnya terisi, angkanya menggambarkan perilaku setengah
tahun sebelumnya.

**Kesimpulan: rata-rata per perawat belum menjadi instrumen yang bisa dipakai pada
volume ini.** Bukan karena ambangnya salah dipilih — berapa pun angkanya, pilihannya
hanya antara "kosong sangat lama" dan "satu pasien yang sedang kesal menjatuhkan
seorang perawat".

Yang tetap bekerja sejak rating pertama adalah **temuannya**. Karena itu urutan
keluarannya sebaiknya dibalik:

| Keluaran | Berlaku ambang minimum? | Kapan berguna |
|---|---|---|
| Rating rendah sebagai temuan di Inbox | **Tidak** | Sejak rating pertama |
| Rata-rata per perawat | **Ya** | Setelah berbulan-bulan; laporkan per 6–12 bulan, atau ganti dengan jumlah rating rendah |

Memisahkan keduanya juga melindungi maksud aslinya: perawat tidak dinilai dari
angka yang terlalu sedikit, tetapi keluhan pasien tidak mengendap menunggu ambang.

## 3. Integrasi survei: tidak bisa menumpang `undangan`

PRD mengusulkan ops membuat tautan sekali pakai dan halaman ratingnya berada di
aplikasi survei. Arahnya benar, tetapi skema `joderma-survey` terikat alur ekspor
Omnicare di **tiga titik**, dan rating yang dibuat saat tindakan berlangsung tidak
memenuhi satu pun:

| Tabel | Kolom yang menghalangi | Mengapa rating tidak memenuhinya |
|---|---|---|
| `undangan` | `rm` → `pasien(rm)`, `no_faktur NOT NULL`, `unggahan_id NOT NULL` | Pasien belum ada di tabel `pasien` (baru terisi saat ekspor diunggah), belum ada faktur, belum ada batch unggahan |
| `sesi_jawaban` | `unggahan_id NOT NULL`, `dokter NOT NULL` | Sesi rating tidak punya unggahan, dan sering tidak punya dokter |
| `izin_kontak` | `rm NOT NULL` | Token rating sengaja tidak membawa RM (lihat bagian 5) |

Dua aturan lain juga tidak boleh ikut terbawa. `MASA_BERLAKU_LINK = 30` hari dan
`JEDA_BELUM_MENGISI = 30` hari ada untuk mencegah pasien dispam **survei klinik**;
rating per sesi iramanya berbeda — pasien yang datang empat kali sebulan wajar
dimintai bintang empat kali.

**Yang sudah ada dan bisa dipakai ulang**, sehingga pekerjaannya tidak sebesar
kelihatannya:

- `set_pertanyaan` sudah ada pada tabel `pertanyaan` dan `undangan`. "Survei
  perawat satu pertanyaan, terpisah dari survei klinik" adalah **set kedua**, bukan
  mesin baru.
- Jenis `skala_1_5` sudah ada — persis bintang 1–5.
- `tampil_bila = 'ada_nilai_rendah'` sudah ada: pertanyaan lanjutan yang hanya
  muncul bila nilainya rendah.
- Halaman publik `/s/<token>` sudah menangani link terpakai, kedaluwarsa,
  dibatalkan, dan salah, dengan pesan ramah tanpa membocorkan apakah token itu
  pernah ada, serta penjagaan agar token tidak bocor lewat `Referer`.

**Satu hal yang perlu diubah:** `AMBANG_NILAI_RENDAH = 2` adalah konstanta global
yang dipakai semua set. Keputusan "pertanyaan lanjutan muncul pada bintang 1–3"
tidak boleh diterapkan dengan mengubah konstanta itu, karena survei klinik ikut
berubah. Ambangnya perlu menjadi **setelan per set pertanyaan**.

## 4. Catatan dasarnya belum kuat

Rating menumpang tally. Keadaan tally sekarang:

```
Okt  1   2   3   4   5   6   7   8   9  10  11  12
     5   1   5  17   8   4   3   5   4   3   2   1
```

- Puncaknya 4 Okt lalu **menurun terus**; tiga hari terakhir hanya 3, 2, 1.
- **9 dari 25 hari operasional** (per cabang per hari) tidak punya tally sama sekali.
- **14 dari 72 baris (19%) adalah tally susulan** — dicatatkan Koordinator Shift
  karena perawatnya lupa menulis. Fitur susulan itu sendiri baru ditambahkan 8 Okt
  justru karena masalah ini.

Kalau catatan dasarnya tidak terisi, ratingnya lebih jarang lagi. **Memperbaiki
input perlu didahulukan daripada menambah rating di atasnya.**

### Justru di sini katalog tindakan terbukti layak

Dari 58 tally ada **30 variasi penulisan tindakan** — hampir setiap tally kedua
punya ejaan sendiri:

```
sculptra · Sculptra · Scluptra     tiga ejaan, satu di antaranya salah ketik
V Ozone · infus ozone              dua penulisan untuk hal yang sama
FO (13) · BT (10) · RF (4)         singkatan tanpa kamus
```

Tujuan tally adalah rekonsiliasi dengan Omnicare, dan dengan 30 ejaan untuk 58
baris pencocokan itu pasti menyakitkan. Ini kemungkinan besar salah satu akar
keluhan poin asistensi yang tidak cocok (5 Okt, Alya: buku 29 vs lokadok 26).

**Katalog tindakan layak dikerjakan meskipun rating ditunda.** Memilih dari daftar
juga lebih cepat daripada mengetik, jadi Fase 1 berpeluang memperbaiki tingkat
pengisian — persoalan di atas.

### Dua asumsi PRD yang perlu dikoreksi

**Eligibility belum bisa dipakai ulang di Citraland.** `ProcedureCategory` hanya
ada **3 baris, semuanya milik Jemur** (Asistensi dokter, Tindakan estetik, Tindakan
infus). Citraland **nol kategori**, padahal justru Citraland yang tallynya lebih
banyak (36 vs 22). Kebutuhan A — *"perawat hanya memilih tindakan yang
kompetensinya ia miliki"* — tidak bisa jalan di Citraland sampai kategorinya
dibuat. **Masuk Fase 0.**

**`ProcedureAssignment` tidak pernah dipakai (0 baris).** Sempat terpikir katalog
sebaiknya dibangun di atas model itu karena sudah punya FK kategori, FK antrean,
siklus status, dan penegakan eligibility. Pemeriksaan membatalkannya: model itu
kosong di produksi, sedangkan `CommissionTurnEvent` hidup (180 baris) dan
`NurseRosterEntry` 91. Giliran dipakai, penugasannya tidak. **PRD benar memilih
tally sebagai dasar.** Yang perlu diputuskan terpisah: `ProcedureAssignment`
dihidupkan atau dipensiunkan, karena keberadaannya sekarang mengundang orang
menyimpulkan hal yang keliru tentang sistem.

## 5. Keputusan product owner, 13 Oktober 2026

Diambil saat membahas tinjauan ini.

| Hal | Keputusan |
|---|---|
| Isi token rating | **Hanya perawat dan sesi pelayanan.** Tidak membawa nomor RM maupun nama pasien |
| Judul halaman rating | Menyebut **nama panggilan** perawat dan **tanggal**; detail tindakan disembunyikan, bisa dibuka pasien dengan klik bila perlu |
| Masa berlaku tautan | **24 jam** |
| Pertanyaan lanjutan | Muncul pada bintang **1–3**, boleh dilewati pasien |
| Pilihan bisa dihubungi | Ada |
| Perawat melihat ratingnya | **Overall saja, bukan rincian.** Rincian hanya lewat percakapan dengan Direktur Operasional, atas permintaan perawat sendiri |
| Sifat percakapan itu | Membangun, bukan menyalahkan: memahami apakah rating rendah berasal dari salah paham pasien tentang makna survei, tindakan yang memang bisa diperbaiki, atau sentimen pribadi pasien |
| Ambang minimum | **Berlaku untuk semua** — Direktur dan Owner juga, bukan hanya tampilan perawat |

Konsekuensi yang mengikuti keputusan-keputusan itu:

**Menyembunyikan detail tindakan di balik klik** membuat layar HP pasien di ruang
tunggu tidak memamerkan tindakan apa yang baru ia jalani. Perlindungan privasi yang
nyata, bukan sekadar kerapian tampilan.

**Jembatan "bisa dihubungi" dipindah ke ops.** Karena token tidak membawa RM,
`izin_kontak` yang ada tidak bisa dipakai. Usulnya: token memetakan ke satu entri
tally, dan ops yang tahu RM-nya; pasien menyetujui → aplikasi survei hanya mencatat
"sesi ini bersedia dihubungi" → ops yang menerjemahkan jadi pasien mana. Hasilnya
lebih baik daripada membawa RM: **tidak ada satu sistem pun yang bisa
mere-identifikasi sendirian**, dan jembatannya tetap hanya terbentuk oleh
persetujuan — persis maksud rancangan survei yang sekarang.

**Angka overall sebaiknya per periode, bukan rata-rata hidup.** Bila angkanya
bergerak setiap ada rating masuk, perawat tetap bisa menebak: 12 rating rata-rata
4,8 lalu besok 13 rating rata-rata 4,6 berarti rating terakhir rendah, dan ia tahu
siapa saja pasien yang ia tangani kemarin. Tebakan itu bisa jatuh ke orang yang
salah. Yang menutup celahnya bukan menyembunyikan lebih banyak, melainkan
menampilkan **angka bulan berjalan yang final di akhir bulan**. Jumlah penawaran —
yang memang dikendalikan perawat — boleh tampil langsung.

**Sistem menyimpan rating secara anonim, tetapi percakapan bisa membukanya.** Begitu
disebut "ini dari pasien yang Anda tangani Selasa pagi", perawat tahu persis siapa
orangnya. Itu keputusan Direktur Operasional saat itu, bukan sesuatu yang bisa
dicegah sistem. Pegangannya: bicarakan **apa yang dikeluhkan**, tanpa menyebut kapan
atau siapa.

## 6. Dua hal yang perlu dipertimbangkan lagi

**Judul yang menyebut nama perawat akan membuat rating menumpuk di bintang 5.**
Menilai orang yang namanya tertera, sesaat setelah tindakan, sering saat orangnya
masih di dekat kita — sebarannya selalu condong ke atas. PRD sendiri memakai
analogi *"seperti rating kurir online"*; analogi itu membawa serta penyakitnya,
yaitu rata-rata yang akhirnya tidak berarti sehingga yang dipakai justru *persentase
yang bukan 5*. Masa berlaku 24 jam sudah banyak menolong karena pasien bisa mengisi
setelah keluar ruangan. Yang perlu ditetapkan sejak awal: **angka mana yang akan
dibaca** bila sebarannya memang menumpuk — lebih baik diputuskan sekarang daripada
setelah ada perawat yang merasa dinilai tidak adil.

**Jaring bintang 1–3 akan banyak menangkap hal di luar kendali perawat.** Bintang 3
dengan catatan "bagus, cuma nunggunya lama" itu masalah antrean; "obatnya mahal" itu
masalah harga. Keduanya berharga, tetapi bukan urusan perawat yang namanya tertera
di judul. Karena itu temuan dari kanal ini sebaiknya masuk Inbox **tanpa otomatis
melekat ke perawat** — Direktur Operasional yang memilah apakah ini soal perawat,
antrean, harga, atau kejadian medis. Mesin pilahnya sudah ada persis untuk itu.

**Rating bisa memunculkan kejadian medis, bukan hanya keluhan layanan.** Bintang 1
dengan catatan "kulit saya perih sampai sekarang" adalah kejadian tidak diinginkan,
dan penanganannya sudah ditetapkan dr. Yohanes (6 Okt: perawatan luka digratiskan,
sampai kemungkinan pengembalian biaya paket). Perlu aturan tertulis: temuan seperti
itu diteruskan ke penanggung jawab medis, bukan mengendap di dashboard.

## 7. Usul perubahan rencana fase

Rencana PRD tetap, dengan tiga penyesuaian:

**Fase 0 — tambahkan tiga butir.**
1. Buat `ProcedureCategory` untuk **Citraland** (sekarang nol), tanpa itu kebutuhan A tidak bisa jalan di sana.
2. Rancang tabel rating di `joderma-survey` beserta integrasinya: set pertanyaan terpisah, ambang nilai rendah per set, kolom yang perlu dibuat nullable.
3. Putuskan nasib `ProcedureAssignment` — dihidupkan atau dipensiunkan.

**Fase 1 (katalog dan layar langkah) — naikkan prioritasnya, dan ukur dampaknya
pada pengisian tally**, bukan hanya pada kecepatan input. 30 variasi penulisan untuk
58 tally membuat fase ini layak berdiri sendiri, bahkan bila rating tidak pernah
dikerjakan.

**Fase 2 (rating) — ubah keluaran utamanya.** Temuan ke Inbox sejak rating pertama;
angka per perawat ditunda sampai volumenya memadai dan dilaporkan per periode, bukan
sebagai rata-rata hidup. Fase 4 (dashboard) menyesuaikan.

## 8. Yang masih terbuka

- [ ] **N** (jumlah rating minimum) belum ditetapkan. Bagian 2 menunjukkan N=20 berarti kosong 4–24 bulan; angkanya perlu dipilih sadar akan hal itu, atau keluarannya diganti.
- [ ] Angka mana yang dibaca bila sebaran menumpuk di bintang 5 — rata-rata, atau proporsi yang bukan 5.
- [ ] Aturan peneruskan temuan yang bersifat **medis** ke penanggung jawab medis.
- [ ] Nasib `ProcedureAssignment`.
- [ ] Keputusan terbuka di PRD aslinya yang belum dijawab, termasuk pertanyaan untuk dr. Yohanes tentang isi layar langkah dan daftar tindakan fase pertama.

## Cara mengulang pengukuran

Angka di bagian 2 dan 4 diambil dengan skrip agregat yang **tidak pernah membaca**
`rm_number` maupun `patient_name`. Dijalankan di produksi karena database laptop
tidak punya data tally:

```bash
ssh joderma-jemur@joderma-jemur
cd ~/joderma-ops
docker compose exec -T app python manage.py shell -c "
from django.db.models import Count
from nurses.models import NurseActionTally
for r in (NurseActionTally.objects.filter(susulan=False)
          .values('nurse__display_name').annotate(n=Count('id')).order_by('-n')):
    print(r['n'], r['nurse__display_name'])
" </dev/null
```

`</dev/null` di akhir diperlukan; tanpanya `docker compose exec` menelan sisa skrip
(lihat `docs/lanjutkan-pekerjaan.md`).
