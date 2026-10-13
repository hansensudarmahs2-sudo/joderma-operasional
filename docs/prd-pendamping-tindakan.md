> **Diarsipkan ke repo 13 Oktober 2026.** Isi di bawah ini **utuh seperti aslinya**;
> hanya blok ini yang ditambahkan. Berkas asal:
> `PRD — Pendamping Tindakan Perawat (ops.joderma.id).md`.
>
> **Baca bersama [`tinjauan-pendamping-tindakan.md`](tinjauan-pendamping-tindakan.md).**
> Tinjauan itu memverifikasi klaim dokumen ini terhadap kode (semuanya terbukti
> benar), tetapi menemukan bahwa volume tindakan belum cukup untuk rata-rata per
> perawat, skema aplikasi survei tidak bisa menampung rating apa adanya, dan
> Citraland belum punya kategori tindakan. Beberapa keputusan terbuka di bagian
> terakhir dokumen ini **sudah dijawab product owner 13 Okt** — jawabannya ada di
> bagian 5 tinjauan tersebut.

# PRD — Pendamping Tindakan Perawat (ops.joderma.id)

Oct 13, 2026 · @Hansen Sudarma

## Ringkasan

Pendamping Tindakan memperluas tally perawat di ops.joderma.id menjadi alur lengkap per tindakan: perawat memasukkan nomor RM dan memilih tindakan, layar menampilkan langkah yang akan dilakukan untuk dijelaskan ke pasien, lalu setelah tindakan pasien yang bersedia diajak memberi rating bintang lewat HP-nya dan diteruskan ke survei.

Tiga bagian fitur ini, dengan keputusan yang sudah dibuat:

- **Layar langkah tindakan.** Tujuannya transparansi dan melibatkan pasien, bukan informed consent medis (consent sudah diambil saat konsultasi). Isi ditulis dan disetujui dr. Yohanes.
- **Lembar kombinasi dan tips untuk perawat.** Hanya dibaca perawat, tidak tampil ke pasien. Tawaran tindakan medis apa pun tetap lewat persetujuan dokter; perawat hanya membagi informasi.
- **Rating satu pertanyaan.** Bintang 1–5 tentang sesi pelayanan perawat, diisi pasien sendiri di HP-nya setelah menyetujui secara lisan atas ajakan perawat, lalu tersambung ke survei yang sudah siap pakai.

Dokumen ini juga memuat hal yang belum diputuskan (bagian terakhir) supaya bisa dibahas bersama Owner dan dr. Yohanes sebelum pengerjaan.

## Latar belakang dan kondisi sistem saat ini

Ops sudah punya modul perawat dan tally yang berjalan, sehingga fitur ini dibangun di atasnya, bukan dari nol. Temuan berikut dibaca dari repo joderma-operasional (13 Oktober 2026); repo survei (joderma-survey) belum saya baca, jadi bagian integrasi survei bersandar pada catatan di current-progress.md.

| Hal | Kondisi sekarang | Dampak untuk fitur ini |
| --- | --- | --- |
| Stack | Django 5.1, app `nurses`, di mini PC klinik, diakses lewat Cloudflare/Tailscale | Fitur baru cukup menjadi tambahan di app `nurses`, tanpa teknologi baru |
| Tally | `NurseActionTally` menyimpan nomor RM, nama pasien, nama tindakan (teks bebas), dan jumlah; perawat hanya melihat tally miliknya sendiri | Nama tindakan masih teks bebas, jadi perlu daftar tindakan terkontrol agar langkah bisa ditampilkan |
| Kategori | `ProcedureCategory` per cabang menandai tindakan berkomisi, dan `NurseEligibility` mencatat kompetensi perawat per kategori | Bisa dipakai ulang untuk syarat kompetensi lembar kombinasi; tally dan giliran berkaitan dengan komisi |
| Peran | Peran `PERAWAT` sudah ada, ditegakkan di sisi server (403 bila tidak berhak) | Hak akses fitur baru mengikuti pola yang sama |
| Data pasien | Antrean memakai prinsip data minimum; tally saat ini masih menyimpan nama pasien selain RM | Fitur baru hanya memakai nomor RM; perlu diputuskan apakah kolom nama pasien di tally tetap dipakai |
| Survei | Aplikasi terpisah (joderma-survey), dibuka dari menu Survei di ops, halaman pasien di survey.joderma.id; tautan unik per pasien dibuat dari ekspor Omnicare | Rating perlu jalur sendiri, karena tautan survei yang ada dibuat sesudah kunjungan dari berkas Omnicare |
| Omnicare | Tidak ada API; sumber transaksi adalah ekspor .xls | Nomor RM tetap diketik perawat, dan tally yang ada sudah mewajibkannya sehingga tidak menambah input |

