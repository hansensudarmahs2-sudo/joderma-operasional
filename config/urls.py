"""URL utama JoDerma Staff Ops."""
from django.contrib import admin
from django.urls import include, path

from core import views as core_views

urlpatterns = [
    path("", core_views.home, name="home"),
    path("hari-ini/", include(("core.urls", "core"), namespace="core")),
    path("akun/", include(("accounts.urls", "accounts"), namespace="accounts")),
    path("pembukaan/", include(("checklists.urls", "checklists"), namespace="checklists")),
    path("kas/", include(("cash.urls", "cash"), namespace="cash")),
    path("antrean/", include(("queueing.urls", "queueing"), namespace="queueing")),
    path("giliran-perawat/", include(("nurses.urls", "nurses"), namespace="nurses")),
    path("jadwal-istirahat/", include(("breaks.urls", "breaks"), namespace="breaks")),
    path("catatan/", include(("issues.urls", "issues"), namespace="issues")),
    path("notifikasi/", include(("notifications.urls", "notifications"), namespace="notifications")),
    path("laporan/", include(("reports.urls", "reports"), namespace="reports")),
    path("order-online/", include(("orders.urls", "orders"), namespace="orders")),
    path("direktur/", include(("direktur.urls", "direktur"), namespace="direktur")),
    path("jadwal/", include(("jadwal.urls", "jadwal"), namespace="jadwal")),
    path("stok-apotek/", include(("stok.urls", "stok"), namespace="stok")),
    path("owner/", include(("owner.urls", "owner"), namespace="owner")),
    path("audit/", include(("audit.urls", "audit"), namespace="audit")),
    path("health/", core_views.health, name="health"),
    path("django-admin/", admin.site.urls),
]

handler403 = "core.views.permission_denied"
