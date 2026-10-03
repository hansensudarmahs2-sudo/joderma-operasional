"""Tampilan foto lampiran: ``{% load foto %}``.

- ``{{ peta|ambil:obj.pk }}``: ambil daftar foto dari dict hasil `core.photos.photos_for`.
- ``{% foto_thumbs daftar %}``: gambar kecil yang membuka foto ukuran penuh (lewat izin
  `core:attachment`, bukan URL media publik).
"""
from django import template

register = template.Library()


@register.filter
def ambil(mapping, key):
    try:
        return mapping.get(key) or []
    except AttributeError:
        return []


@register.inclusion_tag("includes/photo_thumbs.html")
def foto_thumbs(photos):
    return {"photos": photos or []}


@register.inclusion_tag("includes/photo_field.html")
def foto_input(label="Foto (opsional)", name="foto", help_text=""):
    return {"label": label, "name": name, "help_text": help_text}
