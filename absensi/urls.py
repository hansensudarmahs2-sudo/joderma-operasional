from django.urls import path

from . import views

app_name = "absensi"

urlpatterns = [
    path("", views.index, name="index"),
    path("saya/", views.saya, name="saya"),
    path("unggah/", views.unggah, name="unggah"),
    path("staf/<int:pk>/", views.staf, name="staf"),
]
