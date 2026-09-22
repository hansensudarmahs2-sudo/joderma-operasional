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

## Sebelas peran

| Peran | Untuk siapa | Kewenangan utama |
|---|---|---|
| `STAF` | staf operasional umum | mengisi checklist, membuat komplain/masukan/kerusakan |
| `FRONT_DESK` | koordinator kasir | kas dan rekonsiliasi transaksi |
| `PERAWAT` | perawat | checklist ruang dan tally jumlah tindakan |
| `APOTEKER` | apoteker | stok farmasi, cold chain, obat emergensi, verifikasi stok ruangan |
| `ASISTEN_APOTEKER` | asisten apoteker | menerima dan memproses order produk online bersama apoteker |
| `ONLINE` | koordinator online dan reservasi | kebersihan awal, jadwal dokter, booking, order produk, serah-terima tindakan |
| `SUPERVISOR` | koordinator shift | review, verifikasi, override beralasan, roster, jadwal istirahat, triase, penutupan hari, audit |
| `PIC` | PIC fungsi di cabang | delegasi dan tindak lanjut operasional dalam cabangnya |
| `AOM` | Area Operational Manager | koordinasi lintas cabang, laporan rahasia sesuai scope, dan publikasi masukan |
| `ADMIN` | pengelola sistem | pengguna, peran, konfigurasi, template |
| `OWNER` | pemilik dan manajemen | laporan dan audit, hanya baca |

**Admin tidak berada di atas Supervisor.** Keduanya sejajar dengan wewenang yang
berbeda: admin mengurus sistem, supervisor mengurus operasional. Admin tanpa
kapabilitas tambahan tidak dapat membuka halaman kas, dan supervisor tidak dapat
membuka halaman pengguna.

`AOM` dan `PIC` adalah role akses yang dapat diberikan atau dicabut. Keduanya
tidak boleh diikat ke nama orang tertentu di kode. Jabatan organisasi formal
disimpan terpisah dari role akses; fungsi PIC juga selalu bercabang dan memiliki
periode aktif.

## Sepuluh kapabilitas

Kapabilitas diberikan per orang lewat **Admin ▸ Pengguna ▸ pilih akun**, terlepas
dari perannya. Setiap pemberian tercatat di audit log sebagai `PERMISSION_CHANGED`.

| Kapabilitas | Membuka |
|---|---|
| `cash.view_amounts` | melihat nominal kas |
| `cash.approve` | memverifikasi dan mengoreksi kas |
| `patient.view_detail` | melihat nama lengkap pasien, bukan inisial |
| `issue.view_restricted` | membuka komplain bertanda terbatas |
| `report.view_confidential` | membuka laporan rahasia dalam scope cabang yang diizinkan |
| `suggestion.publish` | memublikasikan masukan ke cabang setelah review |
| `user.manage` | mengelola pengguna tanpa menjadikan akun tersebut admin teknis |
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
| Menugaskan penanggung jawab catatan | supervisor, PIC, AOM | — |
| Membuka komplain terbatas | supervisor, AOM, owner | `issue.view_restricted`, `report.view_confidential`, `admin.full_access` |
| Menutup hari operasional | supervisor | — |
| Membaca audit log | supervisor, AOM, owner | `audit.view`, `admin.full_access` |
| Mengekspor laporan | supervisor, AOM, owner | `report.export`, `admin.full_access` |
| Mengelola pengguna | admin, superuser bootstrap | `user.manage`, `admin.full_access` |
| Mengubah konfigurasi | admin, superuser bootstrap | — |
| Mengelola template checklist | admin, supervisor, superuser bootstrap | — |

## Scope cabang

Pengguna biasa hanya melihat cabang tempat ia punya `UserRole`. `AOM` dan
`OWNER` dapat membaca lintas cabang sesuai kebutuhan koordinasi dan pengawasan.
URL langsung tetap diperiksa server-side: objek issue, action item, lampiran,
dan aset dari cabang lain harus menghasilkan 403 untuk pengguna tanpa scope.

## Task dan delegasi

Task memakai `ActionItem` sebagai inti lama, lalu penerima barunya disimpan di
`TaskAssignment`. `ActionItem.owner` tetap ada untuk kompatibilitas task lama.

Pemberi tugas dapat mengirim task ke satu user, beberapa user, fungsi PIC, role
dalam cabang, atau seluruh staf cabang. Daftar penerima disimpan sebagai
snapshot saat dikirim, sehingga perubahan role/PIC setelahnya tidak mengubah
histori task tersebut.

Penerima hanya dapat mengajukan selesai. Konfirmasi final dilakukan pemberi
tugas, AOM berwenang, atau PIC pemberi tugas sesuai scope; penerima task tidak
dapat mengonfirmasi pekerjaannya sendiri.

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
