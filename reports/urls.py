from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.index, name="index"),
    path("masuk/", views.inbox, name="inbox"),
    path("masuk/pilah/<str:sumber>/<int:pk>/", views.inbox_triage, name="inbox_triage"),
    path("ekspor/<str:dataset>/", views.export_csv, name="export"),
    # Laporan (plan bagian 9)
    path("laporan/", views.laporan_list, name="laporan_list"),
    path("laporan/buat/", views.laporan_create, name="laporan_create"),
    path("laporan/<int:pk>/", views.laporan_detail, name="laporan_detail"),
    path("laporan/<int:pk>/status/", views.laporan_status, name="laporan_status"),
    path("laporan/<int:pk>/arsip/", views.laporan_archive, name="laporan_archive"),
    # Masukan (plan bagian 10)
    path("masukan/", views.masukan_list, name="masukan_list"),
    path("masukan/buat/", views.masukan_create, name="masukan_create"),
    path("masukan/<int:pk>/", views.masukan_detail, name="masukan_detail"),
    path("masukan/<int:pk>/publikasi/", views.masukan_publish, name="masukan_publish"),
    path("masukan/<int:pk>/arsip/", views.masukan_archive, name="masukan_archive"),
    # Halaman HTML (Fase 5)
    path("laporan-saya/", views.laporan_page, name="laporan_page"),
    path("laporan-saya/<int:pk>/", views.laporan_page_detail, name="laporan_page_detail"),
    path("masukan-saya/", views.masukan_page, name="masukan_page"),
    path("masukan-saya/<int:pk>/", views.masukan_page_detail, name="masukan_page_detail"),
]
