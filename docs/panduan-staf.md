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
  atas. Selama dikerjakan, tekan **Lapor progres** untuk mencatat kemajuan (teks wajib, foto
  opsional); progres terakhir tampil di bawah judul task dan di riwayat task. Bila sudah selesai,
  tekan **Ajukan selesai**, tulis **catatan bukti** (wajib: apa yang sudah dikerjakan) dan
  lampirkan **foto bukti** bila ada (opsional), lalu **Kirim**; task tetap tampil dengan tanda
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
