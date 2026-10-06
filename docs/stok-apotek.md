# Stok Apotek (`/stok-apotek/`)

Spesifikasi yang berlaku untuk modul Stok Apotek, app Django `stok`. Dokumen ini adalah
revisi PRD 30 September 2026 (asli: `apotek/PRD Modul Stok Apotek di ops.joderma.id.md`)
dengan temuan audit data dan keputusan product owner 1 Oktober 2026. Bila keduanya berbeda,
dokumen ini yang berlaku.

## Tujuan

Apoteker melihat produk yang harus diorder, diproduksi, atau dipindah antar cabang dalam
satu layar, dihitung otomatis dari ekspor Omnicare, bukan dari limit MIN/MAX Omnicare yang
tidak mengikuti pemakaian.

## Status

| Fase | Isi | Status |
|---|---|---|
| 1 | Impor tiga jenis file, penggabungan unduhan, uji kelengkapan, tab Prioritas Order, Transfer, Impor Data, parameter | Selesai 1 Okt 2026, commit `e966da7`, dideploy ke mini PC 1 Okt |
| 2 | Tab Moving dan Kandidat Nonaktif, tanda tindak lanjut, unduh daftar order | Belum (ditahan product owner 6 Okt) |
| 3 | Lead time per distributor, pemakaian bulan berjalan, ukuran kemasan | Belum |

Layar parameter semula fase 2; ikut fase 1 karena keputusan akses 1 Okt.

## Hak akses (keputusan 1 Okt 2026)

Halaman ini milik operasional apotek. Diperiksa di server lewat
`core.permissions.can_view_stok` dan `can_edit_stok`, ditambah `core/peran.py`.

| Peran | Buka | Unggah | Ubah parameter |
|---|---|---|---|
| Apoteker | Ya | Ya | Ya |
| Asisten apoteker | Ya | Ya | Ya |
| Direktur Operasional (`AOM`) | Ya | Ya | Ya |
| Owner | Ya (baca) | Tidak | Tidak |
| Peran lain, Admin sistem | Tidak (403) | Tidak | Tidak |

Apoteker membuka cabangnya sendiri; Direktur dan Owner membuka "Kedua cabang". Semua peran
yang boleh membuka bisa melihat kedua cabang, karena saran transfer butuh stok cabang lain.
Owner hanya-baca (dikonfirmasi 6 Okt, A6). Setiap unggahan dan perubahan parameter
tercatat di audit log.

## Impor dari Omnicare

Tiga jenis ekspor .xls diunggah manual dari tab Impor Data, boleh beberapa file sekaligus.
Daftar Produk selalu diproses lebih dulu.

| File | Dikenali dari judul | Dipakai |
|---|---|---|
| Daftar Produk (`product_list`) | "DAFTAR PRODUK" | ID, nama, dosis, kategori, MIN/MAX, penanda non-stok "~", dan tanda produksi sendiri (dari kolom pabrikan; namanya tidak disimpan) |
| Tingkat Persediaan (`stock_level`) | "TINGKAT PERSEDIAAN … PER <tanggal>" | stok per produk |
| Ringkasan Pergerakan Stok (`stock_movement_summary`) | "PERGERAKAN STOK 01 … S/D <akhir bulan>" | stok awal, 10 jenis pergerakan, stok akhir |

Aturan baca (`stok/parser.py`):

- `xlrd` menolak semua file Omnicare dengan setelan bawaan ("Workbook corruption"); file
  dibuka dengan `ignore_workbook_corruption=True`.
- Kolom dibaca menurut posisi, bukan label (header pergerakan memuat salah ketik "DJIUAL").
- Nama bulan di judul tidak seragam antar laporan Omnicare: Daftar Produk/Pergerakan memakai bahasa
  Indonesia ("05 OKTOBER 2026"), Penjualan Produk bahasa Inggris ("01 OCTOBER 2026"), Penjualan Farmasi
  singkatan ("01 SEP 2026"). Parser menerima ketiganya (`stok.parser.BULAN`); bulan yang tidak dikenal
  menjadi pesan galat yang jelas, bukan error 500.
- Angka dibulatkan 2 desimal (file memuat sisa pecahan seperti 7,499994 dan −0,015).
- Laporan pergerakan harus satu bulan penuh; selain itu ditolak.
- Kunci pencocokan = nama + dosis, huruf kecil tanpa spasi. Daftar Produk memisahkan nama
  dan dosis; dua laporan lain menggabungkannya ("Rydian Tablet10 mg"). Pada data 30 Sep
  semua baris cocok.
