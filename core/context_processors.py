"""Context global: notifikasi dan menu per tampilan peran (lihat `core/peran.py`)."""
from __future__ import annotations

from notifications.services import unread_count

from .peran import LABELS, nav_sections, persona, route_allowed


def app_context(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {"app_name": "JoDerma Staff Ops"}
    who = persona(user)
    from django.core.exceptions import ValidationError

    from .permissions import user_clinic_queryset
    from .services import active_clinic

    try:
        clinic = active_clinic(user)
    except ValidationError:
        clinic = None
    choices = list(user_clinic_queryset(user).order_by("id")) if who != "OWNER" else []
    return {
        # Cabang aktif selalu terlihat di kanan atas; pengalih tampil bila akun punya >1 cabang.
        "nav_clinic": clinic,
        "nav_clinic_choices": choices if len(choices) > 1 else [],
        "app_name": "JoDerma Staff Ops",
        "unread_notifications": unread_count(user),
        # Menu hanya kemudahan; halaman di luar tampilan peran ditolak di server
        # (PersonaAccessMiddleware dan izin masing-masing view).
        "nav_sections": nav_sections(user),
        "nav_persona": who,
        "nav_persona_label": LABELS[who],
        "nav_can_team_plan": route_allowed(user, "jadwal:plan"),
    }
