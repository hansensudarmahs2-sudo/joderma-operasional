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
    plan_title = models.CharField(
        "task besar", max_length=200, blank=True,
        help_text="Nama penanganan temuan dari Direktur, mis. 'Membuat alur untuk temuan X'.",
    )
    completed_at = models.DateTimeField("dinyatakan selesai", null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
    proposed_target = models.DateField("usulan target", null=True, blank=True)
    proposed_reason = models.TextField("alasan usulan target", blank=True)
    proposed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    proposed_at = models.DateTimeField(null=True, blank=True)
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


class UsulanKind(models.TextChoices):
    PERSETUJUAN = "PERSETUJUAN", "Minta persetujuan"
    LAPORAN = "LAPORAN", "Laporan masalah/risiko"


class UsulanStatus(models.TextChoices):
    MENUNGGU = "MENUNGGU", "Menunggu keputusan"
    DISETUJUI = "DISETUJUI", "Disetujui"
    DITOLAK = "DITOLAK", "Ditolak"
    RAPAT = "RAPAT", "Dibawa ke rapat"
    TERKIRIM = "TERKIRIM", "Terkirim"
    DIBACA = "DIBACA", "Sudah dibaca"
    DIBATALKAN = "DIBATALKAN", "Dibatalkan"


class Usulan(models.Model):
    """Usulan Direktur Operasional ke Owner atas inisiatif sendiri (tahap 4).

    Minta persetujuan (Owner: setujui / tolak / bahas di rapat) atau laporan masalah/risiko
    (Owner menandai sudah dibaca). Percakapan dua arah ada di `UsulanCatatan`.
    """

    kind = models.CharField("jenis", max_length=12, choices=UsulanKind.choices)
    title = models.CharField("judul", max_length=200)
    description = models.TextField("uraian")
    amount = models.PositiveBigIntegerField("nominal anggaran (Rp)", null=True, blank=True)
    clinic = models.ForeignKey(
        "core.Clinic", on_delete=models.PROTECT, null=True, blank=True, related_name="usulan",
        help_text="Kosong bila lintas cabang.",
    )
    needed_by = models.DateField("perlu jawaban sebelum", null=True, blank=True)
    status = models.CharField(max_length=12, choices=UsulanStatus.choices)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField("catatan keputusan", blank=True)
    decision = models.ForeignKey(
        "direktur.Decision", on_delete=models.SET_NULL, null=True, blank=True, related_name="usulan",
        help_text="Perkara rapat bila usulan dibawa ke rapat.",
    )
    read_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    read_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.TextField("alasan pembatalan", blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="usulan_dibuat")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "usulan"
        verbose_name_plural = "usulan"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"Usulan#{self.pk} · {self.title}"

    @property
    def is_open(self) -> bool:
        return self.status in (UsulanStatus.MENUNGGU, UsulanStatus.TERKIRIM)

    def is_overdue(self, today) -> bool:
        return bool(self.needed_by and self.needed_by < today and self.status == UsulanStatus.MENUNGGU)


class UsulanCatatan(models.Model):
    """Percakapan pada usulan (Owner atau Direktur). Tidak diubah atau dihapus."""

    usulan = models.ForeignKey(Usulan, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    note = models.TextField("catatan")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "catatan usulan"
        verbose_name_plural = "catatan usulan"
        ordering = ("created_at", "id")

    def __str__(self) -> str:
        return self.note[:80]
