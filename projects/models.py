"""Projects: wadah task kecil yang diberikan ke individu.

Task project adalah `core.ActionItem` biasa dengan ``source_type="proyek"`` dan ``source_id`` =
pk project ini, sehingga otomatis tampil di "Tugas saya" staf dan Daftar Task Direktur.
Aturan dan izin ada di `projects.services`.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

SOURCE_TYPE = "proyek"


class ProjectStatus(models.TextChoices):
    AKTIF = "AKTIF", "Berjalan"
    SELESAI = "SELESAI", "Selesai"
    DIBATALKAN = "DIBATALKAN", "Dibatalkan"


class Project(models.Model):
    name = models.CharField("nama project", max_length=200)
    description = models.TextField("uraian", blank=True)
    target_date = models.DateField("target", null=True, blank=True)
    clinic = models.ForeignKey(
        "core.Clinic", on_delete=models.PROTECT, null=True, blank=True, related_name="projects",
        help_text="Kosong bila lintas cabang.",
    )
    status = models.CharField(max_length=12, choices=ProjectStatus.choices, default=ProjectStatus.AKTIF)
    leader = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="led_projects", verbose_name="Project leader",
    )
    co_leaders = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="co_led_projects", verbose_name="Co-project leader",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_projects",
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    close_note = models.TextField("catatan penutupan", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "project"
        verbose_name_plural = "project"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return self.name

    @property
    def is_active(self) -> bool:
        return self.status == ProjectStatus.AKTIF

    def tasks(self):
        """Task project yang belum dibatalkan."""
        from core.models import ActionItem, ActionItemStatus

        return ActionItem.objects.filter(source_type=SOURCE_TYPE, source_id=self.pk).exclude(
            status=ActionItemStatus.BATAL
        )

    def progress(self) -> dict:
        """Progres: ``total`` task, ``done`` (task selesai), ``percent`` (0-100), ``partial``.

        Persen = rata-rata kontribusi per task. Task selesai = 1; task INDIVIDUAL dengan banyak
        penerima = dikonfirmasi / penerima aktif; task BERSAMA = 1 bila penerima yang mengambilnya
        sudah dikonfirmasi, selain itu 0. ``partial`` True bila ada task belum selesai yang sudah
        sebagian jalan (persen ikut memuat pecahan).
        """
        from core.models import ActionItemStatus, TaskAssignmentMode, TaskAssignmentStatus

        items = list(self.tasks().prefetch_related("task_assignments"))
        total = len(items)
        done = 0
        score = 0.0
        partial = False
        for item in items:
            if item.status == ActionItemStatus.SELESAI:
                done += 1
                score += 1
                continue
            active = [a for a in item.task_assignments.all() if a.status != TaskAssignmentStatus.CANCELLED]
            if item.assignment_mode == TaskAssignmentMode.BERSAMA:
                claimer = next((a.claimed_by_id for a in active if a.claimed_by_id), None)
                fraction = 1.0 if claimer and any(
                    a.assignee_id == claimer and a.status == TaskAssignmentStatus.CONFIRMED for a in active
                ) else 0.0
            elif active:
                fraction = sum(a.status == TaskAssignmentStatus.CONFIRMED for a in active) / len(active)
            else:
                fraction = 0.0
            if 0 < fraction < 1:
                partial = True
            score += fraction
        percent = round(score / total * 100) if total else 0
        return {"total": total, "done": done, "percent": percent, "partial": partial}

    def is_overdue(self, today=None) -> bool:
        from core.models import local_today

        if self.status != ProjectStatus.AKTIF or not self.target_date:
            return False
        return self.target_date < (today or local_today())
