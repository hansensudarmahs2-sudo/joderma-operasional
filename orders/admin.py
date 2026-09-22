from django.contrib import admin

from .models import OnlineOrder, Product

admin.site.register(Product)


@admin.register(OnlineOrder)
class OnlineOrderAdmin(admin.ModelAdmin):
    list_display = ("order_no", "clinic", "customer_name", "product_name", "quantity", "status", "created_at")
    list_filter = ("clinic", "status")
