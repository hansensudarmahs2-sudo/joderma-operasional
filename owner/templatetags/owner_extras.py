from django import template

register = template.Library()


@register.filter
def rupiah(value):
    """1500000 -> "Rp1.500.000"; kosong tetap kosong."""
    if value in (None, ""):
        return ""
    return f"Rp{int(value):,}".replace(",", ".")
