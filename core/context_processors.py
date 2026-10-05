"""Context global: notifikasi dan menu per tampilan peran (lihat `core/peran.py`)."""
from __future__ import annotations

from notifications.services import unread_count

from .peran import LABELS, nav_sections, persona, route_allowed, subnav


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
        "banner": soft_banner(request, who),
        "subnav": subnav(user, getattr(getattr(request, "resolver_match", None), "view_name", "")),
    }


SESSION_DEFAULT_PASSWORD = "sandi_awal"


def soft_banner(request, who: str) -> dict:
    """Saran lembut di atas layar (bukan paksaan; 'Nanti' menyembunyikan 7 hari di browser itu).

    - password: akun masih memakai password awal. Dicek sekali per sesi (saat login dari isian
      login; untuk sesi lama, sekali di sini) dan disimpan di sesi, bukan di database.
    - location: ajakan mengizinkan lokasi untuk jejak kehadiran; status izin dibaca di browser.
      Tidak untuk Owner, dan tidak di perangkat klinik terdaftar (jejaknya sudah Kuat).
    """
    user = request.user
    session = getattr(request, "session", None)
    uses_default = False
    if session is not None:
        if SESSION_DEFAULT_PASSWORD not in session:
            from accounts.peran_standar import DEFAULT_PASSWORD

            session[SESSION_DEFAULT_PASSWORD] = bool(user.has_usable_password()
                                                     and user.check_password(DEFAULT_PASSWORD))
        uses_default = bool(session.get(SESSION_DEFAULT_PASSWORD))
    match = getattr(request, "resolver_match", None)
    on_password_page = bool(match and match.view_name == "accounts:change_password")
    if uses_default and not on_password_page:
        return {"password": True, "location": False}
    location = who != "OWNER"
    if location:
        from audit.middleware import client_ip
        from jejak.models import KnownDevice

        ip = client_ip(request)
        if ip and KnownDevice.objects.filter(ip_address=ip, is_clinic_device=True).exists():
            location = False
    return {"password": False, "location": location}
