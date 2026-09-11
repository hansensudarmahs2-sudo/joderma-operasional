# UAT Issue Register — JoDerma Staff Ops

**Versi:** 1.0
**Periode pilot:** ____ s/d ____ (5 hari operasional)
**Pencatat:** Supervisor (pilot lead), dibantu admin teknis

Semua temuan selama pilot dicatat di sini — termasuk yang terlihat sepele. Satu baris
per temuan. Gunakan ID skenario dari `UAT_TEST_SCENARIOS.md` bila temuan berasal dari
skenario tertentu.

---

## 1. Cara mencatat

1. Beri **ID** berurutan: `UAT-001`, `UAT-002`, dst.
2. Isi minimal: judul, modul, pelapor, severity, langkah reproduksi, hasil yang
   diharapkan vs yang terjadi.
3. Status awal selalu **New**.
4. Jangan menghapus baris. Temuan yang ternyata bukan masalah diberi status
   **Closed** dengan catatan "bukan cacat — <alasan>".
5. Temuan yang sebenarnya permintaan fitur baru diberi status **Deferred** dan
   dipindahkan ke daftar backlog fase 2 di bagian 6.

---

## 2. Definisi severity

| Severity | Definisi | Contoh | Batas waktu penanganan |
|---|---|---|---|
| **Critical** | Data hilang/rusak, data sensitif bocor, aplikasi tidak dapat dipakai, atau salah hitung uang. Memicu evaluasi stop criteria. | Nominal kas terlihat staf tanpa izin; entri antrean hilang; total pecahan salah | Hentikan pekerjaan terkait, perbaiki hari itu juga |
| **High** | Alur kerja utama terhambat dan tidak ada jalan memutar yang wajar; atau aturan bisnis dilanggar tanpa jejak audit. | Kas tidak bisa diverifikasi sama sekali; override tidak tercatat di audit | Perbaiki sebelum hari pilot berikutnya |
| **Medium** | Mengganggu tetapi ada jalan memutar; atau salah label/istilah yang membingungkan staf. | Terlalu banyak klik untuk tugas rutin; istilah tidak dipahami staf | Perbaiki sebelum go-live |
| **Low** | Kosmetik atau peningkatan kenyamanan. | Perataan teks, urutan kolom, teks bantuan kurang jelas | Boleh setelah go-live |

**Aturan penting:** severity ditentukan oleh **dampak pada operasional dan data**, bukan
oleh sulitnya perbaikan. Temuan pada skenario **SEC** atau **ADM-02** otomatis minimal
**High**; bila menyangkut kebocoran data, otomatis **Critical**.

---

## 3. Definisi status

| Status | Arti | Siapa yang mengubah |
|---|---|---|
| **New** | Baru dilaporkan, belum diverifikasi orang lain | Pelapor |
| **Confirmed** | Sudah direproduksi oleh orang kedua; memang cacat | Supervisor / admin teknis |
| **Fixing** | Sedang diperbaiki | Admin teknis |
| **Ready for Retest** | Perbaikan selesai, menunggu diuji ulang oleh pelapor | Admin teknis |
| **Closed** | Diuji ulang dan benar-benar teratasi (atau dinyatakan bukan cacat) | Pelapor / supervisor |
| **Deferred** | Nyata tetapi sengaja ditunda ke fase berikutnya, dengan persetujuan owner | Owner |

Alur normal: `New → Confirmed → Fixing → Ready for Retest → Closed`
Alur alternatif: `New → Confirmed → Deferred` (butuh persetujuan owner)
Bila retest gagal: `Ready for Retest → Confirmed` (kembali, catat di riwayat)

---

## 4. Daftar temuan

> Salin blok template di bawah untuk setiap temuan baru.

### Template

