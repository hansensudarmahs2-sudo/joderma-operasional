# Panduan Direktur Operasional

Halaman ini untuk pemegang role `AOM` (Direktur Operasional). Semua halaman di bawah menolak
pengguna lain di server (HTTP 403), bukan hanya disembunyikan dari menu.

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
