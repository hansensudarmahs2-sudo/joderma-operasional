# Panduan Singkat Staf — JoDerma Staff Ops

Supervisor: lihat juga [`panduan-supervisor.md`](panduan-supervisor.md).
Admin: lihat [`panduan-admin.md`](panduan-admin.md).

Aplikasi diakses dari ponsel, tablet, atau komputer klinik melalui alamat yang
diberikan admin. Anda harus terhubung Tailscale dan memakai akun pribadi.
**Akun tidak boleh dipakai bersama** — semua tindakan tercatat atas nama Anda.

## Menu Anda

Sesudah login Anda langsung masuk ke **Tugas hari ini**. Menu staf sengaja pendek:

| Menu | Isi |
|---|---|
| **Tugas hari ini** | Butir checklist **porsi Anda** hari ini (dari Pembagian Tugas) dengan tombol ke halaman pengisiannya, task yang dikirim kepada Anda, jadwal istirahat hari ini, dan kotak **Kas** bila Anda kasir hari ini. Bila sesi hari belum dibuat, tekan **Buat sesi hari ini** |
| **Jadwal saya** | Jadwal jaga dan porsi tugas Anda sebulan. Perubahan diajukan ke Koordinator Shift |
| **Istirahat saya** | Jadwal istirahat Anda hari ini dan 7 hari ke depan |
| **Tindakan saya** | Untuk perawat: giliran Anda (berikutnya atau urutan ke berapa), tally hari ini dan total bulan ini, tombol **Saya istirahat / Saya tersedia lagi**, tindakan yang ditugaskan, dan **Catat tally saya** |
| **Kas** | Hanya muncul pada hari Anda ditugaskan sebagai kasir. Bila jadwal kasir berubah mendadak, minta Koordinator Shift mengganti pelaksana porsi "Kasir hari ini" |
| **Kebijakan** | Aturan yang sudah ditetapkan Direktur Operasional dan berlaku di cabang Anda. Kebijakan baru juga datang lewat notifikasi (lonceng); yang ditetapkan 7 hari terakhir ditandai **Baru** |
| **Lapor** | Komplain, Masukan, Kerusakan, Laporan Saya, Masukan Saya |

Halaman **Hari Ini** (buka/tutup hari) dan **semua checklist** tetap bisa dibuka dari tautan di bawah
kotak checklist pada Tugas hari ini.

## Pagi: membuka klinik

1. Buka **Tugas hari ini** → tekan **Buat sesi hari ini** bila belum ada.
2. Tekan tombol porsi Anda (mis. *Pembukaan · Akses umum 0/3*) dan isi butirnya.
3. Untuk tiap item pilih hasil: OK, Tidak lengkap, Rusak, atau Tidak berlaku.
   - Butir yang beres: tekan **Check**.
   - Butir bermasalah: buka **Ada masalah?** di bawah butir itu, pilih hasilnya, tulis
     masalahnya (**wajib**), dan bila perlu lampirkan **foto** (opsional, dikecilkan otomatis).
     Jangan memotret wajah atau data pasien.
   - Item bertipe jumlah: isi jumlah aktual yang Anda hitung.
   - Item **Rusak** → tekan *Buat laporan kerusakan* (foto butir ikut terbawa).
   - Item **Tidak lengkap** → tekan *Buat tindak lanjut kekurangan*.
4. Front desk mencatat **Kas awal**: (1) isi jumlah lembar per pecahan; (2) angka **yang seharusnya
   ada** diisi sistem dari kas akhir terakhir cabang ini; (3) kotak **Selisih** langsung berubah: hijau
   bila sesuai, kuning bila uang lebih/kurang. Bila kuning, hitung ulang; bila tetap, tulis penjelasan
   di catatan. Lalu tekan **Simpan dan ajukan verifikasi**.
5. Orang kedua (rekan front desk atau supervisor) membuka **Review kas** dan
   menyimpan verifikasi. Anda tidak dapat memverifikasi hitungan Anda sendiri.
6. Supervisor membuka **Review pembukaan** lalu konfirmasi, atau *Terima dengan
   pengecualian* disertai alasan.
7. Di **Hari Ini**, jalankan aksi **Tandai siap** lalu **Buka klinik**.

## Cabang yang tampil

Cabang aktif tampil di kanan atas. Akun yang bekerja di dua cabang bisa menggantinya dari
pilihan di sana; pilihan itu berlaku untuk hari ini saja. Tanpa memilih, sistem memakai
cabang tugas di jadwal jaga hari ini, atau cabang asal bila Anda sedang off.

## Sepanjang hari

