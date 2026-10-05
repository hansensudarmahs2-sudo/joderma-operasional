# Absensi Jam Kerja

> **STATUS: Tahap 1-5 selesai — pemetaan ID, model cap, importer, mesin
> perhitungan, laporan pengecualian, halaman web, dan "Absensi saya" untuk staf.**
> Belum di-merge ke `master`; ada di branch `absensi-jam-kerja`.
> **Belum boleh dipakai untuk penilaian nyata** sampai bagian 9 beres.

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
| Hari Minggu | Hari biasa. Tidak ada premi; penggantinya hari off di jadwal jaga (D2) |
| Hari off tetapi tetap mengecap | Dibayar (D2) |
| Lembur sangat panjang | Tidak perlu persetujuan (D3) |

**Hanya satu angka di modul ini yang mengubah bayaran: ambang datang-awal 60 menit.**
Ambang lain yang ada di kode (`AMBANG_CURIGA_CABANG_MENIT`,
`AMBANG_LEMBUR_PANJANG_MENIT`) hanya memutuskan apakah suatu hari masuk daftar
"Perlu dicek". Lihat bagian 6, D6.

Sumber jam shift adalah `core.Clinic.open_time`/`close_time`, dan cabang per hari
diambil dari `jadwal.DutyRoster.clinic` (bukan `home_clinic`, karena hari
perbantuan memakai jam cabang tujuan).

Ambang datang-awal berupa **gerbang**, bukan potongan: lolos 60 menit berarti
seluruh menitnya dibayar, bukan dikurangi 60 dulu. Konsekuensinya ada tebing di
menit ke-60 — satu menit mengubah bayaran 60 menit. Pada September 2026 satu hari
jatuh tepat di ambang itu (Lia, 13 Sep, masuk 13.00 untuk shift 14.00).

## 3. Yang sudah dibangun

```
absensi/
  models.py        AttendanceDevice, AttendanceImport, AttendancePunch
  parser.py        pembaca .xlsx "Kartu Laporan" (zipfile + ElementTree, tanpa dependensi baru)
  services.py      impor_kartu_laporan() — penentuan waktu, pemetaan ID, dedup
  perhitungan.py   hitung_hari / hitung_periode / laporan_pengecualian
  views.py/urls.py halaman /absensi/
  management/commands/{petakan_id_absensi,impor_absensi,laporan_absensi}.py
templates/absensi/
  index.html / staf.html
```

82 test di `absensi/tests/`. Seluruh suite repo 831 lulus.

### Halaman dan hak akses

| Halaman | Isi |
|---|---|
| `/absensi/?tab=skor` | Papan skor bulanan, satu baris per staf, tertaut ke rinciannya |
| `/absensi/?tab=pengecualian` | Hari yang perlu dilihat manusia, urut tanggal |
| `/absensi/?tab=impor` | Unggah berkas ekspor mesin dan riwayat impor beserta peringatannya |
| `/absensi/staf/<id>/` | Rincian harian satu staf: shift, cap, dan asal setiap angka |
| `/absensi/saya/` | Jam kerja sendiri (D5). Tidak punya parameter staf, jadi tidak bisa diminta untuk orang lain |

Tiga hak yang sengaja dipisah:

| Hak | Siapa | Pemeriksa |
|---|---|---|
| Membaca papan skor dan pengecualian | Direktur Operasional, Admin berakses penuh, Owner | `can_view_absensi` |
| Mengimpor berkas mesin | Direktur Operasional, Admin berakses penuh | `can_edit_absensi` |
| **Mengoreksi cap, skor, lembur** | Direktur Operasional, Direktur Utama, Owner (D4) | `can_correct_absensi` |

Mengimpor hanya memasukkan apa yang dicatat mesin; mengoreksi mengubah angka yang
dipakai menilai orang. Karena itu Admin boleh mengimpor tetapi tidak mengoreksi, dan
Owner sebaliknya. Mengubah pemilik satu ID mesin dihitung sebagai koreksi, karena
memindahkan seluruh cap bulan itu ke orang lain.

