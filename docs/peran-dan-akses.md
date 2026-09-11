# Peran dan Akses — JoDerma Staff Ops

Siapa boleh melakukan apa, dan mengapa batasnya digambar di situ.

Isi dokumen ini diambil dari `core/permissions.py` dan `accounts/models.py`.
Bila keduanya berubah, perbarui dokumen ini.

## Prinsip

**Menyembunyikan tombol bukan kontrol akses.** Setiap pembatasan ditegakkan di
sisi server. Tombol yang tidak tampil hanyalah kenyamanan; mengetik URL secara
langsung tetap ditolak dengan 403.

**Tidak ada tingkatan berdasarkan nomor akun.** Tidak ada anggapan bahwa akun
yang dibuat lebih dulu lebih berkuasa. Kewenangan hanya berasal dari peran dan
kapabilitas.

**Dua sumbu yang terpisah.** Peran menentukan pekerjaan; kapabilitas menentukan
akses ke data sensitif. Seseorang dapat memegang beberapa peran sekaligus.

## Enam peran

| Peran | Untuk siapa | Kewenangan utama |
|---|---|---|
| `STAF` | staf operasional umum | mengisi checklist, membuat komplain/masukan/kerusakan |
| `FRONT_DESK` | front desk dan kasir | kas, antrean, status pembayaran |
| `PERAWAT` | perawat | checklist ruang, tindakan yang ditugaskan |
| `SUPERVISOR` | supervisor operasional | review, verifikasi, override beralasan, roster, jadwal istirahat, triase, penutupan hari, audit |
| `ADMIN` | pengelola sistem | pengguna, peran, konfigurasi, template |
| `OWNER` | pemilik dan manajemen | laporan dan audit, hanya baca |

**Admin tidak berada di atas Supervisor.** Keduanya sejajar dengan wewenang yang
berbeda: admin mengurus sistem, supervisor mengurus operasional. Admin tanpa
kapabilitas tambahan tidak dapat membuka halaman kas, dan supervisor tidak dapat
membuka halaman pengguna.

## Tujuh kapabilitas

Kapabilitas diberikan per orang lewat **Admin ▸ Pengguna ▸ pilih akun**, terlepas
dari perannya. Setiap pemberian tercatat di audit log sebagai `PERMISSION_CHANGED`.

| Kapabilitas | Membuka |
|---|---|
| `cash.view_amounts` | melihat nominal kas |
| `cash.approve` | memverifikasi dan mengoreksi kas |
| `patient.view_detail` | melihat nama lengkap pasien, bukan inisial |
| `issue.view_restricted` | membuka komplain bertanda terbatas |
| `audit.view` | membaca audit log |
| `report.export` | mengunduh laporan CSV |
| `admin.full_access` | seluruh data bisnis sekaligus (lihat bagian berikut) |

## Kapabilitas `admin.full_access`

PRD bagian 6.3 menetapkan admin teknis **tidak** otomatis berwenang atas data
bisnis, sebab peran admin dapat dipegang vendor IT dari luar klinik. Itulah
perilaku bawaan: admin polos menerima 403 pada `/kas/` dan `/audit/`.

Bila klinik memutuskan peran admin dipegang manajemen sendiri, kapabilitas
`admin.full_access` membuka semuanya dalam satu centang:

- melihat dan mengubah nominal kas, memverifikasi, serta mengoreksi setelah verifikasi
- mengelola antrean dan melihat detail pasien
- membuka komplain bertanda terbatas
- membaca audit log dan mengekspor laporan

Kapabilitas ini sengaja **tidak** melekat otomatis pada peran ADMIN. Alasannya:

1. Pemberiannya tercatat di audit log sebagai keputusan sadar, bukan efek samping.
2. Admin teknis pihak ketiga tetap dapat dibatasi tanpa mengubah kode.
3. Dapat dicabut kembali kapan saja.

