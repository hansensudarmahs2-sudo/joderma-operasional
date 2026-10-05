"""Model laporan cabang dan laporan rahasia AOM (PRD/plan bagian 9)."""
from __future__ import annotations

from django.conf import settings
from django.db import models


class ReportVisibility(models.TextChoices):
    CABANG = "CABANG", "Terlihat satu cabang"
    RAHASIA_AOM = "RAHASIA_AOM", "Rahasia — hanya pelapor dan Direktur Operasional"


class ReportStatus(models.TextChoices):
    OPEN = "OPEN", "Baru"
    UNDER_REVIEW = "UNDER_REVIEW", "Ditinjau"
    RESOLVED = "RESOLVED", "Selesai"
    CLOSED = "CLOSED", "Ditutup"
    ARCHIVED = "ARCHIVED", "Diarsipkan"


ACTIVE_STATUSES = {
    ReportStatus.OPEN,
    ReportStatus.UNDER_REVIEW,
    ReportStatus.RESOLVED,
    ReportStatus.CLOSED,
}

REPORT_WORKFLOW: dict[str, set[str]] = {
    ReportStatus.OPEN: {ReportStatus.UNDER_REVIEW, ReportStatus.RESOLVED, ReportStatus.CLOSED},
    ReportStatus.UNDER_REVIEW: {ReportStatus.RESOLVED, ReportStatus.CLOSED},
    ReportStatus.RESOLVED: {ReportStatus.CLOSED, ReportStatus.UNDER_REVIEW},
    ReportStatus.CLOSED: {ReportStatus.UNDER_REVIEW},
    ReportStatus.ARCHIVED: set(),
}


class Laporan(models.Model):
    """Laporan umum satu cabang atau laporan rahasia ke AOM (plan 9.1, 9.2).

    Tidak ada publikasi otomatis lintas cabang. Visibilitas ``RAHASIA_AOM``
    hanya terlihat oleh pelapor dan AOM — lihat ``reports.permissions``.
    """

    clinic = models.ForeignKey("core.Clinic", on_delete=models.CASCADE, related_name="laporan_set")
    visibility = models.CharField(
        "visibilitas", max_length=20, choices=ReportVisibility.choices, db_index=True
    )
    status = models.CharField(
        max_length=20, choices=ReportStatus.choices, default=ReportStatus.OPEN, db_index=True
    )
    title = models.CharField("ringkasan", max_length=200)
    description = models.TextField("uraian", blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="laporan_dibuat",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    archived_at = models.DateTimeField(null=True, blank=True)
    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="laporan_diarsipkan",
    )
    archive_reason = models.TextField("alasan arsip", blank=True)

    version = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "laporan"
        verbose_name_plural = "laporan"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["clinic", "visibility", "status"])]

    def __str__(self) -> str:
        return f"Laporan#{self.pk} · {self.title}"

    def allowed_next_statuses(self) -> set[str]:
        return REPORT_WORKFLOW.get(self.status, set())


class LaporanUpdate(models.Model):
    """Riwayat perubahan status laporan (mirip IssueUpdate)."""

    laporan = models.ForeignKey(Laporan, on_delete=models.CASCADE, related_name="updates")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="laporan_updates"
    )
    from_status = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=20, blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "riwayat laporan"
        verbose_name_plural = "riwayat laporan"
        ordering = ("created_at", "id")

    def __str__(self) -> str:
        return f"Laporan#{self.laporan_id} {self.status}"


class Masukan(models.Model):
    """Masukan/saran privat; dapat dipublikasikan AOM ke cabang (plan 10).

    Visibilitas awal: pengirim dan AOM. Publikasi tidak mengubah baris ini
    secara retroaktif — setiap publikasi membuat ``MasukanPublication`` berisi
    snapshot isi saat dipublikasikan (mirror pola
    ``checklists.services.create_template_version``/``TaskAudienceSnapshot``).
    """

    clinic = models.ForeignKey(
        "core.Clinic",
        on_delete=models.CASCADE,
        related_name="masukan_set",
        help_text="Cabang pengirim saat masukan dibuat (bukan target publikasi).",
    )
    title = models.CharField("ringkasan", max_length=200)
    description = models.TextField("uraian", blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="masukan_dibuat",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    archived_at = models.DateTimeField(null=True, blank=True)
    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="masukan_diarsipkan",
    )
    archive_reason = models.TextField("alasan arsip", blank=True)

    version = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "masukan"
        verbose_name_plural = "masukan"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"Masukan#{self.pk} · {self.title}"

    @property
    def is_published(self) -> bool:
        return self.publications.exists()


