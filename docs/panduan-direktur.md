# Panduan Direktur Operasional dan Owner

Halaman ini untuk pemegang role `AOM` (Direktur Operasional) dan `OWNER`. Semua halaman di bawah
menolak pengguna lain di server (HTTP 403), bukan hanya disembunyikan dari menu.

## Menyiapkan sekali

```bash
.venv/bin/python manage.py seed_audit_direktur --dry-run   # lihat dulu apa yang akan dibuat
.venv/bin/python manage.py seed_audit_direktur             # isi butir checklist Direktur
```

Perintah ini idempoten: menjalankannya lagi tidak menggandakan butir dan tidak menimpa teks
yang sudah disunting lewat Django admin. Untuk sengaja mengembalikan teks ke isi awal, pakai
`--update`.

Isi awalnya diambil dari Checklist Harian dan Checklist Mingguan Direktur Operasional
(Revisi 00), dengan perubahan yang diputuskan 27 September 2026:

| Siklus | Butir | Catatan |
|---|---|---|
| Harian | 8 | 6 butir dokumen + **Kas** + **Kebersihan ruang** (pengingat pengamatan langsung) |
| Mingguan | 13 | Sesuai dokumen; pemeriksaan bulanan tas emergency kit dipindah ke bulanan |
| Bulanan | 1 | Pemeriksaan bulanan tas emergency kit |

Butir "Kesiapan buka Citraland" hanya muncul untuk cabang berkode `citraland`. Deposit/keep
antrian tidak masuk checklist ini karena pencatatannya sudah dipegang Finance.

## Menu

Menu atas sengaja pendek (5 Okt 2026): **Ringkasan**, **Inbox**, **Dari staf**, **Tim**, lalu tiga menu
kelompok lagi —
**Task** (Daftar Task, Kanban, Prioritas, Jadwal Task), **Evaluasi staf** (KPI, Jejak), dan
**Kebijakan** (Kebijakan, Keputusan, Bahan Rapat). Membuka menu kelompok membawa Anda ke halaman
pertamanya; halaman lain dalam kelompok dipilih lewat **baris tab di atas halaman**. Detail task,
detail keputusan, dan rincian KPI per staf juga menampilkan tab kelompoknya.

- **Tugas saya** — task yang dikirim kepada Anda (termasuk yang Anda tugaskan ke diri sendiri) tampil
  paling atas di **Ringkasan** dan di **Hari Ini**, dengan tombol **Lapor progres** dan **Ajukan
  selesai**. Kedua tombol itu juga ada di halaman detail task, di baris nama Anda pada tabel
  Penerima. Task yang penerimanya Anda diperiksa Direktur Utama / Owner (kecuali sub task temuan
  Owner, lihat di bawah): sesudah diajukan, statusnya
  **Diajukan selesai** (menunggu konfirmasi) sampai Owner mengonfirmasi atau meminta revisi. Bila
  evaluasinya Anda sendiri, pakai Lapor progres dan geser Target ke tanggal evaluasi; ajukan selesai
  sesudahnya.
- **Dari staf** — satu menu dengan tab Komplain, Masukan, Kerusakan, Laporan staf, dan Masukan privat
  staf dari **semua
  cabang** (kolom/keterangan cabang di setiap baris), termasuk yang sudah ditangani cabang. Persempit ke
  satu cabang lewat **Filter ▸ Cabang**. Masukan/saran bernomor SUG-… yang ditulis staf lewat Lapor ▸
  Masukan ada di menu **Masukan**; **Masukan privat staf** adalah kotak saran privat (hanya pengirim
  dan Anda). Inbox tetap tempat memilah.
- **Tim** — per cabang: butir checklist staf yang belum diisi hari ini, pemegang tiap fungsi
  PIC, task per orang (belum selesai / menunggu konfirmasi / selesai 7 hari), dan temuan
  Direktur yang masih terbuka. Hanya untuk membaca; tidak ada skor atau peringkat.
- **Checklist Direktur** — pilih cabang dan siklus (harian, mingguan, bulanan). Butir yang
  belum punya hasil pada periode berjalan tampil sebagai **Belum dicek**; periode mingguan
  mulai Senin, bulanan mulai tanggal 1. Kotak "Saran cek langsung" memilih tiga rincian harian
  secara acak dan tetap sama sepanjang hari.
- **Catatan** — tulis langsung atau tempel percakapan WhatsApp. Catatan hanya terlihat oleh
  penulisnya. "Jadikan task" mengirim catatan sebagai task; judul diusulkan dari baris
  pertama tanpa awalan jam dan nama pengirim WhatsApp. Catatan tidak pernah dihapus: diarsipkan
  manual dan dapat dipulihkan.

## Mencatat hasil cek

1. Pilih **Sesuai**, **Ada temuan**, atau **Tidak berlaku**; centang **Dicek langsung** bila
   Anda memeriksanya sendiri di lapangan.
