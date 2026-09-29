"""Isi checklist harian dan porsi tugas, disusun dari Project-AOM.

Sumber (folder Project-AOM, yang berlaku bila berbeda dari SOP lama):
- `Perapian SOP/03 Formulir Baru/Lembar_Opening_Session_A_Berlaku_Sekarang.docx`
  (rangkaian 13.30–14.00, delapan langkah) dan `memory/16-OPENING.md`.
- `Perapian SOP/03 Formulir Baru/JD-FOB-F04_Lembar_Closing_Session.docx` Revisi 01 dan
  `memory/19-CLOSING.md` (pemicu panggilan terakhir, tiga ruangan, papan tally).
- `memory/17-PIKET-KEBERSIHAN.md`: piket bergilir 2–3 orang, jadwal oleh PJ Kebersihan,
  toilet dua kali (opening dan 19.00), resepsionis dilihat tiap jam.
- KP-179, KP-180, KP-186: alur limbah lima langkah; kotak pertama penuh → hubungi vendor.
- `memory/08-KASIR.md`, KP-211 (satu hari satu kasir), Pegangan PJ Area (Kasir).
- `Laporan/Instruksi_Checklist_Harian_Stok_ED_Harga_2026-09-27.docx` dan KP-212 (apotek).

Ketetapan product owner 29 September 2026 yang ikut dipakai:
- Tugas apotek (FEFO, cold chain, stock opname) hanya untuk peran apotek.
- Briefing 13.45–13.50.
- Closing: salin tally harian dan jumlahkan ke total bulanan; rapikan tiga ruangan; cek log
  limbah dan limbah secara langsung; catat jam panggilan terakhir dan pasien terakhir selesai.
- Opening: tally harian kemarin masuk ke total bulanan, papan harian dinolkan.
"""
from __future__ import annotations

from accounts.models import PicFunction, Role
from checklists.models import ChecklistArea, ChecklistSession, InputType

from .models import DutyGroup

APOTEK_ROLES = [Role.APOTEKER, Role.ASISTEN_APOTEKER]

