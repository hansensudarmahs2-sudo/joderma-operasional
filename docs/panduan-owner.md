# Panduan Owner dan Direktur Utama

Untuk akun berperan `OWNER`: `yohanes` (Owner) dan `jean` (Direktur Utama). Keduanya memakai
tampilan yang sama. Owner **membaca** keadaan klinik. Yang ia buat dan putuskan sendiri:
**Permintaan Owner**, **keputusan** atas perkara yang menunggunya, dan **tanggapan** atas Summary Harian. Rancangan lengkapnya ada di
[`KEBUTUHAN_REDEFINISI_PERAN.md`](KEBUTUHAN_REDEFINISI_PERAN.md).

Sesudah login, Owner langsung masuk ke **Dashboard**. Halaman sejenis digabung dalam satu menu
(5 Okt 2026): **Task** (Daftar Task, Kanban, Prioritas, Jadwal Task), **Evaluasi staf** (KPI, Jejak),
dan **Kebijakan** (Kebijakan, Keputusan, Bahan Rapat). Di dalam halaman itu ada baris tab di atas
untuk pindah antarhalaman kelompoknya. Isi tiap halaman:

| Menu | Isi |
|---|---|
| **Dashboard** | Kartu **Menunggu keputusan Anda** di paling atas (lihat bagian *Keputusan yang menunggu Anda*), lalu Permintaan Owner, lalu **Agenda rapat Kamis** (perkara yang menunggu keputusan bersama dan task yang tertahan karenanya), lalu ringkasan yang sama dengan Ringkasan Direktur: kuadran prioritas gabungan dua cabang, keputusan menggantung, kebijakan baru, menunggu konfirmasi, jadwal task, dan kartu per cabang. Setiap kotak dapat diketuk untuk membuka Prioritas, Kanban, Jadwal Task, Keputusan, atau Tim |
| **Inbox** | Semua yang masuk ke Direktur Operasional (komplain, masukan, kerusakan, laporan staf, permintaan dan temuan Anda) beserta hasil pilahnya, hanya baca (lihat di bawah) |
| **Daftar Task** | Semua task kedua cabang dalam satu tabel: cari, saring, urutkan, unduh CSV. Hanya baca |
| **Keputusan** | Register keputusan dan kebijakan. Perkara yang menunggu Anda dapat diputuskan dari sini atau dari kartu di Dashboard |
| **Bahan Rapat** | Bahan rapat Kamis yang tersusun otomatis (Kamis lalu s.d. Rabu): agenda keputusan, permintaan dan temuan, task selesai, task lewat target, Inbox per cabang. Bisa dicetak atau disalin ke WhatsApp |
| **Jejak** | Jejak kehadiran staf (IP, perangkat, lokasi sesaat) dengan label Kuat/Sedang/Lemah, hanya baca |
| **KPI** | Angka per staf per bulan: kelengkapan porsi checklist, pembukaan tepat waktu, jejak di klinik, task tepat target, dan tanda centang massal. Tanpa skor gabungan dan tanpa peringkat selama uji coba; ketuk nama staf untuk rincian per hari; unduh CSV. Staf belum melihat halaman ini |
| **Jadwal Task** (dari Dashboard: *Lihat di Jadwal Task*) | Satu baris per permintaan/temuan Anda dari tanggal diminta sampai target (garis putus-putus oranye), dengan task turunan yang dibuat Direktur di bawahnya. Yang belum dipecah ditandai |
| **Summary Harian** | Summary of the day dari Direktur Operasional, pilih per tanggal; **Unduh PDF** untuk menyimpan atau meneruskannya. Di bawahnya ada daftar siapa yang sudah membaca dan utas **Tanggapan** |
| **Jadwal** | Pilih cabang, lihat siapa yang bertugas hari itu dan siapa yang libur, cuti, atau sedang di cabang lain. Tombol **Lihat jadwal penuh** membuka grid bulanan (hanya baca) |

Halaman lain (Hari Ini, checklist, pembagian tugas, kas, laporan, audit, pengaturan klinik) tidak
ada di menu Owner dan ditolak bila alamatnya dibuka langsung.

## Permintaan dan temuan Owner

