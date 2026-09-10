"""Optimistic locking sederhana untuk aksi sensitif (PRD 18).

Versi yang dikirim klien dibandingkan dengan nilai di DATABASE, bukan dengan
atribut objek in-memory — objek yang sudah basi membawa versi lamanya sendiri,
sehingga perbandingan terhadap dirinya sendiri selalu lolos dan konflik lolos
tanpa terdeteksi.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError

STALE_MESSAGE = (
    "Data sudah diubah pengguna lain. Muat ulang halaman sebelum menyimpan agar "
    "perubahan orang lain tidak tertimpa."
)


def assert_current_version(instance, expected_version, field: str = "version") -> None:
    """Raise ValidationError bila versi klien tidak sama dengan versi di DB."""
    if expected_version is None:
        return
    current = (
        type(instance)
        .objects.filter(pk=instance.pk)
        .values_list(field, flat=True)
        .first()
    )
    if current is None:
        raise ValidationError("Data sudah tidak tersedia.")
    if int(expected_version) != int(current):
        raise ValidationError(STALE_MESSAGE)
