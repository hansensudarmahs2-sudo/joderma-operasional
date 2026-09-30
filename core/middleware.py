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
        if not route_allowed(user, route):
            raise PermissionDenied("Halaman ini bukan bagian dari tampilan peran Anda.")
        return None
