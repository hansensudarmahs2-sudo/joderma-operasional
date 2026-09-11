# Panduan Admin — JoDerma Staff Ops

Untuk pengelolaan pengguna, peran, dan konfigurasi. Prosedur teknis server ada di
[`runbook.md`](runbook.md) dan [`deployment-klinik.md`](deployment-klinik.md).
Penjelasan lengkap kewenangan ada di [`peran-dan-akses.md`](peran-dan-akses.md).

## Membuat akun staf

**Admin ▸ Pengguna ▸ Tambah pengguna.** Isi nama pengguna, nama tampilan, jabatan,
lalu pilih peran. Password awal yang Anda tetapkan bersifat sementara — pengguna
wajib menggantinya saat login pertama.

Panduan memilih peran:

| Pekerjaan | Peran |
|---|---|
| Front desk atau kasir | `FRONT_DESK` |
| Perawat | `PERAWAT` |
| Supervisor operasional | `SUPERVISOR` |
| Pemilik atau manajemen | `OWNER` |
| Staf lain | `STAF` |

Satu orang boleh memegang beberapa peran. Perawat yang kadang menjaga front desk
diberi `PERAWAT` dan `FRONT_DESK` sekaligus.

**Satu akun untuk satu orang.** Akun bersama membuat audit log kehilangan
maknanya — bila terjadi selisih kas, tidak ada yang dapat ditanyai.

## Memberi akses data sensitif

Kapabilitas diberikan per orang pada halaman detail pengguna, terlepas dari
perannya. Gunakan bila seseorang membutuhkan akses yang tidak tercakup perannya —
misalnya owner yang perlu mengekspor laporan, atau front desk senior yang
dipercaya memverifikasi kas.

`admin.full_access` membuka seluruh data bisnis sekaligus: kas, verifikasi,
koreksi, antrean, detail pasien, komplain terbatas, audit, dan ekspor. Berikan
hanya kepada admin yang juga bagian dari manajemen klinik. Bila suatu saat
pengelolaan sistem diserahkan ke pihak luar, jangan berikan kapabilitas ini.

Setiap perubahan peran dan kapabilitas tercatat di audit log sebagai
`PERMISSION_CHANGED` lengkap dengan nilai sebelum dan sesudah.

## Menonaktifkan akun

Staf yang berhenti **dinonaktifkan**, bukan dihapus. Hapus akun akan memutus
riwayat audit dan membuat catatan lama kehilangan penanggung jawab. Hilangkan
centang **Aktif** pada halaman detail pengguna.

Dua tindakan ditolak sistem untuk mencegah klinik terkunci dari pengelolaannya
sendiri: menonaktifkan akun Anda sendiri, dan mencabut peran ADMIN dari admin
aktif terakhir.

## Akun terkunci atau lupa password

Login gagal berulang kali akan mengunci akun sementara. Tunggu masa kuncinya
berakhir, atau setel ulang password lewat halaman detail pengguna.

Bila **semua** akun admin tidak dapat masuk, pemulihan dilakukan dari server:

```bash
ssh joderma-jemur@joderma-jemur
cd ~/joderma-ops
docker compose exec app python manage.py createsuperuser
```

Akun superuser hasil perintah ini dapat mengelola pengguna dan konfigurasi,
tetapi tidak otomatis melihat kas dan audit. Gunakan untuk memulihkan akses, lalu
kembali bekerja dengan akun pribadi.

## Template checklist

Template pembukaan dikelola lewat Django admin di `/django-admin/`. Template
bersifat **berversi**: mengubah template tidak mengubah checklist hari-hari yang
sudah lewat, karena setiap hari menyimpan salinannya sendiri.

Perubahan template sebaiknya dilakukan di luar jam sibuk dan diberitahukan ke
supervisor, agar staf tidak menemukan daftar yang berbeda tanpa penjelasan.

Apakah Django admin cukup nyaman untuk ini, atau perlu halaman khusus, tercatat
sebagai OPEN DECISION OD-D di [`../OWNER_DECISION_REVIEW.md`](../OWNER_DECISION_REVIEW.md).

## Konfigurasi klinik

**Hari Ini ▸ Konfigurasi** memuat jam operasional, minimum staf aktif, dan
ambang-ambang lain. Perubahan berlaku untuk hari berikutnya dan tercatat di audit
log.

## Pemeriksaan kesiapan

Sebelum hari pertama pemakaian nyata, dan sesudah perubahan besar:

```bash
cd ~/joderma-ops
docker compose exec app python manage.py pilot_check
```

Perintah ini hanya membaca, tidak mengubah apa pun. Yang diperiksa: template
aktif untuk keempat area, kategori tindakan yang memiliki perawat eligible, peran
yang belum terisi, dan akun yang masih memakai password demo.

## Yang bukan wewenang admin

Verifikasi kas, review pembukaan, roster perawat, triase catatan, dan penutupan
hari adalah wewenang supervisor. Admin tanpa `admin.full_access` bahkan tidak
dapat membuka halaman kas. Pemisahan ini disengaja: orang yang mengatur izin
sebaiknya bukan orang yang sama dengan yang menyetujui uang.
