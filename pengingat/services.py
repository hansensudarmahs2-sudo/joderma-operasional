"""Penjadwalan dan aksi kartu Pengingat Harian DO (kebutuhan bagian 3 dan 4).

Kartu dibentuk sekali per hari kerja, saat DO pertama kali membuka Ringkasan, lalu dikunci
(keputusan PO 14 Okt 2026). Pemilihan butir (`pilih`) murni dan diuji dengan tanggal tiruan:

1. Butir paksa yang tanggalnya sudah tiba dan belum ditangani: di luar kuota.
2. Sisanya diberi skor = hari sejak terakhir diingatkan ÷ interval kelasnya. Belum pernah
   diingatkan = skor tak terhingga, diurutkan menurut kelas lalu urutan katalog.
3. Hanya skor ≥ 1 yang jatuh tempo; skor tertinggi dulu, lalu kelas A, B, C.
4. Kuota diisi dengan variasi sasaran: bila sasaran calon sama persis dengan butir yang sudah
   terpilih, ambil calon berikutnya yang berbeda (bila ada).
5. Jatuh tempo kurang dari kuota: kartu berisi lebih sedikit.

"Terakhir diingatkan" = tanggal terakhir di log Sudah diingatkan (cabang mana pun) atau tanggal
kartu tempat butir itu dilewati: Lewati memundurkan jadwal satu interval tanpa masuk riwayat.
"""
from __future__ import annotations

import datetime as dt
import math
import re
from dataclasses import dataclass

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from audit.models import AuditAction
from audit.services import log_event
from core.models import Clinic, local_today
from core.permissions import can_manage_pengingat as can_manage
from core.permissions import can_view_pengingat_history as can_view_history

from .models import Butir, Diingatkan, Kartu, Materi, Paksa, Pengaturan, Saluran, Sebab, Status

ULANGAN_HARI = (1, 3, 7, 14, 30)
KELAS_URUT = {"A": 0, "B": 1, "C": 2}


# --- Izin (`core.permissions.can_manage_pengingat` / `can_view_pengingat_history`) -----------


def _assert_manage(user) -> None:
    if not can_manage(user):
        raise PermissionDenied("Pengingat harian hanya untuk Direktur Operasional.")


# --- Hari kerja --------------------------------------------------------------------------------


def is_workday(day: dt.date, cfg: Pengaturan) -> bool:
    return day.weekday() in (cfg.hari_kerja or [])


def next_workday(day: dt.date, cfg: Pengaturan) -> dt.date:
    """Hari kerja sesudah `day` (paling jauh seminggu; tanpa hari kerja sama sekali = besok)."""
    for i in range(1, 8):
        cand = day + dt.timedelta(days=i)
        if is_workday(cand, cfg):
            return cand
    return day + dt.timedelta(days=1)


def on_or_after_workday(day: dt.date, cfg: Pengaturan) -> dt.date:
    return day if is_workday(day, cfg) else next_workday(day, cfg)


# --- Pemilihan butir (murni) -------------------------------------------------------------------


def skor(anchor: dt.date | None, day: dt.date, interval: int) -> float:
    if anchor is None:
        return math.inf
    return (day - anchor).days / max(1, interval)


def pilih(day: dt.date, materi: list, anchors: dict, forced_ids: list, cfg: Pengaturan) -> list:
    """Materi untuk kartu `day`: butir paksa (urut `forced_ids`) lalu butir kuota."""
    if not is_workday(day, cfg):
        return []
    by_id = {m.pk: m for m in materi}
    forced = [by_id[i] for i in forced_ids if i in by_id and by_id[i].aktif]
    forced_set = {m.pk for m in forced}
    due = []
    for m in materi:
        if not m.aktif or m.pk in forced_set:
            continue
        s = skor(anchors.get(m.pk), day, cfg.interval(m.kelas))
        if s >= 1:
            due.append((s, m))
    due.sort(key=lambda sm: (-sm[0], KELAS_URUT.get(sm[1].kelas, 9), sm[1].urutan, sm[1].kode))
    chosen = list(forced)
    calon = [m for _, m in due]
    picks = []
    while len(picks) < cfg.kuota and calon:
        seen = [set(c.sasaran) for c in chosen]
        idx = next((i for i, m in enumerate(calon) if set(m.sasaran) not in seen), 0)
        m = calon.pop(idx)
        picks.append(m)
        chosen.append(m)
    return forced + picks


# --- Data dari basis data ----------------------------------------------------------------------


def anchors_until(day: dt.date) -> dict:
    """Per materi: tanggal terakhir diingatkan atau dilewati, sampai dengan `day`."""
    out = dict(Diingatkan.objects.filter(tanggal__lte=day).values("materi").annotate(t=Max("tanggal"))
               .values_list("materi", "t"))
    skipped = (Butir.objects.filter(status=Status.DILEWATI, kartu__tanggal__lte=day).values("materi")
               .annotate(t=Max("kartu__tanggal")).values_list("materi", "t"))
    for mid, t in skipped:
        if mid not in out or t > out[mid]:
            out[mid] = t
    return out


