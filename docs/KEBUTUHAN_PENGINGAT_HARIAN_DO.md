# Kebutuhan: Pengingat Harian Direktur Operasional

Dokumen kebutuhan untuk agen pengembang ops.joderma.id. Disusun 13 Oktober 2026 oleh
dr. Hansen Sudarma (Direktur Operasional, product owner). Ikuti `AGENTS.md`: baca dulu,
kerjakan di worktree sendiri, berhenti di setiap approval gate.

## 1. Masalah dan tujuan

Alur ringkas, SOP, dan standar pelayanan sudah disosialisasikan, tetapi staf cepat lupa
bila tidak diulang. Selama ini Direktur Operasional (DO) mengingatkan tim secara spontan,
sehingga ada materi yang terus diulang dan ada yang tidak pernah disebut lagi.

Tujuan: **setiap kali DO membuka aplikasi, ia langsung tahu materi apa yang hari ini
perlu diingatkan ke tim, kepada siapa, dan teks apa yang tinggal disalin ke WhatsApp.**
Materi bergilir otomatis menurut jadwal berkala, sehingga semua materi terus muncul
kembali dan tidak ada yang terlupa.

Yang **bukan** tujuan tahap ini:

- Aplikasi tidak mengirim pesan ke staf. DO yang mengirim sendiri (grup WA, briefing,
  atau langsung). Aplikasi hanya menyiapkan dan mencatat.
- Tidak ada kuis atau penilaian staf di fitur ini.

## 2. Pengguna dan akses

| Peran | Akses |
|---|---|
| Direktur Operasional | Melihat kartu pengingat, menandai sudah diingatkan, mengelola katalog materi |
| Direktur Utama, Owner | Melihat riwayat pengingat (baca saja) |
| Staf lain | Tidak ada akses |

Otorisasi diterapkan server-side di `core/permissions.py` (bukan hanya menyembunyikan
tombol). Perbarui `docs/peran-dan-akses.md`.

## 3. Perilaku yang diharapkan

### 3.1 Kartu "Pengingat hari ini"

Muncul di bagian paling atas halaman Ringkasan Direktur, setiap hari kerja.

Setiap butir menampilkan:

- judul materi dan kodenya (mis. `AR-07 Siap Sebelum Memanggil Dokter`);
- sasaran: peran dan cabang (mis. "Perawat · Jemur dan Citraland");
- tiga poin kunci;
- teks WhatsApp siap salin, dengan tombol **Salin**;
- tautan ke dokumen rujukan bila ada;
- kapan terakhir diingatkan, per cabang.

Tombol per butir:

| Tombol | Akibat |
|---|---|
| **Sudah diingatkan** | Membuka isian singkat: cabang (Jemur / Citraland / keduanya), saluran (grup WA / briefing / langsung), catatan opsional. Disimpan ke log; butir hilang dari kartu hari ini |
| **Tunda ke besok** | Butir dipaksa muncul besok; tidak dihitung sebagai diingatkan |
| **Lewati** | Alasan wajib (mis. "materi sedang direvisi"); butir kembali ke giliran normal |

Butir yang tidak disentuh sampai hari berganti **tetap jatuh tempo** dan otomatis
muncul lagi besok. Tidak ada butir yang hilang diam-diam.

Di bawah kartu ada pratinjau **7 hari ke depan** (judul saja), supaya DO bisa
menyiapkan diri.

### 3.2 Naikkan karena temuan

Saat DO menemukan pelanggaran di lapangan (mis. dokter menunggu alat IPL), DO bisa
membuka materi terkait dan menekan **Ingatkan besok**. Butir itu ditambahkan ke kartu
besok di luar kuota harian.

### 3.3 Halaman katalog materi

DO dapat menambah, mengubah, menonaktifkan materi, dan mengatur frekuensinya
(lihat bagian 5). Materi yang dinonaktifkan tidak dijadwalkan, tetapi riwayatnya tetap
tersimpan.

### 3.4 Halaman riwayat

Daftar semua pengingat yang sudah dikirim: tanggal, materi, cabang, saluran, catatan.
Bisa disaring per materi, per cabang, per bulan. Halaman ini juga menjadi bukti
sosialisasi untuk akreditasi, jadi harus bisa diekspor (CSV cukup).