Staf tidak melihat jam kerja tim, hanya jam kerjanya sendiri lewat
"Absensi saya". Pemeriksaannya ganda:
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

Harga dari pilihan itu: skor bulan lalu bisa berubah bila rosternya dikoreksi hari
ini. Keputusan **D4** menerima itu, tetapi perhatikan satu ketegangan yang tersisa —
yang boleh *mengoreksi absen* hanya tiga peran, sedangkan *jadwal jaga* tetap boleh
diubah Admin dan Koordinator Shift. Mengubah jadwal jaga tanggal lampau tetap
menggeser skor bulan itu, lewat jalur yang berbeda. Bila nanti itu jadi masalah,
jalan keluarnya Tahap 7 (kunci periode), bukan mencabut hak Koordinator Shift.

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
| `LEMBUR_PANJANG` | Lembur sehari ≥ 180 menit; informasi saja, tidak memotong bayaran |

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

### Pemetaan ID mesin

Nomor di mesin bukan username, dan sebagian ejaannya berbeda. Pemetaan awal dibuat
`manage.py petakan_id_absensi`; sesudah itu perubahannya lewat Django admin, bukan
dengan mengedit berkas perintah.

| ID | Nama di mesin | User | | ID | Nama di mesin | User |
|---|---|---|---|---|---|---|
| 4 | Heny | `heni` | | 13 | Regita | `regitta` |
| 5 | Desy | `desy` | | 14 | **Agustin** | `nanda` |
| 7 | Yani | `yani` | | 15 | Alya | `alya` |
| 8 | Luki | `luki` | | 16 | Lia | `lia` |
| 10 | Arsi | `arsi` | | 17 | Elvira | `elvira` |
| 11 | **Rahayu** | `ayu` | | 18 | **Nadiya** | `naya` |
| 12 | Silvi | `silvi` | | | | |

Yang ditebalkan ejaannya berbeda jauh; ID 14 bahkan nama yang lain sama sekali.
Importer memperingatkan bila nama pada berkas tidak lagi cocok dengan pemetaan,
karena ID yang berpindah orang adalah kesalahan mahal yang sulit terlihat.

ID **2 (Izul)**, **6 (Isya)**, dan **9 (Lina)** tidak ada di jadwal jaga kedua
cabang, jadi jam shift-nya tidak diketahui. Keputusan **D1**: capnya direkam, tidak
dinilai. Devicenya ditandai `recording_only`, usernya dibuat **nonaktif dan tanpa
peran** — cukup untuk menautkan cap, tidak cukup untuk masuk aplikasi. Pada September
2026 itu menambah 128 cap (Isya 26 hari, Izul 19, Lina 27) yang sebelumnya hilang.

Mereka muncul di papan skor pada bagian terpisah "Direkam tanpa penilaian", dan tidak
pernah menghasilkan pengecualian — kalau dinilai, setiap harinya akan jadi
`TANPA_ROSTER` dan menenggelamkan temuan yang benar-benar perlu dilihat.

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
11.40–21.00 sepanjang bulan, yaitu jam Citraland, bukan Jemur.

### Cara mengulang verifikasi

Belum ada perintah sekali-jalan; langkahnya manual dan memakai **salinan** database,
tidak pernah database produksi (`AGENTS.md`).

```bash
cp data/db.sqlite3 /tmp/uji.sqlite3
export DJANGO_DB_PATH=/tmp/uji.sqlite3
python manage.py migrate
python manage.py petakan_id_absensi
python manage.py impor_absensi "SEPTEMBER 2026.xlsx"
python manage.py laporan_absensi 2026-09
```

Satu langkah tidak bisa diotomatiskan sekarang: **roster September tidak ada di
sistem**, hanya Oktober. Verifikasi di atas memuatnya dari hasil ekstraksi PDF
jadwal awal bulan. Untuk bulan yang rosternya sudah terisi di sistem, langkah itu
hilang dan perintah di atas cukup.

