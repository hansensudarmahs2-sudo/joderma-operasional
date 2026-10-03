from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.db import transaction

from accounts.models import Role
from core.permissions import can_access_clinic, has_role

from .models import OnlineOrder, OnlineOrderItem, OnlineOrderStatus


def normalize_rm_number(clinic, raw_value: str) -> str:
    """Normalisasi RM: JJ-/JC-; fallback J_- bila cabang belum dipetakan."""
    import re

    raw = re.sub(r"[^A-Z0-9_]", "", (raw_value or "").upper())
    # Bersihkan placeholder lama yang sempat tampil sebagai nilai awal field.
    raw = raw.replace("J_-", "").replace("J_", "")
    if not raw:
        raise ValueError("Nomor RM wajib diisi.")
    if raw.startswith("JJ"):
        return f"JJ-{raw[2:]}"
    if raw.startswith("JC"):
        return f"JC-{raw[2:]}"
    if raw.startswith("J_"):
        return f"J_-{raw[2:]}"
    if raw.startswith("C"):
        return f"JC-{raw[1:]}"
    if raw.startswith("J"):
        return f"JJ-{raw[1:]}"
    from core.services import rm_prefix

    return f"{rm_prefix(clinic)}{raw}"


def can_manage_online_orders(user):
    return bool(user and user.is_authenticated and has_role(user, Role.ONLINE, Role.SUPERVISOR, Role.PIC))


def can_process_online_orders(user):
    return bool(user and user.is_authenticated and has_role(user, Role.APOTEKER, Role.ASISTEN_APOTEKER, Role.SUPERVISOR))


def create_online_order(*, clinic, user, **data):
    if not can_manage_online_orders(user) or not can_access_clinic(user, clinic):
        raise PermissionDenied("Hanya koordinator online yang dapat membuat order.")
    latest = OnlineOrder.objects.filter(clinic=clinic).order_by("-id").first()
    sequence = (latest.id + 1) if latest else 1
    product = data.pop("product", None)
    product_name = data.pop("product_name", "")
    quantity = data.pop("quantity", 1)
    data["rm_number"] = normalize_rm_number(clinic, data["rm_number"])
    order = OnlineOrder.objects.create(clinic=clinic, order_no=f"ONL-{clinic.code.upper()}-{sequence:05d}", created_by=user, status=OnlineOrderStatus.DRAFT, product_name=product_name or (product.name if product else "Draft"), **data)
    OnlineOrderItem.objects.create(order=order, product=product, product_name=product_name or (product.name if product else ""), quantity=quantity)
    order.recalculate_totals()
    return order


def add_order_item(order, *, user, **data):
    if not can_manage_online_orders(user) or order.status != OnlineOrderStatus.DRAFT:
        raise PermissionDenied("Item hanya dapat ditambahkan pada draft order Anda.")
    product = data.get("product")
    item = OnlineOrderItem.objects.create(order=order, product=product, product_name=data.get("product_name") or (product.name if product else ""), quantity=data.get("quantity", 1))
    order.recalculate_totals()
    return item


def submit_order(order, *, user):
    if not can_manage_online_orders(user) or order.status != OnlineOrderStatus.DRAFT:
        raise PermissionDenied("Draft order tidak dapat dikirim.")
    if not order.items.exists():
        raise PermissionDenied("Draft order belum memiliki produk.")
    order.status = OnlineOrderStatus.BARU
    order.save(update_fields=("status", "updated_at"))
    return order


@transaction.atomic
def update_order_status(order, *, user, status, note=""):
    if not can_process_online_orders(user):
        raise PermissionDenied("Hanya apoteker/asisten apoteker yang dapat memproses order.")
    if order.status == OnlineOrderStatus.DRAFT:
        raise PermissionDenied("Draft belum dikirim oleh koordinator online.")
    if not can_access_clinic(user, order.clinic):
        raise PermissionDenied("Order berada di luar klinik Anda.")
    order.status = status
    order.note = note
    order.handled_by = user
    order.save(update_fields=("status", "note", "handled_by", "updated_at"))
    return order
