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

# Seberapa jauh jam cap harus lebih cocok ke cabang lain sebelum hari itu
# ditandai CABANG_BEDA. Terlalu kecil: banyak temuan palsu pada hari lembur
# panjang. Terlalu besar: kekeliruan roster lolos (mis. Rahayu 18 Sep 2026,
# selisih 78, lolos pada ambang 90).
AMBANG_CURIGA_CABANG_MENIT = 90

# Lembur sehari sebesar ini ditandai supaya terlihat. Tidak memotong bayaran:
# keputusan product owner (D3) adalah lembur pulang tanpa plafon dan tanpa
# persetujuan.
AMBANG_LEMBUR_PANJANG_MENIT = 180


class Pengecualian(models.TextChoices):
    TANPA_ROSTER = "TANPA_ROSTER", "Ada cap tetapi hari itu tidak ada di jadwal jaga"
    LIBUR_TAPI_NGECAP = "LIBUR_TAPI_NGECAP", "Jadwal off/cuti tetapi tetap mengecap"
    TANPA_CAP = "TANPA_CAP", "Dijadwalkan masuk tetapi tidak ada cap"
    CAP_TUNGGAL = "CAP_TUNGGAL", "Hanya satu cap; sisi lainnya tidak terhitung"
    CABANG_BEDA = "CABANG_BEDA", "Jam cap lebih cocok dengan cabang lain"
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


def _cabang_lebih_cocok(masuk, keluar, dipakai: Clinic, tanggal: dt.date, cabang) -> Clinic | None:
    """Cabang lain yang jam bukanya jauh lebih pas dengan cap hari itu.

    Dipakai untuk menandai kemungkinan salah cabang di roster. Ini penting karena
    salah cabang tidak menghasilkan selisih kecil: jam shift kedua cabang berbeda
    dua jam, sehingga satu baris keliru menggeser bayaran sekitar dua jam.
    """
    if masuk is None or keluar is None:
        return None

    def biaya(clinic: Clinic) -> int:
        awal, akhir = jendela_shift(clinic, tanggal)
        return abs(_menit(masuk - awal)) + abs(_menit(keluar - akhir))

    terbaik = min(cabang, key=biaya, default=None)
    if terbaik is None or terbaik.pk == dipakai.pk:
        return None
    return terbaik if biaya(dipakai) - biaya(terbaik) >= AMBANG_CURIGA_CABANG_MENIT else None


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

    if roster is None:
        if caps:
            hasil.pengecualian.append(Pengecualian.TANPA_ROSTER)
            hasil.catatan.append("Jam shift tidak diketahui; skor hari ini tidak dihitung.")
        return hasil

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

    if cabang is None:
        cabang = list(Clinic.objects.filter(active=True))
    lain = _cabang_lebih_cocok(hasil.masuk, hasil.keluar, clinic, tanggal, cabang)
    if lain is not None:
        hasil.pengecualian.append(Pengecualian.CABANG_BEDA)
        hasil.catatan.append(
            f"Jam capnya lebih cocok dengan {lain.name}; periksa cabang di jadwal jaga."
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