## 5. Batasan yang diketahui

Ditulis supaya tidak ditemukan ulang dengan cara yang mahal.

**Parser terikat bentuk ekspor.** Blok dikenali dari sel `Minggu Tgl`, dan nama/ID
dari label `Nama`/`ID` di dalam blok. Bila vendor mengubah tata letak, parser
melempar `FileTidakDikenal` — gagal keras, bukan diam-diam salah. Satu bagian tetap
menebak: blok terakhir di satu pita tidak punya tetangga kanan sebagai pembatas,
jadi lebarnya disamakan dengan blok tersempit di pita itu. Pada berkas dengan satu
blok per pita, batasnya jatuh ke kolom terjauh sheet.

**`BATAS_DINI_JAM` = 06.00 mengasumsikan tidak ada shift subuh.** Cap antara 00.00
dan 05.59 dianggap milik shift hari sebelumnya. Kedua cabang mulai 12.00 dan 14.00,
jadi aman sekarang; shift yang benar-benar mulai jam 5 pagi akan salah tanggal.

**Ambang `CABANG_BEDA` 90 menit adalah heuristik pengembang, bukan aturan bayaran.**
Ia hanya memutuskan apakah satu hari ditandai untuk ditinjau. Ia tidak menangkap
semua kekeliruan: Rahayu 18 September (selisih 78 menit) lolos tanpa tanda.
Menurunkan ambangnya menambah temuan palsu pada hari yang memang lembur panjang.
Angka ini layak ditinjau setelah beberapa bulan data nyata. Ada test
(`test_ambang_penandaan_tidak_pernah_mengubah_angka`) yang menjaga agar mengubahnya
tidak pernah menggeser skor.

**Tafsir `CAP_TUNGGAL` bisa keliru.** Satu cap ditafsir masuk atau pulang dari
kedekatannya ke jam buka/tutup. Orang yang lupa cap masuk lalu pulang sangat awal
bisa tertafsir terbalik. Karena itu barisnya selalu muncul di daftar "Perlu dicek".

**Zona waktu diambil dari `settings.TIME_ZONE`, bukan `Clinic.timezone_name`.**
Kedua cabang Asia/Jakarta, jadi hasilnya sama. Bila nanti ada cabang di zona lain,
`perhitungan._aware()` dan `services.waktu_cap()` harus diubah memakai zona cabang.

**Skor tidak punya riwayat.** Tidak ada "kunci periode": mengoreksi roster bulan lalu
hari ini mengubah skor bulan lalu. Itu disengaja (bagian 3), tetapi menjadi masalah
begitu skor dipakai membayar sesuatu. Lihat keputusan **D4**.

**Hari libur yang tetap ngecap memakai jam cabang asal.** Hari off tidak punya
`DutyRoster.clinic`, jadi jatuh ke `home_clinic`. Bila `home_clinic` basi — misalnya
staf sudah pindah cabang tetapi baris off-nya belum diperbarui — selisihnya dua jam.
Pada verifikasi September satu baris semacam itu menggeser skor 127 menit.

## 6. Keputusan yang masih terbuka

### Sudah dijawab (product owner, Okt 2026)