# ---------------------------------------------------------------------------
# Porsi tugas. Urutan di sini juga urutan penyusunan: porsi yang calonnya
# paling sempit (PIC, kasir, apotek) disusun lebih dulu, supaya porsi terbuka
# dibagi ke orang yang bebannya paling ringan hari itu.
# ---------------------------------------------------------------------------
PORTIONS = [
    {
        "code": "opn-ks", "name": "Opening · Koordinator Shift", "group": DutyGroup.OPENING,
        "description": "Saksi modal awal, papan tally dan papan urutan, briefing 13.45–13.50, papan istirahat.",
        "eligible_roles": [Role.SUPERVISOR, Role.PERAWAT], "pic_function": PicFunction.SHIFT_COORDINATOR,
    },
    {
        "code": "cls-ks", "name": "Closing · Koordinator Shift", "group": DutyGroup.CLOSING,
        "description": "Panggilan terakhir, rekonsiliasi tiga angka, tally ke total bulanan, verifikasi kas, kunci pintu.",
        "eligible_roles": [Role.SUPERVISOR, Role.PERAWAT], "pic_function": PicFunction.SHIFT_COORDINATOR,
    },
    {
        "code": "kas", "name": "Kasir hari ini", "group": DutyGroup.KAS,
        "description": "Satu hari satu kasir: modal awal, tutup kas, setoran, nota tertahan.",
        "eligible_roles": [Role.FRONT_DESK], "pic_function": PicFunction.CASHIER,
    },
    {
        "code": "apt-harian", "name": "Apotek · FEFO dan kedaluwarsa", "group": DutyGroup.APOTEK,
        "description": "Rak FEFO, ED dicek saat diambil, nota setiap pengeluaran, lemari obat terkunci.",
        "eligible_roles": APOTEK_ROLES, "pic_function": PicFunction.PHARMACY,
    },
    {
        "code": "apt-coldchain", "name": "Apotek · Cold chain", "group": DutyGroup.APOTEK,
        "description": "Suhu kulkas obat dicatat; di luar 2–8 °C dilaporkan ke APJ.",
        "eligible_roles": APOTEK_ROLES,
    },
    {
        "code": "apt-opname", "name": "Apotek · Stock opname mingguan", "group": DutyGroup.APOTEK,
        "description": "Stok estetik dicocokkan dengan Omnicare dan nota; daftar hampir ED 12/6/3/1 bulan.",
        "eligible_roles": APOTEK_ROLES, "pic_function": PicFunction.PHARMACY, "weekdays": [0],
    },
    {
        "code": "kbr-pj", "name": "Kebersihan · Verifikasi PJ", "group": DutyGroup.KEBERSIHAN,
        "description": "Memastikan, bukan mengerjakan: checklist piket, pouch steril, catatan sterilisasi.",
        "eligible_roles": [Role.SUPERVISOR, Role.APOTEKER], "pic_function": PicFunction.CLEANLINESS,
    },
    {
        "code": "opn-ruang-konsul", "name": "Opening · Ruang konsultasi", "group": DutyGroup.OPENING,
        "description": "BHP cukup, alat lengkap dan berfungsi.",
        "eligible_roles": [Role.PERAWAT],
    },
    {
        "code": "opn-ruang-tindakan", "name": "Opening · Ruang tindakan dan facial", "group": DutyGroup.OPENING,
        "description": "BHP cukup, alat lengkap dan berfungsi.",
        "eligible_roles": [Role.PERAWAT],
    },
    {
        "code": "lmb-ruang", "name": "Limbah · Ruangan dan log", "group": DutyGroup.LIMBAH,
        "description": "Limbah tiap ruangan; yang ¾ dipindahkan; log limbah harian diisi.",
        "eligible_roles": [Role.PERAWAT],
    },
    {
        "code": "opn-akses", "name": "Opening · Pintu, lampu, AC", "group": DutyGroup.OPENING,
        "description": "Pintu dibuka, lampu dan AC dinyalakan.",
    },
    {
        "code": "opn-sistem", "name": "Opening · Komputer dan meja depan", "group": DutyGroup.OPENING,
        "description": "Omnicare terbuka, EDC dan QRIS berfungsi, berkas meja resepsionis rapi.",
    },
    {
        "code": "kbr-piket", "name": "Kebersihan · Piket", "group": DutyGroup.KEBERSIHAN,
        "description": "Tiga ruang dibersihkan sebelum opening; toilet saat opening dan pukul 19.00.",
        "people": 2,
    },
    {
        "code": "kbr-resepsionis", "name": "Kebersihan · Area resepsionis tiap jam", "group": DutyGroup.KEBERSIHAN,
        "description": "Dilihat setiap jam: bersih atau kotor, bukan pemeriksaan terperinci.",
    },
    {
        "code": "cls-resepsionis", "name": "Closing · Rapikan resepsionis", "group": DutyGroup.CLOSING,
        "description": "Resepsionis dirapikan.",
    },
    {
        "code": "cls-konsul", "name": "Closing · Rapikan ruang konsultasi", "group": DutyGroup.CLOSING,
        "description": "Ruang konsultasi dirapikan.",
    },
    {
        "code": "cls-facial", "name": "Closing · Rapikan ruang facial dan estetik", "group": DutyGroup.CLOSING,
        "description": "Ruang facial dan estetik dirapikan.",
    },
    {
        "code": "cls-limbah", "name": "Closing · Limbah dan log", "group": DutyGroup.LIMBAH,
        "description": "Limbah dicek langsung dan dipindahkan; log limbah dicek terisi; kotak pertama penuh → vendor.",
        "eligible_roles": [Role.PERAWAT, Role.SUPERVISOR],
    },
    {
        "code": "cls-sistem", "name": "Closing · Alat, Omnicare, listrik, cadangan data", "group": DutyGroup.CLOSING,
        "description": "Alat pembayaran dan Omnicare ditutup, AC dan lampu mati, pencadangan data.",
    },
]
for _order, _p in enumerate(PORTIONS, start=1):
    _p.setdefault("eligible_roles", [])
    _p.setdefault("pic_function", "")
    _p.setdefault("people", 1)
    _p.setdefault("weekdays", [])
    _p["sort_order"] = _order * 10


