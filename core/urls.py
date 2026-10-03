from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("tugas/", views.today, name="today"),
    path("hari/<int:pk>/aksi/", views.day_action, name="day_action"),
    path("action-items/", views.action_items, name="action_items"),
    path("action-items/<int:pk>/ubah/", views.action_item_update, name="action_item_update"),
    path("assignment/<int:pk>/ambil/", views.assignment_claim, name="assignment_claim"),
    path("assignment/<int:pk>/ajukan/", views.assignment_submit, name="assignment_submit"),
    path("assignment/<int:pk>/progres/", views.assignment_progress, name="assignment_progress"),
    path("assignment/<int:pk>/konfirmasi/", views.assignment_confirm, name="assignment_confirm"),
    path("assignment/<int:pk>/revisi/", views.assignment_revision, name="assignment_revision"),
    path("assignment/<int:pk>/batal/", views.assignment_cancel, name="assignment_cancel"),
    path("lampiran/<int:pk>/", views.attachment_download, name="attachment"),
    path("konfigurasi/", views.config_page, name="config"),
    path("klinik/", views.clinic_profile, name="clinic_profile"),
]
