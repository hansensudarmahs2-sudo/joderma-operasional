"""Isi awal checklist Direktur Operasional.

Sumber: `Checklist_Harian_Direktur_Operasional.docx` dan
`Checklist_Mingguan_Direktur_Operasional.docx` (Revisi 00), ditambah keputusan
Direktur 27 September 2026:

- butir harian **Kas** ditambahkan (isi dari Pegangan Penanggung Jawab Area,
  halaman Kasir) — usulan, perlu ditinjau Direktur;
- butir harian **Kebersihan ruang** sebagai pengingat pengamatan langsung
  Direktur (ruang konsultasi, resepsionis, facial, dan benda yang tidak
  semestinya ada di area klinik);
- pemeriksaan **bulanan** tas emergency kit dipindahkan dari butir mingguan #9
  menjadi checklist bulanan tersendiri.

Deposit/keep antrian sengaja tidak dimasukkan: pencatatannya sudah diambil alih
Finance (keputusan Direktur, kasus ditutup).
"""
from __future__ import annotations

from accounts.models import PicFunction

KS = PicFunction.SHIFT_COORDINATOR
KASIR = PicFunction.CASHIER
ONLINE = PicFunction.ONLINE
BERSIH = PicFunction.CLEANLINESS

# (code, number, title, description, source_label, pic_function, clinic_codes, points)
HARIAN = [
    (
        "harian-limbah", 1, "Limbah",
        "Limbah dibuang sesuai jenisnya; freezer limbah biologis dan bak dalam keadaan terkunci; "
        "bila satu tempat penampungan penuh, vendor sudah dipanggil",
        "Koordinator Shift", KS, [],
        [
            ("Piket memeriksa limbah tiap ruangan; wadah yang terisi tiga perempat, termasuk kotak jarum, "
             "sudah dipindahkan dalam keadaan tertutup",
             "Log limbah harian tim perawat (JD-FAC-F04) terisi tiap ruangan"),
            ("Tempat pembuangan diperiksa hari ini, walau tidak ada yang dipindahkan", "Paraf di log hari ini"),
            ("Dua kotak penampungan terkunci; limbah biologis tertutup di dalam freezer",
             "Lihat langsung gembok dan freezer"),
            ("Bila kotak pertama penuh, vendor sudah dihubungi untuk menjemput",
             "Pesan ke vendor; log limbah medis (JD-FAC-F03)"),
        ],
    ),
    (
        "harian-sdm", 2, "SDM",
        "Papan jaga dan papan istirahat terisi; satu hari satu kasir; ketidakhadiran dan tukar jaga "
        "sudah dilaporkan",
        "Koordinator Shift", KS, [],
        [
            ("Papan jaga menunjukkan Koordinator Shift dan petugas hari ini", "Papan jaga"),
            ("Papan istirahat terisi; istirahat sesuai giliran di papan", "Papan istirahat"),
            ("Satu kasir sepanjang hari; modal awal kasir disaksikan saat buka",
             "Nama kasir di papan; paraf modal awal"),
            ("Piket sesuai jadwal; ketidakhadiran dan tukar jaga sudah dilaporkan",
             "Jadwal piket; laporan Koordinator Shift"),
        ],
    ),
    (
        "harian-komplain", 3, "Komplain",
        "Komplain yang masuk hari ini tercatat di berkas komplain, beserta PIC dan tindak lanjutnya",
        "Koordinator Shift", KS, [],
        [
            ("Setiap komplain hari ini, termasuk lewat WhatsApp, dicatat pada formulir komplain",
             "Map berkas komplain"),
            ("Tiap komplain punya PIC dan tindak lanjut; sudah diteruskan kepada Direktur Operasional",
             "Isi formulir; pesan terusan"),
            ("Komplain yang perlu refund dan mendesak sudah diputuskan Direktur Operasional", "Catatan keputusan"),
            ("Komplain WhatsApp ditangani PIC Online atau perawat senior, tidak dialihkan ke petugas lain",
             "Riwayat chat"),
        ],
    ),
    (
        "harian-obat", 4, "Obat",
        "Setiap pengeluaran barang bernota dan tercatat di Omnicare; ED dicek saat diambil; "
        "produk estetik yang keluar tercatat",
        "PIC apotek", "", [],
        [
            ("Setiap pengeluaran barang, termasuk yang diambil dokter atau perawat, bernota dan tercatat "
             "di Omnicare saat itu juga",
             "Nota hari ini dicocokkan dengan Omnicare, acak 2–3 nota"),
            ("ED dicek saat produk diambil; produk kedaluwarsa disisihkan di tempat berlabel OBAT KADALUWARSA",
             "Rak dan tempat obat kedaluwarsa"),
            ("Produk estetik yang keluar hari ini tercatat", "Omnicare dan nota produk estetik"),
        ],
    ),
    (
        "harian-kesiapan-buka-citraland", 5, "Kesiapan buka Citraland",
        "Foto checklist kesiapan buka diterima sebelum klinik buka",
        "Koordinator Shift", KS, ["citraland"],
        [
            ("Foto checklist kesiapan buka diterima sebelum klinik buka", "Foto di WhatsApp dan jamnya"),
            ("Rangkaian buka lengkap: pintu, lampu, AC, Omnicare, alat pembayaran, modal awal kasir, BHP dan "
             "alat tiap ruangan, berkas meja resepsionis, diparaf",
             "Checklist yang difoto, termasuk paraf"),
            ("Emergency kit ada di tempatnya; ruang tindakan siap dipakai",
             "Foto atau konfirmasi Koordinator Shift"),
        ],
    ),
    (
        "harian-laporan-balik", 6, "Laporan balik",
        "Status setiap instruksi Owner dan Direktur Utama (sudah/belum) terkirim hari ini",
        "PIC instruksi", "", [],
        [
            ("Instruksi Owner dan Direktur Utama yang masuk hari ini dicatat: isi, tanggal, PIC",
             "Daftar instruksi"),
            ("PIC melapor status tiap instruksi (sudah/belum) sebelum tutup", "Pesan PIC"),
            ("Rekap status dikirim kepada Owner dan Direktur Utama tanpa menunggu ditanya; yang belum "
             "selesai terbawa ke esok",
             "Pesan terkirim hari ini"),
        ],
    ),
    (
        "harian-kas", 7, "Kas",
        "Setiap transaksi bernota dan cocok dengan Omnicare; tutup kas dan serah terima tercatat; "
        "selisih — termasuk kelebihan — ditulis beserta sebabnya",
        "Kasir", KASIR, [],
        [
            ("Setiap transaksi terbit notanya dan cocok dengan Omnicare",
             "Nota hari ini dicocokkan dengan Omnicare, acak 2–3 nota"),
            ("Tutup kas pada akhir shift dan serah terimanya tercatat, bukan hanya diucapkan",
             "Catatan tutup kas dan serah terima"),
            ("Selisih kas, termasuk kelebihan, ditulis beserta sebabnya dan dilaporkan malam itu juga",
             "Catatan selisih; pesan laporan"),
            ("Nota sementara tetap dicetak dan diarsip per tanggal", "Arsip nota sementara hari ini"),
        ],
    ),
    (
        "harian-kebersihan-ruang", 8, "Kebersihan ruang",
        "Pengingat pengamatan langsung: ruang konsultasi, ruang resepsionis, dan ruang facial bersih; "
        "tidak ada benda yang tidak semestinya berada di area klinik",
        "Pengamatan langsung Direktur", BERSIH, [],
        [
            ("Ruang konsultasi bersih dan rapi", "Lihat langsung"),
            ("Ruang resepsionis bersih dan rapi", "Lihat langsung"),
            ("Ruang facial bersih dan rapi", "Lihat langsung"),
            ("Tidak ada benda yang tidak semestinya berada di area klinik (barang pribadi, makanan, "
             "kardus, alat yang bukan tempatnya)",
             "Lihat langsung"),
        ],
    ),
]