## 4. Aturan penjadwalan

### 4.1 Pengaturan (bisa diubah DO)

| Pengaturan | Nilai awal |
|---|---|
| Hari kerja | Senin–Sabtu |
| Jumlah butir per hari | 2 |
| Interval kelas A | 7 hari |
| Interval kelas B | 14 hari |
| Interval kelas C | 28 hari |

Dengan katalog awal yang aktif (6 butir A, 9 butir B, 6 butir C), kebutuhan rata-rata ±12 butir
per minggu, pas dengan kapasitas 2 butir × 6 hari = 12. Bila DO menambah banyak materi, tampilkan
peringatan di halaman katalog: "Kapasitas mingguan X, kebutuhan Y — sebagian materi akan
terlambat dari jadwalnya."

### 4.2 Cara memilih butir hari ini

1. Masukkan dulu semua butir **paksa**: yang ditunda kemarin dan yang dinaikkan karena temuan.
2. Untuk butir aktif lainnya, hitung `skor = hari sejak terakhir diingatkan ÷ interval kelasnya`.
   Butir yang belum pernah diingatkan diberi skor tinggi, diurutkan menurut prioritas,
   supaya minggu pertama tidak menumpuk.
3. Butir dengan skor ≥ 1 jatuh tempo. Urutkan dari skor tertinggi; bila sama, kelas A
   lebih dulu, lalu B, lalu C.
4. Isi kuota harian. **Variasi sasaran**: bila dua kandidat teratas punya sasaran peran
   yang sama persis, ambil kandidat berikutnya yang sasarannya berbeda, supaya satu
   kelompok staf tidak menerima dua pengingat sekaligus.
5. Bila jatuh tempo kurang dari kuota, kartu boleh berisi lebih sedikit. Jangan
   mengisinya dengan butir yang belum jatuh tempo.

"Terakhir diingatkan" dihitung dari log **Sudah diingatkan**, untuk cabang mana pun.
Simpan per cabang juga, karena kartu menampilkan keduanya.

### 4.3 Materi baru: ulangan rapat lalu berkala

Materi yang ditambahkan setelah fitur berjalan (atau yang ditandai "baru disosialisasikan"
dengan tanggal) mendapat jadwal ulangan tetap: **hari ke-1, ke-3, ke-7, ke-14, ke-30**
sesudah tanggal sosialisasi. Setelah itu materi masuk giliran normal sesuai kelasnya.
Ulangan tetap ini dihitung sebagai butir paksa (langkah 1).

Katalog awal di bagian 5 **tidak** mendapat ulangan ini, supaya hari pertama tidak
dibanjiri 22 butir. Pengecualian: butir yang di katalog sudah diberi `tanggal_sosialisasi`
(saat ini hanya AR-12).

### 4.4 Pratinjau 7 hari

Pratinjau adalah simulasi algoritma yang sama dengan anggapan semua butir hari-hari
sebelumnya ditandai "Sudah diingatkan". Cukup ditampilkan sebagai perkiraan, dan beri
label "perkiraan".

## 5. Katalog awal

Isi data awal (seed) melalui data migration atau fixture. Kolom `aktif: false` berarti
dimasukkan ke katalog tetapi tidak dijadwalkan sampai DO mengaktifkannya; alasannya
ada di `catatan`.

Kelas: **A** = mingguan, sering terlewat atau berisiko ke pasien; **B** = dua mingguan;
**C** = bulanan.

Teks WA ditulis untuk ditempel apa adanya; `{cabang}` diganti nama cabang atau
dihapus bila "keduanya".