## Tujuan, bukan-tujuan, dan prinsip

Tujuan utamanya membuat pasien paham dan merasa dilibatkan dalam terapinya, dengan penjelasan yang seragam di semua perawat dan cabang.

**Tujuan**

1. Setiap tindakan dijelaskan ke pasien dengan langkah, durasi, dan sensasi yang wajar, memakai isi yang disetujui dr. Yohanes.
2. Perawat punya bahan baca singkat tentang kombinasi tindakan yang lazim, untuk membantu pasien mendapat opsi yang sesuai kebutuhan.
3. Klinik mendapat suara pasien per sesi lewat rating satu pertanyaan, dan menjaring pasien yang bersedia mengisi survei.

**Bukan tujuan**

- Bukan pengganti informed consent medis dan bukan dokumen hukum.
- Bukan alat memutuskan atau mengubah rencana tindakan; keputusan medis tetap di dokter.
- Bukan alat menaikkan omset sebagai ukuran utama.
- Bukan penilaian kinerja perawat dari satu rating.

**Prinsip desain**

- **Membantu pasien dulu.** Tawaran tambahan hanya bila sesuai kondisi kulit pasien, dan selalu lewat persetujuan dokter.
- **Terbuka dan jujur.** Perawat membagi informasi, tidak menyudutkan atau menyesatkan pasien.
- **Data minimum.** Fitur baru hanya memakai nomor RM; tidak ada nomor telepon, diagnosis, atau foto.
- **Sederhana.** Perawat mengisi sesedikit mungkin dan tidak mengetik ulang apa yang sudah ada di tally.
- **Transparan ke perawat.** Perawat tahu sejak awal bahwa rating pasien tercatat per perawat, seperti rating kurir online.

## Alur penggunaan

Alur satu tindakan berjalan dalam tujuh langkah, dan hanya langkah 6 yang bercabang bergantung pada kesediaan pasien.

1. **Input.** Perawat membuka ops, mengetik nomor RM, dan memilih tindakan dari daftar. Ini menggantikan pengisian tally manual yang sekarang.
2. **Layar "Hari ini kita akan...".** Layar menampilkan 3–5 langkah dalam bahasa awam, perkiraan durasi, dan sensasi yang wajar (misalnya hangat atau perih sebentar). Perawat menunjukkannya ke pasien dan menjelaskan.
3. **Aba-aba.** Perawat mengucapkan satu kalimat: bila terasa tidak nyaman, pasien mengangkat tangan dan tindakan berhenti.
4. **Tombol "Sudah dijelaskan".** Perawat menekannya; waktu dicatat. Ini bukti SOP penjelasan dijalankan, bukan persetujuan hukum.
5. **Tindakan berjalan.** Saat menunggu alat siap (misalnya vapor), perawat bisa membuka lembar bacaan khusus perawat.
6. **Ajakan rating.** Setelah selesai, perawat mengingatkan dan mengajak pasien memberi bintang. Bila pasien bersedia secara lisan, tautan atau kode QR muncul di layar perawat; pasien memindainya dan mengisi sendiri di HP. Bila tidak bersedia, selesai di sini dan tidak ada tindak lanjut.
7. **Ajakan survei.** Setelah memberi bintang, pasien yang bersedia diajak melanjutkan ke survei yang sudah siap pakai.