| Kode | Pertanyaan | Jawaban | Keadaan di kode |
|---|---|---|---|
| **D1** | Izul (2), Isya (6), Lina (9) ikut skema ini? | Ikut, **rekam saja** — capnya disimpan, tidak dinilai | Selesai. `AttendanceDevice.recording_only`; user dibuat nonaktif tanpa peran. 72 hari cap September kini terekam |
| **D2** | Hari off tetapi tetap ngecap dibayar? | **Dibayar.** Hari Minggu hari biasa, penggantinya hari off | Selesai. Sudah sesuai perilaku sebelumnya; ditambah test penjaga agar Minggu tidak pernah diberi perlakuan khusus |
| **D3** | Lembur sangat panjang perlu persetujuan? | **Tidak, untuk saat ini** | Selesai. `LEMBUR_PANJANG` tetap hanya tanda, tidak memotong |
| **D5** | Staf melihat jam kerjanya sendiri? | **Ya** | Selesai. `/absensi/saya/`, menu "Absensi saya". Tidak ada parameter staf di rute itu, jadi tidak ada cara meminta data orang lain |
| **D4** | Siapa boleh mengoreksi absen, skor, dan lembur? | **Direktur Operasional, Direktur Utama, dan Owner.** Jadwal jaga tidak berubah: tetap Admin, Koordinator Shift, Direktur Operasional | Selesai. `core.permissions.can_correct_absensi`, ditegakkan di Django admin tempat koreksi dilakukan sekarang |

### Masih terbuka

| Kode | Pertanyaan | Keadaan sekarang | Yang perlu diputuskan |
|---|---|---|---|
| **D6** | Ambang `CABANG_BEDA` 90 menit | 90, pilihan pengembang | Dipertahankan, diturunkan, atau tanda ini dimatikan saja. Lihat penjelasan di bawah |

**D6 — mengapa ada angka 90 dan dari mana asalnya.** Angka itu **bukan** aturan
bayaran dan bukan keputusan Anda; saya yang memilihnya sebagai titik awal, dan saya
keliru menaruhnya di daftar keputusan tanpa menyebut asalnya. Penjelasan lengkap:

- Ambang **60 menit** milik Anda ada di `AMBANG_DATANG_AWAL_MENIT`. Itu satu-satunya
  angka di modul ini yang menyentuh bayaran.
- Ambang **90 menit** ada di `AMBANG_CURIGA_CABANG_MENIT`. Ia dipakai di satu tempat
  saja: memutuskan apakah suatu hari muncul di daftar "Perlu dicek" dengan tanda
  `CABANG_BEDA`. Ia tidak pernah menyentuh terlambat, lembur, datang awal, atau skor.
- Cara kerjanya: untuk satu hari, dihitung seberapa jauh jam cap meleset dari jam
  buka dan tutup tiap cabang. Bila cabang lain lebih cocok **90 menit atau lebih**,
  hari itu ditandai agar manusia memeriksa apakah cabang di jadwal jaga keliru.
- Contoh nyata, Rahayu 18 September 2026, cap 11.57–21.51:
  meleset dari Jemur (14.00–22.00) sebesar `123 + 9 = 132` menit; dari Citraland
  (12.00–21.00) sebesar `3 + 51 = 54` menit. Selisih 78 — di bawah 90, jadi hari itu
  **tidak** ditandai meski polanya Citraland sedangkan rosternya Jemur.

Di kode, ketiga angka itu sekarang dipisah dengan judul "mengubah bayaran" dan
"hanya menandai", dan ada test yang gagal bila ambang penandaan sampai menggeser
skor.

## 7. Rencana tahap berikutnya

Satu tahap satu kali, berhenti di setiap approval gate (`AGENTS.md`).

**Tahap 4 — koreksi cap dari halaman.** Sekarang cap yang hilang atau salah tafsir
diperbaiki lewat Django admin, yang sudah memakai `can_correct_absensi` (D4). Yang
dibutuhkan: tombol pada baris "Perlu dicek" untuk menambah atau mengubah satu cap,
tersimpan sebagai `SumberCap.MANUAL` dengan alasan wajib dan tercatat di audit, dengan
hak yang sama. Bergantung pada: tidak ada.

**Tahap 5 — halaman "Absensi saya".** *Selesai.* Staf melihat rincian hariannya
sendiri di `/absensi/saya/`. Yang belum ada: tombol "cap saya kurang" yang membuat
permintaan koreksi. Itu menunggu Tahap 4 supaya permintaannya ada tempat mendarat.

