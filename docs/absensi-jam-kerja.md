# Absensi Jam Kerja

> **STATUS: Tahap 1-3 selesai — pemetaan ID, model cap, importer, mesin
> perhitungan, laporan pengecualian, dan halaman web.**

## 1. Mengapa modul ini ada

Jam kerja staf selama ini dihitung tangan di satu berkas Excel per bulan: ekspor
mesin sidik jari, lalu dua kolom diisi manual (menit terlambat dan menit lembur),
lalu skor bulanan = lembur dikurangi terlambat.

Cara itu punya satu kesalahan yang mahal dan beberapa yang menular:

- **Lewat tengah malam.** Shift Jemur tutup 22.00 dan pulang 00.28 bukan hal aneh.
  Dihitung sebagai jam dinding, `00:28 - 22:00` menghasilkan **-1292 menit**, bukan
  **+148**. Pada data September 2026 ada 10 cap semacam ini; bila dihitung naif,
  lima staf dengan lembur terbanyak justru jatuh ke dasar papan skor.
- **Aturan tidak seragam.** 22 September 2026 (pendampingan visitasi) tiga orang
  datang ±5 jam lebih awal; dua dikredit ±300 menit, satu hanya 19 menit.
- **Salah ketik.** Pada ekspor yang sama ada menit terlambat yang terlewat, dan
  angka yang terbaca seperti digit menit dari jam masuk (masuk `09:14` dicatat
  terlambat `14`).

## 2. Aturan yang sudah diputuskan product owner

| Hal | Keputusan |
|---|---|
| Jam shift | Mengikuti cabang tempat bertugas hari itu: Jemur 14.00–22.00, Citraland 12.00–21.00 |
| Datang lebih awal | Dihitung bila **≥ 60 menit**; bila lolos ambang, seluruh menitnya dibayar |
| Lembur pulang | Tanpa plafon |
| Terlambat | Mengurangi skor |
| Skor | `lembur_pulang + datang_awal − terlambat`, satuan menit |

Sumber jam shift adalah `core.Clinic.open_time`/`close_time`, dan cabang per hari
diambil dari `jadwal.DutyRoster.clinic` (bukan `home_clinic`, karena hari
perbantuan memakai jam cabang tujuan).

## 3. Yang sudah dibangun

```
absensi/
  models.py        AttendanceDevice, AttendanceImport, AttendancePunch
  parser.py        pembaca .xlsx "Kartu Laporan" (zipfile + ElementTree, tanpa dependensi baru)
  services.py      impor_kartu_laporan() — penentuan waktu, pemetaan ID, dedup
  perhitungan.py   hitung_hari / hitung_periode / laporan_pengecualian
  management/commands/petakan_id_absensi.py
  management/commands/impor_absensi.py
  management/commands/laporan_absensi.py
  views.py / urls.py          halaman /absensi/ (tab papan skor, perlu dicek, impor)
templates/absensi/
  index.html / staf.html
```

### Halaman dan hak akses

| Halaman | Isi |
|---|---|
| `/absensi/?tab=skor` | Papan skor bulanan, satu baris per staf, tertaut ke rinciannya |
| `/absensi/?tab=pengecualian` | Hari yang perlu dilihat manusia, urut tanggal |
| `/absensi/?tab=impor` | Unggah berkas ekspor mesin dan riwayat impor beserta peringatannya |
| `/absensi/staf/<id>/` | Rincian harian satu staf: shift, cap, dan asal setiap angka |

Direktur Operasional (dan Admin berakses penuh) membaca dan mengimpor; Owner hanya
membaca. Staf tidak melihat halaman ini sama sekali. Pemeriksaannya ganda:
`core.permissions.can_view_absensi`/`can_edit_absensi` di view, dan `core/peran.py`
untuk menu serta `PersonaAccessMiddleware`. Menunya masuk kelompok **Evaluasi staf**,
bersebelahan dengan KPI dan Jejak.

### Skor tidak disimpan

`perhitungan.py` menghitung ulang dari cap + roster setiap kali dipanggil, dan tidak
menyimpan hasilnya. Roster berubah setelah fakta (tukar off, cuti menyusul, koreksi
cabang), dan skor tersimpan akan diam-diam basi. Verifikasi September 2026
menunjukkan satu baris roster yang salah menggeser skor **127 menit** untuk satu
hari saja, jadi angka yang selalu ikut roster terkini lebih aman daripada angka yang
cepat dibaca.

### Pengecualian

Tujuh keadaan dilaporkan, bukan ditebak:

| Kode | Arti |
|---|---|
| `TANPA_ROSTER` | Ada cap tetapi hari itu tidak ada di jadwal jaga; skor tidak dihitung |
| `LIBUR_TAPI_NGECAP` | Jadwal off/cuti tetapi tetap mengecap; dihitung memakai jam cabang asal |
| `TANPA_CAP` | Dijadwalkan masuk tetapi tidak ada cap |
| `CAP_TUNGGAL` | Hanya satu cap; ditafsir dari kedekatan ke jam buka/tutup, sisi lain nol |
| `CABANG_BEDA` | Jam cap lebih cocok dengan cabang lain (ambang 90 menit) |
| `LEWAT_TENGAH_MALAM` | Cap pulang setelah tengah malam |
| `LEMBUR_PANJANG` | Lembur sehari >= 180 menit; informasi saja, tidak memotong bayaran |

