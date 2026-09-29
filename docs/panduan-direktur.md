# Panduan Direktur Operasional dan Owner

Halaman ini untuk pemegang role `AOM` (Direktur Operasional) dan `OWNER`. Semua halaman di bawah
menolak pengguna lain di server (HTTP 403), bukan hanya disembunyikan dari menu.

## Menyiapkan sekali

```bash
.venv/bin/python manage.py seed_audit_direktur --dry-run   # lihat dulu apa yang akan dibuat
.venv/bin/python manage.py seed_audit_direktur             # isi butir checklist Direktur
```

Perintah ini idempoten: menjalankannya lagi tidak menggandakan butir dan tidak menimpa teks
yang sudah disunting lewat Django admin. Untuk sengaja mengembalikan teks ke isi awal, pakai
`--update`.

Isi awalnya diambil dari Checklist Harian dan Checklist Mingguan Direktur Operasional
(Revisi 00), dengan perubahan yang diputuskan 27 September 2026:

| Siklus | Butir | Catatan |
|---|---|---|
| Harian | 8 | 6 butir dokumen + **Kas** + **Kebersihan ruang** (pengingat pengamatan langsung) |
| Mingguan | 13 | Sesuai dokumen; pemeriksaan bulanan tas emergency kit dipindah ke bulanan |
| Bulanan | 1 | Pemeriksaan bulanan tas emergency kit |

Butir "Kesiapan buka Citraland" hanya muncul untuk cabang berkode `citraland`. Deposit/keep
antrian tidak masuk checklist ini karena pencatatannya sudah dipegang Finance.

## Menu

- **Tim** — per cabang: butir checklist staf yang belum diisi hari ini, pemegang tiap fungsi
  PIC, task per orang (belum selesai / menunggu konfirmasi / selesai 7 hari), dan temuan
  Direktur yang masih terbuka. Hanya untuk membaca; tidak ada skor atau peringkat.
- **Checklist Direktur** — pilih cabang dan siklus (harian, mingguan, bulanan). Butir yang
  belum punya hasil pada periode berjalan tampil sebagai **Belum dicek**; periode mingguan
  mulai Senin, bulanan mulai tanggal 1. Kotak "Saran cek langsung" memilih tiga rincian harian
  secara acak dan tetap sama sepanjang hari.
- **Catatan** — tulis langsung atau tempel percakapan WhatsApp. Catatan hanya terlihat oleh
  penulisnya. "Jadikan task" mengirim catatan sebagai task; judul diusulkan dari baris
  pertama tanpa awalan jam dan nama pengirim WhatsApp. Catatan tidak pernah dihapus: diarsipkan
  manual dan dapat dipulihkan.

## Mencatat hasil cek

1. Pilih **Sesuai**, **Ada temuan**, atau **Tidak berlaku**; centang **Dicek langsung** bila
   Anda memeriksanya sendiri di lapangan.
2. **Ada temuan** wajib diberi keterangan dan otomatis membuat satu task tindak lanjut.
   Penerima bawaan adalah fungsi PIC butir itu bila ada pemegangnya di cabang tersebut; bila
   tidak ada, temuan tetap tercatat tanpa penerima dan terlihat di halaman Tim. Mencatat ulang
   butir yang sama tidak menggandakan task.
3. Mengubah hasil yang sudah tercatat wajib diberi alasan dan dicatat di audit sebagai
   koreksi. Isi butir disimpan sebagai snapshot pada saat dicek, jadi menyunting teks butir
   kemudian tidak mengubah riwayat.
4. Temuan ditutup dari halaman Tim dengan **Tandai selesai** beserta catatan penutupan, atau
   lewat alur konfirmasi task biasa bila penerimanya mengajukan selesai.

## Ringkasan untuk Owner dan Direktur

Owner cukup tahu apakah ada masalah, keputusan apa yang menggantung, dan kebijakan apa yang
ditetapkan — tanpa sedetail pemeriksaan Direktur. Owner hanya membaca; semua tombol aksi hanya
muncul, dan hanya diterima server, untuk Direktur.

| Menu | Isi | Owner | Direktur |
|---|---|---|---|
| **Ringkasan** | Halaman utama yang sengaja ringkas: empat kotak kuadran prioritas (gabungan kedua cabang), empat kotak angka (keputusan menggantung, kebijakan baru, menunggu konfirmasi, jadwal task), lalu infografik per cabang. Setiap kotak dapat diketuk untuk membuka detailnya | baca | baca |
| **Prioritas** | Matriks Eisenhower seluruh task yang belum selesai, dengan penyaring cabang dan sumber; dari Ringkasan terbuka satu kuadran saja | baca | baca |
| **Jadwal Task** | Gantt: setiap bar dari task dibuat sampai targetnya, 7 hari ke belakang s.d. 21 hari ke depan. Task lewat target berwarna merah dan memanjang sampai hari ini; task tanpa target bergaris | baca | baca |
| **Kanban** | Baru · Dikerjakan · Menunggu konfirmasi · Selesai 7 hari | baca | baca |
| **Keputusan** | Register perkara: menunggu, ditetapkan, kebijakan berlaku, dibatalkan | baca | catat, tetapkan, batalkan |
| **Tim** | Detail per orang dan per checklist | baca | baca + tutup temuan |

Warna kartu cabang (di bagian **Per cabang**, diketuk membuka halaman Tim pada cabang itu):

- **Merah** — ada task lewat target, temuan tanpa penerima, atau keputusan lewat tenggat.
- **Kuning** — ada temuan terbuka, task menunggu konfirmasi, keputusan menggantung, atau butir
  checklist staf belum diisi setelah klinik buka.
- **Hijau** — tidak ada di atas.

Matriks prioritas: *penting* = prioritas Tinggi/Kritis; *mendesak* = target ≤ ambang jam atau
prioritas Kritis. Ambang bawaan 48 jam, dapat diubah per cabang lewat Konfigurasi
(`dashboard.urgent_hours`). Karena task baru bawaannya prioritas Sedang, isilah prioritas saat
membuat task agar matriks bermakna.

Kolom kanban dibaca dari status penerima task, bukan dari status task utama; perpindahan kolom
tetap lewat alur ajukan selesai → konfirmasi supaya jejak audit utuh. Kanban hanya membaca.

**Keputusan.** Direktur mencatat perkara yang perlu diputuskan (siapa pemutusnya, tenggatnya),
lalu menetapkannya setelah diputuskan — oleh Owner, Direktur Utama, atau Direktur sendiri.
Centang *Kebijakan berlaku* bila keputusan itu menjadi aturan bagi staf. Perkara tidak dihapus;
yang tidak jadi diputuskan dibatalkan dengan alasan.