```yaml
- kode: SP-01
  judul: Standar Dasar Pelayanan
  jenis: standar
  sasaran: [Semua staf]
  kelas: A
  rujukan: Standar_Dasar_Pelayanan_JoDerma.docx
  poin:
    - "Ramah: sapa begitu pasien datang, sebut namanya, HP disimpan saat melayani"
    - "Empati dan mau membantu: dengar sampai selesai; jangan berhenti di 'tidak bisa', tawarkan pilihan"
    - "Profesional: pertanyaan medis ke dokter, harga dari daftar resmi, hanya janjikan yang bisa dipenuhi"
  teks_wa: |
    Selamat pagi tim {cabang} 🙏 Pengingat Standar Dasar Pelayanan hari ini:
    1. Sapa pasien begitu datang dan sebut namanya. HP disimpan saat melayani.
    2. Dengar keluhan sampai selesai. Jangan berhenti di "tidak bisa" — tawarkan pilihan.
    3. Pesan WA pasien dibalas ≤ 15 menit.
    Empat nilai ini masuk penilaian kinerja. Terima kasih 🙏

- kode: AR-01
  judul: Menanggapi Keluhan dan Potensi Komplain
  jenis: alur
  sasaran: [Meja depan, Petugas online, Kasir, Perawat]
  kelas: A
  rujukan: Alur_Ringkas_Menanggapi_Keluhan.docx (SOP JD-CPL-01)
  poin:
    - "Enam langkah: Dengar, Akui, Cek, Tawarkan, Naikkan, Catat"
    - "Informasi baru dari pasien ('sudah janji dokter', 'sudah bayar') dicek, bukan dijawab dengan aturan yang sama"
    - "Keluhan dicatat di formulir komplain hari itu juga"
  teks_wa: |
    Pengingat menghadapi pasien yang kesal 🙏
    Dengar sampai selesai → akui perasaannya → CEK faktanya (jangan menebak) → tawarkan pilihan → naikkan ke koordinator bila buntu → catat di formulir komplain hari ini juga.
    Bila pasien menyampaikan hal baru ("saya sudah janji dengan dokter"), itu informasi yang harus dicek, bukan dibantah.

- kode: AR-07
  judul: Siap Sebelum Memanggil Dokter (ruang estetik dan injeksi)
  jenis: alur
  sasaran: [Perawat]
  kelas: A
  rujukan: Alur_Ringkas_Siap_Memanggil_Dokter_Estetik.docx
  poin:
    - "Alat energi sudah menyala, filter atau handpiece benar sudah terpasang"
    - "Injeksi: bola stres, alat getar, dan kasa sudah di tangan pendamping"
    - "Consent dan foto sebelum sudah ada sebelum dokter dipanggil"
  teks_wa: |
    Pengingat untuk perawat 🙏 Dokter dipanggil hanya setelah semuanya siap:
    ✅ Alat menyala, filter/handpiece sesuai
    ✅ Injeksi: bola stres, alat getar, kasa sudah di tangan pendamping
    ✅ Consent dan foto sebelum sudah ada
    ✅ Kacamata pasien terpasang (alat energi)
    Dokter masuk, langsung bekerja.

- kode: AR-02
  judul: Nomor Antrian
  jenis: alur
  sasaran: [Petugas online, Meja depan, Koordinator shift]
  kelas: A
  rujukan: Alur_Ringkas_Nomor_Antrian.docx
  poin:
    - "Nomor diberikan setelah biaya konsultasi dibayar; tanpa bayar tidak ada keep nomor kecuali izin dr. Yohanes atau Bu Jean"
    - "Pasien dipanggil menurut nomor; nomor yang belum datang dilewati, bukan dibatalkan"
    - "Pasien mengaku sudah janji langsung dengan dokter: konfirmasi ke dokter dulu"
  teks_wa: |
    Pengingat nomor antrian 🙏
    1. Nomor diberikan setelah biaya konsultasi dibayar.
    2. Sampaikan jam hadir 15 menit sebelum perkiraan giliran, dan bahwa 30 menit per nomor itu perkiraan.
    3. Nomor belum datang → lewati, jangan batalkan.
    4. Pasien bilang sudah janji langsung dengan dokter → konfirmasi ke dokter dulu, dokter yang memutuskan.

- kode: AR-03
  judul: Foto Klinis
  jenis: alur
  sasaran: [Perawat]
  kelas: B
  rujukan: Alur_Ringkas_Foto_Klinis.docx
  catatan: >
    Kebijakan ops P-9 (revisi 9/10: foto pasien hanya dengan perangkat klinik) belum
    selaras dengan alur ini (HP pribadi darurat: unggah lalu hapus, keputusan DO 7/10).
    Teks WA di bawah sengaja tidak menyebut HP pribadi sampai DO menyelaraskan keduanya.
  poin:
    - "Lima sudut wajah setiap kali: 90° kiri, 45° kiri, depan, 45° kanan, 90° kanan"
    - "Pakai kamera Photodex, cocokkan posisi dengan bayangan foto sebelumnya"
    - "Cek sebelum pasien beranjak: tajam, kepala utuh, lima sudut, sudah terunggah"
  teks_wa: |
    Pengingat foto klinis 📸
    • Selalu lima sudut: 90° kiri, 45° kiri, depan, 45° kanan, 90° kanan — walau keluhannya di satu sisi.
    • Pakai kamera Photodex, cocokkan dengan bayangan foto sebelumnya. Kamera sejajar wajah, pasien yang berputar.
    • Sebelum pasien beranjak: tajam, kepala utuh, lima sudut lengkap, sudah terunggah.

- kode: FAC-01
  judul: Limbah Medis
  jenis: alur
  sasaran: [Perawat, Piket]
  kelas: A
  rujukan: JD-FAC-X03_Alur_Limbah_Medis_Siap_Cetak.docx
  catatan: Dokumen sumber memuat kode gembok. Jangan pernah memasukkan kode gembok ke teks WA atau tampilan aplikasi.
  poin:
    - "Tiga perempat terisi sudah wajib dipindahkan; kotak jarum dipindahkan tertutup"
    - "Tempat pembuangan diperiksa setiap hari; gembok dikunci kembali setiap kali"
    - "Log limbah diisi saat memindahkan; tidak ada limbah tulis NIHIL"
  teks_wa: |
    Pengingat limbah medis 🗑️
    • Terisi ¾ → wajib dipindahkan (kotak jarum: kotaknya, tertutup — isinya jangan disentuh).
    • Tempat pembuangan dicek setiap hari, gembok dikunci kembali.
    • Kotak penampungan pertama penuh → hubungi vendor hari itu juga.
    • Log diisi saat memindahkan. Tidak ada limbah → tulis NIHIL.

- kode: AST-01
  judul: Cek Asistensi Harian
  jenis: kebijakan
  sasaran: [Kasir, Koordinator shift]
  kelas: A
  catatan: >
    Ketentuan sudah diumumkan DO. Sasaran peran perlu dipastikan DO di halaman katalog
    (siapa yang mengecek asistensi di tiap cabang). Bila ketentuan ini sudah ada di
    modul Kebijakan, tautkan ke record itu; bila belum, simpan sebagai teks di katalog.
  poin:
    - "Asistensi wajib dicek setiap hari"
    - "Ada ketidaksesuaian: wajib lapor Bu Jean paling lambat 2 hari"
    - "Lebih dari 2 hari: wajib menulis laporan kronologis lengkap"
  teks_wa: |
    Pengingat cek asistensi 📋
    1. Asistensi WAJIB dicek setiap hari.
    2. Ada ketidaksesuaian → lapor Bu Jean paling lambat 2 hari.
    3. Lewat dari 2 hari → wajib menulis laporan kronologis lengkap.

- kode: AR-04
  judul: Pendamping Injeksi
  jenis: alur
  sasaran: [Perawat]
  kelas: B
  rujukan: Alur_Ringkas_Pendamping_Injeksi.docx
  poin:
    - "Semua perlengkapan siap sebelum pasien masuk, bukan setelah diminta dokter"
    - "Satu meja, satu pasien, satu tindakan; tidak ada vial atau label pasien lain di meja"
    - "Periksa nama, batch, ED, segel; catatan suhu terputus atau segel rusak → jangan dipakai"
  teks_wa: |
    Pengingat pendamping injeksi 💉
    • Perlengkapan siap sebelum pasien masuk: bola stres, alat getar (sudah dicoba), kasa steril, wadah tahan tusuk.
    • Satu meja, satu pasien, satu tindakan.
    • Cek nama, batch, ED, segel. Ragu → jangan dipakai, lapor dokter dan apotek.

- kode: AR-05
  judul: Persiapan Operasi Minor
  jenis: alur
  sasaran: [Perawat, Koordinator shift]
  kelas: B
  rujukan: Alur_Ringkas_Persiapan_Operasi_Minor.docx (SOP T10, F08)
  poin:
    - "Begitu tahu ada tindakan, persiapan dimulai saat itu juga, sambil dokter memeriksa pasien lain"
    - "Consent tertulis lengkap sebelum pasien naik bed"
    - "Hitung kasa dan instrumen bersama sebelum insisi, dicatat di F08"
  teks_wa: |
    Pengingat persiapan operasi minor 🩺
    Begitu tahu ada tindakan: kabari koordinator → mintakan consent → siapkan ruang dan set steril → set anestesi berdiri → baru panggil dokter.
    Dokter tidak boleh menunggu alat atau consent. Hitung kasa dan instrumen bersama sebelum insisi.

- kode: AR-06
  judul: Pemesanan Online
  jenis: alur
  sasaran: [Petugas online, Apotek]
  kelas: B
  rujukan: Alur_Ringkas_Pemesanan_Online.docx
  poin:
    - "Stok dipastikan dulu, baru pasien diminta membayar"
    - "Identitas dicek dua kali: saat pesanan masuk dan oleh apotek sebelum diserahkan"
    - "Pesanan selesai setelah pasien mengonfirmasi barang diterima"
  teks_wa: |
    Pengingat pemesanan online 📦
    1. Pastikan stok dan harga ke apotek dulu, baru minta pasien bayar.
    2. Dana masuk = mulai hitungan 2 jam. 1,5 jam belum berangkat → kabari pasien.
    3. Identitas dicek dua kali. Obat resep hanya untuk pasien yang resepnya dari konsultasi di klinik.
    4. Selesai setelah pasien konfirmasi diterima; catat di buku logistik.

- kode: PO-01
  judul: Opening dan Closing Petugas Online
  jenis: alur
  sasaran: [Petugas online, Koordinator shift]
  kelas: C
  rujukan: Opening_Closing_Session_Petugas_Online.docx
  poin:
    - "Opening: baca semua pesan sejak closing kemarin, kerjakan pesanan menggantung lebih dulu"
    - "Closing: setiap pesanan belum selesai ditulis di lembar serah terima beserta statusnya"
    - "Cocokkan form pemesanan, nota apotek, dan uang masuk setiap hari"
  teks_wa: |
    Pengingat petugas online 📱
    Opening: baca semua pesan sejak closing kemarin, kerjakan yang menggantung dulu, konfirmasi booking H dan H-1.
    Closing: tulis semua pesanan/pesan yang belum selesai di lembar serah terima, cocokkan form – nota – uang masuk.

- kode: AR-08
  judul: Diagnosis di Kwitansi
  jenis: alur
  sasaran: [Kasir, Perawat]
  kelas: B
  rujukan: Alur_Ringkas_Diagnosis_di_Kwitansi.docx
  poin:
    - "Diagnosis ditulis sesuai yang ditetapkan dokter, tidak disingkat atau ditebak"
    - "Kasir memastikan kolom diagnosis terisi sebelum mencetak kwitansi"
    - "Kosong: tanyakan dokter atau perawat pendamping sebelum pasien pulang"
  teks_wa: |
    Pengingat kasir dan perawat 🧾
    Sebelum mencetak kwitansi, pastikan kolom diagnosis terisi dan sama dengan yang ditulis dokter. Kosong → tanyakan ke dokter/perawat pendamping sebelum pasien pulang.
    Perawat: ingatkan dokter bila diagnosis belum ditulis saat konsultasi selesai.

- kode: AR-09
  judul: Kirim Barang Antar Cabang
  jenis: alur
  sasaran: [Koordinator shift, Apotek]
  kelas: C
  rujukan: Alur_Ringkas_Kirim_Barang_Antar_Cabang.docx
  poin:
    - "Setiap kiriman memakai nota pengiriman; tanpa tanda terima dianggap belum selesai"
    - "Koordinator pengirim mengabari penerima: barang apa, dibawa siapa, perkiraan tiba"
    - "Obat, krim, dan produk dingin tidak ditinggal di mobil"
  teks_wa: |
    Pengingat kirim barang antar cabang 🚗
    Setiap kiriman: nota pengiriman → kabari koordinator penerima → penerima cek, tanda tangan, foto nota dikirim balik.
    Termasuk yang dititipkan ke dokter/Owner. Obat dan produk dingin tidak ditinggal di mobil.

- kode: PHR-01
  judul: Cold Chain
  jenis: alur
  sasaran: [Apotek, Perawat]
  kelas: B
  rujukan: Alur_Staf_Cold_Chain.docx
  poin:
    - "Suhu dicatat dua kali sehari: 13.30 dan saat penutupan"
    - "Suhu di luar 2–8 °C: pindahkan produk ke unit cadangan sebelum melapor"
    - "Produk terpapar dikarantina sampai Apoteker dan PJ Klinik memutuskan"
  teks_wa: |
    Pengingat cold chain ❄️
    • Catat suhu kulkas pukul 13.30 dan saat penutupan.
    • Di luar 2–8 °C → pindahkan produk ke unit cadangan DULU, baru lapor Apoteker.
    • Produk terpapar dikarantina, tidak dipakai sampai diputuskan Apoteker dan PJ Klinik.
    • Pintu kulkas segera ditutup; ED terdekat keluar lebih dulu.

- kode: FO-01
  judul: Input Data Pasien Baru
  jenis: alur
  sasaran: [Perawat, Koordinator shift, Meja depan]
  kelas: B
  rujukan: Alur_Staf_Input_Data_Pasien_Baru.docx
  poin:
    - "Koordinator menetapkan penginput (perawat utama dan pengganti) saat briefing"
    - "Input segera di Omnicare dan emr.joderma.id, sebelum konsultasi"
    - "Konsultasi tidak dimulai sebelum data pasien baru lengkap di Omnicare"
  teks_wa: |
    Pengingat pasien baru 📝
    Data diri pasien baru diinput SEGERA selagi pasien menunggu — Omnicare dan emr.joderma.id.
    Cocokkan nama dan tanggal lahir. Konsultasi tidak dimulai sebelum data lengkap di Omnicare.

- kode: FO-02
  judul: Double Check Front Office
  jenis: alur
  sasaran: [Meja depan, Kasir]
  kelas: B
  catatan: >
    Tiga titik double check sudah disosialisasikan lisan oleh DO pada 10/10 dan
    diputuskan aktif. Isi tiga titiknya belum tertulis di dokumen; sampai DO mengisi
    poin lewat halaman katalog, kartu menampilkan label "poin belum diisi" dan teks WA
    di bawah dipakai apa adanya.
  aktif: true
  poin: ["(diisi DO)", "(diisi DO)", "(diisi DO)"]
  teks_wa: |
    Pengingat double check front office ✅
    Tiga titik double check yang sudah disampaikan tetap dijalankan setiap pasien, tanpa terkecuali.
    Ragu di salah satu titik → cek ulang dulu sebelum lanjut.

- kode: AR-10
  judul: ED Pendek dan Stok Kosong
  jenis: alur
  sasaran: [Apotek]
  kelas: C
  rujukan: Alur_Ringkas_ED_Pendek_dan_Stok_Kosong.docx (SOP PHR-01)
  poin:
    - "Daftar ED empat tingkat (≤12, ≤6, ≤3, ≤1 bulan) diperbarui setiap minggu"
    - "Produk diretur karena ED dekat: pesan ulang hari yang sama, minta ED panjang"
    - "Stok akan kosong: beri tahu dokter, koordinator shift, dan petugas online"
  teks_wa: |
    Pengingat apotek 💊
    • Daftar ED empat tingkat diperbarui minggu ini?
    • Produk yang diretur karena ED dekat → pesan ulang hari itu juga, tanyakan ED batch pengganti.
    • Stok akan kosong → kabari dokter, koordinator, dan petugas online supaya tidak dijanjikan ke pasien.

- kode: AR-11
  judul: Surat Sakit
  jenis: alur
  sasaran: [Meja depan, Kasir, Perawat]
  kelas: C
  rujukan: Alur_Ringkas_Surat_Sakit.docx
  poin:
    - "Berlaku mulai tanggal berobat, tidak boleh mundur"
    - "Paling lama 5 hari kecuali kebijakan dokter; alasannya ditulis di RM"
    - "Lama istirahat ditentukan dokter, bukan petugas"
  teks_wa: |
    Pengingat surat sakit 📄
    Mulai tanggal berobat, tidak berlaku mundur, paling lama 5 hari — kecuali keputusan dokter (alasannya ditulis di RM).
    Pasien minta di luar aturan → jawab sopan, teruskan ke dokter. Petugas tidak memutuskan sendiri.

- kode: CGV-01
  judul: Pengiriman Sampel Biologis
  jenis: alur
  sasaran: [Perawat]
  kelas: C
  rujukan: Alur_Staf_Pengiriman_Sampel_Biologis.docx (formulir JD-CGV-F04)
  poin:
    - "Satu wadah satu lokasi; label ditulis dulu sebelum sampel diambil"
    - "Label dibacakan di depan orang kedua, keduanya paraf"
    - "Simpan suhu ruang, jangan masuk kulkas; hasil belum datang di tanggal perkiraan → tagih lab"
  teks_wa: |
    Pengingat sampel biologis 🧪
    Tanya dokter sebelum tindakan: berapa sampel, lokasi, pemeriksaan, medium.
    Satu wadah satu lokasi, label ditulis dulu. Bacakan label di depan orang kedua, paraf berdua.
    Suhu ruang — jangan masuk kulkas. Label ragu/sampel hilang → hentikan, lapor dokter.

- kode: PHR-02
  judul: Peminjaman Produk dan Bahan
  jenis: alur
  sasaran: [Semua staf]
  kelas: C
  rujukan: Alur_Staf_Peminjaman_Produk_dan_Bahan.docx (formulir JD-PHR-F03)
  poin:
    - "Satu permintaan satu lembar formulir JD-PHR-F03"
    - "Izin belum ada → barang tidak diserahkan; tidak ada 'pakai dulu, izin menyusul'"
    - "Setiap pengeluaran bernota dan dicatat saat itu juga"
  teks_wa: |
    Pengingat peminjaman barang 📋
    Isi formulir JD-PHR-F03, minta izin ke yang berwenang dulu. Belum ada izin → barang tidak diserahkan.
    Setiap barang keluar bernota dan dicatat saat itu juga.

- kode: EST-01
  judul: Tindakan Estetik Bayar di Akhir
  jenis: alur
  sasaran: [Kasir, Perawat, Dokter]
  kelas: C
  rujukan: Bacaan_Staf_Alur_Tindakan_Estetik_Bayar_di_Akhir.docx (Memo 006)
  catatan: Ditunda oleh DO (13 Oktober 2026). Jangan dijadwalkan sampai DO mengaktifkannya.
  aktif: false
  poin:
    - "Kasir membuat rincian sementara tindakan selagi pasien menunggu"
    - "Perawat menunjukkan rincian dan harga setelah cleansing, sebelum tindakan dilanjutkan"
    - "Form asistensi dibawa ke kasir; upselling ditulis di kolom catatan"
  teks_wa: |
    Pengingat tindakan estetik 💆
    Rincian dan harga ditunjukkan ke pasien setelah cleansing, sebelum tindakan dilanjutkan. Yang ditolak dicoret.
    Form asistensi dibawa ke kasir bersama pasien; upselling di kolom catatan.

- kode: AR-12
  judul: Pasien Asuransi
  jenis: alur
  sasaran: [Meja depan, Perawat, Kasir]
  kelas: B
  rujukan: Alur_Ringkas_Pasien_Asuransi.docx; DRAF_Lembar_Resume_Medis_Asuransi.docx
  catatan: >
    Disetujui 13 Oktober 2026. Materi baru: mendapat ulangan hari ke-1, 3, 7, 14, 30
    sejak tanggal sosialisasi, lalu giliran normal kelas B.
  aktif: true
  tanggal_sosialisasi: 2026-10-13
  poin:
    - "Cara bayar ditanyakan sejak pendaftaran"
    - "Dokumen klaim ditandatangani dokter saat konsultasi"
    - "Di kasir: nota rinci, kwitansi dengan diagnosis, dan dokumen klaim diserahkan sekaligus"
  teks_wa: |
    Pengingat pasien asuransi 🏥
    Tanyakan cara bayar sejak pendaftaran. Bila asuransi: lampirkan formulir asuransi pasien atau Lembar Resume Medis di berkas RM, tandai "ASURANSI".
    Dokter tanda tangan saat konsultasi. Kasir menyerahkan nota rinci, kwitansi dengan diagnosis, dan dokumen klaim sekaligus.
    Jangan menjanjikan klaim pasti diganti.
```

