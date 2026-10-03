"""Service notifikasi in-app dengan deduplikasi jendela pendek (PRD 10.3)."""
from __future__ import annotations

from datetime import timedelta

from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from .models import Notification

DEDUPE_WINDOW = timedelta(minutes=10)


def _resolve_url(url_name: str | None, url_args=None) -> str:
    if not url_name:
        return ""
    try:
        return reverse(url_name, args=url_args or [])
    except NoReverseMatch:
        return ""


def notify_user(
    user,
    *,
    type_code: str,
    title: str,
    body: str = "",
    entity_ref: str = "",
    url_name: str | None = None,
    url_args=None,
) -> Notification | None:
    if user is None or not getattr(user, "is_active", False):
        return None

    cutoff = timezone.now() - DEDUPE_WINDOW
    duplicate = Notification.objects.filter(
        user=user,
        type_code=type_code,
        entity_ref=entity_ref,
        read_at__isnull=True,
        created_at__gte=cutoff,
    ).first()
    if duplicate:
        duplicate.title = title[:160]
        duplicate.body = body[:300]
        duplicate.save(update_fields=["title", "body"])
        return duplicate

    return Notification.objects.create(
        user=user,
        type_code=type_code,
        title=title[:160],
        body=body[:300],
        entity_ref=entity_ref,
        url=_resolve_url(url_name, url_args),
    )


def notify_role(clinic, role: str, **kwargs) -> list[Notification]:
    from accounts.models import User

    recipients = User.objects.filter(
        is_active=True, user_roles__role=role, user_roles__clinic=clinic
    ).distinct()
    created = []
    for user in recipients:
        notif = notify_user(user, **kwargs)
        if notif:
            created.append(notif)
    return created


def unread_count(user) -> int:
    if not user or not user.is_authenticated:
        return 0
    return Notification.objects.filter(user=user, read_at__isnull=True).count()


def mark_read(user, notification_id: int | None = None) -> int:
    qs = Notification.objects.filter(user=user, read_at__isnull=True)
    if notification_id:
        qs = qs.filter(pk=notification_id)
    return qs.update(read_at=timezone.now())


def notify_leaders(*, owners: bool = False, **kwargs) -> list[Notification]:
    """Kirim ke semua Direktur Operasional (peran AOM di cabang mana pun), dan Owner bila diminta.

    `notify_role(clinic, "AOM")` hanya sampai bila Direktur memegang peran AOM di cabang pengirim;
    Direktur biasanya hanya terdaftar di satu cabang, sehingga laporan dari cabang lain tidak sampai
    (kasus Citraland 3 Okt 2026). Fungsi ini lintas cabang.
    """
    from accounts.models import Role, User

    roles = [Role.AOM] + ([Role.OWNER] if owners else [])
    recipients = User.objects.filter(is_active=True, user_roles__role__in=roles).distinct()
    created = []
    for user in recipients:
        notif = notify_user(user, **kwargs)
        if notif:
            created.append(notif)
    return created
