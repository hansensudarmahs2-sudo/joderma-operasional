"""Jejak kehadiran (tahap 3 paket E).

Setiap kejadian penting (login, buka/tutup hari, isi checklist, kas, lapor progres, ajukan selesai)
meninggalkan satu jejak: IP, jenis jaringan, perangkat, dan lokasi sesaat bila diizinkan. Targetnya
bukan bukti 100% tetapi pola yang benar lebih dari 60% (keputusan product owner, 3 Okt 2026), jadi
tidak ada yang diblokir; setiap jejak hanya diberi label Kuat / Sedang / Lemah.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models


class Event(models.TextChoices):
    LOGIN = "LOGIN", "Masuk aplikasi"
    BUKA_HARI = "BUKA_HARI", "Buka hari"
    TUTUP_HARI = "TUTUP_HARI", "Tutup hari"
    CHECKLIST = "CHECKLIST", "Isi checklist"
    KAS = "KAS", "Hitung kas"
    KAS_AJUKAN = "KAS_AJUKAN", "Ajukan kas"
    PROGRES = "PROGRES", "Lapor progres"
    AJUKAN = "AJUKAN", "Ajukan selesai"


class Network(models.TextChoices):
    TAILSCALE = "TAILSCALE", "Perangkat Tailscale"
    LOKAL = "LOKAL", "Jaringan lokal"
    PUBLIK = "PUBLIK", "Internet umum"
    TIDAK_DIKETAHUI = "", "Tidak diketahui"


class GeoStatus(models.TextChoices):
    OK = "OK", "Lokasi didapat"
    DITOLAK = "DITOLAK", "Izin lokasi ditolak"
    TIDAK_TERSEDIA = "TIDAK_TERSEDIA", "Lokasi tidak tersedia"
    TIDAK_DIMINTA = "", "Tidak diminta"


class Confidence(models.TextChoices):
    KUAT = "KUAT", "Kuat"
    SEDANG = "SEDANG", "Sedang"
    LEMAH = "LEMAH", "Lemah"


class KnownDevice(models.Model):
    """Perangkat yang dikenali lewat IP tetapnya (praktis: IP Tailscale 100.x perangkat klinik)."""

    ip_address = models.GenericIPAddressField("alamat IP", unique=True)
    name = models.CharField("nama perangkat", max_length=80)
    clinic = models.ForeignKey(
        "core.Clinic", on_delete=models.SET_NULL, null=True, blank=True, related_name="known_devices",
        help_text="Cabang tempat perangkat ini berada. Kosong bila berpindah-pindah.",
    )
    is_clinic_device = models.BooleanField(
        "perangkat milik klinik", default=False,
        help_text="Centang untuk PC/tablet klinik. Jejak dari perangkat ini berlabel Kuat.",
    )
    note = models.CharField("catatan", max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "perangkat dikenal"
        verbose_name_plural = "perangkat dikenal"
        ordering = ("-is_clinic_device", "name")

    def __str__(self) -> str:
        return f"{self.name} ({self.ip_address})"


class PresenceStamp(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="presence_stamps")
    clinic = models.ForeignKey(
        "core.Clinic", on_delete=models.SET_NULL, null=True, blank=True, related_name="presence_stamps"
    )
    event = models.CharField("kejadian", max_length=12, choices=Event.choices)
    entity_type = models.CharField(max_length=40, blank=True)
    entity_id = models.PositiveIntegerField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    ip_prefix = models.CharField("kelompok IP", max_length=64, blank=True, db_index=True)
    network = models.CharField(max_length=10, choices=Network.choices, blank=True)
    device = models.ForeignKey(KnownDevice, on_delete=models.SET_NULL, null=True, blank=True, related_name="stamps")
    device_kind = models.CharField("jenis perangkat", max_length=20, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    geo_status = models.CharField(max_length=16, choices=GeoStatus.choices, blank=True)
    # Dibulatkan 4 desimal (~11 m): cukup untuk jarak ke klinik, tidak untuk melacak.
    latitude = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    longitude = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    accuracy_m = models.PositiveIntegerField("akurasi (m)", null=True, blank=True)
    distance_m = models.PositiveIntegerField("jarak ke klinik (m)", null=True, blank=True)
    confidence = models.CharField(max_length=8, choices=Confidence.choices, default=Confidence.LEMAH)
    reason = models.CharField("alasan label", max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "jejak kehadiran"
        verbose_name_plural = "jejak kehadiran"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["clinic", "ip_prefix", "confidence"])]

    def __str__(self) -> str:
        return f"{self.user} · {self.get_event_display()} · {self.created_at:%d/%m %H:%M}"
