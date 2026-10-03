# Panduan Owner dan Direktur Utama

Untuk akun berperan `OWNER`: `yohanes` (Owner) dan `jean` (Direktur Utama). Keduanya memakai
tampilan yang sama. Owner **membaca** keadaan klinik; satu-satunya yang ia buat adalah
**Permintaan Owner**. Rancangan lengkapnya ada di
[`KEBUTUHAN_REDEFINISI_PERAN.md`](KEBUTUHAN_REDEFINISI_PERAN.md).

Sesudah login, Owner langsung masuk ke **Dashboard**. Menunya:

| Menu | Isi |
|---|---|
| **Dashboard** | Permintaan Owner di atas, lalu **Agenda rapat Kamis** (perkara yang menunggu keputusan bersama dan task yang tertahan karenanya), lalu ringkasan yang sama dengan Ringkasan Direktur: kuadran prioritas gabungan dua cabang, keputusan menggantung, kebijakan baru, menunggu konfirmasi, jadwal task, dan kartu per cabang. Setiap kotak dapat diketuk untuk membuka Prioritas, Kanban, Jadwal Task, Keputusan, atau Tim |
| **Laporan Masuk** | Komplain, masukan, kerusakan, dan laporan staf dari kedua cabang, hanya baca (lihat di bawah) |
| **Daftar Task** | Semua task kedua cabang dalam satu tabel: cari, saring, urutkan, unduh CSV. Hanya baca |
| **Keputusan** | Register keputusan dan kebijakan, hanya baca |
| **Summary Harian** | Summary of the day dari Direktur Operasional, pilih per tanggal |
| **Jadwal** | Pilih cabang, lihat siapa yang bertugas hari itu dan siapa yang libur, cuti, atau sedang di cabang lain. Tombol **Lihat jadwal penuh** membuka grid bulanan (hanya baca) |

Halaman lain (Hari Ini, checklist, pembagian tugas, kas, laporan, audit, pengaturan klinik) tidak
ada di menu Owner dan ditolak bila alamatnya dibuka langsung.

## Permintaan Owner

1. Di Dashboard, tekan **+ Permintaan baru**. Tulis apa yang diminta, rinciannya bila perlu, dan
   **tanggal target**. Temuan di klinik bisa dilampiri **foto** (opsional, dikecilkan otomatis).
   Tekan **Kirim permintaan**.
2. Direktur Operasional menerima notifikasi. Ia memecah permintaan menjadi satu atau beberapa task.
3. Di Dashboard setiap permintaan menampilkan status dan progres dari task-tasknya:
   - **Menunggu Direktur**: belum dipecah menjadi task.
   - **Berjalan**: sebagian task selesai, dengan batang progres (mis. 1/3 task).
   - **Selesai**: semua task selesai. Permintaan selesai tetap tampil 14 hari, lalu hilang dari Dashboard.
   - **Lewat target**: target sudah lewat dan belum selesai. Permintaan ini tampil paling atas.
4. Buka permintaan untuk melihat task-tasknya dan **catatan**. Bila target perlu diubah atau
   tidak terpenuhi, Direktur membicarakannya langsung (WhatsApp) atau menulis catatan di sini.
   Owner juga dapat menulis catatan, juga dengan foto. Setiap catatan memberi notifikasi ke pihak
   lain. Foto permintaan ikut terlihat oleh penerima task yang dibuat darinya.

Tidak ada tombol tolak atau kembalikan; permintaan hanya dibaca progresnya.

## Laporan Masuk

Menu **Laporan Masuk** memuat semua Komplain, Masukan, Kerusakan, Laporan staf, dan Masukan staf
dari kedua cabang beserta nama pelapor, bisa disaring per cabang dan jenis. Owner membuka isinya
**baca saja**; tindak lanjut dilakukan Direktur Operasional atau Koordinator Shift cabang. Catatan
kritis juga muncul di lonceng notifikasi Owner.

## Summary Harian

Direktur Operasional mengirim summary dari Checklist Direktur. Isinya: hasil checklist Direktur
per cabang, catatan Direktur, keputusan dan task hari itu, serta status Permintaan Owner. Bila
Direktur mengirim ulang di hari yang sama, yang tampil adalah versi terakhir beserta jamnya.
Pakai tombol ← → atau pilih tanggal untuk melihat hari lain.

## Notifikasi

Ikon **lonceng** di kanan atas menampilkan bulatan merah berisi jumlah notifikasi yang belum dibaca
(summary baru, catatan pada permintaan, dan lainnya). Ketuk lonceng untuk membuka daftarnya.
