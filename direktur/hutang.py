"""Halaman "Hutang DO" (15 Okt 2026): satu tempat untuk semua yang masih menunggu Direktur Operasional.

Tidak ada model baru. Halaman ini hanya membaca yang sudah ada — task saya, task yang saya berikan,
permintaan Owner yang tinggal ditutup, keputusan yang menunggu Owner, dan kartu pengingat hari ini —
lalu mengurutkannya menurut tenggat. Catatan cepat di halaman ini langsung menjadi task untuk diri
sendiri, memakai jalur `create_manual_task` yang sama dengan Task baru.
"""
from __future__ import annotations

from django.db.models import Q
from django.utils import timezone

from core.models import ActionItem, ActionItemStatus, Priority, local_today
from core.permissions import user_clinic_queryset
from core.task_services import my_tasks
from owner.models import OwnerRequest
from owner.services import effective_target
from pengingat.services import kartu_context

from . import dashboard, services

OPEN = (ActionItemStatus.BARU, ActionItemStatus.DIKERJAKAN)


def _due_key(item: ActionItem):
    # Tanpa tenggat diletakkan paling bawah; yang lewat tenggat otomatis paling atas.
    return (item.due_at is None, item.due_at or timezone.now(), item.pk)


def tugas_saya(user) -> list[dict]:
    rows = my_tasks(user)
    rows.sort(key=lambda r: _due_key(r["item"]))
    return rows


def tugas_dari_saya(user) -> list[ActionItem]:
    """Task yang DO buat untuk orang lain dan belum selesai, diurutkan tenggat."""
    items = (
        ActionItem.objects.filter(created_by=user, status__in=OPEN, clinic__in=user_clinic_queryset(user))
        .exclude(owner=user)
        .select_related("clinic", "owner")
    )
    return sorted(items, key=_due_key)


def permintaan_owner(user) -> dict:
    """Permintaan Owner yang belum ditandai selesai, dipisah: tinggal ditutup vs masih berjalan.

    "Tinggal ditutup" = semua task-nya sudah selesai (atau tidak punya task sama sekali), tetapi
    Direktur belum menekan selesai di halaman permintaan. Inilah yang paling sering terlupa.
    """
    today = local_today()
    tutup, berjalan = [], []
    for req in OwnerRequest.objects.filter(completed_at__isnull=True).select_related("clinic").order_by("created_at"):
        tasks = list(req.tasks())
        open_tasks = [t for t in tasks if t.status in OPEN]
        row = {
            "req": req,
            "target": effective_target(req),
            "tasks_total": len(tasks),
            "tasks_open": open_tasks,
            "overdue": bool(effective_target(req) and effective_target(req) < today),
        }
        (berjalan if open_tasks else tutup).append(row)
    return {"tutup": tutup, "berjalan": berjalan}


def keputusan_menunggu(user) -> list:
    return list(dashboard.pending_decisions(user))


def context(user) -> dict:
    today = local_today()
    mine = tugas_saya(user)
    delegated = tugas_dari_saya(user)
    owner = permintaan_owner(user)
    decisions = keputusan_menunggu(user)
    pengingat = kartu_context(user)
    terbuka_pengingat = len(pengingat["terbuka"]) if pengingat else 0
    return {
        "today": today,
        "mine": mine,
        "mine_overdue": sum(1 for r in mine if r["overdue"]),
        "delegated": delegated,
        "owner_tutup": owner["tutup"],
        "owner_berjalan": owner["berjalan"],
        "decisions": decisions,
        "decisions_no_date": sum(1 for d in decisions if d.needed_by is None),
        "pengingat": pengingat,
        "pengingat_terbuka": terbuka_pengingat,
        "clinics": user_clinic_queryset(user).order_by("id"),
        "total": len(mine) + len(delegated) + len(owner["tutup"]) + terbuka_pengingat,
    }


def catat_cepat(*, user, title: str, due: str, clinic) -> ActionItem:
    """Catatan cepat → task untuk diri sendiri. Tenggat opsional (YYYY-MM-DD)."""
    return services.create_manual_task(
        actor=user,
        clinic=clinic,
        title=title,
        description="",
        target=f"user:{user.pk}",
        priority=Priority.SEDANG,
        due_at=services.parse_due(due),
    )
