"""Bintang penilaian task (8 Okt 2026): ``{% load bintang %}``.

- ``{{ a.rating|bintang }}``: "★★★★☆" (kosong bila belum dinilai).
- ``{% bintang_input key who=penerima %}``: pilihan 5 bintang (radio ``bintang``) dan alasan
  (``catatan_bintang``), wajib untuk bintang 1–3. Aturannya tetap diperiksa server.
"""
from django import template

from core.models import RATING_MAX, RATING_NOTE_REQUIRED_MAX

register = template.Library()


@register.filter
def bintang(value) -> str:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return ""
    if not 1 <= n <= RATING_MAX:
        return ""
    return "★" * n + "☆" * (RATING_MAX - n)


@register.inclusion_tag("includes/bintang_field.html")
def bintang_input(key, who=None, current=None, note=""):
    """`key`: pembeda id per formulir (mis. pk assignment); `who`: penerima yang dinilai (opsional)."""
    return {
        "prefix": f"bintang-{key}",
        "label": f"Bintang untuk {who}" if who else "Bintang",
        "choices": range(1, RATING_MAX + 1),
        "current": current,
        "note": note or "",
        "note_max": RATING_NOTE_REQUIRED_MAX,
    }