Semua langkah di atas tercatat pada satu entri tally yang sama (nomor RM, tindakan, waktu dijelaskan, apakah rating ditawarkan).

## Kebutuhan fungsional

### A. Katalog tindakan dan layar langkah

- Daftar tindakan terkontrol menggantikan teks bebas pada tally. Setiap tindakan punya: nama, kategori, 3–5 langkah, durasi, sensasi yang wajar, dan satu kalimat aba-aba.
- Isi ditulis dan disetujui dr. Yohanes. Setiap tindakan punya nomor versi, tanggal persetujuan, dan status (draf atau disetujui); hanya yang disetujui tampil ke pasien.
- Layar menghadap pasien: huruf besar, bahasa awam, tanpa nama pasien dan tanpa istilah klinis yang tidak perlu.
- Tombol "Sudah dijelaskan" mencatat waktu dan nama perawat pada entri tally.
- Tindakan yang belum ada di katalog tetap bisa dicatat (jalur cadangan), tetapi ditandai agar bisa ditambahkan ke katalog.
- Perawat hanya memilih tindakan yang kompetensinya ia miliki (memakai `NurseEligibility` yang ada).

### B. Lembar kombinasi dan tips (khusus perawat)

- Halaman terpisah dari layar pasien; tidak pernah tampil di layar yang dihadapkan ke pasien.
- Isi: kombinasi tindakan yang lazim, ditulis dokter, berlabel jelas **"opsi pendamping yang bisa ditawarkan sesuai kebutuhan pasien"**, bukan indikasi medis. Tips komunikasi ditulis sebagai cara menjelaskan manfaat dan batasannya, bukan teknik menekan.
- Syarat sebelum perawat membuka halaman ini: lulus kuis atau checklist penilaian kulit wajah (standar disusun dokter). Status lulus tercatat per perawat.
- Bacaan singkat (kurang dari satu menit per butir) agar bisa dibaca saat menunggu alat siap.
- Tawaran tindakan medis apa pun yang disetujui pasien hanya masuk ke tally setelah perawat menandai "sudah dikonfirmasi dokter". Tanpa penanda itu, tindakan tambahan tidak tercatat.

### C. Rating pasien

- Satu pertanyaan tentang sesi pelayanan perawat, jawaban bintang 1–5, tanpa kolom teks wajib.
- Diisi pasien sendiri di HP-nya; perawat tidak bisa mengisi atau mengubah rating. Perawat hanya mengingatkan dan mengajak, setelah pasien menyetujui secara lisan.
- Setiap rating terikat pada satu entri tally (perawat, tindakan, tanggal), tanpa nama pasien. Satu tautan hanya berlaku sekali dan kedaluwarsa dalam waktu singkat.
- Setelah memberi bintang, pasien melihat ajakan ke survei dan boleh menolak.
- Perawat diberi tahu sejak awal bahwa rating tercatat per perawat. Dashboard menampilkan rata-rata hanya setelah jumlah rating minimum tertentu, supaya satu rating buruk tidak mendominasi.
- Ukuran pembanding adil: persentase tindakan per perawat yang ditawari rating, dibanding jumlah tindakannya di tally. Perawat yang tingkat penawarannya jauh di bawah rata-rata menjadi sinyal untuk ditinjau, karena rating hanya bermakna bila semua pasien punya peluang yang sama diajak.

## Data, akses, dan integrasi

Usulan data baru, semuanya di app `nurses` kecuali bila disebut lain:

