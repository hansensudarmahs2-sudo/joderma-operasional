from django.urls import path

from . import views

app_name = "issues"

urlpatterns = [
    path("", views.list_view, name="list"),
    path("baru/", views.create, name="create"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/status/", views.change_status_view, name="status"),
    path("<int:pk>/tugaskan/", views.assign_view, name="assign"),
    path("<int:pk>/catatan/", views.add_note, name="note"),
    path("<int:pk>/perbaikan/", views.repair, name="repair"),
    path("<int:pk>/lampiran/", views.upload_attachment, name="upload"),
    path("aset/", views.asset_list, name="assets"),
    path("aset/<int:pk>/jangan-digunakan/", views.asset_block, name="asset_block"),
]