Ringkasan katalog awal: 22 butir. Yang aktif: A = 6, B = 9, C = 6 (EST-01 ditunda);
kebutuhan ±12 butir per minggu, pas dengan kapasitas. AR-12 adalah satu-satunya butir
katalog awal yang mendapat ulangan materi baru (4.3), karena tanggal sosialisasinya diisi.

### 5.1 Kebijakan yang sudah ada di ops

Modul Kebijakan sudah memuat ±53 kebijakan berlaku. Katalog pengingat boleh merujuk
satu kebijakan sebagai materi (jenis `kebijakan`, tautan ke record kebijakan). Jangan
menyalin isinya ke tabel baru; tampilkan dari record aslinya. Tahap ini tidak perlu
memasukkan kebijakan mana pun secara otomatis; DO memilih sendiri lewat halaman katalog.

## 6. Data minimal

Model dan nama field boleh disesuaikan agen dengan pola yang sudah ada di repo.

| Entitas | Isi |
|---|---|
| Materi pengingat | kode (unik), judul, jenis (alur / sop / standar / kebijakan), sasaran peran, cabang (Jemur / Citraland / keduanya), kelas, poin (3), teks WA, rujukan (teks atau tautan), aktif, tanggal sosialisasi (opsional), catatan |
| Log pengingat | materi, tanggal, cabang, saluran, catatan, oleh (user) |
| Penundaan | materi, tanggal paksa muncul, sebab (tunda / temuan / ulangan materi baru), sudah dipakai |
| Pengaturan | hari kerja, kuota harian, interval A/B/C |

