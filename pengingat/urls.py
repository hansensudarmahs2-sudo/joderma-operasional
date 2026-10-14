from django.urls import path

from . import views

app_name = "pengingat"

urlpatterns = [
    path("", views.katalog, name="katalog"),
    path("materi/baru/", views.materi_baru, name="materi_baru"),
    path("materi/<int:pk>/", views.materi_ubah, name="materi_ubah"),
    path("materi/<int:pk>/aktif/", views.materi_aktif, name="materi_aktif"),
    path("materi/<int:pk>/ingatkan-besok/", views.materi_besok, name="ingatkan_besok"),
    path("pengaturan/", views.pengaturan, name="pengaturan"),
    path("riwayat/", views.riwayat, name="riwayat"),
    path("butir/<int:pk>/diingatkan/", views.butir_diingatkan, name="diingatkan"),
    path("butir/<int:pk>/tunda/", views.butir_tunda, name="tunda"),
    path("butir/<int:pk>/lewati/", views.butir_lewati, name="lewati"),
]
