# Panduan Owner dan Direktur Utama

Untuk akun berperan `OWNER`: `yohanes` (Owner) dan `jean` (Direktur Utama). Keduanya memakai
tampilan yang sama. Owner **membaca** keadaan klinik; satu-satunya yang ia buat adalah
**Permintaan Owner**. Rancangan lengkapnya ada di
[`KEBUTUHAN_REDEFINISI_PERAN.md`](KEBUTUHAN_REDEFINISI_PERAN.md).

Sesudah login, Owner langsung masuk ke **Dashboard**. Menunya:

| Menu | Isi |
|---|---|
| **Dashboard** | Permintaan Owner di atas, lalu **Agenda rapat Kamis** (perkara yang menunggu keputusan bersama dan task yang tertahan karenanya), lalu ringkasan yang sama dengan Ringkasan Direktur: kuadran prioritas gabungan dua cabang, keputusan menggantung, kebijakan baru, menunggu konfirmasi, jadwal task, dan kartu per cabang. Setiap kotak dapat diketuk untuk membuka Prioritas, Kanban, Jadwal Task, Keputusan, atau Tim |
| **Inbox** | Semua yang masuk ke Direktur Operasional (komplain, masukan, kerusakan, laporan staf, permintaan dan temuan Anda) beserta hasil pilahnya, hanya baca (lihat di bawah) |
| **Daftar Task** | Semua task kedua cabang dalam satu tabel: cari, saring, urutkan, unduh CSV. Hanya baca |
| **Keputusan** | Register keputusan dan kebijakan, hanya baca |
| **Bahan Rapat** | Bahan rapat Kamis yang tersusun otomatis (Kamis lalu s.d. Rabu): agenda keputusan, permintaan dan temuan, task selesai, task lewat target, Inbox per cabang. Bisa dicetak atau disalin ke WhatsApp |
| **Jejak** | Jejak kehadiran staf (IP, perangkat, lokasi sesaat) dengan label Kuat/Sedang/Lemah, hanya baca |
| **KPI** | Angka per staf per bulan: kelengkapan porsi checklist, pembukaan tepat waktu, jejak di klinik, task tepat target, dan tanda centang massal. Tanpa skor gabungan dan tanpa peringkat selama uji coba; ketuk nama staf untuk rincian per hari; unduh CSV. Staf belum melihat halaman ini |
| **Jadwal Task** (dari Dashboard: *Lihat di Jadwal Task*) | Satu baris per permintaan/temuan Anda dari tanggal diminta sampai target (garis putus-putus oranye), dengan task turunan yang dibuat Direktur di bawahnya. Yang belum dipecah ditandai |
| **Summary Harian** | Summary of the day dari Direktur Operasional, pilih per tanggal |
| **Jadwal** | Pilih cabang, lihat siapa yang bertugas hari itu dan siapa yang libur, cuti, atau sedang di cabang lain. Tombol **Lihat jadwal penuh** membuka grid bulanan (hanya baca) |

Halaman lain (Hari Ini, checklist, pembagian tugas, kas, laporan, audit, pengaturan klinik) tidak
ada di menu Owner dan ditolak bila alamatnya dibuka langsung.

## Permintaan dan temuan Owner

1. Di Dashboard, tekan **+ Catat temuan** untuk hal yang Anda lihat dan perlu dibereskan (target
   **opsional**; Direktur yang menentukan PIC, prioritas, dan target), atau **+ Permintaan** untuk
   permintaan dengan **tanggal target**. Pilih cabang (atau lintas cabang), centang **Mendesak**
   bila perlu, dan lampirkan **foto** (opsional, dikecilkan otomatis).
2. Keduanya masuk **Inbox** Direktur Operasional dan memberi notifikasi. Direktur memilahnya:
   dijadikan satu atau beberapa task, diteruskan ke pemegang wewenang lain, dibawa ke rapat Kamis,
   atau tidak ditindaklanjuti (dengan alasan). Hasil pilah tampil di halaman permintaan.
3. Di Dashboard setiap permintaan/temuan menampilkan status dan progres dari task-tasknya:
   - **Menunggu Direktur**: belum dipecah menjadi task.
   - **Berjalan**: sebagian task selesai, dengan batang progres (mis. 1/3 task).
   - **Selesai**: semua task selesai. Permintaan selesai tetap tampil 14 hari, lalu hilang dari Dashboard.
   - **Lewat target**: target sudah lewat dan belum selesai. Permintaan ini tampil paling atas.
4. Buka permintaan untuk melihat task-tasknya dan **catatan**. Bila target perlu diubah atau
   tidak terpenuhi, Direktur membicarakannya langsung (WhatsApp) atau menulis catatan di sini.
   Owner juga dapat menulis catatan, juga dengan foto. Setiap catatan memberi notifikasi ke pihak
   lain. Foto permintaan ikut terlihat oleh penerima task yang dibuat darinya.

Tidak ada tombol tolak atau kembalikan; permintaan hanya dibaca progresnya.

## Verifikasi pekerjaan Direktur Operasional

Pekerjaan yang dikerjakan sendiri oleh Direktur Operasional diverifikasi Direktur Utama / Owner.
Bila ia mengajukan selesai, Anda mendapat notifikasi dan bagian **Menunggu verifikasi Anda**
muncul di atas Dashboard, lengkap dengan catatan buktinya. Buka task, periksa bukti (dan foto bila
ada), lalu tekan **Konfirmasi selesai** atau **Minta revisi** (catatan wajib). Anda juga dapat
menambah catatan di riwayat task itu. Akun jean dan yohanes sama-sama dapat memverifikasi.

Di bagian bawah Dashboard, **Capaian 7 hari terakhir** memuat task yang selesai dan terverifikasi,
siapa yang mengerjakan, dan siapa yang memverifikasi.

## Inbox

Menu **Inbox** memuat semua yang masuk ke Direktur Operasional dari kedua cabang: Komplain, Masukan,
Kerusakan, Laporan staf, Masukan staf, serta permintaan dan temuan Anda, beserta nama pelapor dan
**hasil pilah** (ditugaskan ke task mana, diteruskan ke siapa, dibawa ke rapat, atau tidak
ditindaklanjuti dengan alasannya). Tab **Belum dipilah** menunjukkan apa yang belum disentuh
Direktur. Owner membuka isinya **baca saja**. Catatan kritis juga muncul di lonceng notifikasi Owner.

## Summary Harian

Direktur Operasional mengirim summary dari Checklist Direktur. Isinya: hasil checklist Direktur
per cabang, catatan Direktur, keputusan dan task hari itu, serta status Permintaan Owner. Bila
Direktur mengirim ulang di hari yang sama, yang tampil adalah versi terakhir beserta jamnya.
Pakai tombol ← → atau pilih tanggal untuk melihat hari lain.

## Notifikasi

Ikon **lonceng** di kanan atas menampilkan bulatan merah berisi jumlah notifikasi yang belum dibaca
(summary baru, catatan pada permintaan, dan lainnya). Ketuk lonceng untuk membuka daftarnya.
