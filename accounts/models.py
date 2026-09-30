"""Model pengguna dan peran (RBAC) JoDerma Staff Ops."""
from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    STAF = "STAF", "Staf operasional"
    FRONT_DESK = "FRONT_DESK", "Front desk/kasir"
    PERAWAT = "PERAWAT", "Perawat"
    APOTEKER = "APOTEKER", "Apoteker"
    ASISTEN_APOTEKER = "ASISTEN_APOTEKER", "Asisten apoteker"
    ONLINE = "ONLINE", "Koordinator layanan daring"
    SUPERVISOR = "SUPERVISOR", "Koordinator shift"
    PIC = "PIC", "PIC cabang"
    # Kode tetap "AOM" (dipakai di data dan kode); sebutannya kini Direktur Operasional.
    AOM = "AOM", "Direktur Operasional"
    ADMIN = "ADMIN", "Admin"
    OWNER = "OWNER", "Owner / Direktur Utama"


class User(AbstractUser):
    """Akun individual. Akun bersama tidak diperbolehkan (PRD 5)."""

    display_name = models.CharField("nama tampilan", max_length=120, blank=True)
    phone = models.CharField("telepon", max_length=32, blank=True)
    job_title = models.CharField("jabatan", max_length=120, blank=True)
    must_change_password = models.BooleanField("wajib ganti password", default=False)
    deactivated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "pengguna"
        verbose_name_plural = "pengguna"
        ordering = ("username",)

    def __str__(self) -> str:
        return self.display_name or self.get_full_name() or self.username

    @property
    def initials(self) -> str:
        name = self.display_name or self.username
        parts = [p for p in name.replace(".", " ").split() if p]
        return "".join(p[0].upper() for p in parts[:2]) or name[:2].upper()

    def role_codes(self) -> set[str]:
        cached = getattr(self, "_role_cache", None)
        if cached is None:
            cached = {ur.role for ur in self.user_roles.all()}
            self._role_cache = cached
        return cached

    def capability_codes(self) -> set[str]:
        cached = getattr(self, "_cap_cache", None)
        if cached is None:
            cached = {uc.capability for uc in self.extra_capabilities.all()}
            self._cap_cache = cached
        return cached

    def has_role(self, *roles: str) -> bool:
        return bool(self.role_codes() & set(roles))

    @property
    def is_supervisor(self) -> bool:
        return self.has_role(Role.SUPERVISOR)

    @property
    def is_owner(self) -> bool:
        return self.has_role(Role.OWNER)

    @property
    def is_clinic_admin(self) -> bool:
        return self.has_role(Role.ADMIN)


class UserRole(models.Model):
    """Satu orang dapat memiliki lebih dari satu peran (PRD 5)."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_roles")
    clinic = models.ForeignKey("core.Clinic", on_delete=models.CASCADE, related_name="user_roles")
    role = models.CharField(max_length=20, choices=Role.choices)
    granted_at = models.DateTimeField(auto_now_add=True)
    granted_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="roles_granted"
    )

    class Meta:
        verbose_name = "peran pengguna"
        verbose_name_plural = "peran pengguna"
        constraints = [
            models.UniqueConstraint(fields=["user", "clinic", "role"], name="uniq_user_clinic_role")
        ]

    def __str__(self) -> str:
        return f"{self.user} · {self.get_role_display()}"


class OrganizationAssignment(models.Model):
    """Jabatan organisasi formal, terpisah dari hak akses aplikasi."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="organization_assignments")
    clinic = models.ForeignKey(
        "core.Clinic",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="organization_assignments",
        help_text="Kosongkan untuk jabatan lintas cabang.",
    )
    title = models.CharField("jabatan", max_length=120)
    starts_on = models.DateField("mulai")
    ends_on = models.DateField("selesai", null=True, blank=True)
    active = models.BooleanField("aktif", default=True)
    note = models.CharField("catatan", max_length=200, blank=True)

    class Meta:
        verbose_name = "jabatan organisasi"
        verbose_name_plural = "jabatan organisasi"
        ordering = ("user__username", "clinic__code", "title")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "clinic", "title", "starts_on"],
                name="uniq_user_clinic_org_assignment",
            )
        ]

    def __str__(self) -> str:
        clinic = self.clinic.code if self.clinic_id else "lintas-cabang"
        return f"{self.user} · {self.title} · {clinic}"


class PicFunction(models.TextChoices):
    # Nama jabatan mengikuti Project-AOM 04-ISTILAH dan memo penunjukan 002–005.
    SHIFT_COORDINATOR = "SHIFT_COORDINATOR", "Koordinator Shift"
    CASHIER = "CASHIER", "PIC Kasir"
    ONLINE = "ONLINE", "Koordinator Layanan Daring"
    CLEANLINESS = "CLEANLINESS", "PJ Kebersihan dan Sterilitas"
    PHARMACY = "PHARMACY", "PIC Apotek"


class PicAssignment(models.Model):
    """Fungsi PIC bercabang dan berbatas periode."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="pic_assignments")
    clinic = models.ForeignKey("core.Clinic", on_delete=models.CASCADE, related_name="pic_assignments")
    function = models.CharField(max_length=32, choices=PicFunction.choices)
    starts_on = models.DateField("mulai")
    ends_on = models.DateField("selesai", null=True, blank=True)
    active = models.BooleanField("aktif", default=True)
    granted_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="pic_assignments_granted"
    )

    class Meta:
        verbose_name = "penugasan PIC"
        verbose_name_plural = "penugasan PIC"
        ordering = ("clinic__code", "function", "user__username")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "clinic", "function", "starts_on"],
                name="uniq_user_clinic_pic_assignment",
            )
        ]

    def __str__(self) -> str:
        return f"{self.user} · {self.get_function_display()} · {self.clinic.code}"


class Capability(models.TextChoices):
    """Hak bisnis sensitif yang harus diberikan eksplisit (PRD 6.3)."""

    CASH_VIEW_AMOUNTS = "cash.view_amounts", "Melihat nominal kas"
    CASH_APPROVE = "cash.approve", "Menyetujui/verifikasi kas"
    PATIENT_VIEW_DETAIL = "patient.view_detail", "Melihat detail pasien"
    ISSUE_VIEW_RESTRICTED = "issue.view_restricted", "Melihat komplain terbatas"
    REPORT_VIEW_CONFIDENTIAL = "report.view_confidential", "Melihat laporan rahasia"
    SUGGESTION_PUBLISH = "suggestion.publish", "Memublikasikan masukan ke cabang"
    USER_MANAGE = "user.manage", "Mengelola pengguna"
    AUDIT_VIEW = "audit.view", "Membaca audit log"
    REPORT_EXPORT = "report.export", "Mengekspor laporan"
    ADMIN_FULL_ACCESS = (
        "admin.full_access",
        "Admin akses penuh (kas, pasien, komplain terbatas, audit)",
    )


class UserCapability(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="extra_capabilities")
    capability = models.CharField(max_length=40, choices=Capability.choices)
    granted_at = models.DateTimeField(auto_now_add=True)
    granted_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="caps_granted"
    )
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = "kapabilitas tambahan"
        verbose_name_plural = "kapabilitas tambahan"
        constraints = [
            models.UniqueConstraint(fields=["user", "capability"], name="uniq_user_capability")
        ]

    def __str__(self) -> str:
        return f"{self.user} · {self.get_capability_display()}"


class LoginAttempt(models.Model):
    """Untuk rate limit dan lockout bertahap (PRD 15.1)."""

    username = models.CharField(max_length=150, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    successful = models.BooleanField(default=False)
    attempted_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-attempted_at",)
