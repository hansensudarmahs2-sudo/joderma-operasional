"""Notifikasi dalam aplikasi (PRD 10)."""
from __future__ import annotations

from django.conf import settings
from django.db import models


class Notification(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    type_code = models.CharField(max_length=40, db_index=True)
    title = models.CharField(max_length=160)
    body = models.CharField(max_length=300, blank=True)
    entity_ref = models.CharField(max_length=60, blank=True, db_index=True)
    url = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "notifikasi"
        verbose_name_plural = "notifikasi"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.user} · {self.title}"

    @property
    def is_read(self) -> bool:
        return self.read_at is not None