- **Izin lokasi:** saat login, buka/tutup hari, mengisi checklist, kas, lapor progres, atau ajukan
  selesai, browser dapat menanyakan izin lokasi. Lokasi hanya diambil sesaat ketika tombol ditekan
  (tidak dilacak terus) untuk mencatat bahwa pekerjaan dilakukan di klinik. Bila ditolak, pekerjaan
  tetap tersimpan. Selama izin belum diberikan, kotak saran di atas layar menawarkan tombol
  **Izinkan**; bila izin pernah ditolak, kotak itu menunjukkan cara membukanya kembali (iPhone:
  Pengaturan → Safari → Lokasi; Android Chrome: ikon di samping alamat situs → Izin → Lokasi).
  **Nanti** menyembunyikan kotak itu selama 7 hari. Tidak wajib.
- **Password awal**: bila akun masih memakai password awal, kotak saran di atas layar mengajak
  menggantinya (**Ganti sekarang**). Ganti agar tidak ada orang lain yang bisa masuk atas nama Anda.
- **Tugas saya** (paling atas di **Hari Ini**): task yang dikirim Direktur atau PIC kepada Anda,
  dari cabang mana pun, termasuk task yang dikirim ke beberapa orang atau ke satu peran. Tampil
  walau sesi hari operasional belum dibuat. Yang lewat target bertanda merah dan berada paling
  atas. Selama dikerjakan, tekan **Lapor progres** untuk mencatat kemajuan (teks wajib, foto,
  PDF, atau DOCX opsional; dokumen maks. 10 MB); progres terakhir tampil di bawah judul task dan di riwayat task, dan laporan itu
  langsung sampai ke pemberi tugas dan Direktur Operasional (notifikasi). Tekan **Percakapan (n)**
  untuk membaca catatan Direktur pada task itu dan membalasnya. Bila ada yang menghalangi, tekan
  **Ada kendala**, tulis alasannya (wajib) dan, bila perlu, usulan target baru (opsional); task
  diberi label kuning **Terhambat** dan pemberi tugas serta Direktur diberi tahu. Label hilang
  sendiri saat Anda **Lapor progres**, saat usulan target disetujui, atau saat task selesai atau
  dibatalkan. Bila sudah selesai,
  tekan **Ajukan selesai**, tulis **catatan bukti** (wajib: apa yang sudah dikerjakan) dan
  lampirkan **foto, PDF, atau DOCX** bukti bila ada (opsional, dokumen maks. 10 MB), lalu **Kirim**; task tetap tampil dengan tanda
  **Menunggu konfirmasi** sampai pemeriksa mengonfirmasi atau meminta revisi (Anda mendapat
  notifikasi keduanya). Task bersama harus **Ambil task** dulu. Daftar lengkap ada di **Semua
  task saya**.
- **Antrean**: tambah pasien, ubah status (check-in → menunggu → dipanggil →
  dilayani → selesai). Pembatalan dan no-show wajib alasan. Ubah status pembayaran
  saat pasien membayar — nomor antrean dipertahankan bila **Sudah bayar** atau
  **Dibebaskan**.
- **Giliran perawat**: supervisor menyusun roster pagi. Saat tindakan berkomisi
  ditugaskan dan diselesaikan, perawat otomatis pindah ke belakang antrean giliran.
  Memilih perawat di luar giliran hanya boleh supervisor dan wajib alasan.
- **Jadwal istirahat**: supervisor mengatur. Sistem menolak jadwal yang bertabrakan
  dan memperingatkan bila staf aktif turun di bawah minimum.
- **Komplain / Masukan / Kerusakan**: siapa pun boleh membuat. Buka menu yang
  sesuai, lalu tekan tombol hijau di bagian atas halaman:

  | Menu | Tombol | Isi minimal |
  |---|---|---|
  | Komplain | **+ Catat komplain baru** | ringkasan, uraian, sumber pelapor |
  | Masukan | **+ Tulis masukan/saran** | ringkasan, uraian |
  | Kerusakan | **+ Laporkan kerusakan** | ringkasan, lokasi/aset, dampak |

  Form hanya menampilkan field yang relevan dengan tipe yang dipilih, jadi
  daftarnya pendek. Field bertanda `*` wajib diisi. **Foto** (opsional) bisa langsung
  dilampirkan, misalnya kerusakan alat. Komplain sensitif dapat
  ditandai **Terbatas** — hanya pembuat, penanggung jawab, supervisor, dan owner
  yang bisa membukanya.

  Status catatan dan laporan diubah oleh supervisor, PIC, atau Direktur Operasional.
  Bila sebuah catatan **ditugaskan kepada Anda**, Anda sendiri yang mengubah statusnya
  (mis. Dalam proses, lalu Selesai beserta ringkasannya); catatan lain cukup Anda lihat.

  **Tanggapan atas laporan Anda.** Setiap kali laporan Anda ditanggapi (status berubah, ada
  catatan atau tanggapan baru, penanggung jawab ditunjuk, ditandai duplikat, atau dipilah
  Direktur), Anda mendapat notifikasi di lonceng. Isinya bisa dibaca di **Laporan Saya**
  (tampil sebagai **Riwayat**) dan **Masukan Saya** (tampil sebagai **Tanggapan**, termasuk hasil
  pilah, publikasi, arsip, dan tanggapan Direktur). Untuk catatan anonim atau terbatas dan
  Laporan Rahasia, notifikasi hanya berbunyi "Ada tanggapan pada catatan Anda" tanpa isi;
  buka halamannya untuk membaca.

  Bila laporan Anda dijadikan task oleh Direktur dan semua task-nya sudah selesai, status laporan
  Anda berubah sendiri menjadi **Selesai** (atau **Diterapkan** untuk masukan) dan Anda mendapat
  notifikasi; penutupan akhir tetap oleh pengelola.

