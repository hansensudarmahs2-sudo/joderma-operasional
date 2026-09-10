from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("hari/<int:pk>/aksi/", views.day_action, name="day_action"),
    path("action-items/", views.action_items, name="action_items"),
    path("action-items/<int:pk>/ubah/", views.action_item_update, name="action_item_update"),
    path("lampiran/<int:pk>/", views.attachment_download, name="attachment"),
    path("konfigurasi/", views.config_page, name="config"),
]
