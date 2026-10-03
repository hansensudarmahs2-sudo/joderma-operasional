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
notifikasi. Kotak **Inbox** di Ringkasan menunjukkan berapa yang **belum dipilah**.

Tab: **Belum dipilah** (bawaan), **Diteruskan, dipantau**, **Sudah dipilah**, **Semua**. Item yang
sudah ditangani di cabang (status bukan Baru), permintaan yang sudah punya task, dan catatan yang
sudah dijadikan task dihitung sudah dipilah.

Tombol **Pilah** membuka halaman satu item dengan empat pilihan, sesuai matriks wewenang:

- **Putuskan dan tugaskan** — bidang Anda (operasional harian, SDM ringan, kas ≤ Rp1 juta): judul,
  PIC, prioritas, target → menjadi task bersumber item itu. Untuk hal yang berlaku di kedua cabang,
  pilih cabang **Semua cabang**: muncul satu pilihan PIC per cabang dan dibuat satu task per cabang
  (pilihan yang sama ada di Task baru, tindak lanjut keputusan, dan Tambah task permintaan Owner) (pelapornya ikut tercatat, judul sumber
  di detail task bisa diketuk). Permintaan/temuan Owner yang perlu beberapa langkah: task berikutnya
  ditambah dari halaman permintaan (**Tambah task**).
- **Teruskan dan pantau** — di luar bidang Anda (apotek/stok/harga obat → Apoteker, Omnicare,
  keuangan di atas batas, medis, strategis/SP → Dirut). Item tetap di tab **Dipantau** sampai
  selesai.
- **Bawa ke rapat Kamis** — menjadi perkara di Keputusan (pemutus Rapat bersama) dan tampil di
  Agenda rapat Kamis. Pilih **Berlaku untuk**: cabang asal, cabang lain, atau semua cabang.
- **Tidak ditindaklanjuti** — alasan wajib.

Pada komplain/masukan/kerusakan, pilah juga ditulis di riwayat catatan supaya cabang tahu, dan
statusnya maju dari Baru ke Ditinjau / Dipertimbangkan / Ditriase (ke Ditugaskan bila dijadikan
task dan alurnya mengizinkan). Memilah lagi menggantikan hasil sebelumnya; semuanya tercatat di
audit log. Matriks hanya panduan: sistem tidak memaksa (PP belum disahkan).

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
tanggal ada di menu **Summary Harian**.

## Ringkasan untuk Owner dan Direktur

Owner cukup tahu apakah ada masalah, keputusan apa yang menggantung, dan kebijakan apa yang
ditetapkan — tanpa sedetail pemeriksaan Direktur. Owner melihat isi Ringkasan yang sama di
**Dashboard Owner**, ditambah Permintaan Owner (lihat [`panduan-owner.md`](panduan-owner.md)). Owner hanya membaca; semua tombol aksi hanya
muncul, dan hanya diterima server, untuk Direktur.

| Menu | Isi | Owner | Direktur |
|---|---|---|---|
| **Ringkasan** | Halaman utama yang sengaja ringkas: **Agenda rapat Kamis** (perkara keputusan bersama dan task yang tertahan), empat kotak kuadran prioritas (gabungan kedua cabang), empat kotak angka (keputusan menggantung, kebijakan baru, menunggu konfirmasi, jadwal task), lalu infografik per cabang. Setiap kotak dapat diketuk untuk membuka detailnya | baca | baca |
| **Prioritas** | Matriks Eisenhower seluruh task yang belum selesai, dengan penyaring cabang dan sumber; dari Ringkasan terbuka satu kuadran saja | baca | baca |
| **Jadwal Task** | Gantt: setiap bar dari task dibuat sampai targetnya, 7 hari ke belakang s.d. 21 hari ke depan. Task lewat target berwarna merah dan memanjang sampai hari ini; task tanpa target bergaris | baca | baca |
| **Daftar Task** | Semua task dalam satu tabel: cari, saring (status, cabang, PIC, prioritas, sumber, tanggal dibuat), urutkan dengan mengetuk judul kolom, unduh CSV | baca + unduh | baca + unduh |
| **Kanban** | Baru · Dikerjakan · Menunggu konfirmasi · Selesai 7 hari | baca | baca |
| **Keputusan** | Register perkara: menunggu, ditetapkan, kebijakan berlaku, dibatalkan | baca | catat, tetapkan, batalkan |
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
dan tombol **Tandai selesai** tidak tersedia. Direktur juga dapat memilih pemeriksa Dirut untuk
task lain lewat **Ubah task**. Owner dapat menulis catatan di task yang ia periksa, tetapi tidak
dapat mengubah atau menutupnya.

Penerima melaporkan kemajuan lewat **Lapor progres** (tampil di riwayat sebagai *Laporan progres*,
dengan foto bila ada) dan wajib menulis **catatan bukti** saat Ajukan selesai. Penerima mendapat
notifikasi saat dikonfirmasi atau diminta revisi; pemeriksa mendapat notifikasi saat diajukan.

**Keputusan.** Direktur mencatat perkara yang perlu diputuskan (siapa pemutusnya, tenggatnya),
lalu menetapkannya setelah diputuskan — oleh Owner, Direktur Utama, atau Direktur sendiri.
Centang *Kebijakan berlaku* bila keputusan itu menjadi aturan bagi staf. Perkara tidak dihapus;
yang tidak jadi diputuskan dibatalkan dengan alasan.

**Keputusan bersama dan rapat Kamis (K-015, ditambahkan Oktober 2026).** Pilih pemutus
*Rapat bersama (Kamis)* untuk perkara yang dibahas di rapat mingguan. Perkara ini tampil di
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
Ringkasan per staf menampilkan persentase Kuat + Sedang. Siapkan dua hal:

- **Koordinat cabang** di Pengaturan Klinik. Sudah terisi otomatis saat deploy dari titik Google
  Maps (Jemur −7.328501, 112.739425; Citraland −7.286665, 112.655565); ubah di sana bila perlu
  (tombol *Isi dari lokasi saya sekarang* saat berada di dalam klinik). Radius bawaan 150 m.
- **Perangkat klinik** di Jejak → *Perangkat & IP lazim*: IP Tailscale 100.x perangkat milik klinik
  (daftar IP Tailscale yang pernah tercatat tampil di sana). HP staf tidak perlu Tailscale.

**Pelapor.** Kartu task (Kanban, Prioritas), detail task, dan Daftar Task menampilkan pelapor
asal: staf yang mengisi butir checklist, pemeriksa temuan Direktur, Owner untuk permintaan
Owner, penulis catatan; selain itu pembuat task.
