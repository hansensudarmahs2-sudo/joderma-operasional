# AGENTS.md — JoDerma Operasional

## Sumber kerja

- Baca `docs/AOM_MODULE_INTEGRATION_PLAN.md` seluruhnya sebelum mengerjakan integrasi AOM.
- Repository dan GitHub adalah sumber kebenaran. Jangan menganggap riwayat percakapan sebagai
  pengganti dokumen atau bukti dalam repository.
- Agen pengembangan apa pun (mis. Codex atau Claude) wajib mengikuti seluruh aturan di file ini.
  Hanya satu agen yang bekerja pada working tree yang sama pada satu waktu.

## Bekerja paralel: satu working tree satu pihak

Aturan "satu agen per working tree" tidak cukup diucapkan; ia harus dibuat tidak mungkin
dilanggar. Yang terjadi bila tidak: pada 6 Okt 2026 sebuah agen membuat branch
`absensi-jam-kerja`, lalu pekerjaan Kas yang dikerjakan paralel ikut ter-commit ke branch
itu — karena working tree-nya memang sedang berada di sana. `master` jadi tidak punya
pekerjaan Kas sama sekali, dan dua pekerjaan yang tidak berhubungan jadi saling mengunci.
Pemulihannya cherry-pick + rebase, dan hanya mudah karena belum ada yang di-push.

**Protokol:** satu pihak satu direktori kerja. Gunakan `git worktree`, bukan `git switch`
bergantian di direktori yang sama.

```bash
# Direktori utama tetap di master dan dipegang product owner.
cd ~/Desktop/joderma-operasional
git worktree add ../joderma-<topik> -b <topik>   # agen bekerja di sini
git worktree list                                # siapa memegang branch apa
git worktree remove ../joderma-<topik>           # sesudah branch-nya di-merge
```

- **Sebelum commit pertama**, agen menjalankan `git worktree list` dan `git branch --show-current`,
  lalu menyebutkan di laporannya direktori dan branch mana yang ia pegang.
- **Satu branch hanya boleh di-checkout satu worktree.** Git menolak yang kedua; penolakan itu
  fitur, bukan halangan.
- **Jangan `git switch` di direktori milik pihak lain.** Bila butuh branch lain, tambah worktree.
- `data/`, `.venv/`, dan `private_media/` tidak ikut Git, jadi tetap tinggal di direktorinya
  masing-masing. Worktree baru tidak punya `.venv` dan tidak punya database; itu wajar, dan
  untuk pekerjaan Git saja memang tidak diperlukan.
- Bila dua pekerjaan terlanjur tercampur dalam satu branch, periksa dulu apakah berkasnya
  beririsan (`git show --name-only <commit>`). Bila tidak beririsan, pisahkan dengan
  cherry-pick ke `master` lalu `git rebase master` pada branch fitur — aman selama belum
  di-push.

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
