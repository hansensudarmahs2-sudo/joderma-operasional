"""Katalog materi dan pengaturan Pengingat Harian DO (kebutuhan 3.2, 3.3, 4.1, 4.3). Hanya Direktur Operasional."""
from __future__ import annotations

import datetime as dt
import re

from django.core.exceptions import ValidationError
from django.db import transaction

from audit.models import AuditAction
from audit.services import log_event
from core.models import Clinic, local_today

from .models import SASARAN, Jenis, Kelas, Materi, Paksa, Pengaturan, Sebab
from .services import _assert_manage, jadwalkan_ulangan, next_workday

FIELDS = ("kode", "judul", "jenis", "sasaran", "clinic_id", "kelas", "poin", "teks_wa", "rujukan",
          "kebijakan_id", "aktif", "tanggal_sosialisasi", "catatan", "urutan")
HARI = ("Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu")


def policies():
    """Kebijakan berlaku yang boleh dirujuk materi berjenis kebijakan (dari record aslinya)."""
    from direktur.models import Decision, DecisionStatus

    return Decision.objects.filter(status=DecisionStatus.DITETAPKAN, is_policy=True).order_by("title")


def kapasitas(cfg: Pengaturan | None = None) -> dict:
    """Kapasitas mingguan (kuota × hari kerja) dibanding kebutuhan (Σ 7 ÷ interval materi aktif)."""
    cfg = cfg or Pengaturan.get()
    kap = cfg.kuota * len(cfg.hari_kerja or [])
    butuh = sum(7 / max(1, cfg.interval(m.kelas)) for m in Materi.objects.filter(aktif=True).only("kelas"))
    return {"kapasitas": kap, "kebutuhan": round(butuh, 1), "lebih": butuh > kap + 1e-9}


def _snapshot(m: Materi) -> dict:
    out = {}
    for f in FIELDS:
        v = getattr(m, f)
        out[f] = v.isoformat() if isinstance(v, dt.date) else v
    return out


def parse_form(data, *, materi: Materi | None = None) -> dict:
    """Validasi isian formulir materi; mengembalikan nilai field. Galat dikumpulkan jadi satu."""
    errors = []
    kode = (data.get("kode") or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9-]{0,19}", kode):
        errors.append("Kode wajib diisi: huruf besar, angka, dan tanda hubung, mis. AR-13.")
    elif Materi.objects.filter(kode=kode).exclude(pk=materi.pk if materi else None).exists():
        errors.append(f"Kode {kode} sudah dipakai materi lain.")
    judul = (data.get("judul") or "").strip()
    if not judul:
        errors.append("Judul wajib diisi.")
    jenis = data.get("jenis") or ""
    if jenis not in Jenis.values:
        errors.append("Pilih jenis materi.")
    sasaran = [s for s in SASARAN if s in data.getlist("sasaran")]
    if not sasaran:
        errors.append("Pilih minimal satu sasaran.")
    kelas = data.get("kelas") or ""
    if kelas not in Kelas.values:
        errors.append("Pilih kelas A, B, atau C.")
    poin = [p.strip() for p in data.getlist("poin") if p.strip()][:3]
    if not poin:
        errors.append("Tulis minimal satu poin kunci.")
    clinic_id = None
    if data.get("cabang"):
        clinic = Clinic.objects.filter(pk=data["cabang"] if str(data["cabang"]).isdigit() else 0).first()
        if clinic is None:
            errors.append("Cabang tidak dikenal.")
        clinic_id = clinic.pk if clinic else None
    kebijakan_id = None
    if jenis == Jenis.KEBIJAKAN and data.get("kebijakan"):
        pol = policies().filter(pk=data["kebijakan"] if str(data["kebijakan"]).isdigit() else 0).first()
        if pol is None:
            errors.append("Kebijakan tidak ditemukan atau belum berlaku.")
        kebijakan_id = pol.pk if pol else None
    tanggal = None
    if data.get("tanggal_sosialisasi"):
        try:
            tanggal = dt.date.fromisoformat(data["tanggal_sosialisasi"])
        except ValueError:
            errors.append("Tanggal sosialisasi tidak valid.")
    try:
        urutan = int(data.get("urutan") or 100)
        if urutan < 0:
            raise ValueError
    except ValueError:
        urutan = 100
        errors.append("Urutan prioritas harus angka 0 atau lebih.")
    if errors:
        raise ValidationError(errors)
    return {
        "kode": kode, "judul": judul, "jenis": jenis, "sasaran": sasaran, "clinic_id": clinic_id, "kelas": kelas,
        "poin": poin, "teks_wa": (data.get("teks_wa") or "").strip(), "rujukan": (data.get("rujukan") or "").strip(),
        "kebijakan_id": kebijakan_id, "aktif": data.get("aktif") == "1", "tanggal_sosialisasi": tanggal,
        "catatan": (data.get("catatan") or "").strip(), "urutan": urutan,
    }