2. **Ada temuan** wajib diberi keterangan dan otomatis membuat satu task tindak lanjut.
   Penerima bawaan adalah fungsi PIC butir itu bila ada pemegangnya di cabang tersebut; bila
   tidak ada, temuan tetap tercatat tanpa penerima dan terlihat di halaman Tim. Mencatat ulang
   butir yang sama tidak menggandakan task.
3. Mengubah hasil yang sudah tercatat wajib diberi alasan dan dicatat di audit sebagai
   koreksi. Isi butir disimpan sebagai snapshot pada saat dicek, jadi menyunting teks butir
   kemudian tidak mengubah riwayat.
4. **Foto temuan** (opsional) dapat dilampirkan saat mencatat; foto ikut terlihat oleh penerima
   task temuan di Hari Ini mereka dan di detail task.
5. Temuan ditutup dari halaman Tim dengan **Tandai selesai** beserta catatan penutupan, atau
   lewat alur konfirmasi task biasa bila penerimanya mengajukan selesai.

## Inbox (dulu Laporan Masuk)

Menu **Inbox** (di bawah Ringkasan) adalah satu pintu untuk semua yang masuk: Komplain, Masukan,
Kerusakan, Laporan staf, dan Masukan staf dari kedua cabang, **Permintaan dan Temuan Owner**, serta
**Catatan Direktur** milik Anda sendiri (hanya Anda yang melihatnya). Terbaru di atas, dengan nama
pelapor. Saring per cabang, jenis, atau kata kunci. Setiap catatan baru juga masuk ke lonceng
notifikasi. Kotak **Inbox** di Ringkasan menunjukkan berapa yang **belum dipilah**. Inbox dibuka
pada tab **Belum dipilah**; item yang sudah ditangani cabang atau sudah Anda pilah ada di tab
**Sudah dipilah** dan **Semua**.

Tab: **Belum dipilah** (bawaan), **Diteruskan, dipantau**, **Sudah dipilah**, **Semua**. Item yang
sudah ditangani di cabang (status bukan Baru), permintaan yang sudah punya task, dan catatan yang
sudah dijadikan task dihitung sudah dipilah.

Tombol **Pilah** membuka halaman satu item dengan lima pilihan, sesuai matriks wewenang:

- **Putuskan dan tugaskan** — bidang Anda (operasional harian, SDM ringan, kas ≤ Rp1 juta): judul,
  PIC, prioritas, target → menjadi task bersumber item itu. Untuk hal yang berlaku di kedua cabang,
  pilih cabang **Semua cabang**: muncul satu pilihan PIC per cabang dan dibuat satu task per cabang
  (pilihan yang sama ada di Task baru, tindak lanjut keputusan, dan Tambah task permintaan Owner) (pelapornya ikut tercatat, judul sumber
  di detail task bisa diketuk). Permintaan Owner yang perlu beberapa langkah: task berikutnya
  ditambah dari halaman permintaan (**Tambah task**).
  **Temuan Owner** ditangani sebagai task besar di halaman detail temuan:
  - Isi form **Task besar** (nama) dan **target**. Pada temuan Mendesak target otomatis terisi 3 hari sejak dicatat
    dan hanya boleh Anda majukan; selain itu paling lambat 30 hari; target yang belum Anda ubah boleh dipertahankan walau sudah lewat.
    Selama belum diisi, batas 30 hari berlaku dan keterlambatan dihitung darinya.
  - **Usulkan target baru** (kotak lipat di halaman detail permintaan/temuan): untuk permintaan, tanggal apa saja
    mulai hari ini yang berbeda dari target sekarang; untuk temuan, hanya bila tanggalnya melewati batas 3/30 hari
    (dalam batas, ubah langsung di form Task besar). Alasan wajib. Owner menyetujui dengan satu tombol atau menolak
    dengan catatan, dan Anda mendapat notifikasi. Usulan baru menggantikan usulan yang masih menunggu; usulan dan
    jawabannya tercatat di Catatan. Tidak bisa diajukan bila permintaan sudah selesai. Task turunan tidak ikut berubah;
    ubah target di task bila perlu.
  - **Tambah sub task**; penerimanya boleh Anda sendiri. Sub task untuk Anda sendiri selesai tanpa
    verifikasi begitu Anda ajukan (tercatat di riwayat). Sub task staf Anda yang memverifikasi
    (Konfirmasi selesai / Minta revisi); Owner tidak ikut memverifikasi.
  - Tombol **Nyatakan selesai & terverifikasi** muncul hanya bila semua sub task selesai, dengan
    konfirmasi, dan Owner mendapat notifikasi. Temuan tidak tertutup otomatis dan tidak bisa dibuka
    kembali; pernyataan itu menjadi tanggung jawab Anda di hadapan Owner (bila hasilnya keliru,
    Owner menulis catatan).
  - Owner otomatis diberi tahu saat Anda membuat task untuk permintaan/temuannya, saat rencana temuan
    diatur atau berubah, dan saat permintaan selesai karena task terakhirnya selesai atau dibatalkan.