## Bintang untuk task yang selesai

Saat pemberi tugas atau Direktur mengonfirmasi task Anda, ia memberi **bintang 1–5**. Bintang 1–3
selalu disertai alasan. Anda mendapat notifikasi **Task dinilai: ★★★★☆ …** beserta alasannya.
Bintang Anda tampil di kartu **Nilai saya** di halaman **Tugas hari ini**: 10 task terakhir yang
dinilai dan rata-rata bulan ini. Hanya Anda, Direktur Operasional, dan Owner yang melihat bintang
Anda; Anda tidak melihat bintang orang lain. Task yang selesai sebelum fitur ini ada otomatis
bintang 5. Task project baru dinilai sesudah Anda menandainya selesai, oleh Project leader atau
pengatur project; bila dikembalikan untuk revisi, bintangnya gugur dan dinilai lagi.

## Task project

Task yang berasal dari sebuah project muncul di **Tugas saya** dengan tag **Project: nama
project**. Tidak ada tahap konfirmasi: ketuk **Tandai selesai**, **lampirkan bukti (wajib)**
berupa minimal satu foto atau dokumen (catatan boleh dikosongkan), lalu kirim. Tanpa berkas,
sistem menolak dan task tetap terbuka. Pada task **Cukup satu orang**, siapa pun penerimanya
boleh langsung menandai selesai; task otomatis menjadi miliknya. Bila pengatur project
membatalkan status selesai, task kembali ke Anda dengan **Catatan revisi** dan tag **Perlu
revisi**; perbaiki lalu tandai selesai lagi. Selama Anda menerima task di project yang masih
berjalan, menu **Projects** muncul di menu Anda: Anda dapat melihat seluruh project (progres,
semua task, dan bukti), task Anda bertanda **Task saya**, dan Anda dapat membalas di task milik
Anda. Menandai selesai tetap dari **Tugas hari ini**. Bila Anda Project leader atau Co-project
leader, dari menu yang sama Anda juga mengatur task project itu.

## Sore: menutup hari

1. Front desk mencatat **Kas akhir**: hitung lembar per pecahan, lalu isi **Tunai masuk hari ini**
   (penjualan/pembayaran tunai dari Omnicare) dan **Tunai keluar dari laci** (setoran, belanja kecil).
   Yang seharusnya ada = kas awal hari ini + tunai masuk − tunai keluar, dihitung sistem. Periksa kotak
   Selisih, lalu **Simpan dan ajukan verifikasi**.
2. Koordinator Shift: di **Hari Ini** pilih **Tutup hari**. Cukup kas akhir sudah
   **diajukan**; verifikasi oleh Direktur Operasional boleh menyusul, juga sesudah hari
   ditutup. Bila kas akhir belum diajukan atau ada catatan kritis belum ditriase, penutupan
   hanya dapat dilakukan dengan alasan.
3. Tidak ada batas jam penutupan. Bila menunggu pasien terakhir sampai lewat tengah malam, tetap
   tutup seperti biasa: sampai pukul 06.00, aplikasi masih menampilkan hari kemarin yang belum
   ditutup (checklist penutupan, kas akhir, tally, Tutup hari). Jangan menekan *Buat sesi hari ini*
   untuk menutup hari kemarin.
4. Hari tertutup bersifat read-only. Koreksi hanya lewat *Buka kembali* oleh
   supervisor disertai alasan.

## Yang tidak boleh dicatat di sistem ini

Diagnosis, hasil pemeriksaan, foto klinis, catatan medis, nomor kartu/rekening.
Aplikasi ini untuk operasional, bukan rekam medis.

## Bila sistem tidak dapat diakses

Gunakan formulir kertas darurat, lalu masukkan datanya setelah sistem kembali dan
tulis di catatan bahwa entri dibuat susulan. Laporkan gangguannya ke admin teknis.
