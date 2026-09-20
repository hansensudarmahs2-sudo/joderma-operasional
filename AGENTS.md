# AGENTS.md — JoDerma Operasional

## Sumber kerja

- Baca `docs/AOM_MODULE_INTEGRATION_PLAN.md` seluruhnya sebelum mengerjakan integrasi AOM.
- Repository dan GitHub adalah sumber kebenaran. Jangan menganggap riwayat percakapan sebagai
  pengganti dokumen atau bukti dalam repository.
- Codex adalah satu-satunya agen pengembangan untuk proyek ini.

## Cara bekerja

- Kerjakan satu fase rencana pada satu waktu dan berhenti pada setiap approval gate.
- Mulai dari pemeriksaan read-only dan baseline test sebelum mengubah kode.
- Semua implementasi, test otomatis, test UI, migration rehearsal, dan UAT dilakukan di
  perangkat pengembangan, bukan di mini PC produksi.
- Jangan mengubah modul klinik yang tidak diperlukan untuk pekerjaan yang sedang disetujui.
- Pertahankan perubahan pengguna yang tidak terkait dan jangan membersihkan working tree tanpa
  izin eksplisit.
- Gunakan data dummy atau salinan database untuk test. Jangan memakai database produksi dalam
  test atau migration rehearsal.

## Keamanan dan approval

- Jangan mengakses, mengubah, atau melakukan deployment ke mini PC tanpa persetujuan eksplisit
  product owner untuk tahap deployment tersebut.
- Jangan mematikan AOM standalone tanpa persetujuan terpisah setelah rekonsiliasi dan masa
  observasi selesai.
- Jangan memasukkan `.env`, secret, database, backup, media privat, atau data pasien ke Git.
- Semua otorisasi harus diterapkan server-side; menyembunyikan tombol UI bukan kontrol akses.
- Hentikan pekerjaan bila test baseline gagal, scope tidak jelas, terjadi risiko kebocoran
  lintas cabang, atau backup/migrasi belum dapat diverifikasi.

## Kualitas dan Git

- Tambahkan atau perbarui test untuk setiap perubahan perilaku.
- Jalankan test code, test UI yang relevan, dan review diff sebelum commit.
- Jangan commit atau push perubahan implementasi sebelum bukti pengujian ditinjau.
- Commit dan push versi yang disetujui sebelum deployment; deploy hanya commit atau tag yang
  sama dengan yang tersimpan di GitHub.
- Laporkan file yang berubah, test yang dijalankan, hasilnya, risiko tersisa, dan approval yang
  masih diperlukan.
