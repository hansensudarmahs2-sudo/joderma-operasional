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

## Jejak kehadiran (tahap 3 paket E)

- Target akurasi > 60% (keputusan 3 Okt): jejak hanya diberi label, tidak memblokir. IP berganti
  (Telkomsel CGNAT 182.8.x dipakai bersama banyak pelanggan) tetap dicatat; pola dipelajari per
  kelompok IP (IPv4 /24, IPv6 /64) dari jejak yang lokasinya di dalam radius.
- Lokasi disimpan dibulatkan 4 desimal (~11 m) dan hanya diambil saat formulir dikirim. Belum ada
  aturan retensi; tentukan sebelum KPI dipakai formal (usul: 12 bulan).
- `client_ip` kini mengutamakan `CF-Connecting-IP`. Lewat Tailscale, header itu bisa diisi sendiri
  oleh perangkat tailnet; perangkat tailnet dianggap tepercaya.
- Tailscale paket gratis membatasi 6 **user** (perangkat milik user tidak dibatasi, 50 perangkat
  bertag). Jangan pasang Tailscale di HP staf; cukup perangkat milik klinik (di akun pengelola atau
  bertag), lalu daftarkan IP 100.x-nya di **Jejak → Perangkat & IP lazim**.
- Tailnet saat ini (3 Okt): `desktop-4bq5lkv` 100.90.94.23 (PC Windows, pernah dipakai Heni di
  Jemur), `laptop-2p49srt5` 100.101.197.21 (laptop Windows, pernah dipakai Heni/Alya),
  `joderma-jemur` 100.84.175.7 (mini PC). Tandai yang memang perangkat klinik.

## Lain-lain selama uji coba

- Hak "Melihat detail pasien" masih terpasang di hampir semua staf (dipasang manual); tinjau saat
  uji coba selesai.
- Cek ulang setelah uji coba: akun lama `hansen` (nonaktif) dan `AOM_HS` (nonaktifkan bila tidak
  dipakai).