`CABANG_BEDA` adalah jaring pengaman terpenting. Karena jam kedua cabang berbeda dua
jam, satu baris roster yang salah tidak menghasilkan selisih kecil — ia menggeser
bayaran sekitar dua jam, dan arahnya bisa menguntungkan maupun merugikan staf.

### Dua pemisahan yang disengaja

**`shift_date` ≠ `occurred_at`.** `shift_date` adalah hari kerjanya, `occurred_at`
adalah detik sebenarnya. Cap pulang 00.28 pada shift tanggal 4 disimpan sebagai
`shift_date=tanggal 4`, `occurred_at=tanggal 5 pukul 00.28`. Semua perhitungan
lembur memakai `occurred_at`; semua pengelompokan per hari kerja memakai
`shift_date`. Batasnya `services.BATAS_DINI_JAM` (06.00), sejalan dengan
`core.models.late_close_cutoff_hour`.

**Jenis cap boleh `TIDAK_PASTI`.** Bila satu hari hanya punya satu cap, importer
tidak menebak apakah itu masuk atau keluar — ia tidak membaca jadwal. Lapisan
perhitungan yang memutuskan dan melaporkannya sebagai pengecualian. Pada September
2026 ada 8 baris semacam ini.

### Pemetaan ID

Nomor di mesin bukan username, dan sebagian ejaannya berbeda:

| ID | Nama di mesin | User |
|---|---|---|
| 4 | Heny | `heni` |
| 11 | Rahayu | `ayu` |
| 14 | Agustin | `nanda` |
| 18 | Nadiya | `naya` |

ID 2 (Izul), 6 (Isya), dan 9 (Lina) ada di mesin tetapi **belum punya user** dan
tidak ada di jadwal jaga kedua cabang. Capnya tidak diimpor dan importer
memperingatkannya setiap kali. Perlu keputusan: dibuatkan user, atau memang di luar
skema ini.

## 4. Hasil verifikasi September 2026

Dijalankan pada salinan database, dengan roster September dimuat dari PDF jadwal awal
bulan. Skor ke-13 staf **cocok persis** dengan perhitungan manual yang dibuat terpisah
dari berkas Excel.

Pengecualian yang terdeteksi sebelum roster dikoreksi: **69 hari**.

| Jenis | Jumlah |
|---|---|
| `CABANG_BEDA` | 24 (Naya 17, Yani 5, Luki 2) |
| `TANPA_CAP` | 16 |
| `LIBUR_TAPI_NGECAP` | 14 |
| `LEWAT_TENGAH_MALAM` | 10 |
| `CAP_TUNGGAL` | 8 |

Setelah cabang Naya dikoreksi ke Citraland sesuai konfirmasi product owner, tersisa
**53 hari**. Ke-17 hari Naya yang tertandai memang keliru di PDF: jam capnya
11.40-21.00 sepanjang bulan, yaitu jam Citraland, bukan Jemur.

## 5. Belum dibangun

1. **Alur koreksi di halaman** — memperbaiki cap yang hilang atau salah tafsir masih
   lewat Django admin (`SumberCap.MANUAL` sudah tersedia untuk menandainya).
2. **Halaman "Absensi saya"** — staf belum bisa melihat jam kerjanya sendiri.
3. **Ekspor** — papan skor belum bisa diunduh sebagai CSV.
4. **Keputusan yang masih terbuka** — Izul, Isya, dan Lina belum punya user; dan
   `LEMBUR_PANJANG` saat ini hanya informasi, belum ada alur persetujuan.

## 6. Rencana lanjutan: verifikasi selfie dan lokasi

Ke depan cap tidak hanya dari mesin sidik jari, tetapi juga lewat aplikasi dengan
**foto selfie** dan **lokasi sesaat**. Catatan untuk saat itu:

- `absensi.SumberCap` sudah berupa pilihan (`FINGERPRINT`, `MANUAL`); tinggal
  menambah `APLIKASI` tanpa mengubah bentuk `AttendancePunch`.
- `core.Clinic` **sudah** punya `latitude`, `longitude`, dan `radius_m`, dipakai
  modul `jejak` untuk melabeli jejak Kuat/Sedang/Lemah di dalam radius.
- `jejak.PresenceStamp` sudah memiliki pola label kepercayaan (`Confidence`:
  Kuat/Sedang/Lemah) beserta `geo_status`, `accuracy_m`, dan `distance_m`.
  **Pola itu sebaiknya dipakai ulang, bukan dibuat baru** — termasuk keputusan
  product owner (3 Okt 2026) bahwa jejak tidak memblokir siapa pun, hanya memberi
  label.
- Foto selfie adalah lampiran privat: ikut `core.Attachment` dan `private_media/`,
  **tidak boleh** lewat `whitenoise`/`staticfiles`. Lihat `AGENTS.md` soal media
  privat dan data pasien.
- Kolom geo/selfie sengaja **belum** ditambahkan ke `AttendancePunch` supaya tidak
  ada kolom kosong yang menebak-nebak bentuk fitur yang belum dirancang.

## 7. Cara memakai

```bash
python manage.py petakan_id_absensi --dry-run   # periksa rencana pemetaan
python manage.py petakan_id_absensi
python manage.py impor_absensi "SEPTEMBER 2026.xlsx" --actor hansen
python manage.py laporan_absensi 2026-09                     # papan skor + pengecualian
python manage.py laporan_absensi 2026-09 --pengecualian-saja
```

Impor aman diulang: cap dikunci unik pada (staf, waktu cap), jadi mengimpor berkas
yang sama dua kali menghasilkan 0 cap baru. Berkas revisi hanya menambah
kekurangannya.
