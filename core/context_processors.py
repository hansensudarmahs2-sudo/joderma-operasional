"""Context global: notifikasi, izin navigasi, hari operasional."""
from __future__ import annotations

from notifications.services import unread_count

from .permissions import (
    can_export,
    can_manage_config,
    can_manage_users,
    can_view_audit,
    can_view_cash_amounts,
    is_supervisor,
)


def app_context(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {"app_name": "JoDerma Staff Ops"}
    return {
        "app_name": "JoDerma Staff Ops",
        "unread_notifications": unread_count(user),
        "nav_can_cash": can_view_cash_amounts(user),
        "nav_can_audit": can_view_audit(user),
        "nav_can_admin": can_manage_users(user) or can_manage_config(user),
        "nav_can_export": can_export(user),
        "nav_is_supervisor": is_supervisor(user),
    }
