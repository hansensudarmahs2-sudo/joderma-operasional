"""Satu login untuk aplikasi Survei (13 Okt 2026).

Admin survei dipasang di ``ops.joderma.id/survei`` (aplikasi terpisah, repo joderma-survey). Karena
satu hostname, peramban ikut mengirim kuki sesi ops ke /survei; aplikasi survei meneruskannya ke
``/akun/sesi-survei/`` lewat 127.0.0.1 untuk tahu siapa penggunanya dan perannya. Login survei
sendiri tidak dipakai lagi; hak akses mengikuti peran di ops.
"""
from __future__ import annotations

from .models import Role

SURVEY_PATH = "/survei/"

# Peran di aplikasi survei: direktur (kelola semua), owner (unggah + hasil), cs (daftar kirim saja).
DIREKTUR, OWNER, CS = "direktur", "owner", "cs"


def survey_role(user) -> str | None:
    """Peran survei pengguna ops, atau None bila tidak berhak membuka Survei.

    Direktur Operasional (AOM) -> direktur; Owner -> owner; petugas Online (CS WhatsApp) -> cs.
    Yang memegang beberapa peran mendapat peran survei tertinggi."""
    from core.permissions import has_role

    if not user or not user.is_authenticated or not user.is_active:
        return None
    if has_role(user, Role.AOM):
        return DIREKTUR
    if has_role(user, Role.OWNER):
        return OWNER
    if has_role(user, Role.ONLINE):
        return CS
    return None