- **Teruskan dan pantau** — di luar bidang Anda (apotek/stok/harga obat → Apoteker, Omnicare,
  keuangan di atas batas, medis, strategis/SP → Dirut). Item tetap di tab **Dipantau** sampai
  selesai. Bila tujuannya **Direktur Utama / Owner**, tombol ini membuat perkara **Keputusan**
  berpemutus Owner: latar belakangnya berisi uraian asli, "Rujukan: ...", dan "Catatan Direktur: ...",
  dan semua Owner mendapat notifikasi. Owner memutuskannya dari Dashboard (Setujui, Tolak, atau
  Bahas di rapat Kamis); Anda diberi tahu hasilnya dan dapat membuat task tindak lanjut dari
  halaman Keputusan. Tujuan lain (Apoteker, Keuangan, dan seterusnya) tidak berubah.
- **Bawa ke rapat Kamis** — menjadi perkara di Keputusan (pemutus Rapat bersama) dan tampil di
  Agenda rapat Kamis. Pilih **Berlaku untuk**: cabang asal, cabang lain, atau semua cabang.
- **Jadikan kebijakan** — cukup ditetapkan sebagai aturan, tanpa penugasan. Tulis judul dan isi
  kebijakan (terisi dari item, silakan disunting), pilih **Berlaku untuk** (semua cabang atau satu
  cabang) dan **Berlaku mulai**. Kebijakan tercatat di Keputusan (ditetapkan, pemutus Direktur
  Operasional, tanda Kebijakan), diumumkan lewat notifikasi ke semua orang di cabang itu, dan tampil
  di menu **Kebijakan** semua peran. **Nama pelapor dan uraian asli tidak ikut diumumkan**; yang
  diumumkan hanya judul dan isi yang Anda tulis, jadi pastikan isinya tidak menyebut nama.
- **Tidak ditindaklanjuti** — alasan wajib.

Pada komplain/masukan/kerusakan, pilah juga ditulis di riwayat catatan supaya cabang tahu, dan
statusnya maju dari Baru ke Ditinjau / Dipertimbangkan / Ditriase (ke Ditugaskan bila dijadikan
task dan alurnya mengizinkan). Memilah lagi menggantikan hasil sebelumnya; semuanya tercatat di
audit log. Matriks hanya panduan: sistem tidak memaksa (PP belum disahkan).

Pelapor ikut diberi tahu: perubahan status, catatan, penugasan, dan hasil pilah pada komplain,
masukan, atau kerusakan memberi notifikasi ke pelapornya. Pada **Laporan staf**, pilah ditulis ke
Riwayat laporan dan memajukan Baru ke Ditinjau (kecuali **Tidak ditindaklanjuti**); detail
Laporan punya tombol **Tambah tanggapan**. Pada **Masukan privat**, hanya Direktur Operasional yang
melihat tombol **Tulis tanggapan**. Catatan pilah terlihat oleh pengirim Masukan atau Laporan,
jadi tulislah sebagai balasan kepada pelapor, bukan catatan internal.

**Status maju otomatis.** Bila catatan sudah dijadikan task dan **semua** task aktifnya selesai
(dikonfirmasi, ditutup pemberi tugas; task yang dibatalkan tidak dihitung, tetapi minimal harus ada
satu yang selesai), statusnya maju sendiri sampai target: komplain dan kerusakan ke **Selesai**
(ringkasan penyelesaian terisi dari judul task, penerima, dan catatan pengajuannya bila masih
kosong), masukan ke **Diterapkan**, laporan staf ke **Selesai**. Pada hal yang ditugaskan ke
beberapa cabang, status baru maju setelah task terakhir selesai. Riwayat mencatat "Otomatis: task
hasil pilah selesai." dan pelapor diberi tahu. Status yang sudah melewati target atau sudah
ditutup tidak diubah. **Verifikasi dan penutupan tetap manual**: sistem tidak pernah menutup
catatan sendiri. Ringkasan penyelesaian itu disusun dari catatan pengajuan atau penutupan task dan
nama penerimanya, dan dapat dibaca pelapor; tulislah catatan task dengan bahasa yang pantas dibaca pelapor.

Anda bisa dipilih sebagai **penerima task** (dan penanggung jawab komplain/masukan/kerusakan) di
kedua cabang, walau peran Anda tercatat di Jemur saja; pilihan nama Anda muncul di daftar PIC setiap
cabang, termasuk saat **Semua cabang**.

## Ekspor audit

Menu **Audit**: saring per pengguna, aksi, data (mis. `cashsession`, `nurseactiontally`, nama
pasien atau nomor catatan), dan rentang tanggal, lalu tekan **Unduh CSV**. Berkas berisi persis
yang tersaring, termasuk nilai sebelum dan sesudah setiap perubahan, dan terbuka langsung di Excel.
Unduhan itu sendiri tercatat di audit. Koordinator Shift hanya bisa membaca audit di layar.

## Kas dan tally cabang

