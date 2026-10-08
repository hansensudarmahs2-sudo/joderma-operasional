"""Kategori permintaan/temuan Owner dan task turunannya (keputusan PO 8 Okt 2026).

- Diatur Owner dan Direktur Operasional (`can_manage_categories`, diperiksa di server).
- Kategori yang dinonaktifkan tetap melekat pada data lama tetapi tidak bisa dipilih lagi.
- Kategori yang sudah dipakai tidak dihapus; nonaktifkan saja. Halaman ini memang tidak punya
  tombol hapus, dan `PROTECT` pada `OwnerRequest.category` menjaga dari penghapusan lewat admin.
- Task dari permintaan/temuan mewarisi kategorinya (`direktur.services.create_task_from_source`).
"""
from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count

from audit.services import log_create, log_update, snapshot

from .models import TaskCategory
from .permissions import is_aom, is_owner

NAME_MAX = 80
NONE_LABEL = "Tanpa kategori"
FIELDS = ["name", "active", "sort_order"]


def can_manage_categories(user) -> bool:
    return bool(user and user.is_authenticated) and (is_owner(user) or is_aom(user))


def _assert_manage(user) -> None:
    if not can_manage_categories(user):
        raise PermissionDenied("Kategori hanya diatur Owner dan Direktur Operasional.")


def active_categories():
    return TaskCategory.objects.filter(active=True).order_by("sort_order", "name")


def category_choices(current=None) -> list[TaskCategory]:
    """Pilihan untuk formulir: kategori aktif, ditambah kategori yang sedang terpasang walau nonaktif."""
    rows = list(active_categories())
    if current is not None and all(c.pk != current.pk for c in rows):
        rows.append(current)
    return rows


def parse_category(raw, *, required: bool, current=None) -> TaskCategory | None:
    """Kategori dari formulir. Hanya kategori aktif yang boleh dipilih (kecuali yang sudah terpasang)."""
    raw = str(raw or "").strip()
    if not raw:
        if required:
            raise ValidationError("Pilih kategori.")
        return None
    if not (raw.isascii() and raw.isdigit()):
        raise ValidationError("Kategori tidak dikenali.")
    cat = TaskCategory.objects.filter(pk=int(raw)).first()
    if cat is None:
        raise ValidationError("Kategori tidak dikenali.")
    if not cat.active and (current is None or current.pk != cat.pk):
        raise ValidationError(f"Kategori {cat.name} sudah tidak aktif; pilih kategori lain.")
    return cat


def _clean_name(name: str) -> str:
    name = " ".join((name or "").split())
    if not name:
        raise ValidationError("Tulis nama kategori.")
    if len(name) > NAME_MAX:
        raise ValidationError(f"Nama kategori terlalu panjang (maks. {NAME_MAX} karakter).")
    return name


def _parse_order(raw, default: int) -> int:
    raw = str(raw if raw is not None else "").strip()
    if not raw:
        return default
    if not (raw.isascii() and raw.isdigit()) or int(raw) > 9999:
        raise ValidationError("Urutan harus angka 0–9999.")
    return int(raw)


def _name_taken(name: str, exclude_pk=None) -> bool:
    qs = TaskCategory.objects.filter(name__iexact=name)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()


@transaction.atomic
def create_category(*, actor, name: str, sort_order=None) -> TaskCategory:
    _assert_manage(actor)
    name = _clean_name(name)
    if _name_taken(name):
        raise ValidationError(f"Kategori {name} sudah ada.")
    last = TaskCategory.objects.order_by("-sort_order").values_list("sort_order", flat=True).first() or 0
    try:
        cat = TaskCategory.objects.create(name=name, sort_order=_parse_order(sort_order, last + 10), active=True)
    except IntegrityError:
        raise ValidationError(f"Kategori {name} sudah ada.")
    log_create(cat, actor=actor, label=name)
    return cat


@transaction.atomic
def update_category(cat: TaskCategory, *, actor, name: str, sort_order, active: bool) -> TaskCategory:
    """Ganti nama, urutan, dan aktif/nonaktif. Data lama tetap memakai kategori yang sama."""
    _assert_manage(actor)
    cat = TaskCategory.objects.select_for_update().get(pk=cat.pk)
    name = _clean_name(name)
    if _name_taken(name, exclude_pk=cat.pk):
        raise ValidationError(f"Kategori {name} sudah ada.")
    before = snapshot(cat, FIELDS)
    cat.name = name
    cat.sort_order = _parse_order(sort_order, cat.sort_order)
    cat.active = bool(active)
    cat.save(update_fields=FIELDS)
    log_update(cat, before, actor=actor)
    return cat


def categories_with_usage():
    """Semua kategori untuk halaman pengaturan, dengan jumlah permintaan dan task yang memakainya."""
    return TaskCategory.objects.annotate(
        n_requests=Count("owner_requests", distinct=True), n_tasks=Count("action_items", distinct=True),
    ).order_by("sort_order", "name")


@transaction.atomic
def set_task_category(item, *, actor, raw) -> None:
    """Direktur/pemberi tugas mengubah kategori satu task (izin diperiksa pemanggil: can_manage_task)."""
    from .task_services import can_manage_task

    if not can_manage_task(item, actor):
        raise PermissionDenied("Hanya pemberi tugas atau Direktur Operasional yang dapat mengubah task ini.")
    cat = parse_category(raw, required=False, current=item.category)
    if (item.category_id or None) == (cat.pk if cat else None):
        return
    before = snapshot(item, ["category"])
    item.category = cat
    item.save(update_fields=["category", "updated_at"])
    log_update(item, before, actor=actor)


def request_counts(requests) -> list[dict]:
    """Kartu "Per kategori" di Dashboard Owner: jumlah permintaan terbuka/selesai per kategori.

    `requests`: daftar hasil `owner.services.progress` (selesai = state "done", yaitu semua task
    selesai untuk permintaan, atau dinyatakan selesai oleh Direktur untuk temuan). Hanya kategori
    yang punya permintaan; baris "Tanpa kategori" bila ada permintaan lama tanpa kategori."""
    counts: dict = {}
    for r in requests:
        req = r["request"]
        key = req.category_id
        row = counts.setdefault(key, {"category": req.category, "name": req.category.name if req.category else NONE_LABEL,
                                      "open": 0, "done": 0})
        row["done" if r["state"] == "done" else "open"] += 1
    order = {c.pk: (c.sort_order, c.name) for c in TaskCategory.objects.filter(pk__in=[k for k in counts if k])}
    rows = sorted((v for k, v in counts.items() if k), key=lambda v: order[v["category"].pk])
    if None in counts:
        rows.append(counts[None])
    for row in rows:
        row["total"] = row["open"] + row["done"]
    return rows