MINGGUAN = [
    (
        "mingguan-audit-wa", 1, "Audit WA",
        "Waktu balas (batas 15 menit), pesan terlewat, pesanan daring",
        "PIC layanan daring", ONLINE, [],
        [
            ("Pesan pasien dibalas paling lama 15 menit", "Contoh acak 10 percakapan minggu ini"),
            ("Tidak ada pesan yang terlewat atau tidak dibalas", "Daftar chat belum terbaca"),
            ("Harga dijawab dalam rentang, bukan angka pasti", "Isi balasan"),
            ("Pertanyaan dan komplain hanya dijawab PIC Online atau perawat senior", "Siapa yang membalas"),
        ],
    ),
    (
        "mingguan-alur-order-online", 2, "Alur order online",
        "Formulir pesanan, serah terima ke apotek, pengiriman sampai ke pasien",
        "PIC layanan daring", ONLINE, [],
        [
            ("Setiap pesanan daring punya formulir pesanan", "Formulir dicocokkan dengan chat pesanan"),
            ("Serah terima ke apotek tercatat dan bernota", "Nota dan catatan serah terima"),
            ("Pengiriman sampai ke pasien; bukti kirim ada", "Resi atau bukti kirim"),
        ],
    ),
    (
        "mingguan-alur-sampel", 3, "Alur pengiriman sampel",
        "Formulir pengiriman lengkap; semua hasil sudah kembali dan sampai ke dokter",
        "Koordinator Shift", KS, [],
        [
            ("Wadah berlabel sebelum sampel masuk; formalin cukup", "Wadah dan stok formalin"),
            ("Formulir pengiriman lengkap; identitas dicocokkan dua orang", "Formulir pengiriman sampel"),
            ("Serah terima ke laboratorium tercatat", "Tanda terima laboratorium"),
            ("Semua hasil sudah kembali dan sampai ke dokter; yang terlambat dikejar", "Daftar pelacakan hasil"),
        ],
    ),
    (
        "mingguan-alur-limbah", 4, "Alur limbah",
        "Log limbah terisi; keadaan tempat penampungan; jadwal dan bukti pengambilan vendor",
        "Koordinator Shift", KS, [],
        [
            ("Log limbah harian (JD-FAC-F04) terisi setiap shift, tiap ruangan", "Log seminggu"),
            ("Log limbah medis (JD-FAC-F03) terisi setiap kali vendor datang, beserta notanya", "Log dan nota"),
            ("Keadaan dua kotak penampungan; kapan vendor terakhir menjemput", "Lihat langsung"),
        ],
    ),
    (
        "mingguan-obat-ed", 5, "Obat — ED",
        "Daftar hampir ED empat tingkat: 12, 6, 3, 1 bulan; yang naik tingkat sudah dilaporkan",
        "PIC apotek", "", [],
        [
            ("Daftar hampir ED empat tingkat diperbarui: 12, 6, 3, 1 bulan", "Daftar terbaru"),
            ("Produk yang naik tingkat sudah dilaporkan ke dokter dan Direktur Operasional", "Pesan laporan"),
            ("ED kurang dari 4 bulan dipisahkan beserta fakturnya untuk retur", "Tempat dan faktur"),
        ],
    ),
    (
        "mingguan-obat-stok", 6, "Obat — stok",
        "Stok produk estetik cocok dengan Omnicare dan nota; selisih dicatat beserta sebabnya",
        "PIC apotek", "", [],
        [
            ("Stok fisik produk estetik cocok dengan Omnicare dan nota", "Hitung acak 3–5 produk"),
            ("Selisih dicatat beserta sebabnya", "Catatan selisih"),
            ("Sisa stok produk estetik dilaporkan tanpa menunggu ditanya", "Laporan PIC apotek"),
        ],
    ),
    (
        "mingguan-obat-harga", 7, "Obat — harga",
        "Harga di Omnicare sesuai data Owner terbaru",
        "PIC apotek", "", [],
        [
            ("Harga di Omnicare sesuai data Owner terbaru", "Cocokkan acak 5 produk"),
            ("Perubahan harga minggu ini sudah masuk sistem; yang mengubah hanya Direktur Utama",
             "Laporan sudah/belum"),
        ],
    ),
    (
        "mingguan-bhp", 8, "BHP",
        "Stok bahan habis pakai cukup untuk seminggu ke depan; yang menipis sudah diorder",
        "PIC apotek", "", [],
        [
            ("Stok BHP cukup untuk seminggu ke depan", "Kartu stok atau Omnicare"),
            ("Yang menipis sudah diorder; order lebih dari 5 hari dikejar ke vendor", "Catatan order"),
        ],
    ),
    (
        "mingguan-emergency-kit", 9, "Emergency kit dan troli",
        "Isi lengkap, termasuk oksigen, masker oksigen, dan kanul; tidak ada yang kedaluwarsa",
        "Koordinator Shift", KS, [],
        [
            ("Adrenalin dan obat emergensi belum kedaluwarsa; oksigen berisi", "Lihat langsung"),
            ("Masker oksigen dan kanul tersedia, termasuk di Citraland", "Lihat langsung"),
        ],
    ),
    (
        "mingguan-kebersihan-sterilisasi", 10, "Kebersihan dan sterilisasi",
        "Checklist kebersihan terdokumentasi; catatan sterilisasi alat ada",
        "Koordinator Shift", KS, [],
        [
            ("Checklist kebersihan dan zona terdokumentasi, bukan hanya berjalan", "Lembar checklist seminggu"),
            ("Catatan sterilisasi alat ada untuk setiap siklus", "Log sterilisasi"),
            ("Area apotek tidak diverifikasi oleh PIC-nya sendiri", "Paraf verifikator"),
        ],
    ),
    (
        "mingguan-insiden", 11, "Insiden",
        "Insiden dan kejadian tidak diharapkan minggu ini tercatat dan dilaporkan",
        "Koordinator Shift", KS, [],
        [
            ("Insiden dan KTD minggu ini tercatat pada laporan komplain dan insiden", "Laporan insiden"),
            ("Sudah dieskalasi kepada Direktur Operasional atau dr. Yohanes", "Pesan eskalasi"),
            ("Pembelajaran dari kejadian disampaikan ke staf", "Catatan briefing"),
        ],
    ),
    (
        "mingguan-perizinan", 12, "Perizinan",
        "Progres perizinan; tindak lanjut visitasi",
        "PJ perizinan", "", [],
        [
            ("Progres perizinan minggu ini dari PJ perizinan", "Laporan PJ perizinan"),
            ("Tindak lanjut visitasi berjalan", "Daftar tindak lanjut"),
            ("Izin, STR, dan SIP yang habis dalam tiga bulan sudah diurus", "Daftar masa berlaku"),
        ],
    ),
    (
        "mingguan-rekap", 13, "Rekap mingguan",
        "Temuan harian minggu ini: yang belum selesai dibawa ke minggu berikutnya atau ke rapat",
        "Direktur Operasional", "", [],
        [
            ("Temuan harian minggu ini dikumpulkan", "Checklist harian seminggu"),
            ("Yang belum selesai dibawa ke minggu berikutnya atau ke rapat", "Bahan rapat"),
        ],
    ),
]

BULANAN = [
    (
        "bulanan-emergency-kit", 1, "Pemeriksaan bulanan emergency kit",
        "Pemeriksaan bulanan tas emergency kit sudah dilakukan bulan ini",
        "Koordinator Shift", KS, [],
        [
            ("Pemeriksaan bulanan tas emergency kit sudah dilakukan bulan ini", "Lembar pemeriksaan bulanan"),
        ],
    ),
]
