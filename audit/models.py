"""Audit event append-only (PRD 11)."""
from __future__ import annotations

from django.conf import settings
from django.db import models


class AuditAction(models.TextChoices):
    LOGIN_SUCCESS = "LOGIN_SUCCESS", "Login berhasil"
    LOGIN_FAILED = "LOGIN_FAILED", "Login gagal"
    LOGOUT = "LOGOUT", "Logout"
    PASSWORD_CHANGED = "PASSWORD_CHANGED", "Password diubah"
    CREATE = "CREATE", "Membuat"
    UPDATE = "UPDATE", "Mengubah"
    VERIFY = "VERIFY", "Memverifikasi"
    APPROVE = "APPROVE", "Menyetujui"
    CANCEL = "CANCEL", "Membatalkan"
    CLOSE = "CLOSE", "Menutup"
    REOPEN = "REOPEN", "Membuka kembali"
    OVERRIDE = "OVERRIDE", "Override"
    EXPORT = "EXPORT", "Ekspor data"
    VIEW_RESTRICTED = "VIEW_RESTRICTED", "Akses catatan terbatas"
    DOWNLOAD_ATTACHMENT = "DOWNLOAD_ATTACHMENT", "Unduh lampiran"
    PERMISSION_CHANGED = "PERMISSION_CHANGED", "Perubahan peran/izin"
    CONFIG_CHANGED = "CONFIG_CHANGED", "Perubahan konfigurasi"


class AuditEvent(models.Model):
    """Append-only. Tidak boleh diedit atau dihapus lewat aplikasi."""

    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    actor_label = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=32, choices=AuditAction.choices, db_index=True)
    entity_type = models.CharField(max_length=60, db_index=True)
    entity_id = models.CharField(max_length=40, blank=True, db_index=True)
    entity_label = models.CharField(max_length=200, blank=True)
    before_json = models.JSONField(null=True, blank=True)
    after_json = models.JSONField(null=True, blank=True)
    reason = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    correlation_id = models.CharField(max_length=40, blank=True, db_index=True)
    session_key = models.CharField(max_length=60, blank=True)

    class Meta:
        verbose_name = "audit event"
        verbose_name_plural = "audit event"
        ordering = ("-occurred_at", "-id")
        indexes = [models.Index(fields=["entity_type", "entity_id"])]

    def __str__(self) -> str:
        return f"{self.occurred_at:%Y-%m-%d %H:%M} {self.actor_label} {self.action} {self.entity_type}#{self.entity_id}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise RuntimeError("AuditEvent bersifat append-only dan tidak dapat diubah.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("AuditEvent tidak dapat dihapus melalui aplikasi.")

    @property
    def diff_fields(self) -> list[tuple[str, object, object]]:
        before = self.before_json or {}
        after = self.after_json or {}
        keys = sorted(set(before) | set(after))
        return [(k, before.get(k), after.get(k)) for k in keys if before.get(k) != after.get(k)]
