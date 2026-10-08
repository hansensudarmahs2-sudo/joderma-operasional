"""Service layer audit: satu pintu untuk mencatat peristiwa (PRD 11)."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any, Iterable

from django.db import models

from .middleware import get_request_context
from .models import AuditAction, AuditEvent

SENSITIVE_FIELDS = {"password", "password_hash", "token", "secret", "session_key", "csrf"}
# Bintang penilaian task (8 Okt 2026): hanya Direktur Operasional dan Owner yang membaca jejaknya.
RATING_AUDIT_ENTITY = "bintang_task"
RESTRICTED_ENTITY_TYPES = {RATING_AUDIT_ENTITY}


def _serialize_value(value: Any) -> Any:
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, models.Model):
        return f"{value._meta.model_name}#{value.pk}"
    if isinstance(value, models.Manager):
        return None
    if isinstance(value, (list, tuple, set)):
        return [_serialize_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def snapshot(instance: models.Model | None, fields: Iterable[str] | None = None) -> dict | None:
    """Ambil snapshot field model, menyaring field sensitif."""
    if instance is None:
        return None
    if fields is None:
        fields = [
            f.name
            for f in instance._meta.fields
            if not any(s in f.name.lower() for s in SENSITIVE_FIELDS)
        ]
    data = {}
    for name in fields:
        if any(s in name.lower() for s in SENSITIVE_FIELDS):
            continue
        try:
            data[name] = _serialize_value(getattr(instance, name))
        except Exception:  # pragma: no cover - defensif
            continue
    return data


def log_event(
    *,
    action: str,
    entity_type: str,
    entity_id: Any = "",
    entity_label: str = "",
    actor=None,
    before: dict | None = None,
    after: dict | None = None,
    reason: str = "",
    request=None,
) -> AuditEvent:
    ctx = get_request_context()
    if request is not None:
        actor = actor or (request.user if getattr(request, "user", None) and request.user.is_authenticated else None)

    return AuditEvent.objects.create(
        actor=actor if actor and getattr(actor, "pk", None) else None,
        actor_label=str(actor) if actor else ctx.get("actor_label", ""),
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id or ""),
        entity_label=entity_label[:200],
        before_json=before,
        after_json=after,
        reason=reason or "",
        ip_address=ctx.get("ip"),
        user_agent=(ctx.get("user_agent") or "")[:300],
        correlation_id=ctx.get("correlation_id", ""),
        session_key=ctx.get("session_key", ""),
    )


def log_create(instance, *, actor=None, reason: str = "", label: str = "", request=None):
    return log_event(
        action=AuditAction.CREATE,
        entity_type=instance._meta.model_name,
        entity_id=instance.pk,
        entity_label=label or str(instance),
        actor=actor,
        after=snapshot(instance),
        reason=reason,
        request=request,
    )


def log_update(
    instance,
    before: dict | None,
    *,
    actor=None,
    reason: str = "",
    action: str = AuditAction.UPDATE,
    label: str = "",
    request=None,
):
    return log_event(
        action=action,
        entity_type=instance._meta.model_name,
        entity_id=instance.pk,
        entity_label=label or str(instance),
        actor=actor,
        before=before,
        after=snapshot(instance),
        reason=reason,
        request=request,
    )
