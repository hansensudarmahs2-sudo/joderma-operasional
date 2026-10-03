# Panduan Supervisor — JoDerma Staff Ops

Untuk pekerjaan review dan persetujuan. Panduan pengisian harian ada di
[`panduan-staf.md`](panduan-staf.md).

Peran supervisor memegang hampir semua keputusan operasional: verifikasi,
persetujuan, override, dan penutupan hari. Setiap override tercatat atas nama
Anda beserta alasannya, dan dapat dibaca kembali oleh owner.

## Pagi

**1. Pastikan sesi hari ada.** Buka **Hari Ini**. Bila belum ada, tekan **Buat
sesi hari ini**.

**Jadwal hari ini berubah?** (staf sakit, tukar off, perlu perbantuan) Buka
**Pembagian Tugas**, klik tanggal hari ini, lalu di **Siapa bertugas hari ini**
ubah status orangnya (Masuk, Perbantuan ke cabang lain, Off, Cuti) dan Simpan.
Porsi tugasnya otomatis dilepas dan diisi rekan yang bertugas; roster giliran
perawat ikut diperbarui. Untuk tanggal lain di bulan itu, ketuk kotaknya di
**Jadwal Jaga**. Anda mengubah staf yang cabang asalnya cabang Anda; staf
perbantuan dari cabang lain diubah koordinator cabang asalnya atau Direktur.

**2. Susun roster perawat.** Buka **Giliran Perawat ▸ Atur roster**, pilih
perawat yang hadir hari ini beserta urutannya, lalu **Simpan roster**. Roster
menentukan siapa mendapat tindakan berkomisi berikutnya. Perawat yang tidak masuk
roster tidak akan mendapat giliran.

**3. Atur jadwal istirahat.** Buka **Jadwal Istirahat ▸ Tambah jadwal**. Sistem
menolak jadwal yang bertabrakan dan memperingatkan bila staf aktif turun di bawah
minimum. Peringatan minimum dapat dilanjutkan dengan alasan, tetapi alasannya
tercatat.

**4. Review pembukaan.** Setelah staf mengisi checklist, buka **Pembukaan ▸
Review pembukaan**. Dua pilihan:

- **Konfirmasi** bila semua item beres.
- **Terima dengan pengecualian** bila ada item bermasalah yang tidak menghalangi
  operasional. Alasan wajib diisi dan akan muncul di laporan harian.

**5. Verifikasi kas awal.** Buka **Kas ▸ Review/verifikasi**, cocokkan hitungan
dengan uang fisik, lalu **Simpan verifikasi**. Bila Andalah yang menghitung,
verifikasi harus dilakukan orang lain — sistem menolak verifikasi oleh penghitung
yang sama.

**6. Buka klinik.** Di **Hari Ini**, jalankan **Tandai siap** lalu **Buka klinik**.

## Sepanjang hari

**Giliran perawat.** Round-robin berjalan otomatis: perawat yang menyelesaikan
tindakan berkomisi pindah ke belakang antrean. Dua tindakan manual tersedia:

- **Skip** — melewati giliran seseorang, wajib alasan.
- Memilih perawat di luar urutan saat menugaskan tindakan, juga wajib alasan.

Keduanya tercatat di ledger yang bersifat append-only. Bila perawat
mempertanyakan urutannya, buka **Ledger lengkap** — di sana terlihat setiap
perpindahan beserta sebabnya.

**Triase catatan baru.** Komplain dan kerusakan yang masuk perlu ditangani:
buka catatannya, tekan **Tugaskan** untuk menetapkan penanggung jawab, dan
**Ubah status** mengikuti perkembangan. Kerusakan bertingkat kritis memunculkan
notifikasi dan sebaiknya ditriase hari itu juga.

**Koreksi tally.** Bila perawat salah mencatat tally (dobel, salah jumlah, salah
perawat, salah nama tindakan), buka **Giliran Perawat ▸ Koreksi tally per tanggal**,
pilih tanggalnya, tekan **Koreksi** pada barisnya. Isi jumlah baru (0 = batalkan),
perawat, atau tindakan, dan **alasan (wajib)**. Total bulanan ikut terkoreksi dan
perubahan tercatat di audit. Hanya Koordinator Shift cabang itu dan Direktur
Operasional yang bisa mengoreksi.

**Pindah urutan antrean.** Tersedia lewat **Pindah urutan** pada papan antrean,
wajib alasan.

## Sore

**1. Pastikan kas akhir diajukan.** Front desk menghitung kas akhir dan menekan
**Ajukan verifikasi**. Bila terdapat selisih, catatan wajib diisi — jangan
dibulatkan diam-diam. Verifikasinya dilakukan Direktur Operasional, boleh
sesudah hari ditutup; sejak diverifikasi, selisih menjadi tanggung jawab
verifikator (keputusan 3 Oktober 2026).

**2. Tutup hari.** Di **Hari Ini**, pilih **Tutup hari** lalu Jalankan — tidak
perlu menandai siap, buka, atau mulai penutupan lebih dulu. Sistem menahan
penutupan bila kas akhir belum diajukan atau ada catatan kritis yang belum
ditriase. Penutupan tetap dapat dilakukan dengan alasan, dan alasannya masuk
laporan.

**3. Hari tertutup bersifat read-only.** Koreksi hanya mungkin dengan memilih
aksi **Buka kembali (perlu alasan)** pada halaman **Hari Ini**, oleh supervisor,
disertai alasan yang tercatat.

## Koreksi setelah verifikasi

Kas yang sudah diverifikasi hanya dapat dikoreksi oleh supervisor melalui
**Simpan koreksi**, disertai alasan. Nilai lama tidak dihapus — keduanya tersimpan
sehingga riwayatnya utuh. Ini sengaja dibuat merepotkan agar koreksi menjadi
tindakan sadar, bukan kebiasaan.

## Membaca audit log

**Audit** menampilkan siapa melakukan apa, kapan, dari alamat IP mana, beserta
nilai sebelum dan sesudah. Gunakan saat ada pertanyaan yang tidak terjawab oleh
catatan biasa: mengapa urutan perawat berubah, siapa mengubah status pembayaran,
kapan komplain ditutup.

Audit log tidak dapat diubah atau dihapus oleh siapa pun, termasuk admin.

## Yang bukan wewenang supervisor

Membuat akun pengguna, mengubah peran, dan mengubah konfigurasi klinik adalah
wewenang admin. Bila membutuhkan akun baru atau perubahan template, hubungi admin
— pemisahan ini disengaja.
