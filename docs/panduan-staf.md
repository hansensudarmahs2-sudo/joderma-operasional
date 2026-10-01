# Panduan Singkat Staf — JoDerma Staff Ops

Supervisor: lihat juga [`panduan-supervisor.md`](panduan-supervisor.md).
Admin: lihat [`panduan-admin.md`](panduan-admin.md).

Aplikasi diakses dari ponsel, tablet, atau komputer klinik melalui alamat yang
diberikan admin. Anda harus terhubung Tailscale dan memakai akun pribadi.
**Akun tidak boleh dipakai bersama** — semua tindakan tercatat atas nama Anda.

## Pagi: membuka klinik

1. Buka **Hari Ini** → tekan **Buat sesi hari ini** bila belum ada.
2. Masuk **Pembukaan**, isi setiap area (akses umum, komputer, ruang konsultasi,
   ruang tindakan).
3. Untuk tiap item pilih hasil: OK, Tidak lengkap, Rusak, atau Tidak berlaku.
   - Bila bukan OK, **catatan wajib diisi**.
   - Item bertipe jumlah: isi jumlah aktual yang Anda hitung.
   - Item **Rusak** → tekan *Buat laporan kerusakan*.
   - Item **Tidak lengkap** → tekan *Buat tindak lanjut kekurangan*.
4. Front desk mencatat **Kas awal**: isi jumlah lembar per pecahan (total dihitung
   otomatis), isi uang modal yang diharapkan, lalu **Ajukan verifikasi**.
5. Orang kedua (rekan front desk atau supervisor) membuka **Review kas** dan
   menyimpan verifikasi. Anda tidak dapat memverifikasi hitungan Anda sendiri.
6. Supervisor membuka **Review pembukaan** lalu konfirmasi, atau *Terima dengan
   pengecualian* disertai alasan.
7. Di **Hari Ini**, jalankan aksi **Tandai siap** lalu **Buka klinik**.

## Sepanjang hari

- **Tugas saya** (paling atas di **Hari Ini**): task yang dikirim Direktur atau PIC kepada Anda,
  dari cabang mana pun, termasuk task yang dikirim ke beberapa orang atau ke satu peran. Tampil
  walau sesi hari operasional belum dibuat. Yang lewat target bertanda merah dan berada paling
  atas. Bila sudah dikerjakan, tekan **Ajukan selesai**; task tetap tampil dengan tanda
  **Menunggu konfirmasi** sampai pemberi task mengonfirmasi. Task bersama harus **Ambil task**
  dulu. Daftar lengkap ada di **Semua task saya**.
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
  daftarnya pendek. Field bertanda `*` wajib diisi. Komplain sensitif dapat
  ditandai **Terbatas** — hanya pembuat, penanggung jawab, supervisor, dan owner
  yang bisa membukanya.

## Sore: menutup hari

1. Front desk mencatat **Kas akhir** dan mengajukan verifikasi.
2. Orang kedua memverifikasi.
3. Supervisor: **Mulai penutupan** → **Tutup hari**. Bila masih ada kas akhir yang
   belum selesai atau catatan kritis belum ditriase, penutupan hanya dapat dilakukan
   dengan alasan override.
4. Hari tertutup bersifat read-only. Koreksi hanya lewat *Buka kembali* oleh
   supervisor disertai alasan.

## Yang tidak boleh dicatat di sistem ini

Diagnosis, hasil pemeriksaan, foto klinis, catatan medis, nomor kartu/rekening.
Aplikasi ini untuk operasional, bukan rekam medis.

## Bila sistem tidak dapat diakses

Gunakan formulir kertas darurat, lalu masukkan datanya setelah sistem kembali dan
tulis di catatan bahwa entri dibuat susulan. Laporkan gangguannya ke admin teknis.
