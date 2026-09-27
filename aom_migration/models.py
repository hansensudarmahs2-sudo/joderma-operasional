"""Model migrasi legacy AOM standalone (Fase 6 — migration rehearsal).

Semua model di sini bersifat pendukung migrasi satu arah (AOM standalone
lama -> JoDerma Operasional). Tidak ada model di sini yang dipakai langsung
oleh workflow checklist/task modul klinik yang sudah ada; lihat
`docs/AOM_LEGACY_EXPORT_SCHEMA.md` untuk kontrak data lengkap.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models


class LegacyImportBatch(models.Model):
    """Satu kali eksekusi import berkas ekspor legacy AOM standalone."""

    name = models.CharField("nama batch", max_length=120)
    source_label = models.CharField("label sumber", max_length=120, blank=True)
    exported_at = models.DateTimeField("waktu ekspor sumber", null=True, blank=True)
    imported_at = models.DateTimeField("waktu import", auto_now_add=True)
    manifest_checksum = models.CharField("checksum manifest ekspor", max_length=140, blank=True)
    notes = models.TextField(
        "catatan",
        blank=True,
        help_text=(
            "Keputusan eksplisit saat rehearsal, mis. aturan cabang default, "
            "jumlah exception, dan hasil rekonsiliasi."
        ),
    )

    class Meta:
        verbose_name = "batch import legacy AOM"
        verbose_name_plural = "batch import legacy AOM"
        ordering = ("-imported_at",)

    def __str__(self) -> str:
        return f"{self.name} ({self.imported_at:%Y-%m-%d %H:%M})"


class LegacyIdMap(models.Model):
    """Pemetaan ID legacy AOM standalone -> objek JoDerma Operasional.

    Dasar idempotensi: kombinasi (source_model, legacy_id, target_model)
    unik, sehingga import ulang berkas ekspor yang sama tidak pernah membuat
    baris target baru — harus selalu dicek lewat `get_or_create`, tidak
    pernah `create` langsung.
    """

    source_model = models.CharField("model sumber", max_length=60)
    legacy_id = models.CharField("ID legacy", max_length=64)
    target_model = models.CharField("model target", max_length=60)
    target_id = models.PositiveIntegerField("ID target")
    batch = models.ForeignKey(
        LegacyImportBatch, on_delete=models.CASCADE, related_name="id_maps"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "pemetaan ID legacy"
        verbose_name_plural = "pemetaan ID legacy"
        constraints = [
            models.UniqueConstraint(
                fields=["source_model", "legacy_id", "target_model"],
                name="uniq_legacy_id_map",
            )
        ]
        indexes = [models.Index(fields=["source_model", "legacy_id"])]

    def __str__(self) -> str:
        return f"{self.source_model}#{self.legacy_id} -> {self.target_model}#{self.target_id}"


class LegacyActor(models.Model):
    """Label aktor lama dari AOM standalone, dipertahankan apa adanya.

    `mapped_user` HANYA diisi bila ada mapping tervalidasi yang sudah ada
    sebelumnya untuk label ini — importer tidak pernah menebak user dari
    string nama (plan 12.2.4).
    """

    label = models.CharField("label aktor lama", max_length=150, unique=True)
    mapped_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="legacy_actor_labels",
    )

    class Meta:
        verbose_name = "aktor legacy AOM"
        verbose_name_plural = "aktor legacy AOM"
        ordering = ("label",)

    def __str__(self) -> str:
        mapped = self.mapped_user.username if self.mapped_user_id else "belum dipetakan"
        return f"{self.label} ({mapped})"


class LegacyArchive(models.Model):
    """Histori read-only dari entitas AOM standalone yang tidak punya padanan
    live langsung di JoDerma Operasional (ChecklistTemplate, DailyChecklist,
    Note, Activity, DailyClose) — plan 12.2.7: dipertahankan sebagai histori,
    bukan diubah jadi objek checklist baru.
    """

    source_model = models.CharField("model sumber", max_length=60)
    legacy_id = models.CharField("ID legacy", max_length=64)
    batch = models.ForeignKey(
        LegacyImportBatch, on_delete=models.CASCADE, related_name="archives"
    )
    payload = models.JSONField("payload asli", default=dict)
    checksum = models.CharField("checksum record", max_length=140, blank=True)
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "arsip histori legacy AOM"
        verbose_name_plural = "arsip histori legacy AOM"
        constraints = [
            models.UniqueConstraint(
                fields=["source_model", "legacy_id"], name="uniq_legacy_archive"
            )
        ]
        indexes = [models.Index(fields=["source_model", "legacy_id"])]
        ordering = ("source_model", "legacy_id")

    def __str__(self) -> str:
        return f"{self.source_model}#{self.legacy_id}"