- **Verifikasi kas.** Koordinator Shift boleh menutup hari begitu kas akhir diajukan. Sesi yang
  menunggu verifikasi dari kedua cabang tampil di **Kas ▸ Menunggu verifikasi** dan di Hari Ini.
  Verifikasi boleh dilakukan sesudah hari ditutup; sejak itu selisih menjadi tanggung jawab Anda
  sebagai verifikator. Dual-control tetap berlaku: penghitung tidak memverifikasi hitungannya sendiri.
- **Angka diharapkan disusun sistem (6 Okt 2026).** Kas awal = kas akhir terakhir cabang itu; kas akhir =
  kas awal hari itu + tunai masuk − tunai keluar (diisi kasir dari Omnicare). Kasir tidak lagi mengetik
  angka diharapkan, kecuali belum ada kas akhir sebelumnya sama sekali. Dasar angkanya tertulis di
  halaman Review. Untuk kas lama yang diharapkannya 0, halaman Review menampilkan **Pembanding dari
  sistem** (mis. kas akhir kemarin) dan selisih terhadapnya.
- **Selisih karena kekeliruan administratif.** Selisih = Aktual − Diharapkan. Bila kasir tidak mengisi
  **Diharapkan** (cara lama), seluruh uang tampak sebagai selisih. Bila uangnya benar dan yang keliru hanya
  pencatatan, tekan **Setujui: kekeliruan administratif** saat verifikasi (keterangan boleh kosong).
  Kas menjadi *Disetujui dengan catatan*, tanda "Ada selisih" hilang, perkara ditutup; angka selisih tetap
  tersimpan di riwayat dan audit. Kas yang sudah berstatus Selisih dapat ditutup dengan tombol yang
  sama di bagian **Tutup perkara selisih**, tanpa koreksi. Tombol ini hanya untuk Direktur Operasional.
  Memilih hasil **Sesuai** padahal angkanya berbeda ditolak dengan penjelasan.
- **Selisih belum ditutup.** Halaman **Kas** mendaftar semua kas berstatus Selisih dari kedua cabang,
  termasuk dari hari yang sudah lewat. Ketuk untuk membuka Review dan menutup perkaranya.
- **Koreksi tally.** Seperti Koordinator Shift, Anda dapat mengoreksi tally di kedua cabang lewat
  **Giliran Perawat ▸ Koreksi tally per tanggal** (alasan wajib, tercatat di audit).
- **Cabang aktif.** Pilih cabang di kanan atas; pilihan berlaku untuk hari ini.
- **Penugasan staf.** Harian: Pembagian Tugas ▸ klik tanggal ▸ **Siapa bertugas hari ini**,
  ubah status atau kirim perbantuan ke cabang lain. Bulanan: ketuk kotak di **Jadwal Jaga**.
  Porsi tugas dan giliran perawat hari itu menyesuaikan otomatis. Koordinator Shift dapat
  melakukan hal yang sama untuk staf cabangnya.

## Summary harian ke Owner

Di bagian bawah **Checklist Direktur** ada kartu **Summary hari ini untuk Owner** (tautan di atas
halaman langsung menuju ke sana). Summary mencakup semua cabang dan disusun otomatis dari data hari
itu:

1. hasil Checklist Direktur per cabang: berapa butir harian sudah dicek, temuan hari ini, butir
   yang belum dicek, serta kemajuan mingguan dan bulanan;
2. **Catatan Direktur**, satu kotak teks bebas yang Anda tulis sendiri;
3. keputusan yang dicatat atau ditetapkan dan task yang dibuat atau selesai hari itu (task temuan
   tidak diulang karena sudah ada di bagian checklist);
4. status setiap Permintaan Owner yang masih berjalan.

Buka **Pratinjau isi yang disusun otomatis** untuk melihat isinya, tulis catatan, lalu tekan
**Simpan dan kirim summary ke Owner**. Owner mendapat notifikasi di lonceng. Tombol boleh ditekan
lagi di hari yang sama; summary hari itu diperbarui (bukan ditambah), Owner melihat versi terakhir
beserta jamnya dan berapa kali diperbarui, dan notifikasinya tidak menumpuk. Isi yang terkirim adalah
salinan saat tombol ditekan; perubahan data sesudahnya baru masuk bila dikirim ulang. Riwayat per
tanggal ada di menu **Summary Harian**, dengan tombol **Unduh PDF** per tanggal.

Di halaman **Summary Harian** (sama untuk Direktur dan Owner), di bawah summary ada daftar
**Dibaca** per Owner: "Dibaca <nama> <tanggal jam>", "membaca versi sebelumnya" bila summary
dikirim ulang sesudah dibaca, atau "belum membaca". Hanya Owner yang membukanya yang dihitung
membaca. Sesudahnya ada utas **Tanggapan**: Direktur dan Owner dapat menulis, entri tidak dapat
diubah atau dihapus, dan setiap tanggapan memberi notifikasi ke pihak lain. Daftar summary terbaru
menandai "belum dibaca" dan "<n> tanggapan".

