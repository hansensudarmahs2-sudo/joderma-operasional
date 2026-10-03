"""Permintaan Owner: satu-satunya yang dibuat Owner / Direktur Utama.

Owner menulis permintaan beserta tanggal target. Penerimanya hanya Direktur
Operasional, yang memecahnya menjadi task (`core.ActionItem` dengan
``source_type="permintaan_owner"`` dan ``source_id`` = permintaan ini). Progres dibaca
dari task turunannya. Tidak ada alur tolak; revisi dibicarakan langsung (WhatsApp) atau
ditulis sebagai catatan pada permintaan. Lihat `docs/KEBUTUHAN_REDEFINISI_PERAN.md`.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

SOURCE_TYPE = "permintaan_owner"


class RequestKind(models.TextChoices):
    PERMINTAAN = "PERMINTAAN", "Permintaan"
    TEMUAN = "TEMUAN", "Temuan"


class OwnerRequest(models.Model):
    """Permintaan atau temuan Owner. Temuan: target boleh kosong, Direktur yang menentukan."""

    kind = models.CharField("jenis", max_length=12, choices=RequestKind.choices, default=RequestKind.PERMINTAAN)
    title = models.CharField("permintaan", max_length=200)
    description = models.TextField("rincian", blank=True)
    target_date = models.DateField("target", null=True, blank=True)
    clinic = models.ForeignKey(
        "core.Clinic", on_delete=models.PROTECT, null=True, blank=True, related_name="owner_requests",
        help_text="Kosong bila lintas cabang.",
    )
    urgent = models.BooleanField("mendesak", default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="owner_requests"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "permintaan Owner"
        verbose_name_plural = "permintaan Owner"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return self.title

    def tasks(self):
        from core.models import ActionItem, ActionItemStatus

        return (
            ActionItem.objects.filter(source_type=SOURCE_TYPE, source_id=self.pk)
            .exclude(status=ActionItemStatus.BATAL)
            .select_related("clinic", "owner")
            .order_by("due_at", "created_at")
        )


class OwnerRequestNote(models.Model):
    """Catatan pada permintaan (Owner atau Direktur). Tidak diubah atau dihapus."""

    request = models.ForeignKey(OwnerRequest, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    body = models.TextField("catatan")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "catatan permintaan"
        verbose_name_plural = "catatan permintaan"
        ordering = ("created_at",)

    def __str__(self) -> str:
        return self.body[:80]