def _i(portion, label, category, *, input_type=InputType.CEKLIS, unit="", min_quantity=None,
       options=(), performer=(), verifier=(), help_text="", required=True):
    return {
        "required": required,
        "portion": portion,
        "label": label,
        "category": category,
        "input_type": input_type,
        "unit": unit,
        "min_quantity": min_quantity,
        "options": list(options),
        "performer_roles": list(performer),
        "verifier_roles": list(verifier),
        "help_text": help_text,
    }


# Butir mingguan ikut muncul di run harian (run dibuat per hari), jadi tidak wajib;
# porsinya hanya dibagikan pada hari yang dijadwalkan (Senin).
WEEKLY = {"required": False, "help_text": "Mingguan, tiap Senin. Hari lain boleh dilewati."}


def _open_hours(clinic) -> int:
    start = clinic.open_time.hour * 60 + clinic.open_time.minute
    end = clinic.close_time.hour * 60 + clinic.close_time.minute
    return max(1, (end - start) // 60)


def templates_for(clinic) -> list[dict]:
    """Template checklist harian untuk satu cabang."""
    fd = [Role.FRONT_DESK]
    ks = [Role.SUPERVISOR]
    return [
        {
            "key": "OPENING", "name": "Opening session", "area": ChecklistArea.AKSES_UMUM,
            "session": ChecklistSession.OPENING, "target_roles": [],
            "items": [
                _i("opn-akses", "Pintu dibuka, lampu dan AC dinyalakan", "1 · Akses"),
                _i("opn-sistem", "Komputer dinyalakan dan Omnicare terbuka", "2 · Sistem"),
                _i("opn-sistem", "EDC dan QRIS diperiksa — keduanya berfungsi", "2 · Sistem"),
                _i("opn-sistem", "Berkas di meja resepsionis dirapikan", "2 · Sistem"),
                _i("kas", "Modal awal kasir (uang kembalian) dihitung di depan saksi", "3 · Kas",
                   input_type=InputType.KUANTITAS, unit="Rp", performer=fd, verifier=ks,
                   help_text="Modal awal milik kasir; saksinya Koordinator Shift atau Direktur Operasional."),
                _i("opn-ks", "Modal awal kasir disaksikan", "3 · Kas", performer=ks),
                _i("opn-ruang-konsul", "Ruang konsultasi: BHP cukup, alat lengkap dan berfungsi", "4 · Ruangan"),
                _i("opn-ruang-tindakan", "Ruang tindakan estetik dan facial: BHP cukup, alat lengkap dan berfungsi",
                   "4 · Ruangan"),
                _i("opn-ks", "Tally kemarin masuk total bulanan; papan tally harian dinolkan; papan urutan ditetapkan",
                   "5 · Giliran", performer=ks,
                   help_text="Aplikasi menjumlahkan total bulanan otomatis dari tally harian."),
                _i("opn-ks", "Briefing 13.45–13.50: janji temu hari ini, pembagian tugas, giliran istirahat",
                   "6 · Briefing", performer=ks),
                _i("opn-ks", "Papan giliran istirahat dan ibadah terisi", "6 · Briefing", performer=ks),
            ],
        },
        {
            "key": "KEBERSIHAN", "name": "Piket kebersihan", "area": ChecklistArea.KEBERSIHAN,
            "session": ChecklistSession.ANYTIME, "target_roles": [],
            "items": [
                _i("kbr-piket", "Resepsionis dan ruang tunggu bersih sebelum opening", "Piket"),
                _i("kbr-piket", "Ruang konsultasi bersih sebelum opening", "Piket"),
                _i("kbr-piket", "Ruang facial dan estetik bersih sebelum opening", "Piket"),
                _i("kbr-piket", "Toilet dan wastafel — pemeriksaan pertama, saat opening", "Toilet"),
                _i("kbr-piket", "Toilet dan wastafel — pemeriksaan kedua, pukul 19.00", "Toilet"),
                _i("kbr-resepsionis", "Area resepsionis dilihat setiap jam — jumlah pengecekan hari ini",
                   "Resepsionis", input_type=InputType.KUANTITAS, unit="kali", min_quantity=_open_hours(clinic),
                   help_text="Bukan pemeriksaan terperinci: bersih atau kotor. Yang kotor langsung dibereskan."),
                _i("kbr-pj", "Checklist piket terisi setelah dikerjakan (uji petik)", "Verifikasi PJ"),
                _i("kbr-pj", "Pouch steril: bertanggal, indikator berubah warna, disimpan kering dan tertutup",
                   "Verifikasi PJ"),
                _i("kbr-pj", "Catatan siklus sterilisasi lengkap: tanggal, isi, indikator, kesimpulan, pelaksana",
                   "Verifikasi PJ"),
                _i("kbr-pj", "Alat rusak dan bahan habis dilaporkan hari ini juga", "Verifikasi PJ"),
            ],
        },
        {
            "key": "LIMBAH", "name": "Limbah medis", "area": ChecklistArea.LIMBAH,
            "session": ChecklistSession.ANYTIME, "target_roles": [],
            "items": [
                _i("lmb-ruang", "Limbah tiap ruangan diperiksa; yang terisi ¾ dipindahkan ke penampungan",
                   "Ruangan", help_text="Termasuk kotak limbah jarum — dipindahkan tertutup, bukan isinya."),
                _i("lmb-ruang", "Log limbah harian perawat (JD-FAC-F04) diisi", "Ruangan"),
            ],
        },
        {
            "key": "CLOSING", "name": "Closing session", "area": ChecklistArea.AKSES_UMUM,
            "session": ChecklistSession.CLOSING, "target_roles": [],
            "items": [
                _i("cls-ks", "Jam panggilan terakhir", "1 · Waktu", input_type=InputType.JAM, performer=ks),
                _i("cls-ks", "Jam pasien terakhir selesai", "1 · Waktu", input_type=InputType.JAM, performer=ks),
                _i("cls-ks", "Rekonsiliasi tiga angka: janji temu hadir · pendaftaran · transaksi kasir",
                   "2 · Rekonsiliasi", input_type=InputType.PILIHAN,
                   options=("Sama", "Tidak sama — sebab ditulis di catatan"), performer=ks),
                _i("kas", "Kas fisik dihitung ulang", "3 · Kas", input_type=InputType.KUANTITAS, unit="Rp",
                   performer=fd, verifier=ks),
                _i("kas", "Selisih kas ditulis apa adanya (kelebihan juga selisih)", "3 · Kas",
                   input_type=InputType.KUANTITAS, unit="Rp", performer=fd, verifier=ks,
                   help_text="Tulis 0 bila nihil. Jangan ditutup dengan uang pribadi."),
                _i("kas", "Setoran tunai hasil hari ini", "3 · Kas", input_type=InputType.PILIHAN,
                   options=("Diserahkan hari ini ke Direktur Operasional/dr. Yohanes",
                            "Disimpan kasir, diserahkan besok ke Direktur Operasional"),
                   performer=fd, verifier=ks),
                _i("kas", "Nota tertahan (diskon menunggu izin) dan uang keep antrian yang belum ditutup dicatat",
                   "3 · Kas", performer=fd),
                _i("cls-ks", "Kas tutup diverifikasi Koordinator Shift", "3 · Kas", performer=ks),
                _i("cls-ks", "Tally hari ini disalin ke buku khusus dan dijumlahkan ke total bulanan", "4 · Giliran",
                   performer=ks, help_text="Angka hari ini dan total bulan tampil di halaman Giliran Perawat."),
                _i("cls-resepsionis", "Resepsionis dirapikan", "5 · Tiga ruangan"),
                _i("cls-konsul", "Ruang konsultasi dirapikan", "5 · Tiga ruangan"),
                _i("cls-facial", "Ruang facial dan estetik dirapikan", "5 · Tiga ruangan"),
                _i("cls-limbah", "Limbah dicek langsung dan dipindahkan; log limbah dicek sudah terisi", "6 · Limbah"),
                _i("cls-limbah", "Penampungan limbah", "6 · Limbah", input_type=InputType.PILIHAN,
                   options=("Kotak pertama belum penuh", "Kotak pertama penuh — vendor sudah dihubungi"),
                   help_text="Kotak pertama penuh: langsung hubungi vendor untuk menjemput (KP-186)."),
                _i("cls-sistem", "Alat pembayaran dan Omnicare ditutup", "7 · Penutupan"),
                _i("cls-sistem", "AC dan lampu dimatikan", "7 · Penutupan"),
                _i("cls-sistem", "Pencadangan data", "7 · Penutupan"),
                _i("cls-ks", "Pintu dikunci — jam", "7 · Penutupan", input_type=InputType.JAM, performer=ks),
            ],
        },
        {
            "key": "APOTEK", "name": "Apotek", "area": ChecklistArea.APOTEK,
            "session": ChecklistSession.ANYTIME, "target_roles": list(APOTEK_ROLES),
            "items": [
                _i("apt-coldchain", "Suhu kulkas obat", "Cold chain", input_type=InputType.KUANTITAS, unit="°C",
                   performer=APOTEK_ROLES, help_text="Di luar 2–8 °C: pindahkan isi dan laporkan ke APJ."),
                _i("apt-harian", "Rak dan lemari obat tersusun FEFO — ED terdekat di depan", "FEFO",
                   performer=APOTEK_ROLES),
                _i("apt-harian", "ED dicek setiap produk diambil; yang kedaluwarsa disisihkan berlabel OBAT KADALUWARSA",
                   "FEFO", performer=APOTEK_ROLES),
                _i("apt-harian", "Setiap pengeluaran barang bernota dan tercatat di Omnicare, termasuk yang diambil "
                   "dokter atau perawat", "Nota", performer=APOTEK_ROLES),
                _i("apt-harian", "Lemari obat terkunci saat tutup", "Keamanan", performer=APOTEK_ROLES),
                _i("apt-opname", "Stock opname: stok fisik produk estetik dicocokkan dengan Omnicare dan nota; "
                   "selisih dicatat", "Mingguan", performer=APOTEK_ROLES, **WEEKLY),
                _i("apt-opname", "Daftar hampir ED empat tingkat (12, 6, 3, 1 bulan) diperbarui; yang naik tingkat "
                   "dilaporkan ke dokter dan Direktur Operasional", "Mingguan", performer=APOTEK_ROLES, **WEEKLY),
                _i("apt-opname", "ED kurang dari 4 bulan dipisahkan beserta fakturnya untuk retur", "Mingguan",
                   performer=APOTEK_ROLES, **WEEKLY),
                _i("apt-opname", "Sisa stok produk estetik dilaporkan tanpa menunggu ditanya", "Mingguan",
                   performer=APOTEK_ROLES, **WEEKLY),
            ],
        },
    ]


# Template lama yang digantikan template di atas (dinonaktifkan, riwayat tetap).
SUPERSEDED_KEYS = [
    "", "KS_OPENING", "KS_CLOSING", "KSR_OPENING", "KSR_CLOSING", "APT_OPENING", "APT_CLOSING",
    "ONL_OPENING", "PRW_CONSULT", "PRW_TREATMENT",
]