def pending_forced(day: dt.date) -> dict:
    """Materi id -> Paksa tertua yang sudah tiba (≤ `day`) dan belum ditangani."""
    out = {}
    for p in Paksa.objects.filter(selesai_pada__isnull=True, tanggal__lte=day, materi__aktif=True).order_by("tanggal", "id"):
        out.setdefault(p.materi_id, p)
    return out


def kartu_untuk(day: dt.date | None = None) -> Kartu | None:
    """Kartu hari kerja `day`; dibentuk saat pertama kali diminta, lalu tidak berubah. Hari libur: None."""
    day = day or local_today()
    cfg = Pengaturan.get()
    existing = Kartu.objects.filter(tanggal=day).first()
    if existing or not is_workday(day, cfg):
        return existing
    materi = list(Materi.objects.all())
    forced = pending_forced(day)
    chosen = pilih(day, materi, anchors_until(day), list(forced), cfg)
    try:
        with transaction.atomic():
            kartu = Kartu.objects.create(tanggal=day)
            Butir.objects.bulk_create([
                Butir(kartu=kartu, materi=m, paksa=forced.get(m.pk), urutan=i) for i, m in enumerate(chosen)
            ])
    except IntegrityError:  # dua DO membuka bersamaan: pakai kartu yang lebih dulu jadi
        return Kartu.objects.get(tanggal=day)
    return kartu


def jadwalkan_ulangan(materi: Materi, *, actor=None, today: dt.date | None = None) -> list[Paksa]:
    """Ulangan materi baru: hari ke-1, 3, 7, 14, 30 sesudah tanggal sosialisasi (bergeser ke hari
    kerja berikutnya bila jatuh di hari libur). Tanggal yang sudah lewat tidak dibuat."""
    if not materi.tanggal_sosialisasi:
        return []
    cfg = Pengaturan.get()
    today = today or local_today()
    made = []
    for k in ULANGAN_HARI:
        tgl = on_or_after_workday(materi.tanggal_sosialisasi + dt.timedelta(days=k), cfg)
        if tgl >= today and not Paksa.objects.filter(materi=materi, sebab=Sebab.ULANGAN, tanggal=tgl).exists():
            made.append(Paksa.objects.create(materi=materi, tanggal=tgl, sebab=Sebab.ULANGAN, dibuat_oleh=actor))
    return made


# --- Pratinjau ---------------------------------------------------------------------------------


@dataclass
class HariPratinjau:
    tanggal: dt.date
    libur: bool
    materi: list


def pratinjau(day: dt.date | None = None, days: int = 7) -> list[HariPratinjau]:
    """Perkiraan 7 hari ke depan: algoritma yang sama, dengan anggapan semua butir hari-hari
    sebelumnya (termasuk kartu hari ini) ditandai Sudah diingatkan."""
    day = day or local_today()
    cfg = Pengaturan.get()
    materi = list(Materi.objects.all())
    anchors = anchors_until(day)
    kartu = Kartu.objects.filter(tanggal=day).first()
    used_paksa = set()
    if kartu:
        for b in kartu.butir.all():
            anchors[b.materi_id] = day
            if b.paksa_id:
                used_paksa.add(b.paksa_id)
    pending = list(Paksa.objects.filter(selesai_pada__isnull=True, tanggal__lte=day + dt.timedelta(days=days),
                                        materi__aktif=True).exclude(pk__in=used_paksa).order_by("tanggal", "id"))
    out = []
    for i in range(1, days + 1):
        d = day + dt.timedelta(days=i)
        if not is_workday(d, cfg):
            out.append(HariPratinjau(d, True, []))
            continue
        forced_ids = []
        for p in pending:
            if p.tanggal <= d and p.materi_id not in forced_ids:
                forced_ids.append(p.materi_id)
        chosen = pilih(d, materi, anchors, forced_ids, cfg)
        pending = [p for p in pending if p.materi_id not in forced_ids or p.tanggal > d]
        for m in chosen:
            anchors[m.pk] = d
        out.append(HariPratinjau(d, False, chosen))
    return out


# --- Tampilan butir ----------------------------------------------------------------------------


def nama_cabang(clinic: Clinic) -> str:
    return re.sub(r"^JoDerma\s+", "", clinic.name)


def teks_wa(materi: Materi) -> str:
    """Teks WA siap salin: {cabang} diganti nama cabang, atau dihapus bila untuk kedua cabang."""
    teks = materi.teks_wa or ""
    if materi.clinic_id:
        return teks.replace("{cabang}", nama_cabang(materi.clinic))
    return re.sub(r"[ \t]*\{cabang\}", "", teks)


def terakhir_per_cabang(materi_ids, clinics) -> dict:
    """{materi_id: [(cabang, tanggal|None), ...]}; log untuk kedua cabang dihitung di keduanya."""
    rows = list(Diingatkan.objects.filter(materi_id__in=materi_ids).values_list("materi_id", "clinic_id", "tanggal"))
    out = {}
    for mid in materi_ids:
        out[mid] = []
        for c in clinics:
            dates = [t for m, cid, t in rows if m == mid and cid in (None, c.pk)]
            out[mid].append((nama_cabang(c), max(dates) if dates else None))
    return out