```
### UAT-000 — <judul singkat>

| Field | Isi |
|---|---|
| Tanggal ditemukan | |
| Pelapor | |
| Modul | Pembukaan / Kas / Antrean / Giliran Perawat / Jadwal / Komplain / Masukan / Kerusakan / Laporan / Admin / Keamanan |
| Skenario terkait | mis. CSH-04 (kosongkan bila ditemukan di luar skenario) |
| Severity | Critical / High / Medium / Low |
| Status | New |
| Langkah reproduksi | 1. ... 2. ... 3. ... |
| Hasil diharapkan | |
| Hasil aktual | |
| Bukti | Foto layar / nomor catatan / correlation ID dari halaman error |
| Dampak operasional | Apa yang tidak bisa dikerjakan staf karena ini |
| Jalan memutar sementara | |
| Penanggung jawab | |
| Perbaikan yang dilakukan | |
| Tanggal retest | |
| Hasil retest | |
| Tanggal ditutup | |
```

---

### Contoh terisi (hapus saat pilot dimulai)

### UAT-000 — Contoh: pesan error kas tidak menyebutkan pecahan mana yang salah

| Field | Isi |
|---|---|
| Tanggal ditemukan | 2026-09-12 |
| Pelapor | Kasir A |
| Modul | Kas |
| Skenario terkait | CSH-02 |
| Severity | Low |
| Status | New |
| Langkah reproduksi | 1. Isi jumlah pecahan dengan huruf. 2. Simpan. |
| Hasil diharapkan | Pesan menyebut baris pecahan mana yang bermasalah |
| Hasil aktual | Pesan umum: "Nilai jumlah harus berupa angka bulat" |
| Bukti | Foto layar 12.40 |
| Dampak operasional | Kasir perlu memeriksa 10 baris satu per satu |
| Jalan memutar sementara | Periksa manual |
| Penanggung jawab | Admin teknis |
| Perbaikan yang dilakukan | |
| Tanggal retest | |
| Hasil retest | |
| Tanggal ditutup | |

---

## 5. Rekapitulasi

Perbarui setiap akhir hari pilot.

| Severity | New | Confirmed | Fixing | Ready for Retest | Closed | Deferred | Total |
|---|---:|---:|---:|---:|---:|---:|---:|
| Critical | | | | | | | |
| High | | | | | | | |
| Medium | | | | | | | |
| Low | | | | | | | |
| **Total** | | | | | | | |

### Grafik harian (isi jumlah temuan baru per hari)

| Hari | Critical | High | Medium | Low | Total baru |
|---|---:|---:|---:|---:|---:|
| Hari 1 | | | | | |
| Hari 2 | | | | | |
| Hari 3 | | | | | |
| Hari 4 | | | | | |
| Hari 5 | | | | | |

**Sinyal bahaya:** temuan Critical baru pada dua hari berturut-turut memicu evaluasi
stop criteria T6 (lihat `UAT_5_DAY_PILOT_PLAN.md` bagian 6).

**Syarat lulus UAT:** tidak ada Critical berstatus selain Closed; setiap High berstatus
Closed atau Deferred dengan persetujuan owner tertulis.

---

## 6. Backlog fase 2 (temuan yang bukan cacat)

Permintaan fitur yang muncul selama pilot dicatat di sini, **tidak dikerjakan selama
pilot**, dan dibahas owner setelah go-live.

| No | Kebutuhan | Diusulkan oleh | Alasan operasional | Perkiraan nilai (tinggi/sedang/rendah) |
|---|---|---|---|---|
| B1 | | | | |
| B2 | | | | |
| B3 | | | | |

---

## 7. Keputusan yang muncul selama pilot (OPEN DECISION)

Hal yang **tidak boleh diputuskan sepihak oleh tim teknis** dan menunggu keputusan owner.
Rujuk juga `OWNER_DECISION_REVIEW.md`.

| No | Pertanyaan ke owner | Muncul dari | Tanggal | Keputusan owner | Tanggal diputuskan |
|---|---|---|---|---|---|
| OD-1 | | | | | |
| OD-2 | | | | | |
| OD-3 | | | | | |