## Usulan ke Owner

Pakai menu **Direktur ▸ Usulan ke Owner** (`/owner/usulan/`) untuk hal yang Anda sendiri ingin
sampaikan kepada Owner. Ini berbeda dari **Keputusan**: Keputusan adalah register perkara
(termasuk yang datang dari Inbox atau rapat), sedangkan Usulan dipakai untuk inisiatif Anda ke
Owner. Tekan **+ Usulan baru** dan pilih jenisnya:

- **Minta persetujuan** — isi judul dan uraian; **nominal** (Rupiah) dan **perlu jawaban sebelum**
  (tanggal) boleh dikosongkan, begitu juga cabang (kosong = lintas cabang). Semua Owner mendapat
  notifikasi. Owner menjawab **Setujui**, **Tolak** (wajib beralasan), atau **Bahas di rapat**;
  yang terakhir membuat perkara **Keputusan** untuk rapat Kamis dan usulan Anda menautkannya.
  Jawaban Owner pertama yang berlaku, dan Anda mendapat notifikasi.
- **Laporan masalah/risiko** — tanpa nominal dan tanpa jawaban Setuju/Tolak. Owner menandai
  **sudah dibaca**; Anda melihat "Dibaca Owner pukul …" di halaman usulan.

Di halaman detail ada **Percakapan** dua arah: Anda dan Owner dapat menulis, dan setiap catatan
memberi notifikasi ke pihak lain. Selama usulan belum dijawab (atau laporan belum dibaca) Anda
dapat memakai **Batalkan usulan** dengan alasan; semua Owner diberi tahu. Daftar usulan
menampilkan "Perlu tindakan" (bawaan) atau "Semua".

## Projects

Menu **Projects** (`/projects/`) dipakai untuk pekerjaan yang terdiri dari banyak task kecil yang
diberikan ke perorangan, misalnya renovasi ruang tunggu. Project adalah wadah; setiap task di
dalamnya tetap muncul di **Tugas saya** staf dan di Daftar Task, Kanban, dan Jadwal Task Anda
dengan sumber **Project**.

- **Membuat project.** Tekan **+ Project baru**: isi nama, uraian, target, cabang (kosong =
  lintas cabang), **Project leader** (satu orang), dan **Co-project leader** (boleh lebih dari
  satu, staf pun boleh). Leader dan co-leader mendapat notifikasi. Hanya Owner dan Direktur yang
  dapat membuat project; Anda melihat semua project.
- **Hak per peran.** *Project leader*: menambah, mengubah, dan menugaskan task, membatalkan
  status selesai (revisi), mengubah uraian dan target, serta mengatur co-leader. *Co-project
  leader*: sama, kecuali mengubah uraian dan target serta mengatur co-leader. *Pembuat project, Owner, dan
  Direktur*: semua itu ditambah menunjuk atau mengganti leader, **Tutup project**, dan
  **Batalkan project**. Owner dan Direktur juga dapat menutup atau mengubah satu task project dari
  halaman task Direktur (Daftar Task). Staf yang bukan leader atau co-leader tidak melihat menu Projects dan
  halamannya ditolak (403).
- **Menambah task.** Di halaman project buka **+ Task**: judul, uraian, penerima, target,
  prioritas, dan cabang (penerima harus anggota cabang itu). Pilih mode penyelesaian:
  **Semua harus selesai** (tiap penerima menyelesaikan bagiannya) atau **Cukup satu orang**
  (penerima pertama yang menandai selesai otomatis mengambil task; yang lain tidak perlu).
- **Owner sebagai penerima.** Owner (dr. Yohanes, Jean) juga dapat dipilih sebagai penerima di
  cabang mana pun. Mereka mengerjakannya dari kartu **Tugas saya (project)** di Dashboard Owner:
  **Tandai selesai** dengan bukti, **Percakapan**, atau **Tolak** dengan alasan. Hanya Owner yang
  dapat menolak. Penolakan membatalkan bagian Owner itu; Anda, leader, co-leader, dan pembuat
  project mendapat notifikasi "Task ditolak". Di detail task penerimanya bertanda **Ditolak**
  beserta alasannya, dan di tabel project task yang semua penerimanya menolak bertanda **Semua
  penerima menolak** (task tetap terbuka sampai Anda menugaskan ulang atau membatalkannya).
- **Selesai tanpa konfirmasi.** Staf menandai selesai dengan **bukti wajib** (minimal satu foto
  atau dokumen, catatan opsional). Task langsung dihitung selesai; Anda tidak perlu
  mengonfirmasi, dan leader, co-leader, serta pembuat project mendapat notifikasi.
- **Batalkan selesai (revisi).** Bila bukti kurang tepat, buka detail task dan ketuk
  **Batalkan selesai (revisi)** pada penerimanya dengan catatan wajib. Task kembali ke staf dan
  ia diberi tahu.