def simpan_materi(values: dict, *, user, materi: Materi | None = None) -> Materi:
    """Tambah atau ubah materi. Tanggal sosialisasi baru/berubah menjadwalkan ulangan 1/3/7/14/30."""
    _assert_manage(user)
    with transaction.atomic():
        before = _snapshot(materi) if materi else None
        old_tgl = materi.tanggal_sosialisasi if materi else None
        materi = materi or Materi()
        for k, v in values.items():
            setattr(materi, k, v)
        materi.save()
        if materi.tanggal_sosialisasi and materi.tanggal_sosialisasi != old_tgl:
            jadwalkan_ulangan(materi, actor=user)
        log_event(action=AuditAction.UPDATE if before else AuditAction.CREATE, entity_type="pengingat_materi",
                  entity_id=materi.pk, entity_label=str(materi), actor=user, before=before, after=_snapshot(materi))
    return materi


def set_aktif(materi: Materi, aktif: bool, *, user) -> None:
    _assert_manage(user)
    if materi.aktif == aktif:
        return
    materi.aktif = aktif
    materi.save(update_fields=["aktif", "updated_at"])
    log_event(action=AuditAction.UPDATE, entity_type="pengingat_materi", entity_id=materi.pk,
              entity_label=str(materi), actor=user, before={"aktif": not aktif}, after={"aktif": aktif})


def ingatkan_besok(materi: Materi, *, user, today: dt.date | None = None) -> Paksa:
    """Naikkan karena temuan: muncul di kartu hari kerja berikutnya, di luar kuota."""
    _assert_manage(user)
    if not materi.aktif:
        raise ValidationError("Materi nonaktif tidak dijadwalkan; aktifkan dulu.")
    tanggal = next_workday(today or local_today(), Pengaturan.get())
    existing = Paksa.objects.filter(materi=materi, tanggal=tanggal, selesai_pada__isnull=True).first()
    if existing:
        return existing
    p = Paksa.objects.create(materi=materi, tanggal=tanggal, sebab=Sebab.TEMUAN, dibuat_oleh=user)
    log_event(action=AuditAction.CREATE, entity_type="pengingat_paksa", entity_id=p.pk, entity_label=str(materi),
              actor=user, after={"tanggal": tanggal.isoformat(), "sebab": "TEMUAN"})
    return p


def simpan_pengaturan(data, *, user) -> Pengaturan:
    _assert_manage(user)
    cfg = Pengaturan.get()
    hari = sorted({int(h) for h in data.getlist("hari_kerja") if str(h).isdigit() and 0 <= int(h) <= 6})
    errors = []
    if not hari:
        errors.append("Pilih minimal satu hari kerja.")
    vals = {}
    for name, label, lo, hi in (("kuota", "Butir per hari", 1, 10), ("interval_a", "Interval kelas A", 1, 365),
                                ("interval_b", "Interval kelas B", 1, 365), ("interval_c", "Interval kelas C", 1, 365)):
        try:
            v = int(data.get(name, ""))
            if not lo <= v <= hi:
                raise ValueError
            vals[name] = v
        except ValueError:
            errors.append(f"{label} harus angka {lo}–{hi}.")
    if errors:
        raise ValidationError(errors)
    before = {"hari_kerja": cfg.hari_kerja, "kuota": cfg.kuota, "interval_a": cfg.interval_a,
              "interval_b": cfg.interval_b, "interval_c": cfg.interval_c}
    cfg.hari_kerja = hari
    for k, v in vals.items():
        setattr(cfg, k, v)
    cfg.save()
    log_event(action=AuditAction.UPDATE, entity_type="pengingat_pengaturan", entity_id=cfg.pk,
              entity_label="Pengaturan pengingat", actor=user, before=before, after={"hari_kerja": hari, **vals})
    return cfg
