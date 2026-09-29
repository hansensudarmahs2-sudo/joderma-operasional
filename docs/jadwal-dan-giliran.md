# Jadwal Jaga, Pembagian Tugas, dan Giliran Tally

Tiga halaman ini saling bergantung: **jadwal jaga** menentukan siapa bertugas di
cabang mana, **pembagian tugas** membagi opening, closing, kas, kebersihan, limbah,
dan apotek menjadi porsi kecil kepada yang bertugas, dan **giliran perawat**
hanya memberi pasien kepada perawat yang bertugas di cabang itu hari itu.

Isi checklist dan aturan di bawah diambil dari folder Project-AOM (Lembar
Opening Session Versi A, JD-FOB-F04 Lembar Closing Session Rev 01, memory 08, 14,
16, 17, 19, 20; KP-179, KP-186, KP-211, KP-212) dan ketetapan product owner 29
September 2026. Sumber per butir tercatat di `jadwal/seed_data.py`.

## Jadwal Jaga

Menu **Jadwal Jaga**. Satu baris per orang, satu kolom per tanggal:

| Kode | Arti |
|---|---|
| M | Masuk di cabang asal |
| B | Perbantuan dari cabang lain (bertugas di cabang ini) |
| P | Sedang di cabang lain |
| O | Off |
| C | Cuti |

Semua staf dapat membaca jadwal cabangnya. Yang mengubah hanya Direktur
Operasional atau Admin, per tanggal, tercatat di audit.

Jadwal satu bulan diimpor dari berkas JSON (bentuknya: `jadwal/jadwal_bulanan/jadwal-2026-10.json`,
disalin dari "JADWAL LIBUR OCTOBER 2026.pdf"):

```bash
.venv/bin/python manage.py import_jadwal_jaga jadwal/jadwal_bulanan/jadwal-2026-10.json --dry-run
.venv/bin/python manage.py import_jadwal_jaga jadwal/jadwal_bulanan/jadwal-2026-10.json
```

Satu karakter per tanggal: `.` bertugas di cabang tabel itu, `X` off, `P`
perbantuan ke cabang lain, `C` cuti. Orang yang muncul di dua tabel (Yani, Luki)
memakai cabang asal dari `home`. Bila kedua tabel tidak saling cocok untuk satu
tanggal, impor tetap berjalan dan mencetak peringatan.

Cuti belum dibedakan dari off pada giliran tally; diatur bersama jadwal November.

## Pembagian Tugas

Menu **Pembagian Tugas**: tabel satu bulan (baris tanggal, kolom kelompok) dan
beban per orang. Klik tanggal untuk melihat semua porsi hari itu.

Aturan penyusunan otomatis:

1. Hanya yang bertugas di cabang itu pada tanggal itu yang diberi porsi.
2. Porsi fungsi PIC diberikan kepada pemegangnya bila ia masuk: Koordinator
   Shift (opening dan closing), PIC Kasir ("kasir hari ini" — satu hari satu
   kasir), PIC Apotek, PJ Kebersihan dan Sterilitas.
3. Bila pemegang PIC libur, porsinya didelegasikan kepada **satu** orang yang
   memegang peran yang dibutuhkan (opening dan closing Koordinator Shift jatuh ke
   orang yang sama), dipilih yang bebannya paling ringan.
4. Porsi apotek hanya untuk peran Apoteker dan Asisten Apoteker; porsi kas hanya
   untuk peran FRONT_DESK (PIC Kasir dan cadangannya). Keduanya tidak pernah
   jatuh ke orang tanpa peran itu.
5. Porsi terbuka (pintu dan lampu, meja depan, piket, merapikan ruangan)
   digilir: yang porsinya hari itu paling sedikit, lalu yang paling jarang
   mendapat porsi yang sama bulan itu.
6. Piket kebersihan dua orang per hari. Stock opname apotek hanya hari Senin.

Direktur Operasional atau Admin menekan **Susun ulang otomatis**. Porsi yang
sudah diganti manual tidak disentuh. Koordinator Shift cabang itu dapat
**Ganti pelaksana** satu porsi (misalnya tukar hari H); orangnya harus bertugas
dan memegang peran porsi itu.

Staf melihat porsinya di **Checklist Saya ▸ Tugas saya hari ini**; di halaman
checklist setiap butir menampilkan pelaksananya, dan tombol **Hanya tugas saya**
menyaring butir miliknya. Yang ditugaskan boleh mengisi butir porsinya walau tidak
memegang peran pelaksana butir itu (delegasi), dan hanya porsinya.

### Isi checklist harian