- **Progres.** Kartu dan halaman project menampilkan bar progres, mis. "5 dari 8 task · 63%".
  Task yang baru sebagian selesai ikut dihitung sebagian. Galeri **Bukti dari staf** mengumpulkan
  foto dan dokumen dari semua task.
- **Menutup dan membatalkan.** **Tutup project** hanya bila semua task sudah selesai atau
  dibatalkan. **Batalkan project** wajib beralasan dan ikut membatalkan task yang masih terbuka;
  datanya tetap tersimpan, tidak dihapus.

## Ringkasan untuk Owner dan Direktur

Owner cukup tahu apakah ada masalah, keputusan apa yang menggantung, dan kebijakan apa yang
ditetapkan — tanpa sedetail pemeriksaan Direktur. Owner melihat isi Ringkasan yang sama di
**Dashboard Owner**, ditambah Permintaan Owner (lihat [`panduan-owner.md`](panduan-owner.md)). Owner pada dasarnya membaca; tombol aksi hanya
muncul, dan hanya diterima server, untuk Direktur. Pengecualiannya: Owner memutuskan perkara yang
menunggunya (kartu **Menunggu keputusan Anda**, lihat [`panduan-owner.md`](panduan-owner.md)),
menulis Permintaan Owner dan catatannya, serta menulis tanggapan Summary Harian.

| Menu | Isi | Owner | Direktur |
|---|---|---|---|
| **Ringkasan** | Halaman utama yang sengaja ringkas: **Agenda rapat Kamis** (perkara keputusan bersama dan task yang tertahan), empat kotak kuadran prioritas (gabungan kedua cabang), empat kotak angka (keputusan menggantung, kebijakan baru, menunggu konfirmasi, jadwal task), lalu infografik per cabang. Setiap kotak dapat diketuk untuk membuka detailnya | baca | baca |
| **Prioritas** | Matriks Eisenhower seluruh task yang belum selesai, dengan penyaring cabang dan sumber; dari Ringkasan terbuka satu kuadran saja | baca | baca |
| **Jadwal Task** | Gantt: setiap bar dari task dibuat sampai targetnya, 7 hari ke belakang s.d. 21 hari ke depan. Task lewat target berwarna merah dan memanjang sampai hari ini; task tanpa target bergaris. **Permintaan Owner** tampil paling atas: satu baris per permintaan (dari diminta sampai target Owner, garis putus-putus oranye = target) dengan task turunannya di bawahnya (↳), atau "belum dipecah menjadi task"; task lain per cabang | baca | baca |
| **Daftar Task** | Semua task dalam satu tabel: cari, saring (status, cabang, PIC, prioritas, sumber, tanggal dibuat), urutkan dengan mengetuk judul kolom, unduh CSV | baca + unduh | baca + unduh |
| **Kanban** | Baru · Dikerjakan · Menunggu konfirmasi · Selesai 7 hari | baca | baca |
| **Keputusan** | Register perkara: menunggu, ditetapkan, kebijakan berlaku, dibatalkan | baca; putuskan perkara berpemutus Owner | catat, tetapkan, batalkan. Perkara berpemutus Owner tetap boleh Anda catat bila keputusannya diambil di luar aplikasi (mis. lewat WhatsApp), selama belum ada Owner yang memutuskannya di aplikasi; begitu Owner memutuskan, Anda tidak dapat mengubah atau membatalkannya |
| **Tim** | Detail per orang dan per checklist | baca | baca + tutup temuan |

Warna kartu cabang (di bagian **Per cabang**, diketuk membuka halaman Tim pada cabang itu):

- **Merah** — ada task lewat target, temuan tanpa penerima, atau keputusan lewat tenggat.
- **Kuning** — ada temuan terbuka, task menunggu konfirmasi, keputusan menggantung, atau butir
  checklist staf belum diisi setelah klinik buka.
- **Hijau** — tidak ada di atas.

Matriks prioritas: *penting* = prioritas Tinggi/Kritis; *mendesak* = target ≤ ambang jam atau
prioritas Kritis. Ambang bawaan 48 jam, dapat diubah per cabang lewat Konfigurasi
(`dashboard.urgent_hours`). Karena task baru bawaannya prioritas Sedang, isilah prioritas saat
membuat task agar matriks bermakna.

Kolom kanban dibaca dari status penerima task, bukan dari status task utama; perpindahan kolom
tetap lewat alur ajukan selesai → konfirmasi supaya jejak audit utuh. Kanban hanya membaca.

**Detail task** (`/direktur/task/<id>/`, ditambahkan 1 Okt 2026). Judul task di Jadwal Task,
Kanban, Prioritas, Tim, dan daftar "menunggu konfirmasi" di Hari Ini bisa diklik. Halaman ini
memuat uraian, penerima dengan statusnya, dan riwayat. Direktur (atau pembuat task) dapat:

- **Konfirmasi selesai** / **Minta revisi** bila penerima sudah mengajukan selesai;
- **Ubah task**: status Baru/Dikerjakan, prioritas, target, catatan progres;
- **Tandai selesai** tanpa menunggu penerima (catatan wajib; penerima yang masih terbuka
  ikut dikonfirmasi atas nama Direktur sehingga task hilang dari daftar kerja mereka);
