"""Middleware konteks request untuk audit: correlation ID, IP, user agent."""
from __future__ import annotations

import contextvars
import uuid

_request_context: contextvars.ContextVar[dict] = contextvars.ContextVar(
    "audit_request_context", default={}
)


def get_request_context() -> dict:
    return _request_context.get() or {}


def set_request_context(**kwargs) -> None:
    _request_context.set(kwargs)


def client_ip(request) -> str | None:
    """IP pengguna. Lewat ops.joderma.id, Cloudflare mengisi CF-Connecting-IP yang tidak bisa
    dipalsukan pengirim (X-Forwarded-For bisa diisi sendiri lalu hanya ditambah Cloudflare).
    Lewat Tailscale Serve, X-Forwarded-For berisi IP perangkat tailnet (100.x)."""
    cf = request.META.get("HTTP_CF_CONNECTING_IP", "").strip()
    if cf:
        return cf
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class RequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        correlation_id = request.headers.get("X-Correlation-ID") or uuid.uuid4().hex[:16]
        user = getattr(request, "user", None)
        token = _request_context.set(
            {
                "correlation_id": correlation_id,
                "ip": client_ip(request),
                "user_agent": request.META.get("HTTP_USER_AGENT", ""),
                "session_key": request.session.session_key or ""
                if hasattr(request, "session")
                else "",
                "actor_label": str(user) if user and user.is_authenticated else "anonim",
                "path": request.path,
            }
        )
        request.correlation_id = correlation_id
        try:
            response = self.get_response(request)
        finally:
            _request_context.reset(token)
        response["X-Correlation-ID"] = correlation_id
        return response