Semua perubahan materi dan log tercatat di jejak audit yang sudah ada.

## 7. Kriteria selesai

Dicentang 14 Oktober 2026 di branch `pengingat-harian` (test otomatis dan UI test desktop/HP di salinan
database). Keputusan PO saat implementasi: Lewati memundurkan jadwal satu interval; kartu dikunci per
hari; semua akun Direktur Operasional berbagi satu kartu; katalog dan riwayat menjadi tab di kelompok
Kebijakan.

- [x] Kartu muncul di Ringkasan Direktur dengan dua butir pada hari kerja, kosong pada hari libur.
- [x] Butir yang tidak ditandai muncul lagi esok hari.
- [x] "Tunda ke besok" dan "Ingatkan besok" memaksa butir muncul besok di luar kuota.
- [x] Materi baru dengan tanggal sosialisasi muncul pada hari ke-1, 3, 7, 14, 30, lalu giliran normal.
- [x] Dua butir di satu hari tidak memiliki sasaran peran yang sama persis, bila ada alternatif.
- [x] Tombol Salin menyalin teks WA dengan `{cabang}` sudah diganti.
- [x] Peringatan kapasitas muncul bila kebutuhan mingguan melebihi kapasitas.
- [x] Riwayat bisa disaring dan diekspor CSV.
- [x] Staf biasa ditolak server (403) di semua URL fitur ini.
- [x] Tampilan HP nyaman: kartu terbaca tanpa geser ke samping; tombol Salin mudah ditekan.
- [x] Test otomatis untuk algoritma penjadwalan (termasuk tanggal tetap via waktu tiruan) dan izin akses.
- [x] `docs/README.md`, `docs/panduan-direktur.md`, dan `docs/peran-dan-akses.md` diperbarui.

## 8. Tahap berikutnya (bukan sekarang)

- Pengingat diteruskan langsung ke lonceng notifikasi staf sesuai sasaran perannya,
  dengan tanda "sudah dibaca".
- Kuis singkat satu pertanyaan per pengingat untuk mengukur ingatan staf.
- Pengingat otomatis dari temuan: temuan berkategori tertentu langsung menaikkan materi
  terkait ke esok hari.
