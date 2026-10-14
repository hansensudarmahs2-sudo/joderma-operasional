"""Satu login untuk aplikasi CS Booking (14 Okt 2026).

Aplikasi CS booking dipasang di ``ops.joderma.id/booking`` (aplikasi terpisah, repo joderma-booking),
dengan pola yang sama seperti Survei: karena satu hostname, peramban ikut mengirim kuki sesi ops ke
/booking; aplikasi booking meneruskannya ke ``/akun/sesi-booking/`` lewat 127.0.0.1 untuk tahu siapa
penggunanya dan perannya. Aplikasi booking tidak punya login sendiri; hak akses mengikuti peran di ops.
"""
from __future__ import annotations

from .models import Role

BOOKING_PATH = "/booking/"

# Peran di aplikasi booking: admin (CS + jadwal dokter, rekening, jam CS, durasi), cs (verifikasi,
# antrian, data pasien).
ADMIN, CS = "admin", "cs"


def booking_role(user) -> str | None:
    """Peran booking pengguna ops, atau None bila tidak berhak membuka Booking.

    Direktur Operasional (AOM) dan Owner -> admin; petugas Online (CS WhatsApp) -> cs.
    Yang memegang beberapa peran mendapat peran booking tertinggi."""
    from core.permissions import has_role

    if not user or not user.is_authenticated or not user.is_active:
        return None
    if has_role(user, Role.AOM, Role.OWNER):
        return ADMIN
    if has_role(user, Role.ONLINE):
        return CS
    return None