1. Di Dashboard, tekan **+ Catat temuan** untuk hal yang Anda lihat dan perlu dibereskan (form
   temuan **tidak punya kolom target**; Direktur yang menentukan PIC dan target), atau
   **+ Permintaan** untuk permintaan dengan **tanggal target**. Pilih cabang (atau lintas cabang),
   centang **Mendesak** bila perlu, dan lampirkan **foto** (opsional, dikecilkan otomatis).
   Temuan **Mendesak** harus dibereskan paling lambat **3 hari** sejak dicatat. Tanpa centang,
   Direktur menentukan target dan paling lambat **1 bulan** (30 hari) sejak dicatat; selama target
   belum diisi, Dashboard menampilkan "Paling lambat <tanggal>" dan keterlambatan dihitung dari
   tanggal itu.
2. Keduanya masuk **Inbox** Direktur Operasional dan memberi notifikasi. Direktur memilahnya:
   dijadikan satu atau beberapa task (temuan menjadi satu task besar dengan sub task), diteruskan ke pemegang wewenang lain, dibawa ke rapat Kamis,
   atau tidak ditindaklanjuti (dengan alasan). Hasil pilah tampil di halaman permintaan.
3. Di Dashboard setiap permintaan/temuan menampilkan status dan progres dari task-tasknya:
   - **Menunggu Direktur**: belum dipecah menjadi task.
   - **Berjalan**: sebagian task selesai, dengan batang progres (mis. 1/3 task).
   - **Selesai**: semua task selesai. Permintaan selesai tetap tampil 14 hari, lalu hilang dari Dashboard.
   - **Lewat target**: target sudah lewat dan belum selesai. Permintaan ini tampil paling atas.
   **Temuan** punya tampilan sendiri: Direktur menjadikannya satu **task besar** yang dipecah
   menjadi **sub task**. Temuan mendesak yang belum selesai tampil paling atas, dengan target atau
   "Paling lambat", progres "x/y sub task", dan statusnya: **Menunggu Direktur**, **Berjalan**,
   **Siap ditutup** (semua sub task selesai, menunggu pernyataan Direktur), dan **Selesai &
   terverifikasi**. Temuan tidak pernah tertutup otomatis; bila sudah dinyatakan Direktur,
   Dashboard menulis "selesai <tanggal> oleh <Direktur>, tepat waktu / terlambat n hari" dan Anda
   mendapat notifikasi. Di detail temuan, tiap sub task menampilkan siapa yang mengerjakan dan
   statusnya: **Berjalan**, **Menunggu verifikasi**, **Terverifikasi Direktur** (sub task staf),
   atau **Selesai oleh Direktur** (sub task Direktur sendiri, tanpa verifikasi). Anda tidak
   memverifikasi sub task temuan; tanggung jawab pernyataan "selesai" ada pada Direktur di hadapan
   Anda. Tidak ada tombol buka kembali: bila hasilnya keliru, tulis catatan.
   **Usulan target baru:** Direktur dapat mengusulkan tanggal target baru (untuk temuan, hanya yang melewati batas
   3/30 hari) beserta alasannya. Anda mendapat notifikasi, dan di Dashboard permintaan itu bertanda **Usul target**.
   Di halaman permintaan tekan **Setujui target** (target langsung berganti) atau **Tolak** dengan catatan alasan;
   Direktur diberi tahu dan jawaban pertama yang berlaku. Task turunan tidak ikut berubah.
4. Buka permintaan untuk melihat task-tasknya dan **catatan**. Bila target perlu diubah atau
   tidak terpenuhi, Direktur membicarakannya langsung (WhatsApp) atau menulis catatan di sini.
   Owner juga dapat menulis catatan, juga dengan foto. Setiap catatan memberi notifikasi ke pihak
   lain. Foto permintaan ikut terlihat oleh penerima task yang dibuat darinya.
   Anda juga mendapat notifikasi saat Direktur membuat task untuk permintaan atau temuan Anda
   (**Mulai dikerjakan** untuk task pertama, **Task baru** untuk berikutnya, digabung bila berdekatan),
   saat Direktur menetapkan atau mengubah **rencana temuan** (nama task besar dan target), dan saat
   sebuah **permintaan selesai** (semua task selesai), lengkap dengan keterangan tepat waktu atau terlambat.
   Temuan tetap selesai hanya lewat pernyataan Direktur.

Tidak ada tombol tolak atau kembalikan pada permintaan; permintaan hanya dibaca progresnya.
Untuk perkara yang menunggu keputusan Anda, lihat bagian berikut.

## Keputusan yang menunggu Anda