Keputusan apakah ADMIN sebaiknya otomatis mendapat akses penuh tercatat sebagai
OPEN DECISION D8 di [`../OWNER_DECISION_REVIEW.md`](../OWNER_DECISION_REVIEW.md).

## Matriks kewenangan

Diambil dari `core/permissions.py`. Kolom "kapabilitas" berarti pemegang
kapabilitas tersebut juga diizinkan, tanpa memandang peran.

| Kemampuan | Peran yang diizinkan | Kapabilitas yang juga membuka |
|---|---|---|
| Mengisi checklist | semua pengguna yang login | — |
| Melihat nominal kas | front desk, supervisor | `cash.view_amounts`, `admin.full_access` |
| Mencatat dan mengubah kas | front desk, supervisor | `admin.full_access` |
| Memverifikasi kas | front desk, supervisor | `cash.approve`, `admin.full_access` |
| Mengoreksi kas setelah verifikasi | supervisor | `cash.approve`, `admin.full_access` |
| Mengelola antrean | front desk, supervisor | `admin.full_access` |
| Melihat detail pasien | front desk, perawat, supervisor | `patient.view_detail`, `admin.full_access` |
| Menyusun roster perawat | supervisor | `admin.full_access` |
| Mengatur jadwal istirahat | supervisor | `admin.full_access` |
| Review checklist pembukaan | supervisor | — |
| Menugaskan penanggung jawab catatan | supervisor | — |
| Membuka komplain terbatas | supervisor, owner | `issue.view_restricted`, `admin.full_access` |
| Menutup hari operasional | supervisor | — |
| Membaca audit log | supervisor, owner | `audit.view`, `admin.full_access` |
| Mengekspor laporan | supervisor, owner | `report.export`, `admin.full_access` |
| Mengelola pengguna | admin, superuser bootstrap | — |
| Mengubah konfigurasi | admin, superuser bootstrap | — |
| Mengelola template checklist | admin, supervisor, superuser bootstrap | — |

## Dual-control kas

Orang yang menghitung kas tidak boleh memverifikasi hitungannya sendiri.
Verifikator kedua boleh rekan front desk **atau** supervisor. Koreksi setelah
verifikasi lebih ketat: hanya supervisor, dan wajib disertai alasan.

Aturan ini tidak dapat dilewati dengan kapabilitas apa pun, termasuk
`admin.full_access` — yang dicegah adalah orang yang sama mengisi kedua peran,
bukan kurangnya wewenang.

## Superuser bootstrap

Akun hasil `createsuperuser` diperlakukan khusus agar instalasi baru tidak buntu.
Tanpa perlakuan ini, superuser pertama tidak memiliki peran aplikasi apa pun dan
tidak dapat membuat akun siapa pun.

Superuser memperoleh hak **administratif** (pengguna, konfigurasi, template),
tetapi **tidak** memperoleh hak bisnis. Superuser tetap ditolak pada halaman kas
dan audit kecuali diberi peran atau kapabilitas yang sesuai.

Gunakan akun superuser hanya untuk bootstrap dan pemulihan darurat. Untuk
pekerjaan sehari-hari, buat akun pribadi dengan peran yang sesuai.

## Pengaman lockout

Dua tindakan yang dapat mengunci klinik dari pengelolaannya sendiri ditolak:

- admin menonaktifkan akunnya sendiri
- mencabut peran ADMIN dari admin aktif terakhir

Bila terlanjur terkunci, pemulihan dilakukan lewat shell ke server:

```bash
cd ~/joderma-ops
docker compose exec app python manage.py createsuperuser
```

## Data yang selalu terbatas

Berlaku untuk semua peran, tanpa pengecualian:

- Layar antrean bersama hanya menampilkan inisial, misalnya `B*** S.`
- Lampiran disimpan di luar direktori static dan setiap pengambilannya melewati
  pemeriksaan izin serta dicatat di audit log.
- Diagnosis, hasil pemeriksaan, foto klinis, dan catatan medis tidak disimpan
  sama sekali. Ini batas produk, bukan sekadar pengaturan izin.
