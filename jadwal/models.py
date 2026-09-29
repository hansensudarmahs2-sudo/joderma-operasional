"""Jadwal jaga per orang per hari, dan pembagian tugas harian menjadi porsi kecil.

Jadwal jaga adalah sumber siapa yang bertugas di cabang mana pada hari itu. Dari
sana dibaca tiga hal: roster giliran perawat (tidak memberi tally ke yang off
atau sedang perbantuan di cabang lain), cabang aktif staf pada hari itu, dan
siapa yang dapat menerima porsi tugas harian.

Porsi tugas (`DutyPortion`) mengelompokkan beberapa butir checklist yang
dikerjakan satu orang. Butir checklist menunjuk porsinya lewat
`ChecklistTemplateItem.portion`, sehingga halaman checklist dapat menampilkan
siapa pelaksananya tanpa mengubah hak isi checklist yang sudah ada.
"""
from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from accounts.models import PicFunction


class DutyStatus(models.TextChoices):
    MASUK = "MASUK", "Masuk"
    PERBANTUAN = "PERBANTUAN", "Perbantuan ke cabang lain"
    OFF = "OFF", "Off"
    CUTI = "CUTI", "Cuti"


WORKING_STATUSES = (DutyStatus.MASUK, DutyStatus.PERBANTUAN)


class DutyRoster(models.Model):
    """Satu baris per orang per tanggal."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="duty_days")
    date = models.DateField("tanggal")
    home_clinic = models.ForeignKey(
        "core.Clinic", on_delete=models.PROTECT, related_name="duty_home_days", verbose_name="cabang asal"
    )
    clinic = models.ForeignKey(
        "core.Clinic",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="duty_days",
        verbose_name="bertugas di",
        help_text="Kosong bila off atau cuti.",
    )
    status = models.CharField(max_length=12, choices=DutyStatus.choices, default=DutyStatus.MASUK)
    note = models.CharField("catatan", max_length=200, blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "jadwal jaga"
        verbose_name_plural = "jadwal jaga"
        ordering = ("date", "home_clinic_id", "user__username")
        constraints = [models.UniqueConstraint(fields=["user", "date"], name="uniq_duty_user_date")]

    def __str__(self) -> str:
        where = f" di {self.clinic.code}" if self.clinic_id else ""
        return f"{self.user} · {self.date} · {self.get_status_display()}{where}"

    @property
    def is_working(self) -> bool:
        return self.status in WORKING_STATUSES

    def clean(self):
        if self.status == DutyStatus.MASUK and self.clinic_id != self.home_clinic_id:
            raise ValidationError("Status Masuk berarti bertugas di cabang asal.")
        if self.status == DutyStatus.PERBANTUAN and (not self.clinic_id or self.clinic_id == self.home_clinic_id):
            raise ValidationError("Perbantuan wajib menyebut cabang lain tempat bertugas.")
        if self.status in (DutyStatus.OFF, DutyStatus.CUTI) and self.clinic_id:
            raise ValidationError("Off atau cuti tidak bertugas di cabang mana pun.")


class DutyGroup(models.TextChoices):
    OPENING = "OPENING", "Opening"
    CLOSING = "CLOSING", "Closing"
    KEBERSIHAN = "KEBERSIHAN", "Kebersihan"
    LIMBAH = "LIMBAH", "Limbah"
    KAS = "KAS", "Kas"
    APOTEK = "APOTEK", "Apotek"


class DutyPortion(models.Model):
    """Satu porsi kecil tugas harian di satu cabang."""

    clinic = models.ForeignKey("core.Clinic", on_delete=models.CASCADE, related_name="duty_portions")
    code = models.SlugField("kode", max_length=40)
    name = models.CharField("nama", max_length=120)
    group = models.CharField("kelompok", max_length=12, choices=DutyGroup.choices)
    description = models.TextField("isi singkat", blank=True)
    eligible_roles = models.JSONField(
        "peran yang boleh", default=list, blank=True, help_text="Kosong berarti seluruh staf yang bertugas."
    )
    pic_function = models.CharField(
        "didahulukan untuk PIC",
        max_length=32,
        choices=PicFunction.choices,
        blank=True,
        default="",
        help_text="Bila pemegang fungsi ini bertugas, porsi diberikan kepadanya; bila tidak, didelegasikan bergilir.",
    )
    people = models.PositiveSmallIntegerField("jumlah orang", default=1)
    weekdays = models.JSONField(
        "hari", default=list, blank=True, help_text="0=Senin … 6=Minggu. Kosong berarti setiap hari."
    )
    active = models.BooleanField("aktif", default=True)
    sort_order = models.PositiveIntegerField("urutan", default=0)

    class Meta:
        verbose_name = "porsi tugas"
        verbose_name_plural = "porsi tugas"
        ordering = ("clinic_id", "sort_order", "code")
        constraints = [models.UniqueConstraint(fields=["clinic", "code"], name="uniq_duty_portion_code")]

    def __str__(self) -> str:
        return f"{self.name} · {self.clinic.code}"

    @property
    def short_name(self) -> str:
        return self.name.split(" · ", 1)[-1]

    def runs_on(self, day) -> bool:
        return not self.weekdays or day.weekday() in set(self.weekdays)


class AssignmentSource(models.TextChoices):
    OTOMATIS = "OTOMATIS", "Disusun otomatis"
    MANUAL = "MANUAL", "Diubah manual"


class DutyAssignment(models.Model):
    """Siapa mengerjakan satu porsi pada satu tanggal."""

    portion = models.ForeignKey(DutyPortion, on_delete=models.CASCADE, related_name="assignments")
    clinic = models.ForeignKey("core.Clinic", on_delete=models.CASCADE, related_name="duty_assignments")
    date = models.DateField("tanggal")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="duty_assignments")
    source = models.CharField(max_length=10, choices=AssignmentSource.choices, default=AssignmentSource.OTOMATIS)
    note = models.CharField("catatan", max_length=200, blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "pembagian tugas"
        verbose_name_plural = "pembagian tugas"
        ordering = ("date", "portion__sort_order", "user__username")
        constraints = [
            models.UniqueConstraint(fields=["portion", "date", "user"], name="uniq_duty_assignment")
        ]

    def __str__(self) -> str:
        return f"{self.date} · {self.portion.name} · {self.user}"