Di paling atas Dashboard ada kartu **Menunggu keputusan Anda**: perkara Keputusan yang pemutusnya
Owner atau Direktur Utama dan belum diputuskan. Yang **lewat tenggat** diberi label **Lewat tenggat**
dan tampil paling atas. Perkara ini sampai ke Anda dari dua jalan, dan Anda mendapat notifikasi
untuk keduanya: Direktur memilih **Teruskan → Direktur Utama / Owner** di Inbox, atau Direktur
mencatat perkara di halaman Keputusan dengan pemutus Owner atau Direktur Utama.

Ketuk satu perkara untuk membuka halaman keputusannya (`/owner/keputusan/<id>/`). Halaman itu
menampilkan perkaranya, latar belakangnya (untuk yang diteruskan dari Inbox: uraian asli,
"Rujukan: ...", dan "Catatan Direktur: ..."), serta task yang menunggu keputusan ini. Tulis catatan di
kotak yang tersedia, lalu pilih satu dari tiga tombol:

- **Setujui**: catatan boleh kosong. Keputusan tercatat "Disetujui <nama>: <catatan>".
- **Tolak**: alasan wajib. Keputusan tercatat "Ditolak <nama>: <catatan>".
- **Bahas di rapat Kamis**: perkara pindah ke agenda rapat bersama, catatan Anda ditambahkan ke
  latar belakangnya, dan task yang menunggu tetap tertahan sampai diputuskan di rapat.

Siapa saja yang berperan Owner (Owner maupun Direktur Utama) boleh memutuskan, dan **keputusan
pertama yang berlaku**; sesudahnya halaman hanya menampilkan hasilnya. Direktur Operasional dapat
membaca halaman ini tetapi tidak dapat memutuskan di sana. Direktur diberi tahu hasilnya dan dapat
membuat task tindak lanjut dari halaman Keputusan.

## Usulan Direktur

Usulan yang Direktur Operasional ajukan atas inisiatifnya sendiri ada di menu **Usulan Direktur**
(`/owner/usulan/`) dan di kartu **Usulan Direktur** pada Dashboard, dengan tag **Putuskan**,
**Belum dibaca**, atau **Lewat tenggat**. Anda mendapat notifikasi saat usulan masuk. Buka usulannya:

- **Minta persetujuan**: ketuk **Setujui**, **Tolak** (alasan wajib), atau **Bahas di rapat**
  (catatan boleh; perkara Keputusan untuk rapat Kamis dibuat dan ditautkan dari usulan). Siapa pun
  Owner yang menjawab lebih dulu, jawabannya yang berlaku; Direktur diberi tahu.
- **Laporan masalah/risiko**: ketuk **Tandai sudah dibaca**.
- Untuk keduanya, tulis di **Percakapan** bila perlu bertanya atau menanggapi; Direktur diberi
  notifikasi.

## Verifikasi pekerjaan Direktur Operasional

Pekerjaan yang dikerjakan sendiri oleh Direktur Operasional diverifikasi Direktur Utama / Owner
(kecuali sub task temuan Owner: lihat bagian di atas, tidak masuk antrean ini).
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
Pakai tombol ← → atau pilih tanggal untuk melihat hari lain. Tombol **Unduh PDF** (muncul bila summary
tanggal itu ada) menyimpan summary sebagai file PDF A4 bernama `summary-harian-TTTT-BB-HH.pdf`, isinya
sama dengan halaman, untuk disimpan, dicetak, atau dikirim lewat WhatsApp.

Di bawah summary ada daftar **Dibaca** per Owner. Tiap Owner berstatus salah satu dari:
"Dibaca <nama> <tanggal jam>", "membaca versi sebelumnya" (summary dikirim ulang sesudah Anda
membacanya), atau "belum membaca". Hanya Owner yang membuka halaman ini yang dihitung sudah
membaca; Direktur melihat daftar yang sama.

Sesudah itu ada utas **Tanggapan**. Owner dan Direktur sama-sama dapat menulis, entri tidak dapat
diubah atau dihapus, dan setiap tanggapan memberi notifikasi ke pihak lain. Di daftar summary
terbaru, summary yang belum Anda baca ditandai "belum dibaca" dan yang memiliki tanggapan
menampilkan "<n> tanggapan". Tanggapan yang berurutan dalam beberapa menit digabung menjadi satu notifikasi yang menampilkan tanggapan terbaru.

## Notifikasi

Ikon **lonceng** di kanan atas menampilkan bulatan merah berisi jumlah notifikasi yang belum dibaca
(summary baru, catatan pada permintaan, perkara yang menunggu keputusan Anda, tanggapan Summary Harian, dan lainnya). Ketuk lonceng untuk membuka daftarnya.