| Data | Isi | Catatan |
| --- | --- | --- |
| Katalog tindakan | nama, kategori, langkah, durasi, sensasi, aba-aba, versi, status, tanggal persetujuan | Diedit oleh peran yang ditetapkan, disetujui dokter |
| Entri tally (perluasan) | tindakan dari katalog, waktu "sudah dijelaskan", versi katalog yang dipakai, penanda konfirmasi dokter untuk tindakan tambahan | Nomor RM tetap satu-satunya identitas pasien |
| Rating | bintang 1–5, waktu, terikat ke entri tally | Tanpa nama pasien dan tanpa nomor telepon |
| Status kompetensi | lulus kuis penilaian kulit, tanggal, versi kuis | Per perawat |

**Hak akses**

| Peran | Katalog dan lembar kombinasi | Rating |
| --- | --- | --- |
| Perawat | Membaca katalog yang disetujui; membuka lembar kombinasi setelah lulus kuis | Melihat jumlah penawaran dirinya; rata-rata rating dirinya sesuai keputusan di bagian terbuka |
| Direktur Medis (dr. Yohanes) | Menulis dan menyetujui konten | Membaca |
| Direktur Operasional dan Owner | Membaca | Membaca per perawat dan per cabang |
| Koordinator Shift | Membaca | Melihat tingkat penawaran perawat di shift-nya |

Penegakan di sisi server seperti modul lain (menyembunyikan tombol bukan kontrol akses). Nama persis peran dan kapabilitas disesuaikan dengan `core/permissions.py` saat pengerjaan.

**Integrasi dengan survei**

- Survei yang ada membuat tautan unik per pasien dari ekspor Omnicare, dengan aturan kirim ulang 30 hari dan jeda 365 hari setelah menjawab. Rating perlu jalur terpisah karena terjadi saat itu juga dan tidak bergantung pada ekspor.
- Usulan: ops membuat tautan atau kode QR sekali pakai untuk satu entri tally; halaman rating berada di aplikasi survei (publik di survey.joderma.id) supaya pasien tidak perlu login dan tidak ada nomor telepon yang disimpan. Setelah bintang terkirim, halaman menawarkan lanjut ke survei.
- Pencocokan dengan undangan survei yang dibuat dari ekspor Omnicare dilakukan lewat nomor RM dan tanggal kunjungan, sehingga pasien yang sudah mengisi lewat jalur rating tidak dikirimi undangan ganda.
- Pasien yang bersedia hanya diajak, tidak ada pengiriman otomatis.

## Fase pengerjaan dan ukuran keberhasilan

Urutan di bawah adalah usulan; tiap fase berakhir dengan persetujuan product owner, seperti pola kerja ops yang sudah ada.

1. **Fase 0 — Konten dan keputusan.** dr. Yohanes menyusun langkah, durasi, sensasi, dan aba-aba untuk 5–10 tindakan yang paling sering dikerjakan; keputusan terbuka di bawah dijawab. *Gerbang: konten disetujui dokter.*
2. **Fase 1 — Katalog dan layar langkah.** Pilihan tindakan dari katalog di alur tally, layar "Hari ini kita akan...", tombol "Sudah dijelaskan". Uji coba satu cabang, satu minggu. *Gerbang: perawat tidak melaporkan alur melambat dan layar dipakai pada sebagian besar tindakan di katalog.*
3. **Fase 2 — Rating dan sambungan survei.** Tautan atau QR sekali pakai, halaman rating, ajakan survei, penghitungan tingkat penawaran. *Gerbang: rating tersimpan benar dan tidak ada undangan survei ganda.*
4. **Fase 3 — Lembar kombinasi.** Halaman khusus perawat, kuis kompetensi, penanda konfirmasi dokter. Ditaruh sesudah rating karena paling bergantung pada konten dokter dan standar kompetensi.
5. **Fase 4 — Dashboard.** Ringkasan untuk Direktur dan Owner: cakupan penjelasan, tingkat penawaran, rating dengan batas minimum, kepuasan pasien yang menerima tindakan tambahan.