- Bila nama produk diubah di Omnicare, kunci lama disimpan sebagai alias (`ProdukAlias`).
- Baris yang tidak cocok ditampilkan sebagai peringatan, tidak dibuang diam-diam.
- Cabang ditebak dari judul (Tingkat Persediaan) atau kode di nama file (30376 = Jemur,
  31281 = Citraland), dicocokkan ke nama klinik; bisa dipilih manual di formulir.
- File asli setiap unggahan disimpan di `private_media/stok/`.

### Penggabungan unduhan

Setiap unduhan laporan pergerakan bisa kehilangan blok 50 baris. Unggahan untuk cabang dan
periode yang sama digabung per produk; unggahan terbaru menimpa baris yang sama.

### Uji kelengkapan (per cabang per bulan)

Laporan pergerakan hanya memuat produk yang bergerak di bulan itu. Produk yang absen
dianggap tidak bergerak selama stoknya menyambung (data Jul–Sep: 9 kasus di Jemur, 18 di
Citraland).

1. **Seimbang**: stok awal + semua pergerakan = stok akhir, per baris.
2. **Sambung**: stok awal = stok akhir terakhir yang diketahui untuk produk itu. Bila putus,
   bulan di antaranya Belum lengkap dan produknya masuk daftar diduga hilang.
3. **Cocok dengan Tingkat Persediaan** di hari terakhir bulan. Produk yang ada di laporan
   pergerakan tetapi angkanya beda hanya dicatat sebagai selisih (transaksi di antara dua
   waktu unduh). Produk yang absen padahal stoknya berubah dianggap hilang.
4. **Mutasi saling menutup** antar cabang per produk per bulan. Bila satu cabang tidak
   punya barisnya, cabang itu yang diduga kehilangan baris.

Periode Belum lengkap tidak masuk rata-rata dan tampil merah di tab Impor Data beserta
produk yang diduga hilang.

## Aturan perhitungan (`stok/hitung.py`)

Rumus sama dengan workbook *Analisa Persediaan JoDerma Jul-Sep 2026*; test memastikan
angkanya identik.

- **Stok**: Tingkat Persediaan terbaru per cabang. Bila ada laporan pergerakan yang
  berakhir di tanggal yang sama, stok akhir laporan pergerakan yang dipakai untuk produk
  yang ada di sana (laporan pergerakan diunduh belakangan; 16 produk Jemur 30 Sep).
- **Pemakaian bulanan** = −(Dijual + Dipakai + Retur Jual + Fabrikasi yang negatif).
- **Rata-rata** = rata-rata N bulan lengkap terakhir (bulan tanpa baris = 0), minimal 0.
- **Buffer** = rata-rata × bulan buffer. **Bulan stok** = stok ÷ rata-rata.
- **Status**: Kosong (stok ≤ 0, rata-rata > 0) → Di bawah buffer (stok < buffer) →
  Mendekati buffer (stok ≤ buffer × (1 + ambang)) → Aman. Tanpa pemakaian = berstok,
  rata-rata 0.
- **Moving**: Fast = terpakai di semua bulan; Slow = sebagian; Diam = berstok, tidak terpakai.
- **Kebutuhan** (hanya Kosong, Di bawah, Mendekati) = target × rata-rata − stok, 1 desimal.
- **Kelebihan** = stok − cadangan × rata-rata, minimal 0, 1 desimal.
- **Saran transfer** = min(kebutuhan penerima, kelebihan pengirim), dibulatkan ke bawah per
  0,5 unit. **Sisa order** = kebutuhan − transfer masuk.
- **Tanpa harga dan supplier** (keputusan 6 Okt 2026, menggantikan keputusan 1 Okt yang
  hanya menyembunyikan nilai di tab Transfer): harga modal, harga jual, nilai persediaan, dan
  nama pabrikan tidak dibaca dari ekspor dan tidak disimpan (migrasi `stok 0002`). Saran
  transfer diurutkan menurut penerima yang paling mendesak, lalu jumlah terbesar.
- **Tindakan**: produk bertanda produksi sendiri (pabrikan DRYN atau Joderma saat impor) =
  Produksi sendiri; lainnya Order distributor.
