# Catatan Developer

Hal yang **sengaja ditunda selama fase uji coba** (keputusan product owner 3 Oktober 2026). Semua
dicatat agar tidak lupa, bukan blocker. Diberlakukan oleh product owner sesudah uji coba lancar.

## Password

- Password akun yang di-reset massal 29 September 11.01 kembali ke `klinik123` (13 akun). Sampai
  3 Oktober yang sudah menggantinya hanya Naya dan Elvira; akun lain kemungkinan masih memakai
  password awal, termasuk `hansen1` dan `superadmin`.
- Akibatnya audit belum bisa memastikan siapa yang sebenarnya mengerjakan: pada 3 Oktober 05.28–05.39
  satu iPhone login berturut-turut sebagai alya, lia, dan heni (dan mencoba elvira).
- Halaman ganti password sudah muncul sesudah login (`must_change_password`), tetapi **belum
  dikunci**: staf bisa langsung pindah halaman. Saat diberlakukan, cukup tambahkan middleware yang
  mengalihkan semua halaman (kecuali ganti password dan logout) selama `must_change_password` aktif,
  lalu set ulang `must_change_password=True` untuk akun yang masih memakai password awal.
- Ganti password `hansen1` dan `superadmin` sendiri.

## Backup

- Backup harian di mini PC berjalan (`scripts/backup.sh`, kontainer `joderma-ops-backup`), tetapi
  arsipnya **belum terenkripsi** (`BACKUP_PASSPHRASE` kosong) dan **belum ada salinan kedua**
  (`BACKUP_SECOND_COPY_DIR` kosong): bila mini PC rusak atau hilang, backup ikut hilang.
- Saat diberlakukan: isi `BACKUP_PASSPHRASE` di `.env` mini PC (simpan passphrase di tempat aman di
  luar mini PC) dan arahkan `BACKUP_SECOND_COPY_DIR` ke diska atau perangkat lain. Uji pemulihan
  mengikuti [`runbook.md`](runbook.md).

## Lain-lain selama uji coba

- Hak "Melihat detail pasien" masih terpasang di hampir semua staf (dipasang manual); tinjau saat
  uji coba selesai.
- Cek ulang setelah uji coba: akun lama `hansen` (nonaktif) dan `AOM_HS` (nonaktifkan bila tidak
  dipakai).