**Ukuran keberhasilan** (target angka ditetapkan setelah uji coba satu cabang, bukan ditebak sekarang):

| Ukuran | Cara menghitung | Mengapa penting |
| --- | --- | --- |
| Cakupan penjelasan | Tindakan dengan "Sudah dijelaskan" dibanding total tally | Menunjukkan SOP dijalankan |
| Tingkat penawaran rating | Tindakan yang ditawari rating per perawat dibanding total tindakannya | Menjaga rating adil dan bisa dibandingkan |
| Tingkat respons | Pasien yang mengisi dibanding yang ditawari | Menunjukkan apakah ajakan terasa wajar |
| Rating rata-rata | Per perawat dan cabang, hanya di atas jumlah rating minimum | Suara pasien tanpa dominasi satu rating |
| Kepuasan pada tindakan tambahan | Rating pasien yang menerima tindakan tambahan | Memastikan tambahan tindakan membantu pasien, bukan hanya omset |
| Waktu input | Waktu dari pilih tindakan sampai tally tersimpan | Mendeteksi beban kerja tambahan bagi perawat |

## Risiko dan cara menjaganya

| Risiko | Cara menjaga |
| --- | --- |
| Tujuan membantu pasien bergeser menjadi mengejar omset, terutama karena tally berkaitan dengan komisi | Memantau kepuasan pasien yang menerima tindakan tambahan, bukan hanya jumlahnya; persetujuan dokter sebagai langkah wajib di alur |
| Rating dipilih-pilih: perawat hanya mengajak pasien yang tampak puas | Tingkat penawaran per perawat dipantau dan dibandingkan dengan rata-rata |
| Rating dibaca sebagai penilaian kinerja tunggal | Rata-rata hanya tampil setelah jumlah rating minimum; perawat diberi tahu sejak awal |
| Konten penjelasan usang atau tidak seragam | Versi dan tanggal persetujuan pada setiap tindakan; tinjauan berkala oleh dokter |
| Pasien menganggap layar langkah sebagai persetujuan hukum | Judul dan bahasa layar menyebutnya penjelasan; consent medis tetap di konsultasi |
| Beban kerja perawat bertambah | Nomor RM sudah wajib di tally; waktu input diukur selama uji coba satu cabang |
| Data kesehatan masuk ke sistem yang tadinya hanya operasional | Hanya nomor RM; tidak ada nama, telepon, diagnosis, atau foto pada fitur baru; sisa kolom nama pasien di tally diputuskan di bagian terbuka |
| Tautan rating disalahgunakan atau diisi berulang | Sekali pakai, masa berlaku pendek, terikat ke satu entri tally |

## Keputusan yang masih terbuka

- [ ] **dr. Yohanes:** apakah layar langkah perlu memuat risiko khas pasca-tindakan, atau cukup langkah dan sensasi?
- [ ] **dr. Yohanes:** tindakan mana yang masuk katalog fase pertama, dan siapa yang menyusun kuis penilaian kulit?
- [ ] **Hansen:** pasien mengisi rating lewat kode QR di layar perawat (usulan, tanpa nomor telepon) atau tautan yang dikirim CS lewat WhatsApp?
- [ ] **Hansen:** apakah perawat melihat rata-rata rating dirinya sendiri, dan siapa saja yang boleh melihat rating per perawat?
- [ ] **Hansen:** apakah kolom nama pasien pada tally yang sekarang tetap dipertahankan atau dihapus, mengingat fitur baru hanya memakai nomor RM?
- [ ] **Hansen dan Owner:** apakah katalog tindakan baru berdiri sendiri atau memakai kategori tindakan berkomisi yang sudah ada sebagai induknya?
- [ ] **Owner:** persetujuan konsep, termasuk rating per perawat dan jumlah rating minimum sebelum rata-rata ditampilkan.
