from __future__ import annotations

from django.conf import settings
from django.db import models


class OnlineOrderStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft belum dikirim"
    BARU = "BARU", "Baru"
    DIPROSES = "DIPROSES", "Diproses apoteker"
    SIAP = "SIAP", "Siap diambil/dikirim"
    SELESAI = "SELESAI", "Selesai"
    BATAL = "BATAL", "Dibatalkan"


class Product(models.Model):
    category = models.CharField("golongan", max_length=80, blank=True)
    name = models.CharField("nama produk", max_length=180)
    ingredient = models.CharField("kandungan", max_length=240, blank=True)
    active = models.BooleanField("aktif", default=True)
    source = models.CharField(max_length=120, default="LIST PRODUK JODERMA.xlsx")

    class Meta:
        ordering = ("category", "name")
        constraints = [models.UniqueConstraint(fields=("category", "name"), name="uniq_product_category_name")]

    def __str__(self):
        return self.name


class OnlineOrder(models.Model):
    """Order produk dari kanal online untuk ditindaklanjuti farmasi."""

    clinic = models.ForeignKey("core.Clinic", on_delete=models.PROTECT, related_name="online_orders")
    order_no = models.CharField(max_length=24, unique=True)
    customer_name = models.CharField("nama pelanggan", max_length=120)
    customer_contact = models.CharField("kontak pelanggan", max_length=80)
    rm_number = models.CharField("nomor RM", max_length=32, default="J_-", blank=True)
    customer_address = models.TextField("alamat pemesan", default="", blank=True)
    product_name = models.CharField("produk", max_length=160)
    product = models.ForeignKey(Product, on_delete=models.PROTECT, null=True, blank=True, related_name="online_orders")
    quantity = models.PositiveIntegerField("jumlah", default=1)
    note = models.TextField("catatan", blank=True)
    status = models.CharField(max_length=12, choices=OnlineOrderStatus.choices, default=OnlineOrderStatus.BARU)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="online_orders_created")
    handled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="online_orders_handled")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.order_no} · {self.product_name}"

    def save(self, *args, **kwargs):
        if self.product_id:
            self.product_name = self.product.name
        super().save(*args, **kwargs)


class OnlineOrderItem(models.Model):
    order = models.ForeignKey(OnlineOrder, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, null=True, blank=True, related_name="order_items")
    product_name = models.CharField("produk", max_length=160)
    quantity = models.PositiveIntegerField("jumlah", default=1)

    def save(self, *args, **kwargs):
        if self.product_id:
            self.product_name = self.product.name
        super().save(*args, **kwargs)
