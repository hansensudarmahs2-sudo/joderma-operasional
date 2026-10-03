"""Penolakan server-side per tampilan peran (lihat `core/peran.py`)."""
from __future__ import annotations

from django.core.exceptions import PermissionDenied

from .peran import route_allowed


class PersonaAccessMiddleware:
    """Halaman di luar tampilan peran ditolak (403), bukan hanya disembunyikan dari menu."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        user = getattr(request, "user", None)
        match = getattr(request, "resolver_match", None)
        if not user or not user.is_authenticated or match is None or not match.url_name:
            return None
        route = f"{match.namespace}:{match.url_name}"
        if not route_allowed(user, route, request.method):
            raise PermissionDenied("Halaman ini bukan bagian dari tampilan peran Anda.")
        return None


class ActiveClinicMiddleware:
    """Pilihan cabang dari pengalih di kanan atas berlaku untuk hari ini saja.

    Disimpan di sesi sebagai ``{"id": <pk>, "date": "YYYY-MM-DD"}`` dan dipasang ke
    ``request.user._clinic_override``, yang dibaca `core.services.active_clinic`.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            from .models import local_today
            from .services import CLINIC_SESSION_KEY

            choice = request.session.get(CLINIC_SESSION_KEY) or {}
            if choice.get("date") == local_today().isoformat():
                user._clinic_override = choice.get("id")
            elif choice:
                request.session.pop(CLINIC_SESSION_KEY, None)
        return self.get_response(request)
