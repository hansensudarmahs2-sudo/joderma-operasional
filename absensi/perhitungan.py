"""Menghitung terlambat, lembur, dan skor dari cap absensi.

Aturan yang dipakai (keputusan product owner, Okt 2026):

- Jam shift mengikuti **cabang tempat bertugas hari itu**, bukan cabang asal:
  Jemur 14.00-22.00, Citraland 12.00-21.00. Sumbernya `jadwal.DutyRoster.clinic`
  dan `core.Clinic.open_time`/`close_time`, jadi hari perbantuan otomatis memakai
  jam cabang tujuan.
- Terlambat mengurangi skor, menit per menit.
- Lembur pulang dihitung penuh, **tanpa plafon**.
- Datang lebih awal dihitung bila **>= 60 menit**; begitu ambang itu lewat, seluruh
  menitnya dibayar (gerbang, bukan potongan).
- Skor = lembur_pulang + datang_awal - terlambat, satuan menit.

Hasil tidak disimpan. Roster bisa berubah setelah fakta (tukar off, cuti menyusul),
dan skor yang tersimpan akan diam-diam basi; menghitung ulang dari cap + roster
membuat angka selalu sesuai keadaan terbaru.

Dua hal yang sengaja tidak ditebak dan selalu muncul sebagai pengecualian: hari
tanpa roster, dan hari yang jam capnya lebih cocok ke cabang lain. Keduanya
menggeser bayaran sekitar dua jam per hari, jadi lebih baik ditanyakan daripada
dikira-kira.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field

from django.db import models
from django.utils import timezone

from core.models import Clinic
from jadwal.models import WORKING_STATUSES, DutyRoster

from .models import AttendanceDevice, AttendancePunch

# ---------------------------------------------------------------------------
# Angka yang MENGUBAH BAYARAN. Keputusan product owner; jangan diubah tanpa itu.
# ---------------------------------------------------------------------------

# Datang awal baru dihitung mulai menit ke-60. Gerbang: lolos ambang -> dibayar
# penuh, bukan dikurangi 60 dulu.
AMBANG_DATANG_AWAL_MENIT = 60

# ---------------------------------------------------------------------------
# Angka yang HANYA MENANDAI. Keduanya cuma memutuskan apakah satu hari masuk
# daftar "Perlu dicek"; tidak satu pun menyentuh terlambat, lembur, datang awal,
# atau skor. Dipilih pengembang sebagai titik awal, bukan keputusan product
# owner, dan layak ditinjau setelah ada beberapa bulan data nyata.
# ---------------------------------------------------------------------------

# Seberapa jauh jam cap boleh meleset dari jam buka/tutup cabang dan masih
# dianggap berpola cabang itu. Dipakai untuk MENDUGA cabang pada hari yang tidak
# ada di jadwal jaga, dan untuk menandai hari yang rosternya tampak keliru.
# Tidak pernah mengubah angka: lihat `duga_cabang`.
TOLERANSI_POLA_MENIT = 60

# Pulang lebih awal dari jam tutup praktis tidak pernah terjadi (kolom "pulang awal"
# pada ekspor September 2026 nyaris nol), jadi kelonggarannya kecil. Inilah yang
# membedakan hari Citraland dari hari Jemur yang datang awal.
#
# Nilainya diuji terhadap 328 hari September 2026 dengan 10 hari yang jawabannya
# sudah diketahui dari analisis manual terpisah: 0 dan 5 menit benar sepuluh-duanya
# dengan 305 hari terduga; mulai 10 menit, hari Rahayu 18 Sep (pulang 21.51, sembilan
# menit sebelum jam tutup Jemur) ikut cocok dengan Jemur dan jadi ambigu.
TOLERANSI_PULANG_AWAL_MENIT = 5

# Lembur sehari sebesar ini ditandai supaya terlihat. Tidak memotong bayaran:
# keputusan product owner (D3) adalah lembur pulang tanpa plafon dan tanpa
# persetujuan.
AMBANG_LEMBUR_PANJANG_MENIT = 180


class Pengecualian(models.TextChoices):
    TANPA_ROSTER = "TANPA_ROSTER", "Ada cap tetapi hari itu tidak ada di jadwal jaga"
    LIBUR_TAPI_NGECAP = "LIBUR_TAPI_NGECAP", "Jadwal off/cuti tetapi tetap mengecap"
    TANPA_CAP = "TANPA_CAP", "Dijadwalkan masuk tetapi tidak ada cap"
    CAP_TUNGGAL = "CAP_TUNGGAL", "Hanya satu cap; sisi lainnya tidak terhitung"
    CABANG_BEDA = "CABANG_BEDA", "Jam cap berpola cabang lain"
    CABANG_DUGAAN = "CABANG_DUGAAN", "Cabang diduga dari pola jam, bukan dari jadwal jaga"
    LEWAT_TENGAH_MALAM = "LEWAT_TENGAH_MALAM", "Cap pulang setelah tengah malam"
    LEMBUR_PANJANG = "LEMBUR_PANJANG", "Lembur sehari sangat panjang"


@dataclass
class HasilHarian:
    user: object
    tanggal: dt.date
    clinic: Clinic | None = None
    status_roster: str = ""
    status_label: str = ""
    jam_mulai: dt.datetime | None = None
    jam_selesai: dt.datetime | None = None
    masuk: dt.datetime | None = None
    keluar: dt.datetime | None = None
    # Cabangnya dari dugaan pola jam, bukan dari jadwal jaga.
    cabang_dari_dugaan: bool = False
    terlambat: int = 0
    lembur_pulang: int = 0
    datang_awal: int = 0
    datang_awal_mentah: int = 0
    pengecualian: list[str] = field(default_factory=list)
    catatan: list[str] = field(default_factory=list)

    @property
    def skor(self) -> int:
        return self.lembur_pulang + self.datang_awal - self.terlambat

    @property
    def perlu_dicek(self) -> bool:
        return bool(self.pengecualian)


@dataclass
class RingkasanStaf:
    user: object
    hari: list[HasilHarian] = field(default_factory=list)
    # Staf "rekam saja" (keputusan D1): capnya disimpan dan bisa dilihat, tetapi tidak
    # masuk papan skor. Mereka di luar skema shift dua cabang, jadi menilainya dengan
    # jam Jemur/Citraland hanya akan menghasilkan angka yang tidak berarti.
    dinilai: bool = True

    def _jumlah(self, bidang: str) -> int:
        return sum(getattr(h, bidang) for h in self.hari)

    @property
    def terlambat(self) -> int:
        return self._jumlah("terlambat")

    @property
    def lembur_pulang(self) -> int:
        return self._jumlah("lembur_pulang")

    @property
    def datang_awal(self) -> int:
        return self._jumlah("datang_awal")

    @property
    def skor(self) -> int:
        return self.lembur_pulang + self.datang_awal - self.terlambat

    @property
    def hari_kerja(self) -> int:
        return sum(1 for h in self.hari if h.masuk or h.keluar)

    @property
    def pengecualian(self) -> list[HasilHarian]:
        return [h for h in self.hari if h.perlu_dicek]


def _aware(tanggal: dt.date, jam: dt.time) -> dt.datetime:
    return timezone.make_aware(dt.datetime.combine(tanggal, jam))


def jendela_shift(clinic: Clinic, tanggal: dt.date) -> tuple[dt.datetime, dt.datetime]:
    """Awal dan akhir shift sebagai waktu mutlak.

    Bila jam tutup tidak lebih besar dari jam buka, shift itu melewati tengah malam
    dan jam tutupnya jatuh pada hari berikutnya.
    """
    mulai = _aware(tanggal, clinic.open_time)
    selesai = _aware(tanggal, clinic.close_time)
    if clinic.close_time <= clinic.open_time:
        selesai += dt.timedelta(days=1)
    return mulai, selesai


def _menit(selisih: dt.timedelta) -> int:
    return int(selisih.total_seconds() // 60)


def cabang_dari_timezone(tz: str, cabang) -> Clinic | None:
    """Cabang menurut jendela shift yang dicatat mesin sidik jari.

    Mesin menandai tiap cap pulang dengan jendela shift yang dipakai hari itu.
    Pemetaannya diturunkan dari urutan jam tutup, bukan dari pengaturan terpisah yang
    bisa lupa diisi: "Timezone I" adalah jendela yang lebih awal, "Timezone II" yang
    lebih malam. Pada dua cabang sekarang itu berarti Citraland (tutup 21.00) dan
    Jemur (tutup 22.00).

    Hanya berlaku untuk tepat dua cabang aktif. Lebih dari itu, urutan saja tidak
    cukup untuk memetakan dan keterangan mesin diabaikan — dugaan pola mengambil
    alih, dan hari yang tidak terduga tetap terlihat sebagai lubang.
    """
    if tz not in ("I", "II") or len(cabang) != 2:
        return None
    urut = sorted(cabang, key=lambda c: c.close_time)
    return urut[0] if tz == "I" else urut[1]


def duga_cabang(
    masuk, keluar, tanggal: dt.date, cabang, toleransi: int | None = None
) -> tuple[Clinic | None, str]:
    """Menduga cabang seseorang pada satu hari dari pola jam capnya.

    Jadwal jaga adalah sumber kebenaran bila ada. Untuk bulan yang rosternya belum
    terisi — atau terisi tetapi tidak bisa dipercaya, seperti September 2026 — pola
    jam masih bisa dibaca.

    Yang menentukan adalah **jam pulang**, bukan jam masuk. Alasannya tidak sepele:
    jam kerja Citraland (12.00-21.00) seluruhnya termuat di dalam "hari Jemur yang
    datang dua jam lebih awal", dan datang awal itu dibayar. Jadi jam masuk saja
    tidak pernah bisa membedakan keduanya. Jam pulang bisa: orang Citraland pulang
    sekitar 21.00, orang Jemur sekitar 22.00 atau lebih.

    Satu hari dianggap cocok dengan sebuah cabang bila:

    - **jam masuknya tidak lebih dari `toleransi` menit setelah jam buka.** Tidak ada
      batas bawah: datang awal sah dan dibayar, jadi tidak boleh menggugurkan dugaan.
    - **jam pulangnya tidak lebih awal dari jam tutup** (dengan sedikit kelonggaran).
      Lembur tidak dibatasi; yang tidak masuk akal adalah pulang jauh sebelum tutup.

    Bila dua cabang sama-sama cocok, tidak ada yang diduga. Itu terjadi pada hari
    yang memang tidak bisa dibedakan dari jamnya saja — misalnya datang pagi lalu
    pulang lewat jam tutup Jemur, yang bisa berarti hari Citraland dengan lembur
    panjang atau hari Jemur dengan datang awal. Menebak salah satunya berarti
    memilih selisih sekitar satu jam bayaran secara acak, dan arahnya selalu
    merugikan staf.

    Mengembalikan `(cabang, alasan)`; `alasan` berisi "COCOK", "GANDA", atau
    "TIDAK_COCOK".
    """
    if masuk is None:
        return None, "TIDAK_COCOK"
    # Dibaca saat dipanggil, bukan sebagai nilai bawaan parameter: nilai bawaan terikat
    # saat fungsi didefinisikan, sehingga angkanya tidak bisa diubah belakangan.
    if toleransi is None:
        toleransi = TOLERANSI_POLA_MENIT

    cocok = []
    for clinic in cabang:
        awal, akhir = jendela_shift(clinic, tanggal)
        if _menit(masuk - awal) > toleransi:
            continue  # datang terlalu jauh setelah jam buka
        if keluar is not None and _menit(akhir - keluar) > TOLERANSI_PULANG_AWAL_MENIT:
            continue  # pulang jauh sebelum jam tutup
        cocok.append(clinic)

    if len(cocok) == 1:
        return cocok[0], "COCOK"
    if len(cocok) > 1:
        return None, "GANDA"
    return None, "TIDAK_COCOK"


def hitung_hari(
    user,
    tanggal: dt.date,
    caps: list[AttendancePunch],
    roster: DutyRoster | None,
    cabang=None,
    dinilai: bool = True,
) -> HasilHarian:
    """Satu orang, satu hari kerja.

    `cabang` adalah daftar cabang aktif untuk mendeteksi kemungkinan salah cabang di
    roster; pemanggil yang mengolah banyak hari sebaiknya mengambilnya sekali lalu
    meneruskannya, agar tidak satu query per hari per staf.
    """
    hasil = HasilHarian(user=user, tanggal=tanggal)
    caps = sorted(caps, key=lambda c: c.occurred_at)
    hasil.status_roster = roster.status if roster else ""
    hasil.status_label = roster.get_status_display() if roster else "Tidak ada di jadwal"

    if not dinilai:
        # Hanya merekam jam masuk dan pulang; tidak ada jam shift untuk dibandingkan.
        if caps:
            hasil.masuk = caps[0].occurred_at
            hasil.keluar = caps[-1].occurred_at if len(caps) > 1 else None
        return hasil

    if cabang is None:
        cabang = list(Clinic.objects.filter(active=True))

    if roster is None:
        if not caps:
            return hasil
        masuk = caps[0].occurred_at
        keluar = caps[-1].occurred_at if len(caps) > 1 else None

        # Keterangan mesin lebih dulu: ia tahu jendela shift yang sebenarnya dipakai,
        # termasuk pada hari yang jamnya tidak mungkin ditebak (datang jauh lebih awal,
        # atau hanya ada satu cap).
        tz = next((c.tz_mesin for c in reversed(caps) if c.tz_mesin), "")
        duga = cabang_dari_timezone(tz, cabang)
        sumber = "jendela shift yang dicatat mesin"
        alasan = "MESIN"
        if duga is None:
            duga, alasan = duga_cabang(masuk, keluar, tanggal, cabang)
            sumber = "pola jamnya"
        if duga is None:
            # Capnya tetap ditampilkan walau tidak dinilai: hari ini perlu diisi manusia,
            # dan yang mengisinya butuh melihat jamnya.
            hasil.masuk, hasil.keluar = masuk, keluar
            hasil.pengecualian.append(Pengecualian.TANPA_ROSTER)
            hasil.catatan.append(
                "Tidak ada di jadwal jaga dan polanya tidak mengarah ke satu cabang"
                + (" (cocok dengan lebih dari satu)" if alasan == "GANDA" else "")
                + "; skor hari ini tidak dihitung."
            )
            return hasil
        clinic = duga
        hasil.cabang_dari_dugaan = True
        hasil.pengecualian.append(Pengecualian.CABANG_DUGAAN)
        hasil.catatan.append(
            f"Tidak ada di jadwal jaga; {sumber} mengarah ke {duga.name}, jadi jam itu yang dipakai."
        )
        libur = False
    else:
        clinic = roster.clinic or roster.home_clinic
        libur = roster.status not in WORKING_STATUSES

    if libur and not caps:
        return hasil
    if not caps:
        hasil.clinic = clinic
        hasil.pengecualian.append(Pengecualian.TANPA_CAP)
        return hasil
    if libur:
        # Tetap dihitung dengan jam cabang asal supaya lemburnya tidak hilang diam-diam,
        # tetapi ditandai karena shift hari libur tidak pernah benar-benar terjadwal.
        clinic = roster.home_clinic or clinic
        hasil.pengecualian.append(Pengecualian.LIBUR_TAPI_NGECAP)
        hasil.catatan.append(
            f"Jadwal {roster.get_status_display().lower()}; dihitung memakai jam {clinic.name}."
        )

    hasil.clinic = clinic
    hasil.jam_mulai, hasil.jam_selesai = jendela_shift(clinic, tanggal)

    if len(caps) == 1:
        hasil.pengecualian.append(Pengecualian.CAP_TUNGGAL)
        satu = caps[0]
        dekat_awal = abs(_menit(satu.occurred_at - hasil.jam_mulai))
        dekat_akhir = abs(_menit(satu.occurred_at - hasil.jam_selesai))
        if dekat_awal <= dekat_akhir:
            hasil.masuk = satu.occurred_at
            hasil.catatan.append("Ditafsir cap masuk; cap pulang tidak ada.")
        else:
            hasil.keluar = satu.occurred_at
            hasil.catatan.append("Ditafsir cap pulang; cap masuk tidak ada.")
    else:
        hasil.masuk, hasil.keluar = caps[0].occurred_at, caps[-1].occurred_at

    if hasil.masuk is not None:
        selisih = _menit(hasil.masuk - hasil.jam_mulai)
        hasil.terlambat = max(0, selisih)
        hasil.datang_awal_mentah = max(0, -selisih)
        if hasil.datang_awal_mentah >= AMBANG_DATANG_AWAL_MENIT:
            hasil.datang_awal = hasil.datang_awal_mentah

    if hasil.keluar is not None:
        hasil.lembur_pulang = max(0, _menit(hasil.keluar - hasil.jam_selesai))
        if timezone.localtime(hasil.keluar).date() != tanggal:
            hasil.pengecualian.append(Pengecualian.LEWAT_TENGAH_MALAM)
        if hasil.lembur_pulang >= AMBANG_LEMBUR_PANJANG_MENIT:
            hasil.pengecualian.append(Pengecualian.LEMBUR_PANJANG)

    if not hasil.cabang_dari_dugaan:
        tz = next((c.tz_mesin for c in reversed(caps) if c.tz_mesin), "")
        duga = cabang_dari_timezone(tz, cabang) or duga_cabang(
            hasil.masuk, hasil.keluar, tanggal, cabang
        )[0]
        if duga is not None and duga.pk != clinic.pk:
            hasil.pengecualian.append(Pengecualian.CABANG_BEDA)
            hasil.catatan.append(
                f"Jam capnya berpola {duga.name}; periksa cabang di jadwal jaga."
            )
    return hasil


def hitung_periode(mulai: dt.date, selesai: dt.date, users=None) -> list[RingkasanStaf]:
    """Ringkasan per staf untuk satu rentang tanggal, urut skor tertinggi.

    Staf yang ID mesinnya ditandai `recording_only` ikut keluar di sini supaya capnya
    tetap bisa dilihat, tetapi dengan `dinilai=False`, tanpa skor dan tanpa
    pengecualian. Pemanggil yang menampilkan papan skor menyaringnya sendiri.
    """
    caps = AttendancePunch.objects.filter(shift_date__range=(mulai, selesai)).select_related("user")
    roster = DutyRoster.objects.filter(date__range=(mulai, selesai)).select_related(
        "user", "clinic", "home_clinic"
    )
    if users is not None:
        ids = [u.pk for u in users]
        caps = caps.filter(user_id__in=ids)
        roster = roster.filter(user_id__in=ids)

    per_cap: dict[tuple[int, dt.date], list[AttendancePunch]] = defaultdict(list)
    orang: dict[int, object] = {}
    for c in caps:
        per_cap[(c.user_id, c.shift_date)].append(c)
        orang[c.user_id] = c.user
    per_roster: dict[tuple[int, dt.date], DutyRoster] = {}
    for r in roster:
        per_roster[(r.user_id, r.date)] = r
        orang.setdefault(r.user_id, r.user)
    if users is not None:
        for u in users:
            orang.setdefault(u.pk, u)

    cabang = list(Clinic.objects.filter(active=True))
    rekam_saja = set(
        AttendanceDevice.objects.filter(recording_only=True).values_list("user_id", flat=True)
    )

    ringkasan = []
    for uid, user in orang.items():
        staf = RingkasanStaf(user=user, dinilai=uid not in rekam_saja)
        tanggal = mulai
        while tanggal <= selesai:
            kunci = (uid, tanggal)
            if kunci in per_cap or kunci in per_roster:
                staf.hari.append(
                    hitung_hari(
                        user, tanggal, per_cap.get(kunci, []), per_roster.get(kunci),
                        cabang, dinilai=staf.dinilai,
                    )
                )
            tanggal += dt.timedelta(days=1)
        ringkasan.append(staf)

    # Yang dinilai lebih dulu, lalu skor tertinggi; yang "rekam saja" selalu di bawah
    # karena skornya nol menurut konstruksi, bukan menurut kinerja.
    ringkasan.sort(key=lambda s: (not s.dinilai, -s.skor, str(s.user)))
    return ringkasan


def laporan_pengecualian(mulai: dt.date, selesai: dt.date, users=None) -> list[HasilHarian]:
    """Semua hari yang perlu dilihat manusia, urut tanggal lalu nama."""
    hari = [h for staf in hitung_periode(mulai, selesai, users) for h in staf.hari if h.perlu_dicek]
    hari.sort(key=lambda h: (h.tanggal, str(h.user)))
    return hari