- **Batalkan task** atau **keluarkan** satu penerima (alasan wajib);
- **Tambah catatan** ke riwayat.

Semua perubahan tercatat di riwayat task dan audit log. Owner membuka halaman yang sama tanpa
tombol.

**Pemeriksa dan verifikasi Dirut (tahap 2 paket C).** Setiap task menampilkan **Pemeriksa**.
Bawaannya Direktur Operasional. Bila salah satu penerima task adalah Direktur Operasional sendiri,
pemeriksanya otomatis **Direktur Utama / Owner** (akun Owner, mis. jean dan yohanes): hanya mereka
yang dapat Konfirmasi selesai / Minta revisi, notifikasi "Menunggu verifikasi" dikirim ke mereka,
dan tombol **Tandai selesai** tidak tersedia (kecuali sub task temuan Owner: pemeriksanya tetap Direktur, sub task staf Anda verifikasi, sub task Anda sendiri selesai tanpa verifikasi, dan **Tandai selesai** tersedia; lihat Pilah ▸ Putuskan dan tugaskan). Direktur juga dapat memilih pemeriksa Dirut untuk
task lain lewat **Ubah task**. Owner dapat menulis catatan di task yang ia periksa, tetapi tidak
dapat mengubah atau menutupnya.

Penerima melaporkan kemajuan lewat **Lapor progres** (tampil di riwayat sebagai *Laporan progres*,
dengan foto bila ada) dan wajib menulis **catatan bukti** saat Ajukan selesai. Penerima mendapat
notifikasi saat dikonfirmasi atau diminta revisi; pemeriksa mendapat notifikasi saat diajukan.

**Arus balik dari staf.** Laporan progres, balasan percakapan, dan **Ada kendala** dari penerima
memberi notifikasi (*Progres*, *Balasan*, *Kendala*) ke pemberi tugas dan semua Direktur
Operasional aktif. Task yang dilapori kendala menampilkan kotak kuning **Terhambat** di detail
task, berisi alasan dan usulan target; tombol **Setujui target dd/mm/yyyy** (hanya pemberi tugas
atau Direktur) memindahkan target ke tanggal itu, menghapus label, dan memberi notifikasi ke
penerima. **Simpan catatan** di detail task kini juga memberi notifikasi ke penerima task yang
masih aktif; penerima membacanya di **Percakapan (n)** pada kartu Tugas saya. Label **Terhambat**
tampil di Daftar Task dan halaman Tim, dan Ringkasan menunjukkan **n task terhambat**.

**Keputusan.** Direktur mencatat perkara yang perlu diputuskan (siapa pemutusnya, tenggatnya),
lalu menetapkannya setelah diputuskan — oleh Owner, Direktur Utama, atau Direktur sendiri.
Perkara berpemutus Owner atau Direktur Utama yang Anda catat di sini memberi notifikasi ke semua
Owner, dan Owner memutuskannya sendiri dari Dashboard (keputusan pertama yang berlaku, tertulis
"Disetujui <nama>: <catatan>" atau "Ditolak <nama>: <catatan>"); Anda diberi tahu hasilnya.
Halaman perkara itu dapat Anda baca, tetapi tidak dapat Anda putuskan atas nama Owner.
Centang *Kebijakan berlaku* bila keputusan itu menjadi aturan bagi staf. Perkara tidak dihapus;
yang tidak jadi diputuskan dibatalkan dengan alasan.

**Keputusan bersama dan rapat Kamis (K-015, ditambahkan Oktober 2026).** Pilih pemutus
*Rapat bersama (Kamis)* untuk perkara yang dibahas di rapat mingguan (Owner juga dapat memindahkan
perkaranya ke sini lewat **Bahas di rapat Kamis**). Perkara ini tampil di
bagian **Agenda rapat Kamis** paling atas Ringkasan Direktur dan Dashboard Owner, bersama task
yang tertahan karenanya; perkara dengan pemutus lain (Owner, Dirut, …) dilipat di bawahnya.

- Di detail task, bagian **Keputusan** → *Tahan task ini sampai ada keputusan*: pilih perkara
  yang sudah tercatat, atau tulis perkara baru (**Bawa ke rapat dan tahan task**). Selama
  ditahan, task bertanda *Menunggu keputusan* dan tenggatnya **tidak dihitung lewat target**
  (tidak membuat kartu cabang merah). Tombol **Lepas** mengakhiri penahanan.
- Saat keputusan ditetapkan atau dibatalkan, task yang menunggu aktif kembali (tenggat lama
  berlaku lagi — ubah targetnya bila perlu), riwayat task mendapat catatan isi keputusan, dan
  penerimanya mendapat notifikasi satu kali.
- Keputusan yang sudah ditetapkan punya tombol **Buat task tindak lanjut**; task itu bersumber
  "Keputusan" dan tercantum di halaman keputusan.