class MasukanPublication(models.Model):
    """Satu peristiwa publikasi: siapa, kapan, cabang mana, dan snapshot isi."""

    masukan = models.ForeignKey(Masukan, on_delete=models.CASCADE, related_name="publications")
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="masukan_dipublikasikan",
    )
    published_at = models.DateTimeField(auto_now_add=True, db_index=True)
    clinics = models.ManyToManyField(
        "core.Clinic", related_name="masukan_publications", verbose_name="cabang tujuan"
    )
    title_snapshot = models.CharField(max_length=200)
    description_snapshot = models.TextField(blank=True)
    source_version = models.PositiveIntegerField(
        help_text="Versi Masukan.version pada saat publikasi (histori tidak berubah)."
    )

    class Meta:
        verbose_name = "publikasi masukan"
        verbose_name_plural = "publikasi masukan"
        ordering = ("-published_at",)

    def __str__(self) -> str:
        return f"Publikasi Masukan#{self.masukan_id} · v{self.source_version}"


class TriageAction(models.TextChoices):
    TUGASKAN = "TUGASKAN", "Diputuskan dan ditugaskan"
    TERUSKAN = "TERUSKAN", "Diteruskan, dipantau"
    RAPAT = "RAPAT", "Dibawa ke rapat bersama"
    KEBIJAKAN = "KEBIJAKAN", "Dijadikan kebijakan"
    TIDAK = "TIDAK", "Tidak ditindaklanjuti"


class ForwardTo(models.TextChoices):
    """Pemegang wewenang di luar bidang Direktur Operasional (matriks wewenang, Okt 2026)."""

    DIRUT = "DIRUT", "Direktur Utama / Owner (strategis, SP/pemberhentian)"
    APOTEKER = "APOTEKER", "Apoteker (apotek, stok, harga obat)"
    KEUANGAN = "KEUANGAN", "Keuangan (di atas Rp1 juta)"
    MEDIS = "MEDIS", "Penanggung jawab medis"
    OMNICARE = "OMNICARE", "Omnicare"
    LAINNYA = "LAINNYA", "Lainnya"


class InboxTriage(models.Model):
    """Hasil pilah satu item Inbox oleh Direktur Operasional (GTD, tahap 2 paket B).

    Satu baris per item sumber; pilah ulang memperbarui baris yang sama (jejaknya di audit log).
    Sumber: issue (komplain/masukan/kerusakan), laporan, masukan staf, permintaan_owner
    (permintaan dan temuan Owner), catatan_direktur.
    """

    source_type = models.CharField("jenis sumber", max_length=24)
    source_id = models.PositiveIntegerField("id sumber")
    action = models.CharField("hasil pilah", max_length=12, choices=TriageAction.choices)
    forwarded_to = models.CharField("diteruskan ke", max_length=12, choices=ForwardTo.choices, blank=True)
    note = models.TextField("catatan", blank=True)
    task = models.ForeignKey(
        "core.ActionItem", on_delete=models.SET_NULL, null=True, blank=True, related_name="inbox_triages"
    )
    decision = models.ForeignKey(
        "direktur.Decision", on_delete=models.SET_NULL, null=True, blank=True, related_name="inbox_triages"
    )
    triaged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="inbox_triages"
    )
    triaged_at = models.DateTimeField("dipilah pada", auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "pilah inbox"
        verbose_name_plural = "pilah inbox"
        constraints = [
            models.UniqueConstraint(fields=["source_type", "source_id"], name="uniq_inbox_triage_source")
        ]

    def __str__(self) -> str:
        return f"{self.source_type}#{self.source_id} · {self.get_action_display()}"
