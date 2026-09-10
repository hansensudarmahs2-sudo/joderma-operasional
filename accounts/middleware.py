"""Session idle & absolute timeout (PRD 16.5)."""
from __future__ import annotations

import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse

IDLE_KEY = "_last_activity"
START_KEY = "_session_started"
EXEMPT_PREFIXES = ("/akun/login", "/akun/logout", "/static/", "/health")


class SessionTimeoutMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and not request.path.startswith(EXEMPT_PREFIXES):
            now = time.time()
            started = request.session.get(START_KEY) or now
            last = request.session.get(IDLE_KEY) or now
            idle_limit = settings.SESSION_IDLE_TIMEOUT_SECONDS
            abs_limit = settings.SESSION_ABSOLUTE_TIMEOUT_SECONDS

            if now - last > idle_limit or now - started > abs_limit:
                logout(request)
                messages.info(request, "Sesi berakhir karena tidak ada aktivitas. Silakan masuk kembali.")
                return redirect(reverse("accounts:login"))

            request.session[IDLE_KEY] = now
            request.session.setdefault(START_KEY, started)

            if not request.user.is_active:
                logout(request)
                messages.error(request, "Akun Anda dinonaktifkan.")
                return redirect(reverse("accounts:login"))

        return self.get_response(request)