def kartu_context(user, day: dt.date | None = None) -> dict | None:
    """Data kartu "Pengingat hari ini" untuk Ringkasan Direktur; None bila bukan DO."""
    if not can_manage(user):
        return None
    day = day or local_today()
    kartu = kartu_untuk(day)
    clinics = list(Clinic.objects.order_by("id"))
    butir = list(kartu.butir.select_related("materi", "materi__clinic", "materi__kebijakan", "paksa",
                                            "ditangani_oleh")) if kartu else []
    last = terakhir_per_cabang([b.materi_id for b in butir], clinics)
    for b in butir:
        b.teks = teks_wa(b.materi)
        b.terakhir = last.get(b.materi_id, [])
    return {
        "tanggal": day,
        "libur": kartu is None,
        "butir": butir,
        "terbuka": [b for b in butir if b.status == Status.TERBUKA],
        "selesai": [b for b in butir if b.status != Status.TERBUKA],
        "pratinjau": pratinjau(day),
        "clinics": clinics,
        "saluran": Saluran.choices,
    }


# --- Aksi butir --------------------------------------------------------------------------------


def _butir_terbuka(butir: Butir, user, today: dt.date) -> None:
    _assert_manage(user)
    if butir.kartu.tanggal != today:
        raise ValidationError("Butir ini dari kartu hari lain.")
    if butir.status != Status.TERBUKA:
        raise ValidationError("Butir ini sudah ditangani.")


def _tutup_paksa(butir: Butir, today: dt.date) -> None:
    Paksa.objects.filter(materi=butir.materi, selesai_pada__isnull=True, tanggal__lte=today).update(selesai_pada=today)


def _selesai(butir: Butir, status: str, user, alasan: str = "") -> None:
    butir.status = status
    butir.alasan = alasan
    butir.ditangani_oleh = user
    butir.ditangani_pada = timezone.now()
    butir.save(update_fields=["status", "alasan", "ditangani_oleh", "ditangani_pada"])


def tandai_diingatkan(butir: Butir, *, user, cabang: str, saluran: str, catatan: str = "",
                      today: dt.date | None = None) -> Diingatkan:
    """Sudah diingatkan. `cabang`: id cabang, atau "" / "keduanya" untuk kedua cabang."""
    today = today or local_today()
    _butir_terbuka(butir, user, today)
    if saluran not in Saluran.values:
        raise ValidationError("Pilih saluran: grup WA, briefing, atau langsung.")
    clinic = None
    if cabang not in ("", "keduanya"):
        clinic = Clinic.objects.filter(pk=int(cabang) if str(cabang).isdigit() else 0).first()
        if clinic is None:
            raise ValidationError("Cabang tidak dikenal.")
    with transaction.atomic():
        log = Diingatkan.objects.create(materi=butir.materi, tanggal=today, clinic=clinic, saluran=saluran,
                                        catatan=(catatan or "").strip(), oleh=user)
        _selesai(butir, Status.DIINGATKAN, user)
        _tutup_paksa(butir, today)
        log_event(action=AuditAction.CREATE, entity_type="pengingat_log", entity_id=log.pk,
                  entity_label=str(butir.materi), actor=user,
                  after={"cabang": clinic.name if clinic else "keduanya", "saluran": saluran, "catatan": log.catatan})
    return log


def tunda(butir: Butir, *, user, today: dt.date | None = None) -> Paksa:
    """Tunda ke besok: dipaksa muncul hari kerja berikutnya, tidak dihitung diingatkan."""
    today = today or local_today()
    _butir_terbuka(butir, user, today)
    with transaction.atomic():
        _selesai(butir, Status.DITUNDA, user)
        _tutup_paksa(butir, today)
        p = Paksa.objects.create(materi=butir.materi, tanggal=next_workday(today, Pengaturan.get()),
                                 sebab=Sebab.TUNDA, dibuat_oleh=user)
        log_event(action=AuditAction.UPDATE, entity_type="pengingat_butir", entity_id=butir.pk,
                  entity_label=str(butir.materi), actor=user, after={"status": "DITUNDA", "muncul": p.tanggal.isoformat()})
    return p


def lewati(butir: Butir, *, user, alasan: str, today: dt.date | None = None) -> None:
    """Lewati (alasan wajib): jadwal mundur satu interval, tidak masuk riwayat diingatkan."""
    today = today or local_today()
    _butir_terbuka(butir, user, today)
    alasan = (alasan or "").strip()
    if not alasan:
        raise ValidationError("Tulis alasan melewati, mis. materi sedang direvisi.")
    with transaction.atomic():
        _selesai(butir, Status.DILEWATI, user, alasan)
        _tutup_paksa(butir, today)
        log_event(action=AuditAction.UPDATE, entity_type="pengingat_butir", entity_id=butir.pk,
                  entity_label=str(butir.materi), actor=user, after={"status": "DILEWATI"}, reason=alasan)