- Produk non-stok ("~" di Daftar Produk) tidak dihitung.

Parameter (model `stok.Parameter`, satu baris; nilai awal asumsi PRD): jumlah bulan
rata-rata 3, bulan buffer 1, ambang mendekati 25%, target 2 bulan, cadangan pengirim 2 bulan.

## Hasil pada data 30 September 2026

| | Jemur | Citraland |
|---|---|---|
| Kosong / Di bawah / Mendekati / Aman / Tanpa pemakaian | 48 / 90 / 14 / 133 / 67 | 43 / 49 / 19 / 149 / 50 |
| Mutasi bersih Jul / Agu / Sep | 7.392 / 6.820 / 8.449 | kebalikannya |

Saran transfer: 40 produk Citraland → Jemur, 19 Jemur → Citraland.

## Kriteria selesai fase 1

- [x] Enam file pergerakan terimpor, keenam periode Lengkap.
- [x] Mutasi bersih Jemur 7.392 / 6.820 / 8.449, selisih antar cabang 0.
- [x] Status Jemur dan Citraland sama dengan tabel di atas.
- [x] Saran transfer 40 + 19 produk.
- [x] File Citraland September yang terpotong membuat periode Belum lengkap dengan Forti D
      5000 di daftar diduga hilang (test memotong blok 50 baris dari file lengkap; file
      terpotong asli belum ada).
- [x] Dua unduhan terpotong untuk periode yang sama tergabung tanpa duplikat.
- [x] Owner tidak melihat tombol unggah atau parameter dan ditolak di server; peran lain 403.

Test: `stok/tests/test_stok.py`, memakai ekspor asli di `stok/tests/fixtures/`.

## Celah yang dicatat

- Harga masih ada di luar database aplikasi: file uji di `stok/tests/fixtures/` (ikut repo
  privat), berkas ekspor asli yang pernah diunggah (`private_media/stok/` di mini PC), backup
  sebelum 6 Okt, dan catatan audit lama. Keputusan 6 Okt: database dulu; sisanya diputuskan
  terpisah.
- Kesegaran data bergantung pada unggahan manual oleh apoteker atau asisten apoteker (A7);
  Omnicare tidak punya API (A9).
- Produk yang sempat kosong tercatat pemakaiannya lebih rendah dari permintaan sebenarnya.
- Satu angka bulan buffer untuk semua produk sampai lead time distributor ada (fase 3).
- Saran dalam unit Omnicare, bukan box; satuan hampir kosong di master.
- Tanggal kedaluwarsa tidak ada di ekspor, jadi saran transfer tidak mempertimbangkan ED.
- Daftar Produk hanya dari akun Jemur. MIN/MAX Omnicare ternyata berbeda per cabang (A5), jadi
  MIN/MAX yang tersimpan adalah milik Jemur; keduanya tidak dipakai dalam perhitungan.
- Belum ada cara menghapus unggahan yang salah dari halaman (lewat Django admin).
- Di layar HP tabel menjadi kartu per baris (pola `table.responsive` yang sudah ada), bukan
  kolom terkunci seperti tertulis di PRD.

## Keputusan product owner 6 Okt 2026

| No | Pertanyaan | Jawaban |
|---|---|---|
| A5 | MIN/MAX Omnicare berbeda per cabang? | Ya, berbeda |
| A6 | Owner cukup hanya-baca? | Ya |
| A7 | Siapa yang mengunggah stok harian? | Apoteker atau asisten apoteker cabang |
| A8 | Pembulatan transfer ke strip atau box? | Belum diketahui |
| A9 | Omnicare punya API atau ekspor terjadwal? | Tidak ada API; unggah manual tetap |

Tambahan: semua faktor harga dan supplier dihapus dari ops.joderma.id, yaitu Stok Apotek
(harga, nilai Rp, pabrikan), Order Produk Online (harga jual, harga satuan, total), dan laporan
kerusakan (pelaksana/vendor, biaya). Kolomnya dibuang dari database lewat migrasi `stok 0002`,
`orders 0005`, dan `issues 0002`.

## Pertanyaan terbuka

- Pembulatan transfer tablet/kapsul ke strip atau box? (A8)
- Apakah bug ekspor terpotong sudah dilaporkan ke Omnicare? (sisa A9)