**Tahap 6 — unduh CSV.** Papan skor dan daftar pengecualian, mengikuti pola unduh
yang sudah ada di `direktur:kpi`. Bergantung pada: tidak ada.

**Tahap 7 — kunci periode.** Hanya bila **D4** dijawab "tidak boleh berubah".
Bentuknya: menyimpan hasil perhitungan satu bulan beserta salinan roster yang
dipakai, lalu menandainya terkunci. Ini membalik keputusan "skor tidak disimpan",
jadi jangan dikerjakan sebelum D4 jelas.

**Tahap 8 — cap lewat aplikasi** (bagian 8 di bawah).

## 8. Rencana lanjutan: verifikasi selfie dan lokasi

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

Tiga hal yang perlu diputuskan sebelum tahap ini dimulai, dan sebaiknya ditulis di
sini lebih dulu:

1. **Apakah cap aplikasi setara cap mesin?** Bila setara, orang bisa memilih yang
   paling menguntungkan. Bila tidak, perlu aturan mana yang menang saat keduanya ada
   pada hari yang sama.
2. **Lokasi di luar radius: ditolak atau ditandai?** Keputusan 3 Okt 2026 untuk
   `jejak` adalah menandai, tidak memblokir. Menyimpang dari itu untuk absensi perlu
   alasan tertulis, karena staf akan melihatnya sebagai aturan yang berbeda-beda.
3. **Berapa lama foto selfie disimpan?** Foto wajah adalah data pribadi; menyimpan
   selamanya tanpa alasan sulit dipertanggungjawabkan. Perlu masa simpan dan
   penghapusan otomatis.

## 9. Sebelum dipakai untuk penilaian nyata

- [ ] Roster bulan itu **lengkap di sistem**, bukan di PDF. Papan skor tidak bisa
      benar tanpa itu — hari tanpa roster muncul sebagai `TANPA_ROSTER` dan skornya 0.
- [x] Semua ID mesin terpetakan (16 dari 16; tiga di antaranya rekam-saja per **D1**).
- [ ] Daftar "Perlu dicek" bulan itu sudah ditinjau dan roster yang keliru dikoreksi.
      Pada September 2026 ada 69 hari; 17 di antaranya satu kekeliruan roster yang sama.
- [x] **D1**, **D2**, **D3**, **D5** dijawab product owner (Okt 2026).
- [x] **D4** dijawab: koreksi absen hanya Direktur Operasional, Direktur Utama, Owner.
- [ ] **D6** diputuskan: ambang penandaan `CABANG_BEDA` dipertahankan atau diubah.
- [ ] Keputusan D1-D6 disalin ke `DECISIONS.md`.
- [ ] Staf diberi tahu cara skor ini dihitung sebelum dipakai menilai mereka.
      Aturannya mudah dijelaskan, tetapi mengejutkan bila baru diketahui setelah dinilai.
- [ ] Angka satu bulan penuh dicocokkan dengan perhitungan tangan sekali lagi,
      memakai roster sistem (bukan roster dari PDF seperti verifikasi September).

## 10. Cara memakai

```bash
python manage.py petakan_id_absensi --dry-run   # periksa rencana pemetaan
python manage.py petakan_id_absensi
python manage.py impor_absensi "SEPTEMBER 2026.xlsx" --actor hansen
python manage.py laporan_absensi 2026-09                     # papan skor + pengecualian
python manage.py laporan_absensi 2026-09 --pengecualian-saja
```

Lewat halaman: **Evaluasi staf → Absensi**, tab **Impor berkas**. Batas ukuran 5 MB
per berkas, dan beberapa berkas boleh sekaligus.

Impor aman diulang: cap dikunci unik pada (staf, waktu cap), jadi mengimpor berkas
yang sama dua kali menghasilkan 0 cap baru. Berkas revisi hanya menambah
kekurangannya. Setiap impor tercatat di `AttendanceImport` beserta peringatannya dan
di audit, sehingga bisa ditelusuri siapa mengimpor apa dan kapan.
