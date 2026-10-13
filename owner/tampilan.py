"""Tata letak Dashboard Owner (keputusan PO 13 Okt 2026).

Empat kartu berita di paling atas menunjukkan keadaan klinik per bidang masalah: Sarana, Alur dan
SOP, SDM, dan Lainnya. Isinya hanya permintaan dan temuan Owner yang masih terbuka. Bidang yang
kosong digantikan kategori dari kelompok "Lainnya" yang paling banyak masalahnya.

Di bawah kartu, daftar Permintaan dan temuan selalu tampil pertama. Bagian lain boleh disembunyikan
dan diurutkan oleh Owner sendiri (`DashboardLayout`); bagian tersembunyi yang berisi sesuatu yang
lewat target tetap diberi penanda merah di bilah navigasi.
"""
from __future__ import annotations

import datetime as dt

from django.core.exceptions import PermissionDenied

from core.models import Priority
from core.permissions import is_owner

# Bidang kartu dan kategori bawaan yang masuk ke dalamnya. Kategori lain (termasuk kategori baru
# atau yang diganti namanya) dan permintaan tanpa kategori masuk "Lainnya".
AREAS = (
    ("sarana", "Sarana", ("Fasilitas & peralatan", "Kebersihan & kerapian")),
    ("alur", "Alur dan SOP", ("Pelayanan pasien", "Administrasi & sistem")),
    ("sdm", "SDM", ("SDM & disiplin",)),
)
OTHER = ("lainnya", "Lainnya")
AREA_LABELS = {key: label for key, label, _ in AREAS} | {OTHER[0]: OTHER[1]}
_AREA_OF_CATEGORY = {name: key for key, _, names in AREAS for name in names}
NONE_KEY = "kat-0"  # bucket "Tanpa kategori" di dalam kelompok Lainnya
NEAR_DAYS = 7  # kartu kuning bila ada target dalam 7 hari
HIGH = (Priority.TINGGI, Priority.KRITIS)


def area_of(req) -> str:
    return _AREA_OF_CATEGORY.get(req.category.name if req.category else "", OTHER[0])


def bucket_of(req) -> str:
    return f"kat-{req.category_id}" if req.category_id else NONE_KEY


def is_open(row) -> bool:
    return row["state"] != "done"


def high_priority(row) -> bool:
    return any(t.priority in HIGH and t.status != "SELESAI" for t in row["tasks"])


def rank(row):
    """Urutan "paling penting dulu": mendesak dan lewat, mendesak, lewat (terlama dulu),
    task berprioritas Tinggi/Kritis, lalu target terdekat. Yang sudah selesai paling akhir."""
    urgent = row["request"].urgent
    late = row["late"]
    return (
        not is_open(row),
        not (urgent and late),
        not urgent,
        not late,
        -row["days_late"] if late else 0,
        not high_priority(row),
        row["target"] or dt.date.max,
        row["request"].pk,
    )


def reason(row) -> tuple[str, str]:
    """Label alasan sebuah baris penting: (teks, kelas tag)."""
    if row["request"].urgent:
        return "Mendesak", "err"
    if row["late"]:
        return f"Lewat {row['days_late']} hari", "err"
    if high_priority(row):
        return "Prioritas tinggi", "warn"
    if row["days_left"] is not None and row["days_left"] <= NEAR_DAYS:
        return ("Hari ini" if row["days_left"] == 0 else f"{row['days_left']} hari lagi"), "warn"
    return row["label"], "info"


def _level(rows) -> str:
    if any(r["request"].urgent or r["late"] for r in rows):
        return "merah"
    if any(high_priority(r) or (r["days_left"] is not None and r["days_left"] <= NEAR_DAYS) for r in rows):
        return "kuning"
    return "biru"


def _card(key, label, rows, *, replaces=None) -> dict:
    rows = sorted(rows, key=rank)
    top = rows[0]
    text, cls = reason(top)
    return {
        "key": key,
        "label": label,
        "level": _level(rows),
        "count": len(rows),
        "top": top,
        "reason": text,
        "reason_class": cls,
        "next": rows[1:3],
        "more": max(0, len(rows) - 3),
        "replaces": replaces,
        "empty": False,
    }


