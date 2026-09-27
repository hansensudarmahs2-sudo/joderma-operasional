"""Context global: notifikasi, izin navigasi, hari operasional."""
from __future__ import annotations

from notifications.services import unread_count

from .permissions import (
    can_export,
    can_manage_config,
    can_manage_users,
    can_view_audit,
    can_view_cash_amounts,
    has_role,
    is_front_desk,
    is_nurse,
    is_owner,
    is_aom,
    is_supervisor,
)
from accounts.models import Role


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
        "nav_is_director": is_aom(user),
        # Navigasi mengikuti fungsi kerja pada checklist/PDF. Ini bukan
        # pengganti permission server-side di masing-masing view.
        "nav_can_queue": False,
        "nav_can_orders": has_role(user, Role.ONLINE, Role.APOTEKER, Role.ASISTEN_APOTEKER, Role.SUPERVISOR, Role.PIC),
        "nav_can_roster": is_nurse(user) or is_supervisor(user),
        "nav_can_breaks": not (is_aom(user) or is_owner(user)),
        "nav_can_issues": not (is_aom(user) or is_owner(user)),
        "nav_can_reports": (
            is_front_desk(user)
            or is_nurse(user)
            or has_role(user, Role.APOTEKER, Role.ASISTEN_APOTEKER, Role.ONLINE, Role.PIC, Role.SUPERVISOR)
            or is_aom(user)
            or is_owner(user)
        ),
    }