**Bahan rapat (tahap 2 paket D).** Menu **Bahan Rapat** (juga tautan "Bahan rapat →" di Agenda
rapat Kamis) menyusun otomatis bahan rapat Kamis untuk periode Kamis lalu s.d. Rabu: agenda
keputusan bersama dan perkara yang menunggu pemutus lain, keputusan yang ditetapkan dalam periode,
permintaan dan temuan Owner yang baru atau masih berjalan, task selesai dan terverifikasi, task
lewat target, yang menunggu verifikasi, serta Inbox yang masuk per cabang. Panah di atas
berpindah ke rapat minggu sebelum/sesudahnya. **Cetak** mencetak halaman tanpa menu; **Salin untuk
WhatsApp** menyalin ringkasan teks untuk ditempel di grup. Halaman ini hanya membaca.

**Jejak kehadiran (tahap 3 paket E).** Menu **Jejak** mencatat setiap login, buka/tutup hari,
isi checklist, hitung/ajukan kas, lapor progres, dan ajukan selesai: IP, jenis jaringan, perangkat,
dan lokasi sesaat bila staf mengizinkan (browser menanyakan izin sekali; lokasi hanya diambil saat
tombol ditekan, tidak dilacak). Setiap jejak berlabel **Kuat** (perangkat klinik terdaftar, atau
lokasi di dalam radius cabang), **Sedang** (lokasi dekat tetapi kurang akurat, atau IP yang lazim di
cabang itu), atau **Lemah**. Tidak ada yang diblokir; targetnya pola yang benar lebih dari 60%.
Ringkasan per staf menampilkan persentase Kuat + Sedang. **Unduh CSV** mengunduh jejak sesuai
saringan (tercatat sebagai ekspor di Audit). Siapkan dua hal:

- **Koordinat cabang** di Pengaturan Klinik. Sudah terisi otomatis saat deploy dari titik Google
  Maps (Jemur −7.328501, 112.739425; Citraland −7.286665, 112.655565); ubah di sana bila perlu
  (tombol *Isi dari lokasi saya sekarang* saat berada di dalam klinik). Radius bawaan 150 m.
- **Perangkat klinik** di Jejak → *Perangkat & IP lazim*: IP Tailscale 100.x perangkat milik klinik
  (daftar IP Tailscale yang pernah tercatat tampil di sana). HP staf tidak perlu Tailscale.

**Banner saran.** Di atas layar staf, Direktur, dan PIC tampil satu kotak saran yang tidak memaksa:
ajakan mengganti password awal (bila akun masih memakainya), atau ajakan mengizinkan lokasi (bila
browser belum diizinkan; tidak tampil di perangkat klinik terdaftar dan tidak untuk Owner).
**Nanti** menyembunyikannya 7 hari. Tidak ada pekerjaan yang diblokir.

**KPI per staf (tahap 3 paket F).** Menu **KPI** menampilkan angka per staf per bulan, satu kolom per
metrik, tanpa skor gabungan dan tanpa peringkat (keputusan uji coba 3 Okt; skor gabungan dipertimbangkan
sesudah 1–2 bulan data). Hanya Direktur Operasional dan Owner yang melihat.

- **Kelengkapan porsi**: butir checklist dari porsi yang ditugaskan kepadanya di Pembagian Tugas, berapa
  yang terisi; "diisi orang lain" bila yang mengisi bukan orang yang ditugaskan di porsi itu. Hari ini
  baru dihitung setelah hari ditutup.
- **Pembukaan tepat waktu**: butir sesi Pembukaan yang ia isi sendiri, selesai sebelum jam buka cabang
  (Pengaturan Klinik) + toleransi 15 menit.
- **Jejak di klinik**: persentase jejak Kuat + Sedang.
- **Task tepat target**: task bertarget bulan itu yang sudah lewat, diajukan selesai (pengajuan pertama)
  sebelum target; juga jumlah terlambat, belum diajukan, dan diminta revisi.
- **Centang massal**: tanda bila ≥5 butir dicentang dalam 60 detik. Hanya untuk dicek, bukan pengurang.

Ketuk nama staf untuk rincian per hari (porsi, siapa yang mengambil alih, jam butir pembukaan terakhir
dan batasnya, jejak, centang massal) dan daftar task-nya. **Unduh CSV** tercatat sebagai ekspor di Audit.
Toleransi dan ambang centang massal diubah per cabang di **Konfigurasi** (`kpi.open_tolerance_minutes`,
`kpi.bulk_items`, `kpi.bulk_seconds`). Pastikan jam buka tiap cabang di Pengaturan Klinik benar, karena
itulah dasar "tepat waktu".

**Pelapor.** Kartu task (Kanban, Prioritas), detail task, dan Daftar Task menampilkan pelapor
asal: staf yang mengisi butir checklist, pemeriksa temuan Direktur, Owner untuk permintaan
Owner, penulis catatan; selain itu pembuat task.