def news_cards(rows) -> list[dict]:
    """Empat kartu berita dari hasil `services.all_progress` (hanya yang terbuka).

    Slot Sarana, Alur dan SOP, dan SDM tetap di tempatnya. Slot yang kosong diisi kategori dari
    kelompok Lainnya yang paling banyak masalahnya; sisa kelompok Lainnya menjadi kartu keempat.
    Slot kosong yang tidak punya pengganti tampil sebagai kartu hijau. Tidak ada yang terbuka sama
    sekali: daftar kosong (template menampilkan satu kartu hijau)."""
    open_rows = [r for r in rows if is_open(r)]
    if not open_rows:
        return []
    by_area = {key: [] for key, _, _ in AREAS}
    buckets: dict[str, list] = {}
    for r in open_rows:
        key = area_of(r["request"])
        if key in by_area:
            by_area[key].append(r)
        else:
            buckets.setdefault(bucket_of(r["request"]), []).append(r)
    spare = sorted(buckets.values(), key=lambda rs: (-len(rs), min(rank(r) for r in rs)))
    cards = []
    for key, label, _ in AREAS:
        if by_area[key]:
            cards.append(_card(key, label, by_area[key]))
        elif spare:
            rs = spare.pop(0)
            req = rs[0]["request"]
            cards.append(_card(bucket_of(req), req.category.name if req.category else "Tanpa kategori", rs,
                               replaces=label))
        else:
            cards.append({"key": key, "label": label, "empty": True, "level": "hijau"})
    rest = [r for rs in spare for r in rs]
    if rest:
        cards.append(_card(OTHER[0], OTHER[1], rest))
    else:
        cards.append({"key": OTHER[0], "label": OTHER[1], "empty": True, "level": "hijau"})
    return cards


def filter_rows(rows, bidang: str) -> list:
    """Saringan daftar Permintaan dan temuan: bidang (sarana/alur/sdm/lainnya) atau kategori (kat-<id>)."""
    if bidang in AREA_LABELS:
        return [r for r in rows if area_of(r["request"]) == bidang]
    if bidang.startswith("kat-"):
        return [r for r in rows if bucket_of(r["request"]) == bidang]
    return list(rows)


def area_chips(rows) -> list[dict]:
    """Chip saringan di atas daftar: jumlah yang terbuka per bidang."""
    counts = {key: 0 for key in AREA_LABELS}
    for r in rows:
        if is_open(r):
            counts[area_of(r["request"])] += 1
    return [{"key": key, "label": label, "open": counts[key]} for key, label in AREA_LABELS.items()]


# Bagian di bawah daftar Permintaan dan temuan, dalam urutan bawaan.
SECTIONS = (
    ("keputusan", "Menunggu keputusan Anda", "Keputusan"),
    ("usulan", "Usulan Direktur", "Usulan"),
    ("verifikasi", "Menunggu verifikasi", "Verifikasi"),
    ("tugas", "Tugas saya (project)", "Tugas saya"),
    ("inbox", "Inbox", "Inbox"),
    ("cabang", "Per cabang", "Cabang"),
    ("matriks", "Yang belum selesai", "Belum selesai"),
    ("agenda", "Agenda rapat", "Agenda"),
    ("kategori", "Per kategori", "Kategori"),
    ("capaian", "Capaian 7 hari terakhir", "Capaian"),
)
SECTION_KEYS = tuple(k for k, _, _ in SECTIONS)
_SECTION_INFO = {k: (label, short) for k, label, short in SECTIONS}


def default_layout() -> list[dict]:
    return [{"key": k, "shown": True} for k in SECTION_KEYS]


def layout_for(user) -> list[dict]:
    """Urutan dan tampil/sembunyi bagian untuk `user`: pilihan tersimpan, digabung dengan daftar
    bagian saat ini (bagian yang sudah tidak ada dibuang, bagian baru ditambah di akhir, tampil)."""
    from .models import DashboardLayout

    saved = DashboardLayout.objects.filter(user=user).values_list("sections", flat=True).first() or []
    seen, out = set(), []
    for item in saved:
        key = item.get("key") if isinstance(item, dict) else None
        if key in _SECTION_INFO and key not in seen:
            seen.add(key)
            out.append({"key": key, "shown": bool(item.get("shown", True))})
    out += [{"key": k, "shown": True} for k in SECTION_KEYS if k not in seen]
    for item in out:
        item["label"], item["short"] = _SECTION_INFO[item["key"]]
    return out


def can_arrange(user) -> bool:
    return is_owner(user)


def save_layout(user, order: list[str], shown: set[str]) -> list[dict]:
    """Simpan pilihan Atur tampilan. `order`: kunci bagian dari atas ke bawah; kunci yang tidak
    dikenal diabaikan, bagian yang tidak disebut ditambahkan di akhir."""
    from audit.models import AuditAction
    from audit.services import log_event

    from .models import DashboardLayout

    if not can_arrange(user):
        raise PermissionDenied("Atur tampilan hanya untuk Owner.")
    seen, sections = set(), []
    for key in order:
        if key in _SECTION_INFO and key not in seen:
            seen.add(key)
            sections.append({"key": key, "shown": key in shown})
    sections += [{"key": k, "shown": k in shown} for k in SECTION_KEYS if k not in seen]
    DashboardLayout.objects.update_or_create(user=user, defaults={"sections": sections})
    log_event(action=AuditAction.UPDATE, entity_type="dashboardlayout", entity_id=user.pk,
              entity_label=f"Tampilan dashboard {user}", actor=user, after={"sections": sections})
    return sections


def reset_layout(user) -> None:
    from .models import DashboardLayout

    if not can_arrange(user):
        raise PermissionDenied("Atur tampilan hanya untuk Owner.")
    DashboardLayout.objects.filter(user=user).delete()