| Checklist | Isi |
|---|---|
| Opening session | pintu, lampu, AC · Omnicare, EDC, QRIS, berkas meja resepsionis · modal awal kasir dan saksinya · BHP dan alat ruang konsultasi, ruang tindakan dan facial · tally kemarin masuk total bulanan, papan harian dinolkan, papan urutan · briefing 13.45–13.50 · papan istirahat |
| Piket kebersihan | tiga ruang sebelum opening · toilet saat opening dan pukul 19.00 · area resepsionis tiap jam (jumlah pengecekan, minimum = jam buka) · verifikasi PJ Kebersihan (pouch steril, catatan sterilisasi) |
| Limbah medis | limbah tiap ruangan, yang ¾ dipindahkan · log limbah harian |
| Closing session | jam panggilan terakhir · jam pasien terakhir selesai · rekonsiliasi tiga angka · kas fisik, selisih, setoran, nota tertahan · tally disalin dan dijumlahkan ke total bulanan · tiga ruangan dirapikan · limbah dicek langsung dan log dicek · kotak pertama penuh → vendor dihubungi · alat, Omnicare, listrik, cadangan data · jam pintu dikunci |
| Apotek | suhu kulkas · FEFO · ED dicek saat diambil · nota setiap pengeluaran · lemari obat terkunci · mingguan: stock opname, daftar hampir ED 12/6/3/1 bulan, ED < 4 bulan untuk retur |

Memasang atau memperbarui isi ini (versi baru; riwayat run lama tetap):

```bash
.venv/bin/python manage.py seed_tugas_harian --dry-run
.venv/bin/python manage.py seed_tugas_harian --susun 2026-10
```

## Giliran perawat

Menu **Giliran Perawat**. Roster hari itu dibuat otomatis dari jadwal jaga saat
halaman pertama kali dibuka: semua pemegang peran PERAWAT yang bertugas di cabang
itu (termasuk Heni, Desy, dan Regitta, serta perawat perbantuan).

1. **Giliran ditentukan per pasien; tally dicatat per tindakan** saat tindakan
   selesai — tiga tindakan pada satu pasien = tally 3, tetapi satu giliran.
2. **Total bulanan** digabung dua cabang dan mulai dari nol tiap tanggal 1.
   Halaman menampilkan tally hari ini dan total bulan ini per orang.
3. **Urutan papan awal hari disusun dari total bulanan terkecil**; yang seri dapat
   ditata Koordinator Shift dengan tombol ▲ ▼. Setelah tally dicatat, perawat
   pindah ke belakang papan.
4. **Yang paling sedikit didahulukan sampai −1.** Perawat yang totalnya paling
   sedikit 2 di bawah total terkecil rekan yang bertugas mendapat pasien
   berturut-turut sampai tinggal satu di bawah rekan itu, lalu giliran kembali
   mengikuti papan. Off — termasuk tukar libur karena masuk hari Minggu atau
   hari raya — tetap dihitung, jadi yang habis off ikut mengejar.
5. **Yang mengajukan cuti tidak mendapat keistimewaan mengejar.** Hari cuti dicatat
   di Jadwal Jaga (kode C); perawat yang punya hari cuti di bulan itu tetap
   mendapat tempat pertama di papan bila totalnya terkecil, tetapi tidak
   didahulukan berturut-turut. Selain itu tidak ada perlakuan khusus.
6. **Yang sedang menangani tidak diberi pasien.** Koordinator Shift menekan
   *Serahkan pasien*; perawat itu berstatus *Sedang menangani* sampai tally-nya
   dicatat. Yang istirahat, off, cuti, atau sedang di cabang lain juga dilewati.

Contoh (skenario product owner 30 Sep): Yani 8 sesudah off, Lia 11, Heni 11,
Desy 12, Alya 11; Koordinator Shift menata Lia–Heni–Alya. Urutan pasien: Yani,
Yani (Yani 10), Lia, Heni, Alya, lalu Yani lagi karena ia kembali 2 di bawah
total terkecil rekan (Desy 12), baru Desy. Akhir: Yani 11, lainnya 12. Esoknya
Yani di urutan pertama papan tanpa keistimewaan berturut-turut, karena selisihnya
tinggal 1.

Ambang 2 dapat diubah per cabang lewat Konfigurasi `nurse.catch_up_gap`.

## Akun staf dan PIC

```bash
.venv/bin/python manage.py seed_staf_cabang --dry-run
.venv/bin/python manage.py seed_staf_cabang --password '<password sementara>' --prune
```

Membuat akun yang belum ada (wajib ganti password saat login pertama), menambah
peran dan fungsi PIC sesuai `jadwal/staff.py`, mengganti username lama `heny`
menjadi `heni`, dan dengan `--prune` mencabut peran di cabang yang bukan
tempatnya lagi (Naya di Jemur). Akun dan password yang sudah ada tidak diubah.
